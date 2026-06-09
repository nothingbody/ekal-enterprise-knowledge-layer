"""Chat service — orchestrates streaming chat with RAG, SQL, agent and multi-agent modes.

Submodule layout:
- chat_constants: prompt templates and constants
- chat_helpers: error classification, truncation, context building
- chat_conversation: conversation CRUD and history
- chat_agent: agent, multi-agent, slash command handlers
"""
import asyncio
import json
import logging
import time
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.chat_history import ChatConversation, ChatMessage
from app.models.model_config import ModelConfig
from app.models.knowledge_base import KnowledgeBase
from app.models.operation_log import add_log_and_sync
from app.schemas.chat import ChatRequest
from app.services.retrieval_service import retrieve
from app.services.chat_router_service import resolve_chat_mode, get_kb_database_sources
from app.services.text_to_sql_service import text_to_sql_query
from app.core.llm_client import chat_completion
from app.core.token_utils import count_tokens as _count_tokens
from app.core.context_engine import get_engine as _get_context_engine
from app.config import settings

# Re-export public API so existing ``from app.services.chat_service import …`` works
from app.services.chat_constants import (  # noqa: F401
    PUBLIC_APP_TITLE_PREFIX,
    DEFAULT_PROMPT_TEMPLATE, HYBRID_PROMPT_TEMPLATE, SQL_ONLY_PROMPT_TEMPLATE,
)
from app.services.chat_helpers import (
    classify_llm_error as _classify_llm_error,
    truncate_context as _truncate_context,
    is_public_chat_request as _is_public_chat_request,
    build_context, build_sql_context as _build_sql_context,
    resolve_agentic_config as _resolve_agentic_config,
)
from app.services.chat_conversation import (  # noqa: F401
    get_or_create_conversation, get_chat_history,
    list_conversations, get_conversation_messages, delete_conversation,
)
from app.services.chat_agent import (
    handle_agent_mode as _handle_agent_mode,
    handle_multi_agent_mode as _handle_multi_agent_mode,
    handle_slash_command as _handle_slash_command,
)

_log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Model resolution
# ---------------------------------------------------------------------------

async def _load_fallback_model(db: AsyncSession, model_config: ModelConfig):
    """Load the first fallback model from model_config.fallback_model_ids (JSON array)."""
    raw = getattr(model_config, "fallback_model_ids", None)
    if not raw:
        return None
    try:
        ids = json.loads(raw) if isinstance(raw, str) else raw
        if not isinstance(ids, list) or not ids:
            return None
    except (json.JSONDecodeError, TypeError):
        return None
    result = await db.execute(
        select(ModelConfig).where(ModelConfig.id == int(ids[0]))
    )
    return result.scalar_one_or_none()


async def _resolve_llm_model(
    db: AsyncSession, user_id: int, chat_req: ChatRequest, kb
) -> "ModelConfig | None":
    """Resolve the LLM model config from request, falling back to user/KB defaults."""
    model_config = None
    if chat_req.llm_model_id:
        model_result = await db.execute(
            select(ModelConfig).where(ModelConfig.id == chat_req.llm_model_id)
        )
        model_config = model_result.scalar_one_or_none()

    if not model_config:
        from app.models.model_config import ModelType
        fallback_ids = [user_id]
        if kb:
            fallback_ids.append(kb.user_id)
        for uid in fallback_ids:
            fb_result = await db.execute(
                select(ModelConfig).where(
                    ModelConfig.user_id == uid,
                    ModelConfig.model_type == ModelType.LLM,
                    ModelConfig.is_default == True,
                )
            )
            model_config = fb_result.scalar_one_or_none()
            if model_config:
                break
    return model_config


# ---------------------------------------------------------------------------
# Result persistence
# ---------------------------------------------------------------------------

async def _save_chat_result(
    db: AsyncSession,
    conv,
    user_id: int,
    chat_req: ChatRequest,
    full_response: str,
    references_json: str,
    retrieval_results: list,
    model_config,
    chat_mode: str,
    start_time: float,
    history: list,
    context_engine,
    messages: list,
    need_rag: bool,
    is_trial_user: bool = False,
):
    """Persist assistant message, log operation, record metrics, extract memories."""
    latency = (time.time() - start_time) * 1000
    token_count = _count_tokens(full_response)
    input_token_count = _count_tokens(
        " ".join(m.get("content", "") or "" for m in messages)
    )

    try:
        from app.core.metrics import (
            llm_call_latency, llm_input_tokens_total, llm_output_tokens_total,
            retrieval_hit_count, retrieval_miss_count, retrieval_top_score,
        )
        import re as _re
        _raw_label = getattr(model_config, 'display_name', 'unknown') or 'unknown'
        model_label = _re.sub(r'[^a-zA-Z0-9_.\-\u4e00-\u9fff]', '_', _raw_label)[:50]
        llm_call_latency.labels(model_name=model_label, chat_mode=chat_mode).observe(latency / 1000)
        llm_input_tokens_total.labels(model_name=model_label).inc(input_token_count)
        llm_output_tokens_total.labels(model_name=model_label).inc(token_count)
        if retrieval_results:
            retrieval_hit_count.labels(search_mode=chat_mode).inc()
            retrieval_top_score.observe(retrieval_results[0].score)
        elif need_rag:
            retrieval_miss_count.labels(search_mode=chat_mode).inc()
    except Exception as _metrics_exc:
        _log.debug("Metrics update failed: %s", _metrics_exc)

    assistant_msg = ChatMessage(
        conversation_id=conv.id,
        role="assistant",
        content=full_response,
        references=references_json,
        token_count=token_count,
        latency_ms=latency,
        msg_type="chat",
    )
    db.add(assistant_msg)

    from sqlalchemy import update as sa_update
    await db.execute(
        sa_update(ChatConversation)
        .where(ChatConversation.id == conv.id)
        .values(
            total_input_tokens=ChatConversation.total_input_tokens + input_token_count,
            total_output_tokens=ChatConversation.total_output_tokens + token_count,
        )
    )

    is_public_chat = _is_public_chat_request(chat_req)
    retrieval_detail_payload = {
        "mode": chat_mode,
        "retrieval_count": len(retrieval_results),
        "top_score": round(retrieval_results[0].score, 4) if retrieval_results else None,
        "avg_score": round(sum(r.score for r in retrieval_results) / len(retrieval_results), 4) if retrieval_results else None,
        "sources": list({r.doc_name for r in retrieval_results if r.doc_name}),
    }
    if is_public_chat:
        retrieval_detail_payload["published_app_id"] = chat_req.published_app_id
        retrieval_detail_payload["visitor_id"] = chat_req.visitor_id
        retrieval_detail_payload["conversation_id"] = conv.id
    retrieval_detail = json.dumps(retrieval_detail_payload, ensure_ascii=False)

    add_log_and_sync(db,
        user_id=user_id,
        action="public_chat" if is_public_chat else "chat",
        resource_type="published_app" if is_public_chat else "conversation",
        resource_id=chat_req.published_app_id if is_public_chat else conv.id,
        detail=retrieval_detail,
        total_tokens=token_count,
        latency_ms=latency,
    )

    await context_engine.after_turn(full_response)
    await db.flush()  # populate assistant_msg.id before commit
    _assistant_msg_id = assistant_msg.id
    await db.commit()

    # Deduct quota after successful completion
    if not is_public_chat:
        try:
            if is_trial_user:
                from app.services.quota_service import consume_trial
                await consume_trial(db, user_id)
            else:
                from app.services.quota_service import consume_tokens
                await consume_tokens(
                    db, user_id,
                    input_tokens=input_token_count,
                    output_tokens=token_count,
                    conversation_id=conv.id,
                    model_name=getattr(model_config, 'display_name', None),
                )
        except Exception as _qt_exc:
            _log.warning("Quota consumption failed (user_id=%s): %s", user_id, _qt_exc)

    if not is_public_chat and full_response:
        try:
            from app.services.memory_service import extract_memories_from_conversation
            conv_messages = history + [{"role": "assistant", "content": full_response}]
            await extract_memories_from_conversation(
                db, user_id, conv.id, conv_messages, model_config,
            )
        except Exception as _mem_exc:
            _log.warning(
                "Memory extraction failed (user_id=%s, conv_id=%s): %s",
                user_id, conv.id, _mem_exc,
            )

    return latency, input_token_count, token_count, _assistant_msg_id


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

async def stream_chat(
    db: AsyncSession,
    user_id: int,
    chat_req: ChatRequest,
) -> AsyncGenerator[str, None]:
    start_time = time.time()

    _is_trial_user = False
    if not _is_public_chat_request(chat_req):
        from app.services.quota_service import check_quota
        quota_info = await check_quota(db, user_id)
        if not quota_info["allowed"]:
            plan = quota_info["plan"]
            if plan == "trial":
                yield json.dumps({
                    "type": "error",
                    "data": f"免费试用额度已用完（共 {quota_info['trial_total']} 次对话）。请联系管理员开通付费方案以继续使用。",
                }, ensure_ascii=False) + "\n"
            else:
                yield json.dumps({
                    "type": "error",
                    "data": "算力额度不足，请充值后继续使用。",
                }, ensure_ascii=False) + "\n"
            return

        _is_trial_user = quota_info["plan"] == "trial"

    conv = await get_or_create_conversation(db, user_id, chat_req)

    kb_result = await db.execute(
        select(KnowledgeBase).where(KnowledgeBase.id == chat_req.kb_id, KnowledgeBase.deleted_at.is_(None))
    )
    kb = kb_result.scalar_one_or_none()

    model_config = await _resolve_llm_model(db, user_id, chat_req, kb)

    if not model_config:
        yield json.dumps({"type": "error", "data": "未找到可用的 LLM 模型，请先配置模型"}, ensure_ascii=False) + "\n"
        return

    slash_gen = await _handle_slash_command(db, user_id, chat_req, conv, model_config)
    if slash_gen is not None:
        collected_content = []
        async for event_str in slash_gen:
            yield event_str
            try:
                evt = json.loads(event_str.strip())
                if evt.get("type") == "content":
                    collected_content.append(evt["data"])
            except Exception:
                pass
        if collected_content:
            full_content = "".join(collected_content)
            assistant_msg = ChatMessage(
                conversation_id=conv.id, role="assistant", content=full_content,
            )
            db.add(assistant_msg)
            await db.commit()
        return

    # --- Resolve chat mode ---
    requested_mode = getattr(chat_req, "chat_mode", "auto")

    # Agent mode bypasses the normal route classifier
    if requested_mode == "agent":
        # Anthropic models don't support OpenAI-style tool calling; auto-downgrade
        from app.core.llm_client import _is_anthropic
        if _is_anthropic(model_config):
            chat_mode = "rag"
            yield json.dumps({
                "type": "status",
                "data": "当前使用的 Anthropic 模型不支持 Agent 工具调用，已自动切换为知识检索模式",
            }, ensure_ascii=False) + "\n"
        else:
            chat_mode = "agent"
    else:
        chat_mode = await resolve_chat_mode(
            db, chat_req.kb_id, chat_req.question,
            requested_mode=requested_mode,
            llm_config=model_config,
            user_id=user_id,
        )

    yield json.dumps({"type": "mode", "data": chat_mode}, ensure_ascii=False) + "\n"

    # Warn if mode was downgraded due to missing database sources
    if requested_mode in ("sql", "hybrid") and chat_mode == "rag":
        yield json.dumps({
            "type": "status",
            "data": f"该知识库未连接数据库源，已自动切换为知识检索模式",
        }, ensure_ascii=False) + "\n"

    # --- Fetch chat history early (needed for context-aware retrieval + LLM) ---
    history = await get_chat_history(db, conv.id)

    # --- Initialize context engine ---
    engine_name = chat_req.context_strategy or settings.CONTEXT_ENGINE
    context_engine = _get_context_engine(engine_name, max_tokens=settings.MAX_HISTORY_TOKENS)
    await context_engine.bootstrap(
        history=history,
        max_tokens=settings.MAX_HISTORY_TOKENS,
        llm_config=model_config,
        db=db,
        conversation_id=conv.id,
        context_summary=getattr(conv, "context_summary", None),
    )

    if chat_mode == "agent":
        async for event_str in _handle_agent_mode(
            db, user_id, chat_req, conv, model_config, kb,
            history, context_engine, start_time,
        ):
            yield event_str
        return

    if chat_mode == "multi_agent":
        async for event_str in _handle_multi_agent_mode(
            db, user_id, chat_req, conv, model_config,
            history, context_engine, start_time,
        ):
            yield event_str
        return

    # --- Helper coroutines for parallel execution ---
    rag_metadata: dict = {}
    _agentic_config = _resolve_agentic_config(chat_req, kb) if chat_mode in ("rag", "hybrid") else None
    _agentic_events: list = []
    _orch_result = None

    async def _do_rag():
        nonlocal _orch_result

        # Compute user interest vector for memory-enhanced retrieval
        _user_interest_emb = None
        if not _is_public_chat_request(chat_req) and user_id:
            try:
                from app.services.memory_service import compute_user_interest_vector, find_embedding_model
                _emb_model = await find_embedding_model(db, user_id)
                _user_interest_emb = await compute_user_interest_vector(db, user_id, embed_model=_emb_model)
            except Exception:
                pass
        _blend_weight = settings.MEMORY_RETRIEVAL_BLEND_WEIGHT

        if _agentic_config:
            from app.core.agentic_rag.orchestrator import AgenticRAGOrchestrator
            orchestrator = AgenticRAGOrchestrator(_agentic_config)
            _orch_result = await orchestrator.execute(
                db=db, query=chat_req.question, kb_id=chat_req.kb_id,
                user_id=user_id, model_config=model_config,
                chat_history=history, top_k=chat_req.top_k,
                score_threshold=chat_req.score_threshold,
                enable_rewrite=chat_req.enable_rewrite,
                event_callback=lambda evt: _agentic_events.append(evt),
                metadata_out=rag_metadata,
                user_context_embedding=_user_interest_emb,
                blend_weight=_blend_weight,
            )
            return _orch_result.retrieval_results

        r = await retrieve(
            db, chat_req.kb_id, chat_req.question,
            top_k=chat_req.top_k,
            enable_rewrite=chat_req.enable_rewrite,
            score_threshold=chat_req.score_threshold,
            user_id=user_id,
            chat_history=history,
            metadata_out=rag_metadata,
            blend_embedding=_user_interest_emb,
            blend_weight=_blend_weight,
        )
        return r

    async def _do_sql():
        sources = await get_kb_database_sources(db, chat_req.kb_id)
        if not sources:
            return None, "（无可用数据库源）"
        try:
            result = await text_to_sql_query(
                db, sources[0], model_config, chat_req.question, summarize=False,
            )
            return result, _build_sql_context(result)
        except Exception as exc:
            _log.warning("Text-to-SQL 查询失败: %s", exc)
            return None, "数据库查询失败，请稍后重试"

    # --- Execute retrieval + SQL (parallel in hybrid mode) ---
    retrieval_results = []
    context = "（未执行知识库检索）"
    sql_result = None
    sql_context = "（未执行数据库查询）"

    need_rag = chat_mode in ("rag", "hybrid")
    need_sql = chat_mode in ("sql", "hybrid")

    if need_rag and need_sql:
        # Hybrid: run sequentially — AsyncSession is NOT safe for concurrent access
        yield json.dumps({"type": "status", "data": "正在检索知识库和查询数据库..."}, ensure_ascii=False) + "\n"
        retrieval_results = await _do_rag()
        context = await build_context(retrieval_results)
        sql_result, sql_context = await _do_sql()
    elif need_rag:
        yield json.dumps({"type": "status", "data": "正在检索知识库..."}, ensure_ascii=False) + "\n"
        retrieval_results = await _do_rag()
        context = await build_context(retrieval_results)
    elif need_sql:
        yield json.dumps({"type": "status", "data": "正在查询数据库..."}, ensure_ascii=False) + "\n"
        sql_result, sql_context = await _do_sql()

    # Emit SQL results to frontend
    if sql_result:
        yield json.dumps({
            "type": "sql",
            "data": {
                "sql": sql_result.get("sql", ""),
                "row_count": sql_result.get("results", {}).get("row_count", 0),
                "columns": sql_result.get("results", {}).get("columns", []),
                "rows": sql_result.get("results", {}).get("rows", [])[:50],
            },
        }, ensure_ascii=False) + "\n"
    elif need_sql and not sql_result and sql_context.startswith("数据库查询失败"):
        yield json.dumps({"type": "sql_error", "data": sql_context}, ensure_ascii=False) + "\n"

    # Emit agentic RAG status events
    for evt in _agentic_events:
        yield json.dumps({"type": "agentic_status", "data": evt}, ensure_ascii=False) + "\n"

    # If orchestrator skipped retrieval entirely, tell the frontend
    if _orch_result and _orch_result.skipped_retrieval:
        yield json.dumps({
            "type": "retrieval_info",
            "data": {"status": "agentic_skip", "message": f"智能判断无需检索: {_orch_result.bypass_reason}"},
        }, ensure_ascii=False) + "\n"

    # Notify frontend about retrieval status (empty results, threshold filtering, etc.)
    if need_rag and not retrieval_results:
        fi = rag_metadata.get("filter_info")
        if fi and fi.get("filtered_all"):
            msg = (
                f"检索到 {fi['before_count']} 条结果，但均低于置信度阈值 {fi['threshold']}"
                f"（最高分 {fi['max_score']}），建议降低阈值后重试。"
            )
            info_status = "filtered_all"
        elif rag_metadata.get("skip_reason"):
            msg = rag_metadata["skip_reason"]
            info_status = "skipped"
        else:
            msg = "未在知识库中找到与问题相关的内容，以下回答仅基于模型自身知识。"
            info_status = "no_results"
        yield json.dumps({
            "type": "retrieval_info",
            "data": {"status": info_status, "message": msg},
        }, ensure_ascii=False) + "\n"

    references_json = json.dumps(
        [r.model_dump() for r in retrieval_results], ensure_ascii=False
    )

    user_msg = ChatMessage(
        conversation_id=conv.id,
        role="user",
        content=chat_req.question,
    )
    db.add(user_msg)
    await db.commit()

    # Re-fetch history (now includes the new user message) and use context engine
    raw_history = await get_chat_history(db, conv.id)
    await context_engine.bootstrap(
        history=raw_history,
        max_tokens=settings.MAX_HISTORY_TOKENS,
        llm_config=model_config,
        db=db,
        conversation_id=conv.id,
        context_summary=getattr(conv, "context_summary", None),
    )
    history = await context_engine.assemble(chat_req.question, max_tokens=settings.MAX_HISTORY_TOKENS)

    # --- Build system prompt based on mode ---
    if chat_mode == "sql":
        prompt_tpl = SQL_ONLY_PROMPT_TEMPLATE
    elif chat_mode == "hybrid":
        prompt_tpl = HYBRID_PROMPT_TEMPLATE
    else:
        prompt_tpl = DEFAULT_PROMPT_TEMPLATE

    if chat_req.prompt_template:
        prompt_tpl = chat_req.prompt_template
    elif chat_req.prompt_template_id:
        try:
            from app.models.prompt_template import PromptTemplate as _PT
            pt_result = await db.execute(
                select(_PT).where(_PT.id == chat_req.prompt_template_id)
            )
            pt = pt_result.scalar_one_or_none()
            if pt:
                prompt_tpl = pt.content
        except Exception:
            pass
    elif kb and getattr(kb, 'prompt_template_id', None):
        try:
            from app.models.prompt_template import PromptTemplate as _PT
            pt_result = await db.execute(
                select(_PT).where(_PT.id == kb.prompt_template_id)
            )
            pt = pt_result.scalar_one_or_none()
            if pt:
                prompt_tpl = pt.content
        except Exception:
            pass
    elif kb and getattr(kb, 'prompt_template', None) and chat_mode == "rag":
        prompt_tpl = kb.prompt_template

    try:
        from datetime import datetime, timezone
        system_prompt = prompt_tpl
        var_map = {
            "{context}": _truncate_context(context),
            "{sql_context}": _truncate_context(sql_context),
            "{question}": chat_req.question or "",
            "{date}": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "{kb_name}": kb.name if kb else "",
            "{history}": "\n".join(
                f"{m['role']}: {m['content'][:200]}" for m in history[-6:]
            ) if history else "",
        }
        for var, val in var_map.items():
            if var in system_prompt:
                system_prompt = system_prompt.replace(var, val)
    except Exception:
        system_prompt = DEFAULT_PROMPT_TEMPLATE.replace("{context}", _truncate_context(context))

    user_memories = []
    if not _is_public_chat_request(chat_req):
        try:
            from app.services.memory_service import (
                search_memories, build_memory_context, find_embedding_model,
                get_user_profile, build_profile_context,
            )
            profile = await get_user_profile(db, user_id)
            profile_ctx = build_profile_context(profile)
            if profile_ctx:
                system_prompt = profile_ctx + "\n\n" + system_prompt

            embed_model = await find_embedding_model(db, user_id)
            user_memories = await search_memories(db, user_id, chat_req.question, top_k=5, embed_model=embed_model)
            memory_ctx = build_memory_context(user_memories)
            if memory_ctx:
                system_prompt = memory_ctx + "\n\n" + system_prompt
        except Exception as _mem_exc:
            _log.warning("Memory retrieval failed (user_id=%s): %s", user_id, _mem_exc)

    messages = [{"role": "system", "content": system_prompt}] + history

    yield json.dumps({
        "type": "references",
        "conversation_id": conv.id,
        "data": [r.model_dump() for r in retrieval_results],
    }, ensure_ascii=False) + "\n"

    if user_memories:
        yield json.dumps({
            "type": "memories",
            "data": [{"content": m["content"], "category": m["category"], "score": m["score"]} for m in user_memories],
        }, ensure_ascii=False) + "\n"

    full_response = ""
    used_fallback = False
    LLM_TOTAL_TIMEOUT = 300   # seconds — total deadline for the entire LLM stream
    LLM_FIRST_CHUNK_TIMEOUT = 90  # seconds — generous wait for the first token
    LLM_CHUNK_TIMEOUT = 30   # seconds — max wait between subsequent chunks

    async def _stream_llm(cfg):
        nonlocal full_response
        stream_gen = await chat_completion(cfg, messages, stream=True)
        deadline = time.time() + LLM_TOTAL_TIMEOUT
        aiter = stream_gen.__aiter__()
        is_first = True
        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                raise asyncio.TimeoutError("total")
            ct = LLM_FIRST_CHUNK_TIMEOUT if is_first else LLM_CHUNK_TIMEOUT
            try:
                chunk = await asyncio.wait_for(
                    aiter.__anext__(), timeout=min(ct, remaining),
                )
            except StopAsyncIteration:
                break
            is_first = False
            full_response += chunk
            yield json.dumps({"type": "content", "data": chunk}, ensure_ascii=False) + "\n"

    try:
        async for event in _stream_llm(model_config):
            yield event
    except asyncio.CancelledError:
        if full_response:
            try:
                await _save_chat_result(
                    db=db, conv=conv, user_id=user_id, chat_req=chat_req,
                    full_response=full_response, references_json=references_json,
                    retrieval_results=retrieval_results, model_config=model_config,
                    chat_mode=chat_mode, start_time=start_time, history=history,
                    context_engine=context_engine, messages=messages, need_rag=need_rag,
                    is_trial_user=_is_trial_user,
                )
            except Exception as _cancel_save_exc:
                _log.warning("Failed to save partial response on cancel: %s", _cancel_save_exc)
        raise
    except Exception as primary_exc:
        _log.error("LLM 流式响应失败: %s", primary_exc, exc_info=True)

        fallback_cfg = await _load_fallback_model(db, model_config)
        if fallback_cfg and not full_response:
            _log.info(
                "尝试 fallback 模型 id=%s (%s)", fallback_cfg.id, fallback_cfg.display_name,
            )
            yield json.dumps({
                "type": "status",
                "data": f"主模型调用失败，正在切换至备用模型「{fallback_cfg.display_name}」...",
            }, ensure_ascii=False) + "\n"
            try:
                async for event in _stream_llm(fallback_cfg):
                    yield event
                used_fallback = True
                model_config = fallback_cfg
            except Exception as fb_exc:
                _log.error("Fallback 模型也失败: %s", fb_exc, exc_info=True)
                error_msg = f"主模型和备用模型均调用失败。{_classify_llm_error(fb_exc)}"
                yield json.dumps({"type": "error", "data": error_msg}, ensure_ascii=False) + "\n"
                full_response = f"⚠️ {error_msg}"
        else:
            error_msg = _classify_llm_error(primary_exc)
            yield json.dumps({"type": "error", "data": error_msg}, ensure_ascii=False) + "\n"
            if not full_response:
                full_response = f"⚠️ {error_msg}"

    if used_fallback and full_response:
        yield json.dumps({
            "type": "status",
            "data": f"（本次回答由备用模型「{model_config.display_name}」生成）",
        }, ensure_ascii=False) + "\n"

    # --- Iterative refinement (FAIR-RAG) ---
    if (
        _agentic_config
        and _agentic_config.enable_iterative_refinement
        and full_response
        and not full_response.startswith("⚠️")
        and need_rag
    ):
        from app.core.agentic_rag.answer_evaluator import evaluate_answer

        for _refine_i in range(_agentic_config.max_refinement_iterations):
            try:
                eval_result = await evaluate_answer(
                    model_config, chat_req.question, full_response, context,
                    iteration=_refine_i,
                    max_iterations=_agentic_config.max_refinement_iterations,
                )
                yield json.dumps({
                    "type": "agentic_status",
                    "data": {
                        "stage": "refinement_eval",
                        "iteration": _refine_i + 1,
                        "score": round(eval_result.score, 2),
                        "sufficient": eval_result.is_sufficient,
                    },
                }, ensure_ascii=False) + "\n"

                if eval_result.is_sufficient or not eval_result.should_iterate:
                    break

                yield json.dumps({
                    "type": "agentic_status",
                    "data": {
                        "stage": "refinement",
                        "iteration": _refine_i + 1,
                        "deficiencies": eval_result.deficiencies,
                        "refined_query": eval_result.refined_query,
                    },
                }, ensure_ascii=False) + "\n"
                yield json.dumps({
                    "type": "status",
                    "data": f"正在优化回答（第{_refine_i + 2}轮检索）...",
                }, ensure_ascii=False) + "\n"

                # Re-retrieve with refined query
                new_results = await retrieve(
                    db, chat_req.kb_id, eval_result.refined_query,
                    top_k=chat_req.top_k,
                    enable_rewrite=False,
                    user_id=user_id,
                    chat_history=history,
                )
                if not new_results:
                    break

                new_context = await build_context(new_results)
                combined_context = _truncate_context(context + "\n\n" + new_context)

                # Rebuild messages with enriched context and previous answer
                refinement_prompt = (
                    f"基于以下补充资料，请完善你之前的回答。\n\n"
                    f"补充资料：\n{new_context}\n\n"
                    f"你之前的回答：\n{full_response[:500]}\n\n"
                    f"用户原始问题：{chat_req.question}\n\n"
                    f"请给出更完整、准确的回答："
                )
                refine_messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": refinement_prompt},
                ]

                # Re-generate (non-streaming, replace previous response)
                refined_response = await chat_completion(model_config, refine_messages, stream=False)
                if refined_response and len(refined_response.strip()) > len(full_response.strip()) * 0.5:
                    full_response = refined_response
                    context = combined_context
                    # Update references with new results (deduplicate)
                    _seen = {(r.doc_name, r.chunk_index) for r in retrieval_results}
                    _new_unique = [r for r in new_results if (r.doc_name, r.chunk_index) not in _seen]
                    retrieval_results = list(retrieval_results) + _new_unique
                    references_json = json.dumps(
                        [r.model_dump() for r in retrieval_results], ensure_ascii=False
                    )
                    yield json.dumps({
                        "type": "content_replace",
                        "data": full_response,
                    }, ensure_ascii=False) + "\n"

            except Exception as _refine_exc:
                _log.warning("Iterative refinement failed at iteration %d: %s", _refine_i, _refine_exc)
                break

    latency, input_token_count, token_count, _assistant_msg_id = await _save_chat_result(
        db=db, conv=conv, user_id=user_id, chat_req=chat_req,
        full_response=full_response, references_json=references_json,
        retrieval_results=retrieval_results, model_config=model_config,
        chat_mode=chat_mode, start_time=start_time, history=history,
        context_engine=context_engine, messages=messages, need_rag=need_rag,
        is_trial_user=_is_trial_user,
    )

    # Persist trajectory if recording was enabled
    if _orch_result and _orch_result.trajectory:
        try:
            from app.models.trajectory import RAGTrajectory
            traj = _orch_result.trajectory
            traj_record = RAGTrajectory(
                trajectory_id=traj.trajectory_id,
                conversation_id=conv.id,
                message_id=_assistant_msg_id,
                kb_id=chat_req.kb_id,
                user_id=user_id,
                original_query=chat_req.question,
                outcome=traj.outcome,
                step_count=len(traj.steps),
                total_duration_ms=traj.total_duration_ms,
                config_snapshot=json.dumps(traj.config_snapshot, ensure_ascii=False),
                steps_json=json.dumps(traj.to_steps_list(), ensure_ascii=False),
                reward_score=traj.aggregate_reward(),
            )
            db.add(traj_record)
            await db.commit()
        except Exception as _traj_exc:
            _log.warning("Trajectory persistence failed: %s", _traj_exc)

        yield json.dumps({
            "type": "trajectory",
            "data": {
                "trajectory_id": traj.trajectory_id,
                "step_count": len(traj.steps),
                "outcome": traj.outcome,
                "total_ms": traj.total_duration_ms,
                "fingerprint": traj.action_sequence_fingerprint(),
            },
        }, ensure_ascii=False) + "\n"

    yield json.dumps({
        "type": "done",
        "conversation_id": conv.id,
        "latency_ms": round(latency, 1),
        "usage": {
            "input_tokens": input_token_count,
            "output_tokens": token_count,
        },
    }, ensure_ascii=False) + "\n"
