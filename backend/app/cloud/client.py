"""HTTP client for communicating with the central server."""

from __future__ import annotations

import logging
from datetime import date
from typing import AsyncGenerator, Optional
from urllib.parse import urlparse, urlunparse

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_client: Optional[httpx.AsyncClient] = None


def _get_server_url() -> str:
    url = getattr(settings, "CENTRAL_SERVER_URL", "").rstrip("/")
    if url and getattr(settings, "CLOUD_REQUIRE_HTTPS", True):
        if url.startswith("http://") and not settings.DEBUG:
            corrected = "https://" + url[len("http://"):]
            logger.warning(
                "CENTRAL_SERVER_URL 使用了 http://，已自动升级为 https://（%s → %s）。"
                "如需禁用，请设置 CLOUD_REQUIRE_HTTPS=false",
                url, corrected,
            )
            url = corrected
    return url


def is_cloud_enabled() -> bool:
    return bool(_get_server_url())


async def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        from app._version import __version__
        _client = httpx.AsyncClient(
            base_url=_get_server_url(),
            timeout=httpx.Timeout(15.0, connect=5.0),
            headers={"User-Agent": f"ZhiShu-Desktop/{__version__}"},
            follow_redirects=True,
        )
    return _client


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _central_api(suffix: str) -> str:
    """中心 API 路径：suffix 为 auth/login、skills/1 等（不含前导 /）。"""
    prefix = getattr(settings, "CENTRAL_API_PREFIX", "/api/v1").rstrip("/")
    tail = suffix.strip().lstrip("/")
    return f"{prefix}/{tail}" if tail else prefix


def get_central_public_origin() -> str:
    return _get_server_url()


def get_central_ws_url(suffix: str) -> str:
    base = _get_server_url()
    parsed = urlparse(base)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    path = _central_api(suffix)
    return urlunparse((scheme, parsed.netloc, path, "", "", ""))


# ─────────────────────────────────────────
# Auth
# ─────────────────────────────────────────

async def cloud_login(
    username: str,
    password: str,
    device_id: str,
    device_name: Optional[str] = None,
    os_info: Optional[str] = None,
    app_version: Optional[str] = None,
) -> dict:
    client = await _get_client()
    payload = {
        "username": username,
        "password": password,
        "device_id": device_id,
        "device_name": device_name,
        "os_info": os_info,
        "app_version": app_version,
    }
    resp = await client.post(_central_api("auth/login"), json=payload)
    resp.raise_for_status()
    return resp.json()


async def cloud_register(
    username: str, email: str, password: str, invite_code: Optional[str] = None
) -> dict:
    client = await _get_client()
    payload = {"username": username, "email": email, "password": password}
    if invite_code:
        payload["invite_code"] = invite_code
    resp = await client.post(_central_api("auth/register"), json=payload)
    resp.raise_for_status()
    return resp.json()


async def cloud_get_register_config() -> dict:
    client = await _get_client()
    resp = await client.get(_central_api("auth/register-config"))
    resp.raise_for_status()
    return resp.json()


async def cloud_refresh_token(refresh_token: str) -> dict:
    client = await _get_client()
    resp = await client.post(_central_api("auth/refresh"), json={"refresh_token": refresh_token})
    resp.raise_for_status()
    return resp.json()


async def cloud_get_me(token: str) -> dict:
    client = await _get_client()
    resp = await client.get(_central_api("auth/me"), headers=_auth_headers(token))
    resp.raise_for_status()
    return resp.json()


async def cloud_logout(token: str) -> dict:
    client = await _get_client()
    resp = await client.post(_central_api("auth/logout"), headers=_auth_headers(token))
    resp.raise_for_status()
    return resp.json()


async def cloud_change_password(token: str, old_password: str, new_password: str) -> dict:
    client = await _get_client()
    resp = await client.post(
        _central_api("auth/change-password"),
        json={"old_password": old_password, "new_password": new_password},
        headers=_auth_headers(token),
    )
    resp.raise_for_status()
    return resp.json()


async def cloud_delete_account(token: str, password: str) -> dict:
    client = await _get_client()
    resp = await client.request(
        "DELETE",
        _central_api("auth/account"),
        json={"password": password},
        headers=_auth_headers(token),
    )
    resp.raise_for_status()
    return resp.json()


async def cloud_update_profile(token: str, data: dict) -> dict:
    client = await _get_client()
    resp = await client.put(_central_api("auth/profile"), json=data, headers=_auth_headers(token))
    resp.raise_for_status()
    return resp.json()


# ─────────────────────────────────────────
# Device
# ─────────────────────────────────────────

async def cloud_device_heartbeat(
    token: str,
    device_id: str,
    app_version: Optional[str] = None,
    extra: Optional[dict] = None,
) -> dict:
    client = await _get_client()
    payload: dict = {"device_id": device_id, "app_version": app_version}
    if extra:
        payload["extra"] = extra
    resp = await client.post(
        _central_api("devices/heartbeat"),
        json=payload,
        headers=_auth_headers(token),
    )
    resp.raise_for_status()
    return resp.json()


# ─────────────────────────────────────────────────────────────
# Remote relay
# ─────────────────────────────────────────────────────────────

async def cloud_publish_hosted_workspaces(token: str, payload: dict) -> dict:
    client = await _get_client()
    resp = await client.post(
        _central_api("relay/hosted-workspaces"),
        json=payload,
        headers=_auth_headers(token),
    )
    resp.raise_for_status()
    return resp.json()


async def cloud_relay_invitation_info(invite_token: str) -> dict:
    client = await _get_client()
    resp = await client.get(_central_api(f"relay/invitations/{invite_token}/info"))
    resp.raise_for_status()
    return resp.json()


async def cloud_relay_accept_invitation(token: str, invite_token: str) -> dict:
    client = await _get_client()
    resp = await client.post(
        _central_api(f"relay/invitations/{invite_token}/accept"),
        headers=_auth_headers(token),
    )
    resp.raise_for_status()
    return resp.json()


async def cloud_relay_shared_kbs(token: str) -> list[dict]:
    client = await _get_client()
    resp = await client.get(_central_api("relay/shared-kbs"), headers=_auth_headers(token))
    resp.raise_for_status()
    data = resp.json()
    return data if isinstance(data, list) else data.get("items", [])


async def cloud_relay_chat_stream(token: str, payload: dict) -> AsyncGenerator[str, None]:
    client = await _get_client()
    async with client.stream(
        "POST",
        _central_api("relay/chat/completions"),
        json=payload,
        headers=_auth_headers(token),
        timeout=httpx.Timeout(300.0, connect=10.0),
    ) as resp:
        resp.raise_for_status()
        async for chunk in resp.aiter_text():
            if chunk:
                yield chunk


# ─────────────────────────────────────────
# Skills Marketplace
# ─────────────────────────────────────────

async def cloud_marketplace(
    token: Optional[str] = None,
    category: Optional[str] = None,
    search: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """Fetch marketplace skills from the central server.

    The server's marketplace endpoint is public, so *token* is optional.
    """
    client = await _get_client()
    params: dict = {"page": page, "page_size": page_size}
    if category:
        params["category"] = category
    if search:
        params["search"] = search
    headers = _auth_headers(token) if token else {}
    resp = await client.get(
        _central_api("skills/marketplace"), params=params, headers=headers
    )
    resp.raise_for_status()
    return resp.json()


async def cloud_get_skill(skill_id: int, token: Optional[str] = None) -> dict:
    """GET 中心服务器技能详情（已上架匿名可看；未上架需作者/管理员，由中心校验 Token）。"""
    client = await _get_client()
    headers = _auth_headers(token) if token else {}
    resp = await client.get(_central_api(f"skills/{skill_id}"), headers=headers)
    resp.raise_for_status()
    return resp.json()


async def cloud_download_skill(token: str, skill_id: int) -> dict:
    client = await _get_client()
    resp = await client.post(
        _central_api(f"skills/{skill_id}/download"), headers=_auth_headers(token)
    )
    resp.raise_for_status()
    return resp.json()


async def cloud_publish_skill(token: str, data: dict) -> dict:
    client = await _get_client()
    resp = await client.post(
        _central_api("skills/publish"), json=data, headers=_auth_headers(token)
    )
    resp.raise_for_status()
    return resp.json()


# ─────────────────────────────────────────
# Usage Report
# ─────────────────────────────────────────

async def cloud_submit_usage(
    token: str,
    device_id: str,
    report_date: date,
    token_count: int = 0,
    conversation_count: int = 0,
    message_count: int = 0,
    kb_count: int = 0,
    doc_count: int = 0,
) -> dict:
    client = await _get_client()
    payload = {
        "device_id": device_id,
        "report_date": str(report_date),
        "token_count": token_count,
        "conversation_count": conversation_count,
        "message_count": message_count,
        "kb_count": kb_count,
        "doc_count": doc_count,
    }
    resp = await client.post(
        _central_api("stats/report"), json=payload, headers=_auth_headers(token)
    )
    resp.raise_for_status()
    return resp.json()


# ─────────────────────────────────────────
# User Data Sync (Memories / Profiles / Agents)
# ─────────────────────────────────────────

async def cloud_sync_memories(token: str, device_id: str, memories: list[dict]) -> dict:
    client = await _get_client()
    resp = await client.post(
        _central_api("stats/sync-memories"),
        json={"device_id": device_id, "memories": memories},
        headers=_auth_headers(token),
    )
    resp.raise_for_status()
    return resp.json()


async def cloud_sync_profile(token: str, device_id: str, profile: dict) -> dict:
    client = await _get_client()
    resp = await client.post(
        _central_api("stats/sync-profile"),
        json={"device_id": device_id, "profile": profile},
        headers=_auth_headers(token),
    )
    resp.raise_for_status()
    return resp.json()


async def cloud_sync_agents(token: str, device_id: str, agents: list[dict]) -> dict:
    client = await _get_client()
    resp = await client.post(
        _central_api("stats/sync-agents"),
        json={"device_id": device_id, "agents": agents},
        headers=_auth_headers(token),
    )
    resp.raise_for_status()
    return resp.json()


async def cloud_get_notifications(token: str, since: str | None = None) -> list:
    client = await _get_client()
    params = {}
    if since:
        params["since"] = since
    try:
        resp = await client.get(
            _central_api("notifications/mine"), params=params, headers=_auth_headers(token)
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("items", data) if isinstance(data, dict) else data
    except Exception:
        return []


async def cloud_submit_detailed_usage(token: str, device_id: str, data: dict) -> dict:
    """Submit detailed per-model usage breakdown to the central server."""
    client = await _get_client()
    resp = await client.post(
        _central_api("stats/detailed-report"),
        json={"device_id": device_id, **data},
        headers=_auth_headers(token),
    )
    resp.raise_for_status()
    return resp.json()


async def cloud_submit_operation_logs(token: str, device_id: str, logs: list[dict]) -> dict:
    """Submit operation logs from desktop client to the central server."""
    client = await _get_client()
    resp = await client.post(
        _central_api("stats/sync-operation-logs"),
        json={"device_id": device_id, "logs": logs},
        headers=_auth_headers(token),
    )
    resp.raise_for_status()
    return resp.json()


async def cloud_get_shared_models(token: str) -> list:
    """Fetch shared model configs from the central server (with decrypted API keys)."""
    client = await _get_client()
    resp = await client.get(_central_api("models/sync"), headers=_auth_headers(token))
    resp.raise_for_status()
    data = resp.json()
    return data.get("items", [])


async def cloud_get_shared_agents(token: str) -> list:
    """Fetch shared agent configs from the central server."""
    client = await _get_client()
    resp = await client.get(_central_api("models/sync-agents"), headers=_auth_headers(token))
    resp.raise_for_status()
    data = resp.json()
    return data.get("items", [])


async def cloud_get_shared_mcp_servers(token: str) -> list:
    """Fetch shared MCP server configs from the central server."""
    client = await _get_client()
    resp = await client.get(_central_api("models/sync-mcp-servers"), headers=_auth_headers(token))
    resp.raise_for_status()
    data = resp.json()
    return data.get("items", [])


async def detect_client_ip() -> str | None:
    """Detect the client's public IP address via an external service."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as c:
            resp = await c.get("https://api.ipify.org?format=json")
            if resp.status_code == 200:
                return resp.json().get("ip")
    except Exception:
        pass
    try:
        async with httpx.AsyncClient(timeout=5.0) as c:
            resp = await c.get("https://ifconfig.me/ip")
            if resp.status_code == 200:
                return resp.text.strip()
    except Exception:
        pass
    return None


async def close_client() -> None:
    global _client
    if _client and not _client.is_closed:
        await _client.aclose()
        _client = None
