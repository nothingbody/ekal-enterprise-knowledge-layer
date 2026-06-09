"""Automation service — create, execute, schedule, and trigger automation tasks."""

from __future__ import annotations

import json
import logging
import secrets
import time
import re
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, update as sa_update, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.automation import AutomationTask, AutomationLog

logger = logging.getLogger(__name__)
_TPL_PATTERN = re.compile(r"\{\{\s*([.\w]+)\s*\}\}")

SUPPORTED_ACTIONS = {
    "summarize_kb",
    "run_agent_query",
    "export_report",
    "notify_channel",
    "run_chain",
}


def _extract_action_params(config: dict) -> dict:
    params = config.get("params")
    if isinstance(params, dict):
        return params
    return {k: v for k, v in config.items() if k not in {"action"}}


def _validate_action_config(config: dict) -> None:
    action = config.get("action")
    if action and action not in SUPPORTED_ACTIONS:
        raise ValueError(f"不支持的动作: {action}，支持: {', '.join(sorted(SUPPORTED_ACTIONS))}")
    if not action:
        raise ValueError("缺少参数: action")

    params = _extract_action_params(config)
    if action in {"summarize_kb", "export_report"} and not params.get("kb_id"):
        raise ValueError("缺少参数: kb_id")
    if action == "run_agent_query":
        if not params.get("kb_id"):
            raise ValueError("缺少参数: kb_id")
        if not params.get("query"):
            raise ValueError("缺少参数: query")
    if action == "notify_channel" and not (params.get("message") or params.get("message_template")):
        raise ValueError("缺少参数: message")
    if action == "run_chain" and not (params.get("chain_id") or params.get("steps")):
        raise ValueError("缺少参数: chain_id 或 steps")


def _resolve_template_value(key: str, sources: list[dict]) -> object:
    parts = key.split(".")
    for source in sources:
        current: object = source
        ok = True
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                ok = False
                break
        if ok:
            return current
    return None


def _render_template(template: str | None, params: dict) -> str:
    if not template:
        return ""

    event_data = params.get("_event_data") or {}
    sources = [
        params,
        {"event": event_data},
        event_data if isinstance(event_data, dict) else {},
    ]

    def _replacer(match: re.Match) -> str:
        value = _resolve_template_value(match.group(1), sources)
        if value is None:
            return match.group(0)
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False)
        return str(value)

    return _TPL_PATTERN.sub(_replacer, template)


async def create_task(
    db: AsyncSession,
    user_id: int,
    *,
    name: str,
    task_type: str,
    config: dict,
    description: str | None = None,
    cron_expression: str | None = None,
    interval_minutes: int | None = None,
    event_trigger: str | None = None,
) -> AutomationTask:
    """Create a new automation task. Generates webhook_token if type is webhook."""

    if task_type not in ("scheduled", "webhook", "event"):
        raise ValueError(f"无效的任务类型: {task_type}")

    if task_type == "scheduled" and not cron_expression and not interval_minutes:
        raise ValueError("定时任务必须设置 cron_expression 或 interval_minutes")

    if cron_expression:
        try:
            from croniter import croniter
            croniter(cron_expression)  # Validate syntax
        except (ValueError, KeyError) as e:
            raise ValueError(f"无效的 cron 表达式: {cron_expression} ({e})")

    if task_type == "event" and not event_trigger:
        raise ValueError("事件任务必须设置 event_trigger")

    _validate_action_config(config)

    webhook_token = None
    if task_type == "webhook":
        webhook_token = secrets.token_urlsafe(32)

    task = AutomationTask(
        user_id=user_id,
        name=name,
        description=description,
        task_type=task_type,
        cron_expression=cron_expression,
        interval_minutes=interval_minutes,
        webhook_token=webhook_token,
        event_trigger=event_trigger,
        config=json.dumps(config, ensure_ascii=False),
        is_active=True,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return task


async def update_task(
    db: AsyncSession,
    task_id: int,
    user_id: int,
    **kwargs,
) -> Optional[AutomationTask]:
    """Update an existing automation task (only fields present in kwargs)."""

    task = (await db.execute(
        select(AutomationTask).where(
            AutomationTask.id == task_id,
            AutomationTask.user_id == user_id,
        )
    )).scalar_one_or_none()
    if not task:
        return None

    if task.task_type == "scheduled":
        next_cron = kwargs.get("cron_expression", task.cron_expression)
        next_interval = kwargs.get("interval_minutes", task.interval_minutes)
        if not next_cron and not next_interval:
            raise ValueError("定时任务必须设置 cron_expression 或 interval_minutes")
    if task.task_type == "event":
        next_event = kwargs.get("event_trigger", task.event_trigger)
        if not next_event:
            raise ValueError("事件任务必须设置 event_trigger")

    if "config" in kwargs and isinstance(kwargs["config"], dict):
        _validate_action_config(kwargs["config"])
        kwargs["config"] = json.dumps(kwargs["config"], ensure_ascii=False)

    for key, value in kwargs.items():
        if hasattr(task, key):
            setattr(task, key, value)

    await db.commit()
    await db.refresh(task)
    return task


async def delete_task(db: AsyncSession, task_id: int, user_id: int) -> bool:
    task = (await db.execute(
        select(AutomationTask).where(
            AutomationTask.id == task_id,
            AutomationTask.user_id == user_id,
        )
    )).scalar_one_or_none()
    if not task:
        return False
    await db.delete(task)
    await db.commit()
    return True


async def get_task(db: AsyncSession, task_id: int, user_id: int) -> Optional[AutomationTask]:
    return (await db.execute(
        select(AutomationTask).where(
            AutomationTask.id == task_id,
            AutomationTask.user_id == user_id,
        )
    )).scalar_one_or_none()


async def list_tasks(
    db: AsyncSession,
    user_id: int,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    total = (await db.execute(
        select(func.count(AutomationTask.id)).where(AutomationTask.user_id == user_id)
    )).scalar() or 0

    result = await db.execute(
        select(AutomationTask)
        .where(AutomationTask.user_id == user_id)
        .order_by(AutomationTask.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = result.scalars().all()
    return {"items": items, "total": total, "page": page, "page_size": page_size}


async def get_task_logs(
    db: AsyncSession,
    task_id: int,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    total = (await db.execute(
        select(func.count(AutomationLog.id)).where(AutomationLog.task_id == task_id)
    )).scalar() or 0

    result = await db.execute(
        select(AutomationLog)
        .where(AutomationLog.task_id == task_id)
        .order_by(AutomationLog.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = result.scalars().all()
    return {"items": items, "total": total, "page": page, "page_size": page_size}


async def get_task_by_webhook_token(db: AsyncSession, token: str) -> Optional[AutomationTask]:
    return (await db.execute(
        select(AutomationTask).where(
            AutomationTask.webhook_token == token,
            AutomationTask.task_type == "webhook",
            AutomationTask.is_active == True,
        )
    )).scalar_one_or_none()


# ---------------------------------------------------------------------------
# Task execution
# ---------------------------------------------------------------------------

async def execute_task(
    db: AsyncSession,
    task_id: int,
    triggered_by: str = "manual",
    event_data: dict | None = None,
) -> AutomationLog:
    """Execute an automation task and record the result."""

    task = (await db.execute(
        select(AutomationTask).where(AutomationTask.id == task_id)
    )).scalar_one_or_none()
    if not task:
        raise ValueError("自动化任务不存在")

    # Atomic CAS: only set running if not already running (prevents duplicate execution)
    cas_result = await db.execute(
        sa_update(AutomationTask)
        .where(
            AutomationTask.id == task_id,
            or_(AutomationTask.last_status.is_(None), AutomationTask.last_status != "running"),
        )
        .values(last_status="running", last_run_at=datetime.now(timezone.utc))
    )
    await db.commit()
    if cas_result.rowcount == 0:
        logger.info("自动化任务 %s 已在其他 Worker 执行中，跳过", task_id)
        return

    start_ms = time.monotonic() * 1000
    output = None
    error_message = None
    status = "success"

    try:
        config = json.loads(task.config)
        action = config.get("action", "")
        params = config.get("params")
        if not isinstance(params, dict):
            # Backward compatibility: older tasks stored action params at the root level.
            params = {
                k: v for k, v in config.items()
                if k not in {"action"}
            }
        if event_data:
            params["_event_data"] = event_data

        output = await _dispatch_action(db, task.user_id, action, params)
    except Exception as exc:
        status = "failed"
        error_message = str(exc)[:2000]
        logger.exception("自动化任务执行失败 (task_id=%s): %s", task_id, exc)

    duration_ms = time.monotonic() * 1000 - start_ms

    log = AutomationLog(
        task_id=task_id,
        status=status,
        output=output[:5000] if output else None,
        error_message=error_message,
        duration_ms=round(duration_ms, 2),
        triggered_by=triggered_by,
    )
    db.add(log)

    await db.execute(
        sa_update(AutomationTask)
        .where(AutomationTask.id == task_id)
        .values(
            last_status=status,
            last_error=error_message,
            run_count=AutomationTask.run_count + 1,
        )
    )
    await db.commit()
    await db.refresh(log)
    return log


async def _dispatch_action(
    db: AsyncSession,
    user_id: int,
    action: str,
    params: dict,
) -> str:
    """Route to the appropriate action handler."""

    if action == "summarize_kb":
        return await _action_summarize_kb(db, user_id, params)
    elif action == "run_agent_query":
        return await _action_run_agent_query(db, user_id, params)
    elif action == "export_report":
        return await _action_export_report(db, user_id, params)
    elif action == "notify_channel":
        return await _action_notify_channel(db, user_id, params)
    elif action == "run_chain":
        return await _action_run_chain(db, user_id, params)
    else:
        raise ValueError(f"未知的自动化动作: {action}")


async def _action_summarize_kb(db: AsyncSession, user_id: int, params: dict) -> str:
    """Generate a summary of recent documents in a knowledge base."""
    from app.models.knowledge_base import KnowledgeBase
    from app.models.document import Document, DocumentChunk
    from app.models.model_config import ModelConfig
    from app.core.llm_client import chat_completion

    kb_id = params.get("kb_id")
    if not kb_id:
        raise ValueError("缺少参数: kb_id")

    kb = (await db.execute(
        select(KnowledgeBase).where(KnowledgeBase.id == kb_id)
    )).scalar_one_or_none()
    if not kb:
        raise ValueError(f"知识库不存在 (id={kb_id})")

    limit = min(params.get("doc_limit", 5), 20)
    docs = (await db.execute(
        select(Document)
        .where(Document.kb_id == kb_id)
        .order_by(Document.created_at.desc())
        .limit(limit)
    )).scalars().all()

    if not docs:
        return "知识库中暂无文档。"

    doc_texts = []
    for doc in docs:
        chunks = (await db.execute(
            select(DocumentChunk.content)
            .where(DocumentChunk.doc_id == doc.id)
            .order_by(DocumentChunk.chunk_index)
            .limit(3)
        )).scalars().all()
        preview = "\n".join(chunks)[:1000]
        doc_texts.append(f"【{doc.filename}】\n{preview}")

    combined = "\n\n---\n\n".join(doc_texts)

    from app.models.model_config import ModelType
    model_id = params.get("model_id") or params.get("llm_model_id")
    if not model_id:
        model = (await db.execute(
            select(ModelConfig)
            .where(ModelConfig.user_id == user_id, ModelConfig.model_type == ModelType.LLM, ModelConfig.is_default == True)
        )).scalar_one_or_none()
        if not model:
            model = (await db.execute(
                select(ModelConfig)
                .where(ModelConfig.user_id == user_id, ModelConfig.model_type == ModelType.LLM)
            )).scalar_one_or_none()
    else:
        model = (await db.execute(
            select(ModelConfig).where(ModelConfig.id == model_id)
        )).scalar_one_or_none()

    if not model:
        raise ValueError("未找到可用的 LLM 模型，请先配置模型")

    messages = [
        {"role": "system", "content": "你是一个文档总结助手。请对以下文档内容进行简明扼要的总结。"},
        {"role": "user", "content": f"请总结以下来自知识库「{kb.name}」的最新文档内容：\n\n{combined}"},
    ]
    result = await chat_completion(model, messages, stream=False)
    return result


async def _action_run_agent_query(db: AsyncSession, user_id: int, params: dict) -> str:
    """Run an LLM query (non-streaming) and return the result."""
    from app.models.model_config import ModelConfig
    from app.core.llm_client import chat_completion

    query = _render_template(params.get("query"), params)
    if not query:
        raise ValueError("缺少参数: query")

    from app.models.model_config import ModelType as _MT
    model_id = params.get("model_id") or params.get("llm_model_id")
    if model_id:
        model = (await db.execute(
            select(ModelConfig).where(ModelConfig.id == model_id)
        )).scalar_one_or_none()
    else:
        model = (await db.execute(
            select(ModelConfig)
            .where(ModelConfig.user_id == user_id, ModelConfig.model_type == _MT.LLM, ModelConfig.is_default == True)
        )).scalar_one_or_none()
        if not model:
            model = (await db.execute(
                select(ModelConfig)
                .where(ModelConfig.user_id == user_id, ModelConfig.model_type == _MT.LLM)
            )).scalar_one_or_none()

    if not model:
        raise ValueError("未找到可用的 LLM 模型，请先配置模型")

    system_prompt = _render_template(
        params.get("system_prompt", "你是一个智能助手，请回答用户的问题。"),
        params,
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": query},
    ]

    # If a kb_id is provided, do retrieval-augmented generation
    kb_id = params.get("kb_id")
    if kb_id:
        try:
            from app.services.retrieval_service import retrieve
            results = await retrieve(db, kb_id, query, top_k=5)
            if results:
                context_parts = [f"[{i+1}] {r.content}" for i, r in enumerate(results)]
                context = "\n\n".join(context_parts)
                messages[0]["content"] += f"\n\n参考资料:\n{context}"
        except Exception as exc:
            logger.warning("自动化任务检索失败 (kb_id=%s): %s", kb_id, exc)

    result = await chat_completion(model, messages, stream=False)
    return result


async def _action_export_report(db: AsyncSession, user_id: int, params: dict) -> str:
    """Generate an analytics report for a knowledge base."""
    from app.models.knowledge_base import KnowledgeBase
    from app.models.document import Document

    kb_id = params.get("kb_id")
    if not kb_id:
        raise ValueError("缺少参数: kb_id")

    kb = (await db.execute(
        select(KnowledgeBase).where(KnowledgeBase.id == kb_id)
    )).scalar_one_or_none()
    if not kb:
        raise ValueError(f"知识库不存在 (id={kb_id})")

    doc_count = (await db.execute(
        select(func.count(Document.id)).where(Document.kb_id == kb_id)
    )).scalar() or 0

    total_size = (await db.execute(
        select(func.sum(Document.file_size)).where(Document.kb_id == kb_id)
    )).scalar() or 0

    from app.models.document import DocumentChunk
    chunk_count = (await db.execute(
        select(func.count(DocumentChunk.id)).where(DocumentChunk.kb_id == kb_id)
    )).scalar() or 0

    report_lines = [
        f"# 知识库报告: {kb.name}",
        f"",
        f"- 文档数量: {doc_count}",
        f"- 切片数量: {chunk_count}",
        f"- 总大小: {total_size / 1024 / 1024:.2f} MB",
        f"- 创建时间: {kb.created_at}",
        f"- 描述: {kb.description or '无'}",
    ]
    return "\n".join(report_lines)


async def _action_notify_channel(db: AsyncSession, user_id: int, params: dict) -> str:
    """Send a notification via webhook (DingTalk / Feishu / generic) or log only."""
    message = _render_template(params.get("message") or params.get("message_template", ""), params)
    channel = params.get("channel") or params.get("channel_id", "log")
    webhook_url = params.get("webhook_url", "")

    if not message:
        raise ValueError("缺少参数: message")

    if webhook_url:
        import httpx
        if "dingtalk" in webhook_url or "oapi.dingtalk.com" in webhook_url:
            payload = {"msgtype": "text", "text": {"content": message[:2000]}}
        elif "feishu" in webhook_url or "open.feishu.cn" in webhook_url:
            payload = {"msg_type": "text", "content": {"text": message[:2000]}}
        else:
            payload = {"text": message[:2000]}

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(webhook_url, json=payload)
            resp.raise_for_status()
        logger.info("自动化通知已发送至 webhook [%s]", channel)
        return f"通知已通过 webhook 发送到 {channel}: {message[:200]}"

    logger.info("自动化通知 [%s]: %s", channel, message[:200])
    return f"通知已记录到日志 ({channel}): {message[:200]}"


async def _action_run_chain(db: AsyncSession, user_id: int, params: dict) -> str:
    """Execute a saved skill chain or a legacy inline mini-chain."""
    chain_id = params.get("chain_id")
    if chain_id is not None:
        from app.services.skill_chain_service import execute_chain
        from app.models.model_config import ModelConfig, ModelType

        model_id = params.get("model_id") or params.get("llm_model_id")
        model = None
        if model_id:
            model = (await db.execute(
                select(ModelConfig).where(ModelConfig.id == model_id)
            )).scalar_one_or_none()
        else:
            model = (await db.execute(
                select(ModelConfig).where(
                    ModelConfig.user_id == user_id,
                    ModelConfig.model_type == ModelType.LLM,
                    ModelConfig.is_default == True,
                )
            )).scalar_one_or_none()
            if not model:
                model = (await db.execute(
                    select(ModelConfig).where(
                        ModelConfig.user_id == user_id,
                        ModelConfig.model_type == ModelType.LLM,
                    )
                )).scalar_one_or_none()

        if not model:
            raise ValueError("未找到可用的 LLM 模型，请先配置模型")

        event_data = params.get("_event_data")
        initial_input = _render_template(params.get("initial_input"), params) if params.get("initial_input") else None
        if initial_input is None and event_data:
            initial_input = json.dumps(event_data, ensure_ascii=False)

        result = await execute_chain(
            db,
            user_id,
            int(chain_id),
            initial_input or "",
            model,
            kb_id=params.get("kb_id"),
        )
        return result.get("final_output") or "技能链执行完成，但没有返回内容。"

    steps = params.get("steps", [])
    if not steps:
        raise ValueError("缺少参数: chain_id 或 steps")

    results = []
    for i, step in enumerate(steps):
        step_action = step.get("action")
        step_params = step.get("params", {})
        if not step_action:
            results.append(f"步骤 {i+1}: 跳过（无动作）")
            continue
        try:
            out = await _dispatch_action(db, user_id, step_action, step_params)
            results.append(f"步骤 {i+1} ({step_action}): 成功\n{out[:500]}")
        except Exception as exc:
            results.append(f"步骤 {i+1} ({step_action}): 失败 — {exc}")
            if step.get("stop_on_error", True):
                break

    return "\n\n---\n\n".join(results)


# ---------------------------------------------------------------------------
# Scheduler helpers
# ---------------------------------------------------------------------------

def _parse_interval_due(task: AutomationTask, now: datetime) -> bool:
    """Check if an interval-based task is due to run."""
    if not task.interval_minutes:
        return False
    if task.last_run_at is None:
        return True
    from datetime import timedelta
    next_run = task.last_run_at + timedelta(minutes=task.interval_minutes)
    return now >= next_run


def _parse_cron_due(task: AutomationTask, now: datetime) -> bool:
    """Simple cron-like check: only supports interval_minutes fallback.

    For full cron parsing, integrate a library like `croniter`.
    This implementation checks if enough time has elapsed since last run
    based on a rough minute-level granularity.
    """
    if not task.cron_expression:
        return False
    try:
        from croniter import croniter
        if task.last_run_at:
            cron = croniter(task.cron_expression, task.last_run_at)
        else:
            from datetime import timedelta
            cron = croniter(task.cron_expression, now - timedelta(days=1))
        next_time = cron.get_next(datetime)
        if next_time.tzinfo is None:
            next_time = next_time.replace(tzinfo=timezone.utc)
        return now >= next_time
    except ImportError:
        logger.warning("croniter 未安装，跳过 cron 表达式解析，使用 interval_minutes 替代")
        return _parse_interval_due(task, now)
    except Exception as exc:
        logger.warning("cron 表达式解析失败 (%s): %s", task.cron_expression, exc)
        return False


async def check_scheduled_tasks(db: AsyncSession) -> int:
    """Check for scheduled tasks that are due and execute them.

    Returns count of tasks executed.
    """
    now = datetime.now(timezone.utc)

    from sqlalchemy import or_
    result = await db.execute(
        select(AutomationTask).where(
            AutomationTask.task_type == "scheduled",
            AutomationTask.is_active == True,
            or_(AutomationTask.last_status.is_(None), AutomationTask.last_status != "running"),
        )
    )
    tasks = result.scalars().all()
    executed = 0

    for task in tasks:
        is_due = False
        if task.interval_minutes:
            is_due = _parse_interval_due(task, now)
        elif task.cron_expression:
            is_due = _parse_cron_due(task, now)

        if not is_due:
            continue

        try:
            await execute_task(db, task.id, triggered_by="schedule")
            executed += 1
        except Exception:
            logger.exception("定时任务执行异常 (task_id=%s)", task.id)

    return executed


async def trigger_event_tasks(
    db: AsyncSession,
    event_name: str,
    event_data: dict,
) -> int:
    """Trigger all active tasks matching the given event.

    Returns count of tasks triggered.
    """
    result = await db.execute(
        select(AutomationTask).where(
            AutomationTask.task_type == "event",
            AutomationTask.event_trigger == event_name,
            AutomationTask.is_active == True,
        )
    )
    tasks = result.scalars().all()
    triggered = 0

    for task in tasks:
        try:
            await execute_task(db, task.id, triggered_by="event", event_data=event_data)
            triggered += 1
        except Exception:
            logger.exception("事件触发任务执行异常 (task_id=%s, event=%s)", task.id, event_name)

    return triggered


async def fire_event(event_name: str, event_data: dict | None = None) -> None:
    """Fire an event asynchronously — safe to call from anywhere.

    Opens its own DB session so callers don't need to pass one.
    """
    try:
        from app.database import async_session
        async with async_session() as db:
            count = await trigger_event_tasks(db, event_name, event_data or {})
            if count:
                logger.info("事件 '%s' 触发了 %d 个自动化任务", event_name, count)
    except Exception:
        logger.exception("事件触发失败: %s", event_name)


# ---------------------------------------------------------------------------
# Scheduler loop (to be called from lifespan)
# ---------------------------------------------------------------------------

async def run_automation_scheduler_loop() -> None:
    """Infinite loop that checks for due scheduled tasks every 60 seconds."""
    import asyncio
    from app.database import async_session

    INTERVAL_SECONDS = 60

    while True:
        try:
            async with async_session() as db:
                count = await check_scheduled_tasks(db)
                if count:
                    logger.info("本轮执行了 %d 个定时自动化任务", count)
        except Exception:
            logger.exception("自动化任务调度循环异常")

        await asyncio.sleep(INTERVAL_SECONDS)
