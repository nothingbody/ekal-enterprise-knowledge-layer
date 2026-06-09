"""Agent mode, multi-agent mode, and slash command handlers for chat."""
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
from app.core.llm_client import chat_completion, chat_completion_with_tools
from app.core.token_utils import count_tokens as _count_tokens
from app.config import settings
from app.services.chat_constants import AGENT_SYSTEM_PROMPT, AGENT_MAX_ITERATIONS
from app.services.chat_helpers import classify_llm_error, is_public_chat_request


async def stream_agent_chat(
    db: AsyncSession,
    user_id: int,
    chat_req: ChatRequest,
    conv: ChatConversation,
    model_config: ModelConfig,
    kb: "KnowledgeBase | None",
    history: list,
    registry=None,
) -> AsyncGenerator[str, None]:
    """Agent mode: ReAct loop with tool calling."""
    agent_logger = logging.getLogger("agent")

    if registry is None:
        from app.core.tools import get_default_registry
        registry = get_default_registry()
    tools_schema = registry.get_openai_tools_schema()

    # Inject context for tools that need db/kb/model
    tool_context = {
        "_db": db,
        "_kb_id": chat_req.kb_id,
        "_user_id": user_id,
        "_model_config": model_config,
        "_chat_history": history,
    }

    system_prompt = AGENT_SYSTEM_PROMPT
    if chat_req.prompt_template:
        system_prompt = chat_req.prompt_template + "\n\n" + AGENT_SYSTEM_PROMPT

    if not is_public_chat_request(chat_req):
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
        except Exception:
            pass

    messages = [{"role": "system", "content": system_prompt}] + history

    all_tool_results = []  # Track for references/logging

    for iteration in range(AGENT_MAX_ITERATIONS):
        agent_logger.info("Agent iteration %d, messages=%d", iteration, len(messages))

        yield json.dumps({
            "type": "status",
            "data": "正在思考..." if iteration == 0 else "正在根据工具结果继续分析...",
        }, ensure_ascii=False) + "\n"

        try:
            response = await chat_completion_with_tools(
                model_config, messages, tools_schema,
            )
        except Exception as exc:
            agent_logger.error("Agent LLM 调用失败: %s", exc, exc_info=True)
            yield json.dumps({"type": "error", "data": classify_llm_error(exc)}, ensure_ascii=False) + "\n"
            return

        tool_calls = response.get("tool_calls")
        content = response.get("content")

        if not tool_calls:
            # No tool calls — LLM wants to give a text response
            yield json.dumps({"type": "status", "data": "正在生成回答..."}, ensure_ascii=False) + "\n"

            # Emit any collected references
            if all_tool_results:
                refs = []
                for tr in all_tool_results:
                    if tr.get("display_type") == "references" and isinstance(tr.get("data"), dict):
                        refs.extend(tr["data"].get("references", []))
                if refs:
                    yield json.dumps({
                        "type": "references",
                        "conversation_id": conv.id,
                        "data": refs,
                    }, ensure_ascii=False) + "\n"

            # Use the content already returned by chat_completion_with_tools
            # to avoid a wasteful second LLM call.
            if content:
                yield json.dumps({"type": "content", "data": content}, ensure_ascii=False) + "\n"
            else:
                # Rare: model returned neither tool_calls nor content — do a
                # streaming follow-up as a fallback.
                try:
                    stream_gen = await chat_completion(model_config, messages, stream=True)
                    async for chunk in stream_gen:
                        yield json.dumps({"type": "content", "data": chunk}, ensure_ascii=False) + "\n"
                except Exception as exc:
                    agent_logger.error("Agent LLM 流式响应失败: %s", exc, exc_info=True)
                    yield json.dumps({"type": "error", "data": classify_llm_error(exc)}, ensure_ascii=False) + "\n"

            yield json.dumps({"type": "agent_complete", "data": {
                "iterations": iteration + 1,
                "tools_used": [tr["tool_name"] for tr in all_tool_results],
            }}, ensure_ascii=False) + "\n"
            return

        # Has tool calls — execute them
        # Append assistant message with tool_calls to messages
        assistant_msg = {"role": "assistant", "content": content or ""}
        assistant_msg["tool_calls"] = tool_calls
        messages.append(assistant_msg)

        for tc in tool_calls:
            func_name = tc["function"]["name"]
            func_args_str = tc["function"]["arguments"]
            tc_id = tc["id"]

            yield json.dumps({
                "type": "tool_call",
                "data": {"name": func_name, "arguments": func_args_str, "id": tc_id},
            }, ensure_ascii=False) + "\n"

            # Parse arguments (with size limit to prevent DoS from LLM output)
            try:
                if func_args_str and len(func_args_str) > 50_000:
                    logger.warning("Tool arguments too large (%d bytes), truncating", len(func_args_str))
                    func_args_str = func_args_str[:50_000]
                func_args = json.loads(func_args_str) if func_args_str else {}
            except json.JSONDecodeError:
                func_args = {}

            # Inject context
            func_args.update(tool_context)

            agent_logger.info("Executing tool: %s(%s)", func_name, {k: v for k, v in func_args.items() if not k.startswith("_")})

            TOOL_EXEC_TIMEOUT = 60  # seconds
            try:
                result = await asyncio.wait_for(
                    registry.execute(func_name, **func_args),
                    timeout=TOOL_EXEC_TIMEOUT,
                )
            except asyncio.TimeoutError:
                agent_logger.warning("Tool %s timed out after %ds", func_name, TOOL_EXEC_TIMEOUT)
                from app.core.tools import ToolResult
                result = ToolResult(success=False, data={"error": f"工具 {func_name} 执行超时（{TOOL_EXEC_TIMEOUT}s）"}, display_type="error")

            # Emit tool result to frontend
            yield json.dumps({
                "type": "tool_result",
                "data": {
                    "name": func_name,
                    "id": tc_id,
                    "result": result.to_frontend_payload(),
                },
            }, ensure_ascii=False) + "\n"

            all_tool_results.append({
                "tool_name": func_name,
                "display_type": result.display_type,
                "data": result.data,
                "success": result.success,
            })

            # Append tool result message for next LLM call
            messages.append({
                "role": "tool",
                "tool_call_id": tc_id,
                "content": result.to_message_content(),
            })

    # Max iterations reached — do a final streaming call without tools
    yield json.dumps({"type": "status", "data": "正在综合所有信息生成最终回答..."}, ensure_ascii=False) + "\n"

    try:
        stream_gen = await chat_completion(model_config, messages, stream=True)
        async for chunk in stream_gen:
            yield json.dumps({"type": "content", "data": chunk}, ensure_ascii=False) + "\n"
    except Exception as exc:
        agent_logger.error("Agent 最终 LLM 响应失败: %s", exc, exc_info=True)
        yield json.dumps({"type": "error", "data": classify_llm_error(exc)}, ensure_ascii=False) + "\n"

    yield json.dumps({"type": "agent_complete", "data": {
        "iterations": AGENT_MAX_ITERATIONS,
        "tools_used": [tr["tool_name"] for tr in all_tool_results],
    }}, ensure_ascii=False) + "\n"


async def handle_agent_mode(
    db: AsyncSession,
    user_id: int,
    chat_req: ChatRequest,
    conv: ChatConversation,
    model_config: ModelConfig,
    kb: "KnowledgeBase | None",
    history: list,
    context_engine,
    start_time: float,
) -> AsyncGenerator[str, None]:
    """Agent mode: build user registry, run ReAct loop, persist results."""
    try:
        from app.services.skill_service import build_user_registry, auto_install_builtins
        await auto_install_builtins(db, user_id)
        user_registry = await build_user_registry(db, user_id)
    except Exception:
        from app.core.tools import get_default_registry
        user_registry = get_default_registry()

    user_msg = ChatMessage(conversation_id=conv.id, role="user", content=chat_req.question)
    db.add(user_msg)
    await db.commit()

    history.append({"role": "user", "content": chat_req.question})
    history = await context_engine.assemble(chat_req.question, max_tokens=settings.MAX_HISTORY_TOKENS)

    full_response = ""
    async for event_str in stream_agent_chat(
        db, user_id, chat_req, conv, model_config, kb, history,
        registry=user_registry,
    ):
        yield event_str
        try:
            event = json.loads(event_str.strip())
            if event.get("type") == "content":
                full_response += event.get("data", "")
        except (json.JSONDecodeError, AttributeError):
            pass

    latency = (time.time() - start_time) * 1000
    token_count = _count_tokens(full_response)
    db.add(ChatMessage(
        conversation_id=conv.id, role="assistant",
        content=full_response, token_count=token_count, latency_ms=latency,
    ))
    add_log_and_sync(db,
        user_id=user_id, action="chat", resource_type="conversation",
        resource_id=conv.id,
        detail=json.dumps({"mode": "agent"}, ensure_ascii=False),
        total_tokens=token_count, latency_ms=latency,
    )
    await db.commit()

    yield json.dumps({
        "type": "done", "conversation_id": conv.id,
        "latency_ms": round(latency, 1),
    }, ensure_ascii=False) + "\n"


async def handle_multi_agent_mode(
    db: AsyncSession,
    user_id: int,
    chat_req: ChatRequest,
    conv: ChatConversation,
    model_config: ModelConfig,
    history: list,
    context_engine,
    start_time: float,
) -> AsyncGenerator[str, None]:
    """Multi-agent mode: orchestrate multiple agents, persist results."""
    from app.services.multi_agent_service import get_user_agents, execute_multi_agent

    agents = await get_user_agents(db, user_id)
    if not agents:
        yield json.dumps({
            "type": "error",
            "data": "当前用户还没有可用的 Agent，请先在「多Agent协作」页面创建并启用 Agent",
        }, ensure_ascii=False) + "\n"
        return

    db.add(ChatMessage(conversation_id=conv.id, role="user", content=chat_req.question))
    await db.commit()

    full_response = ""
    multi_agent_refs = []
    input_token_count = _count_tokens(chat_req.question)

    async for event_str in execute_multi_agent(
        db=db, user_id=user_id, question=chat_req.question,
        agents=agents, llm_config=model_config,
    ):
        try:
            event = json.loads(event_str.strip())
        except (json.JSONDecodeError, AttributeError):
            yield event_str
            continue

        event_type = event.get("type")
        if event_type == "content":
            full_response += event.get("data", "")
        elif event_type == "references":
            multi_agent_refs = event.get("data", []) or []
            event["conversation_id"] = conv.id
        elif event_type == "done":
            continue
        yield json.dumps(event, ensure_ascii=False) + "\n"

    latency = (time.time() - start_time) * 1000
    token_count = _count_tokens(full_response)
    references_json = json.dumps(multi_agent_refs, ensure_ascii=False) if multi_agent_refs else None

    db.add(ChatMessage(
        conversation_id=conv.id, role="assistant", content=full_response,
        references=references_json, token_count=token_count,
        latency_ms=latency, msg_type="chat",
    ))

    from sqlalchemy import update as sa_update
    await db.execute(
        sa_update(ChatConversation).where(ChatConversation.id == conv.id).values(
            total_input_tokens=ChatConversation.total_input_tokens + input_token_count,
            total_output_tokens=ChatConversation.total_output_tokens + token_count,
        )
    )

    add_log_and_sync(db,
        user_id=user_id, action="chat", resource_type="conversation",
        resource_id=conv.id,
        detail=json.dumps({
            "mode": "multi_agent", "agent_count": len(agents),
            "reference_count": len(multi_agent_refs),
        }, ensure_ascii=False),
        total_tokens=token_count, latency_ms=latency,
    )

    await context_engine.after_turn(full_response)
    await db.commit()

    if not is_public_chat_request(chat_req) and full_response:
        try:
            from app.services.memory_service import extract_memories_from_conversation
            conv_messages = history + [
                {"role": "user", "content": chat_req.question},
                {"role": "assistant", "content": full_response},
            ]
            await extract_memories_from_conversation(
                db, user_id, conv.id, conv_messages, model_config,
            )
        except Exception as _mem_exc:
            logging.getLogger(__name__).warning(
                "Memory extraction failed (user_id=%s, conv_id=%s): %s",
                user_id, conv.id, _mem_exc,
            )

    yield json.dumps({
        "type": "done", "conversation_id": conv.id,
        "latency_ms": round(latency, 1),
        "usage": {"input_tokens": input_token_count, "output_tokens": token_count},
    }, ensure_ascii=False) + "\n"


async def handle_slash_command(
    db: AsyncSession,
    user_id: int,
    chat_req: ChatRequest,
    conv: ChatConversation,
    model_config: ModelConfig,
) -> AsyncGenerator[str, None] | None:
    """Detect `/skill_name args` pattern and execute the skill directly.

    Returns an async generator if a slash command was matched, or None otherwise.
    """
    question = chat_req.question.strip()
    if not question.startswith("/"):
        return None

    rest = question[1:]
    if not rest or rest[0] == " ":
        return None

    from app.models.skill import Skill
    from app.models.skill_install import SkillInstall

    parts = rest.split(None, 1)
    skill_name = parts[0]
    user_input = parts[1] if len(parts) > 1 else ""

    result = await db.execute(
        select(Skill)
        .join(SkillInstall, SkillInstall.skill_id == Skill.id)
        .where(SkillInstall.user_id == user_id, SkillInstall.is_active == True)
    )
    installed_skills = result.scalars().all()

    matched = None
    for s in installed_skills:
        if s.name == skill_name or s.slug == skill_name:
            matched = s
            break
    if not matched:
        for s in installed_skills:
            if skill_name in s.name or s.name in skill_name:
                matched = s
                break
    if not matched:
        return None

    async def _generate():
        logger = logging.getLogger("slash_command")
        logger.info("Slash command: skill=%s user_input=%s", matched.name, user_input[:100])

        yield json.dumps({"type": "mode", "data": "skill"}, ensure_ascii=False) + "\n"
        yield json.dumps({"type": "status", "data": f"正在执行技能「{matched.name}」..."}, ensure_ascii=False) + "\n"

        skill_config = json.loads(matched.config) if matched.config else {}
        prompt_template = skill_config.get("prompt_template", "")

        if prompt_template:
            import re
            var_pattern = re.compile(r"\{\{(\w+)\}\}")
            variables = list(dict.fromkeys(var_pattern.findall(prompt_template)))
            var_map = {v: user_input for v in variables}
            var_map["query"] = user_input
            var_map["input"] = user_input
            var_map["text"] = user_input
            rendered = var_pattern.sub(lambda m: var_map.get(m.group(1), m.group(0)), prompt_template)

            messages = [
                {"role": "system", "content": rendered},
                {"role": "user", "content": user_input or "请执行上述任务。"},
            ]
        else:
            messages = [
                {"role": "system", "content": f"你是「{matched.name}」技能助手。{matched.description or ''}"},
                {"role": "user", "content": user_input or "请执行任务。"},
            ]

        try:
            stream_gen = await chat_completion(model_config, messages, stream=True)
            async for chunk in stream_gen:
                yield json.dumps({"type": "content", "data": chunk}, ensure_ascii=False) + "\n"
        except Exception as exc:
            logger.exception("Slash command skill execution failed")
            yield json.dumps({"type": "error", "data": f"技能执行失败: {exc}"}, ensure_ascii=False) + "\n"
            return

        user_msg = ChatMessage(conversation_id=conv.id, role="user", content=question)
        db.add(user_msg)
        await db.flush()

        yield json.dumps({
            "type": "done",
            "conversation_id": conv.id,
        }, ensure_ascii=False) + "\n"

    return _generate()
