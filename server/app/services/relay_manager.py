from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
import uuid
from typing import Any, AsyncGenerator

from fastapi import WebSocket
from redis.asyncio import Redis, from_url as redis_from_url

from app.config import settings

logger = logging.getLogger(__name__)


class HostOfflineError(RuntimeError):
    pass


class RelayRequestError(RuntimeError):
    pass


class RelayManager:
    def __init__(self) -> None:
        self.instance_id = uuid.uuid4().hex
        self._redis: Redis | None = None
        self._listener_task: asyncio.Task | None = None
        self._hosts: dict[str, WebSocket] = {}

    async def start(self) -> None:
        if self._redis is None:
            self._redis = redis_from_url(settings.REDIS_URL, decode_responses=True)
        if self._listener_task is None or self._listener_task.done():
            self._listener_task = asyncio.create_task(self._command_listener(), name="relay:command_listener")
        logger.info("Relay manager started instance=%s", self.instance_id)

    async def stop(self) -> None:
        if self._listener_task and not self._listener_task.done():
            self._listener_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._listener_task
        self._listener_task = None
        if self._redis is not None:
            await self._redis.aclose()
        self._redis = None
        self._hosts.clear()

    async def _get_redis(self) -> Redis:
        if self._redis is None:
            self._redis = redis_from_url(settings.REDIS_URL, decode_responses=True)
        return self._redis

    @staticmethod
    def host_key(user_id: int, device_id: str) -> str:
        return f"{user_id}:{device_id}"

    @staticmethod
    def _host_redis_key(host_key: str) -> str:
        return f"relay:host:{host_key}"

    @staticmethod
    def _response_channel(request_id: str) -> str:
        return f"relay:response:{request_id}"

    def _command_channel(self) -> str:
        return f"relay:cmd:{self.instance_id}"

    async def register_host(self, user_id: int, device_id: str, websocket: WebSocket) -> str:
        host_key = self.host_key(user_id, device_id)
        self._hosts[host_key] = websocket
        await self.touch_host(host_key, user_id, device_id)
        return host_key

    async def unregister_host(self, host_key: str, websocket: WebSocket | None = None) -> None:
        if websocket is not None and self._hosts.get(host_key) is not websocket:
            return
        self._hosts.pop(host_key, None)
        redis = await self._get_redis()
        raw = await redis.get(self._host_redis_key(host_key))
        try:
            meta = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            meta = {}
        if meta.get("instance_id") == self.instance_id:
            await redis.delete(self._host_redis_key(host_key))

    async def touch_host(self, host_key: str, user_id: int, device_id: str) -> None:
        redis = await self._get_redis()
        payload = {
            "instance_id": self.instance_id,
            "user_id": user_id,
            "device_id": device_id,
            "last_seen": time.time(),
        }
        await redis.set(self._host_redis_key(host_key), json.dumps(payload), ex=45)

    async def get_host_meta(self, user_id: int, device_id: str) -> dict[str, Any] | None:
        redis = await self._get_redis()
        raw = await redis.get(self._host_redis_key(self.host_key(user_id, device_id)))
        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    async def is_host_online(self, user_id: int, device_id: str) -> bool:
        return await self.get_host_meta(user_id, device_id) is not None

    async def _command_listener(self) -> None:
        redis = await self._get_redis()
        pubsub = redis.pubsub()
        await pubsub.subscribe(self._command_channel())
        try:
            while True:
                msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if not msg:
                    await asyncio.sleep(0.05)
                    continue
                try:
                    command = json.loads(msg["data"])
                    await self._send_command_to_local_host(command)
                except Exception:
                    logger.exception("Failed to dispatch relay command")
        finally:
            with contextlib.suppress(Exception):
                await pubsub.unsubscribe(self._command_channel())
                await pubsub.aclose()

    async def _send_command_to_local_host(self, command: dict[str, Any]) -> None:
        host_key = str(command.get("host_key") or "")
        request_id = str(command.get("request_id") or "")
        websocket = self._hosts.get(host_key)
        if not websocket:
            await self.publish_response(request_id, {
                "request_id": request_id,
                "type": "error",
                "code": "host_offline",
                "data": "知识库主机离线",
            })
            return
        try:
            await websocket.send_json(command)
        except Exception:
            logger.warning("Relay host send failed host=%s request=%s", host_key, request_id, exc_info=True)
            await self.unregister_host(host_key, websocket)
            await self.publish_response(request_id, {
                "request_id": request_id,
                "type": "error",
                "code": "host_offline",
                "data": "知识库主机离线",
            })

    async def _publish_command(self, meta: dict[str, Any], command: dict[str, Any]) -> None:
        redis = await self._get_redis()
        channel = f"relay:cmd:{meta['instance_id']}"
        await redis.publish(channel, json.dumps(command, ensure_ascii=False))

    async def publish_response(self, request_id: str, message: dict[str, Any]) -> None:
        if not request_id:
            return
        redis = await self._get_redis()
        await redis.publish(self._response_channel(request_id), json.dumps(message, ensure_ascii=False))

    async def stream_host(
        self,
        user_id: int,
        device_id: str,
        action: str,
        payload: dict[str, Any],
        timeout_seconds: int = 300,
    ) -> AsyncGenerator[str, None]:
        host_key = self.host_key(user_id, device_id)
        meta = await self.get_host_meta(user_id, device_id)
        if not meta:
            raise HostOfflineError("知识库主机离线")

        request_id = uuid.uuid4().hex
        redis = await self._get_redis()
        pubsub = redis.pubsub()
        channel = self._response_channel(request_id)
        await pubsub.subscribe(channel)
        completed = False
        try:
            await self._publish_command(meta, {
                "host_key": host_key,
                "request_id": request_id,
                "action": action,
                "payload": payload,
            })
            deadline = time.monotonic() + timeout_seconds
            while time.monotonic() < deadline:
                msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if not msg:
                    await asyncio.sleep(0.05)
                    continue
                event = json.loads(msg["data"])
                event_type = event.get("type")
                if event_type == "event":
                    data = str(event.get("data") or "")
                    yield data if data.endswith("\n") else data + "\n"
                elif event_type == "done":
                    completed = True
                    break
                elif event_type == "error":
                    raise RelayRequestError(str(event.get("data") or "远程知识库请求失败"))
                elif event_type == "result":
                    completed = True
                    break
            if not completed:
                raise RelayRequestError("远程知识库响应超时")
        finally:
            with contextlib.suppress(Exception):
                await pubsub.unsubscribe(channel)
                await pubsub.aclose()
            if not completed:
                with contextlib.suppress(Exception):
                    meta = await self.get_host_meta(user_id, device_id)
                    if meta:
                        await self._publish_command(meta, {
                            "host_key": host_key,
                            "request_id": request_id,
                            "action": "cancel",
                            "payload": {},
                        })

    async def request_host(
        self,
        user_id: int,
        device_id: str,
        action: str,
        payload: dict[str, Any],
        timeout_seconds: int = 30,
    ) -> dict[str, Any]:
        host_key = self.host_key(user_id, device_id)
        meta = await self.get_host_meta(user_id, device_id)
        if not meta:
            raise HostOfflineError("知识库主机离线")

        request_id = uuid.uuid4().hex
        redis = await self._get_redis()
        pubsub = redis.pubsub()
        channel = self._response_channel(request_id)
        await pubsub.subscribe(channel)
        try:
            await self._publish_command(meta, {
                "host_key": host_key,
                "request_id": request_id,
                "action": action,
                "payload": payload,
            })
            deadline = time.monotonic() + timeout_seconds
            while time.monotonic() < deadline:
                msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if not msg:
                    await asyncio.sleep(0.05)
                    continue
                event = json.loads(msg["data"])
                if event.get("type") == "result":
                    data = event.get("data") or {}
                    return data if isinstance(data, dict) else {"data": data}
                if event.get("type") == "error":
                    raise RelayRequestError(str(event.get("data") or "远程知识库请求失败"))
            raise RelayRequestError("远程知识库响应超时")
        finally:
            with contextlib.suppress(Exception):
                await pubsub.unsubscribe(channel)
                await pubsub.aclose()


relay_manager = RelayManager()
