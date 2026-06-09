"""Automation task API — CRUD, manual trigger, webhook trigger, logs."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from typing import Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.core.security import get_current_user
from app.services.automation_service import (
    create_task,
    update_task,
    delete_task,
    get_task,
    list_tasks,
    get_task_logs,
    get_task_by_webhook_token,
    execute_task,
)

router = APIRouter()
webhook_router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class AutomationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: Optional[str] = None
    task_type: str = Field(pattern="^(scheduled|webhook|event)$")
    cron_expression: Optional[str] = None
    interval_minutes: Optional[int] = Field(None, ge=1)
    event_trigger: Optional[str] = None
    config: dict = Field(default_factory=dict)


class AutomationUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    cron_expression: Optional[str] = None
    interval_minutes: Optional[int] = Field(None, ge=1)
    event_trigger: Optional[str] = None
    config: Optional[dict] = None
    is_active: Optional[bool] = None


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------

def _task_dict(t) -> dict:
    import json as _json
    config = t.config
    if isinstance(config, str):
        try:
            config = _json.loads(config)
        except (_json.JSONDecodeError, TypeError):
            pass
    return {
        "id": t.id,
        "user_id": t.user_id,
        "name": t.name,
        "description": t.description,
        "task_type": t.task_type,
        "cron_expression": t.cron_expression,
        "interval_minutes": t.interval_minutes,
        "webhook_token": t.webhook_token,
        "event_trigger": t.event_trigger,
        "config": config,
        "is_active": t.is_active,
        "last_run_at": t.last_run_at.isoformat() if t.last_run_at else None,
        "last_status": t.last_status,
        "last_error": t.last_error,
        "run_count": t.run_count,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
    }


def _log_dict(log) -> dict:
    return {
        "id": log.id,
        "task_id": log.task_id,
        "status": log.status,
        "output": log.output,
        "error_message": log.error_message,
        "duration_ms": log.duration_ms,
        "triggered_by": log.triggered_by,
        "created_at": log.created_at.isoformat() if log.created_at else None,
    }


# ---------------------------------------------------------------------------
# CRUD endpoints
# ---------------------------------------------------------------------------

@router.post("/")
async def create_automation(
    data: AutomationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        task = await create_task(
            db,
            current_user.id,
            name=data.name,
            description=data.description,
            task_type=data.task_type,
            config=data.config,
            cron_expression=data.cron_expression,
            interval_minutes=data.interval_minutes,
            event_trigger=data.event_trigger,
        )
        return _task_dict(task)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.get("/")
async def list_automations(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await list_tasks(db, current_user.id, page=page, page_size=page_size)
    return {
        "items": [_task_dict(t) for t in result["items"]],
        "total": result["total"],
        "page": result["page"],
        "page_size": result["page_size"],
    }


@router.get("/{task_id}")
async def get_automation(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = await get_task(db, task_id, current_user.id)
    if not task:
        raise HTTPException(404, "自动化任务不存在")
    return _task_dict(task)


@router.put("/{task_id}")
async def update_automation(
    task_id: int,
    data: AutomationUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        task = await update_task(
            db, task_id, current_user.id,
            **data.model_dump(exclude_none=True),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    if not task:
        raise HTTPException(404, "自动化任务不存在")
    return _task_dict(task)


@router.delete("/{task_id}")
async def delete_automation(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ok = await delete_task(db, task_id, current_user.id)
    if not ok:
        raise HTTPException(404, "自动化任务不存在")
    return {"ok": True}


@router.post("/{task_id}/run")
async def run_automation(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = await get_task(db, task_id, current_user.id)
    if not task:
        raise HTTPException(404, "自动化任务不存在")
    try:
        log = await execute_task(db, task_id, triggered_by="manual")
        return _log_dict(log)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.get("/{task_id}/logs")
async def get_automation_logs(
    task_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = await get_task(db, task_id, current_user.id)
    if not task:
        raise HTTPException(404, "自动化任务不存在")
    result = await get_task_logs(db, task_id, page=page, page_size=page_size)
    return {
        "items": [_log_dict(log) for log in result["items"]],
        "total": result["total"],
        "page": result["page"],
        "page_size": result["page_size"],
    }


# ---------------------------------------------------------------------------
# Webhook trigger (no auth — uses unique token)
# ---------------------------------------------------------------------------

@webhook_router.post("/webhooks/{token}")
async def trigger_webhook(
    token: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    from app.api.channels import _check_webhook_rate
    _check_webhook_rate(token)
    task = await get_task_by_webhook_token(db, token)
    if not task:
        raise HTTPException(404, "Webhook 无效或已停用")
    try:
        body: dict[str, Any] = {}
        try:
            body = await request.json()
        except Exception:
            pass
        log = await execute_task(db, task.id, triggered_by="webhook", event_data=body)
        return _log_dict(log)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
