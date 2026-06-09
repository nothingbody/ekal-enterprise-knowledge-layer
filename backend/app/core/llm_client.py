import json
import logging
import hashlib
from typing import List, AsyncGenerator, Optional

import httpx
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

from app.models.model_config import ModelConfig, ModelProvider
from app.core.encryption import decrypt_value, is_encrypted
from app.config import settings

# ---------------------------------------------------------------------------
# Client pool — reuse AsyncOpenAI instances to keep HTTP connection pools warm.
# Keyed by (base_url, api_key_hash) so different credentials get separate clients.
# ---------------------------------------------------------------------------
_CLIENT_POOL: dict[str, AsyncOpenAI] = {}
_CLIENT_POOL_MAX = 16


def _decrypt_api_key(encrypted_key: str) -> str:
    """Decrypt the stored API key. Handles both encrypted and legacy plaintext values."""
    if not encrypted_key:
        return ""
    if is_encrypted(encrypted_key):
        return decrypt_value(encrypted_key, settings.SECRET_KEY)
    return encrypted_key


def _build_client(model_config: ModelConfig) -> AsyncOpenAI:
    api_key = _decrypt_api_key(model_config.api_key_encrypted) or "ollama"
    base_url = model_config.api_base

    if model_config.provider == ModelProvider.OLLAMA:
        base_url = model_config.api_base.rstrip("/") + "/v1"
        api_key = "ollama"

    key_hash = hashlib.sha256(api_key.encode()).hexdigest()[:12]
    pool_key = f"{base_url}|{key_hash}"

    client = _CLIENT_POOL.get(pool_key)
    if client is None:
        if len(_CLIENT_POOL) >= _CLIENT_POOL_MAX:
            oldest_key = next(iter(_CLIENT_POOL))
            evicted = _CLIENT_POOL.pop(oldest_key, None)
            if evicted is not None:
                try:
                    import asyncio
                    asyncio.get_event_loop().create_task(evicted.close())
                except RuntimeError:
                    logger.debug("Could not schedule client close (no running loop)")
        client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=httpx.Timeout(connect=30, read=300, write=30, pool=30),
        )
        _CLIENT_POOL[pool_key] = client

    return client


_INTERNAL_PARAM_KEYS = {"_tag", "is_platform"}


def _get_params(model_config: ModelConfig) -> dict:
    if model_config.params:
        try:
            params = json.loads(model_config.params)
            return {k: v for k, v in params.items() if k not in _INTERNAL_PARAM_KEYS}
        except json.JSONDecodeError:
            return {}
    return {}


def _is_anthropic(model_config: ModelConfig) -> bool:
    provider = model_config.provider
    if hasattr(provider, 'value'):
        provider = provider.value
    return str(provider).lower() == "anthropic"


def _build_anthropic_headers(model_config: ModelConfig) -> dict:
    api_key = _decrypt_api_key(model_config.api_key_encrypted) or ""
    return {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }


def _convert_messages_for_anthropic(messages: list) -> tuple[str, list]:
    """Convert OpenAI-style messages to Anthropic format.
    Returns (system_prompt, anthropic_messages).
    """
    system = ""
    anthropic_msgs = []
    for msg in messages:
        role = msg["role"]
        content = msg["content"]
        if role == "system":
            system = (system + "\n" + content).strip() if system else content
        elif role == "assistant":
            anthropic_msgs.append({"role": "assistant", "content": content})
        else:
            anthropic_msgs.append({"role": "user", "content": content})
    # Anthropic requires at least one user message
    if not anthropic_msgs:
        anthropic_msgs.append({"role": "user", "content": "Hi"})
    # Anthropic requires alternating user/assistant; merge consecutive same-role
    merged = []
    for m in anthropic_msgs:
        if merged and merged[-1]["role"] == m["role"]:
            merged[-1]["content"] += "\n" + m["content"]
        else:
            merged.append(dict(m))
    # Must start with user
    if merged and merged[0]["role"] != "user":
        merged.insert(0, {"role": "user", "content": "(continued)"})
    return system, merged


async def _anthropic_chat(
    model_config: ModelConfig,
    messages: list,
    params: dict,
) -> str:
    headers = _build_anthropic_headers(model_config)
    api_base = model_config.api_base.rstrip("/")
    system, anthropic_msgs = _convert_messages_for_anthropic(messages)
    body: dict = {
        "model": model_config.model_name,
        "messages": anthropic_msgs,
        "max_tokens": params.pop("max_tokens", 4096),
    }
    if system:
        body["system"] = system
    body.update(params)

    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(f"{api_base}/messages", headers=headers, json=body)
        resp.raise_for_status()
        data = resp.json()
    # Extract text from content blocks
    content_blocks = data.get("content", [])
    text_parts = [b["text"] for b in content_blocks if b.get("type") == "text"]
    return "\n".join(text_parts)


async def _anthropic_stream_chat(
    model_config: ModelConfig,
    messages: list,
    params: dict,
) -> AsyncGenerator[str, None]:
    headers = _build_anthropic_headers(model_config)
    api_base = model_config.api_base.rstrip("/")
    system, anthropic_msgs = _convert_messages_for_anthropic(messages)
    body: dict = {
        "model": model_config.model_name,
        "messages": anthropic_msgs,
        "max_tokens": params.pop("max_tokens", 4096),
        "stream": True,
    }
    if system:
        body["system"] = system
    body.update(params)

    async with httpx.AsyncClient(timeout=120) as client:
        async with client.stream("POST", f"{api_base}/messages", headers=headers, json=body) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                payload = line[6:]
                if payload.strip() == "[DONE]":
                    break
                try:
                    event = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                event_type = event.get("type")
                # content_block_delta events contain text
                if event_type == "content_block_delta":
                    delta = event.get("delta", {})
                    if delta.get("type") == "text_delta" and delta.get("text"):
                        yield delta["text"]
                elif event_type == "message_delta":
                    stop_reason = event.get("delta", {}).get("stop_reason")
                    if stop_reason and stop_reason != "end_turn":
                        logger.warning("Anthropic stream ended with stop_reason=%s", stop_reason)
                elif event_type == "error":
                    error_msg = event.get("error", {}).get("message", "unknown")
                    logger.error("Anthropic stream error: %s", error_msg)


async def chat_completion(
    model_config: ModelConfig,
    messages: list,
    stream: bool = False,
) -> AsyncGenerator[str, None] | str:
    params = _get_params(model_config)

    if _is_anthropic(model_config):
        if stream:
            return _anthropic_stream_chat(model_config, messages, params)
        return await _anthropic_chat(model_config, messages, params)

    client = _build_client(model_config)

    if stream:
        return _stream_chat(client, model_config.model_name, messages, params)

    response = await client.chat.completions.create(
        model=model_config.model_name,
        messages=messages,
        **params,
    )
    if not response.choices:
        return ""
    return response.choices[0].message.content


async def chat_completion_with_usage(
    model_config: ModelConfig,
    messages: list,
) -> dict:
    """Non-streaming LLM call that also returns token usage.

    Returns::

        {
            "content": str,
            "input_tokens": int,
            "output_tokens": int,
        }

    Inspired by OpenClaw usage-tracking: every agent run records
    inputTokens / outputTokens for cost accounting.
    """
    params = _get_params(model_config)
    params.pop("stream", None)

    if _is_anthropic(model_config):
        api_base = model_config.api_base.rstrip("/")
        headers = _build_anthropic_headers(model_config)
        system, anthropic_msgs = _convert_messages_for_anthropic(messages)
        body: dict = {
            "model": model_config.model_name,
            "messages": anthropic_msgs,
            "max_tokens": params.pop("max_tokens", 4096),
        }
        if system:
            body["system"] = system
        body.update(params)
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(f"{api_base}/messages", headers=headers, json=body)
            resp.raise_for_status()
            data = resp.json()
        text_parts = [
            b["text"] for b in data.get("content", []) if b.get("type") == "text"
        ]
        usage = data.get("usage", {})
        return {
            "content": "\n".join(text_parts),
            "input_tokens": usage.get("input_tokens", 0),
            "output_tokens": usage.get("output_tokens", 0),
        }

    client = _build_client(model_config)
    response = await client.chat.completions.create(
        model=model_config.model_name,
        messages=messages,
        **params,
    )
    usage = response.usage
    content = response.choices[0].message.content if response.choices else ""
    return {
        "content": content,
        "input_tokens": usage.prompt_tokens if usage else 0,
        "output_tokens": usage.completion_tokens if usage else 0,
    }


async def chat_completion_with_tools(
    model_config: ModelConfig,
    messages: list,
    tools: list[dict],
) -> dict:
    """Non-streaming LLM call with tool definitions.

    Returns a dict with:
      - role: 'assistant'
      - content: text content or None
      - tool_calls: list of tool call dicts or None
    """
    params = _get_params(model_config)
    # Remove streaming-incompatible params
    params.pop("stream", None)

    if _is_anthropic(model_config):
        # Anthropic tool calling uses a different format; fall back to no-tools
        result = await _anthropic_chat(model_config, messages, params)
        return {"role": "assistant", "content": result, "tool_calls": None}

    client = _build_client(model_config)
    response = await client.chat.completions.create(
        model=model_config.model_name,
        messages=messages,
        tools=tools if tools else None,
        **params,
    )
    if not response.choices:
        return {"role": "assistant", "content": "", "tool_calls": None}
    msg = response.choices[0].message

    tool_calls = None
    if msg.tool_calls:
        tool_calls = []
        for tc in msg.tool_calls:
            tool_calls.append({
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                },
            })

    return {
        "role": "assistant",
        "content": msg.content,
        "tool_calls": tool_calls,
    }


async def _stream_chat(
    client: AsyncOpenAI,
    model_name: str,
    messages: list,
    params: dict,
) -> AsyncGenerator[str, None]:
    stream = await client.chat.completions.create(
        model=model_name,
        messages=messages,
        stream=True,
        **params,
    )
    async for chunk in stream:
        if chunk.choices and chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content


async def create_embeddings(
    model_config: ModelConfig,
    texts: List[str],
) -> List[List[float]]:
    client = _build_client(model_config)

    response = await client.embeddings.create(
        model=model_config.model_name,
        input=texts,
    )
    if not response.data:
        return [[] for _ in texts]
    return [item.embedding for item in response.data]


async def rerank_documents(model_config: ModelConfig, query: str, documents: List[str]) -> List[tuple]:
    """Rerank documents using a reranker model. Returns list of (index, score) sorted by relevance."""
    try:
        import httpx
        api_base = model_config.api_base.rstrip("/")
        api_key = _decrypt_api_key(model_config.api_key_encrypted)

        async with httpx.AsyncClient(timeout=30) as http_client:
            response = await http_client.post(
                f"{api_base}/rerank",
                json={
                    "model": model_config.model_name,
                    "query": query,
                    "documents": documents,
                    "top_n": len(documents),
                },
                headers={"Authorization": f"Bearer {api_key}"},
            )
            if response.status_code == 200:
                data = response.json()
                results = [(item["index"], item["relevance_score"]) for item in data.get("results", [])]
                results.sort(key=lambda x: x[1], reverse=True)
                return results
    except Exception as exc:
        logger.warning("Reranker 调用失败，保持原始排序: %s", exc)

    # Fallback: preserve original order with neutral scores
    # (caller should treat these as "unranked" and not interpret scores as quality)
    return [(i, 0.5) for i in range(len(documents))]


async def test_model_connection(model_config: ModelConfig) -> dict:
    """Test if a model configuration is valid and reachable."""
    import time as _time
    t0 = _time.monotonic()
    try:
        model_type_str = str(model_config.model_type.value if hasattr(model_config.model_type, 'value') else model_config.model_type)
        if model_type_str == "reranker":
            return await _test_reranker(model_config)

        if _is_anthropic(model_config):
            return await _test_anthropic(model_config, model_type_str)

        client = _build_client(model_config)
        if model_type_str == "llm":
            resp = await client.chat.completions.create(
                model=model_config.model_name,
                messages=[{"role": "user", "content": "Hi"}],
                max_tokens=5,
            )
            latency = round((_time.monotonic() - t0) * 1000)
            detail = ""
            if resp.choices and resp.choices[0].message.content:
                detail = resp.choices[0].message.content[:100]
            return {"success": True, "message": "LLM 模型连接成功", "latency_ms": latency, "detail": detail}
        else:
            response = await client.embeddings.create(
                model=model_config.model_name,
                input=["test"],
            )
            latency = round((_time.monotonic() - t0) * 1000)
            dim = len(response.data[0].embedding)
            return {"success": True, "message": f"Embedding 模型连接成功，维度: {dim}", "latency_ms": latency, "detail": f"向量维度: {dim}"}
    except Exception as e:
        latency = round((_time.monotonic() - t0) * 1000)
        from app.services.chat_helpers import classify_llm_error
        user_msg = classify_llm_error(e)
        return {"success": False, "message": user_msg, "latency_ms": latency, "detail": str(e)[:300]}


async def _test_anthropic(model_config: ModelConfig, model_type_str: str) -> dict:
    """Test Anthropic model connection."""
    import time as _time
    if model_type_str != "llm":
        return {"success": False, "message": "Anthropic 仅支持 LLM 模型类型", "latency_ms": 0, "detail": ""}
    t0 = _time.monotonic()
    try:
        result = await _anthropic_chat(
            model_config,
            [{"role": "user", "content": "Hi"}],
            {"max_tokens": 10},
        )
        latency = round((_time.monotonic() - t0) * 1000)
        detail = result[:100] if isinstance(result, str) else ""
        return {"success": True, "message": "Anthropic LLM 连接成功", "latency_ms": latency, "detail": detail}
    except httpx.HTTPStatusError as e:
        latency = round((_time.monotonic() - t0) * 1000)
        body = e.response.text[:300]
        return {"success": False, "message": f"Anthropic 返回 {e.response.status_code}: {body}", "latency_ms": latency, "detail": body}
    except Exception as e:
        latency = round((_time.monotonic() - t0) * 1000)
        return {"success": False, "message": f"Anthropic 连接失败: {str(e)}", "latency_ms": latency, "detail": str(e)[:200]}


async def _test_reranker(model_config: ModelConfig) -> dict:
    """Test reranker model by sending a small rerank request."""
    import httpx
    import time as _time
    api_base = model_config.api_base.rstrip("/")
    api_key = _decrypt_api_key(model_config.api_key_encrypted)
    t0 = _time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=15) as http_client:
            response = await http_client.post(
                f"{api_base}/rerank",
                json={
                    "model": model_config.model_name,
                    "query": "test query",
                    "documents": ["doc 1", "doc 2"],
                    "top_n": 2,
                },
                headers={"Authorization": f"Bearer {api_key}"},
            )
            latency = round((_time.monotonic() - t0) * 1000)
            if response.status_code == 200:
                data = response.json()
                count = len(data.get("results", []))
                return {"success": True, "message": f"Reranker 模型连接成功，返回 {count} 条结果", "latency_ms": latency, "detail": f"返回 {count} 条排序结果"}
            else:
                detail = response.text[:200]
                return {"success": False, "message": f"Reranker 返回 {response.status_code}: {detail}", "latency_ms": latency, "detail": detail}
    except Exception as e:
        latency = round((_time.monotonic() - t0) * 1000)
        return {"success": False, "message": f"Reranker 连接失败: {str(e)}", "latency_ms": latency, "detail": str(e)[:200]}
