"""MCP Server management API endpoints."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database import get_db
from app.models.user import User
from app.models.mcp_server import McpServerConfig
from app.models.workspace import WorkspaceMember
from app.core.security import get_current_user
from app.core.mcp_client import get_mcp_manager


def _require_admin_for_stdio(user: User, transport_type: str) -> None:
    """Stdio transport can spawn arbitrary processes — restrict to admins."""
    if transport_type == "stdio" and getattr(user, "role", "") != "admin":
        raise HTTPException(
            403,
            "stdio 传输类型仅限管理员使用（该类型会在服务器上执行命令）",
        )


async def _check_workspace_membership(
    db: AsyncSession, workspace_id: int, user: User
) -> None:
    """Raise 403 if *user* is not a member of the workspace."""
    if getattr(user, "role", "") == "admin":
        return
    result = await db.execute(
        select(WorkspaceMember.id).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user.id,
        )
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(403, "无权访问该工作空间的 MCP 服务器")

router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class McpServerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    transport_type: str = Field(pattern="^(stdio|http|sse)$")
    command: Optional[str] = None
    args: Optional[str] = None   # JSON array
    env: Optional[str] = None    # JSON dict
    url: Optional[str] = None
    headers: Optional[str] = None  # JSON dict
    tool_filter: Optional[str] = None
    workspace_id: Optional[int] = None


class McpServerUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    transport_type: Optional[str] = Field(None, pattern="^(stdio|http|sse)$")
    command: Optional[str] = None
    args: Optional[str] = None
    env: Optional[str] = None
    url: Optional[str] = None
    headers: Optional[str] = None
    tool_filter: Optional[str] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _config_to_dict(cfg: McpServerConfig) -> dict:
    return {
        "id": cfg.id,
        "user_id": cfg.user_id,
        "workspace_id": cfg.workspace_id,
        "name": cfg.name,
        "transport_type": cfg.transport_type,
        "command": cfg.command,
        "args": cfg.args,
        "env": cfg.env,
        "url": cfg.url,
        "headers": cfg.headers,
        "tool_filter": cfg.tool_filter,
        "is_active": cfg.is_active,
        "created_at": cfg.created_at.isoformat() if cfg.created_at else None,
        "updated_at": cfg.updated_at.isoformat() if cfg.updated_at else None,
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/")
async def list_mcp_servers(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    workspace_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if workspace_id:
        await _check_workspace_membership(db, workspace_id, current_user)
        filters = [McpServerConfig.workspace_id == workspace_id]
    else:
        filters = [McpServerConfig.user_id == current_user.id, McpServerConfig.workspace_id.is_(None)]

    total = (await db.execute(
        select(func.count(McpServerConfig.id)).where(*filters)
    )).scalar() or 0

    result = await db.execute(
        select(McpServerConfig).where(*filters)
        .order_by(McpServerConfig.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = [_config_to_dict(c) for c in result.scalars().all()]

    # Annotate connection status
    manager = get_mcp_manager()
    for item in items:
        item["connected"] = manager.is_connected(item["id"])

    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/{server_id}")
async def get_mcp_server(
    server_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cfg = await _get_config(db, current_user, server_id)
    data = _config_to_dict(cfg)
    data["connected"] = get_mcp_manager().is_connected(server_id)
    return data


@router.post("/")
async def create_mcp_server(
    data: McpServerCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_admin_for_stdio(current_user, data.transport_type)
    if data.workspace_id:
        await _check_workspace_membership(db, data.workspace_id, current_user)
    cfg = McpServerConfig(
        user_id=current_user.id,
        workspace_id=data.workspace_id,
        name=data.name,
        transport_type=data.transport_type,
        command=data.command,
        args=data.args,
        env=data.env,
        url=data.url,
        headers=data.headers,
        tool_filter=data.tool_filter,
    )
    db.add(cfg)
    await db.commit()
    await db.refresh(cfg)
    return _config_to_dict(cfg)


@router.put("/{server_id}")
async def update_mcp_server(
    server_id: int,
    data: McpServerUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cfg = await _get_config(db, current_user, server_id)
    updates = data.model_dump(exclude_none=True)
    new_transport = updates.get("transport_type", cfg.transport_type)
    _require_admin_for_stdio(current_user, new_transport)
    for key, value in updates.items():
        setattr(cfg, key, value)
    await db.commit()
    await db.refresh(cfg)

    # If connected, reconnect to pick up changes
    manager = get_mcp_manager()
    if manager.is_connected(server_id):
        await manager.disconnect(server_id)
        if cfg.is_active:
            await manager.connect(cfg)

    return _config_to_dict(cfg)


@router.delete("/{server_id}")
async def delete_mcp_server(
    server_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cfg = await _get_config(db, current_user, server_id)
    await get_mcp_manager().disconnect(server_id)
    await db.delete(cfg)
    await db.commit()
    return {"ok": True}


@router.post("/{server_id}/toggle")
async def toggle_mcp_server(
    server_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cfg = await _get_config(db, current_user, server_id)
    cfg.is_active = not cfg.is_active
    await db.commit()
    await db.refresh(cfg)

    manager = get_mcp_manager()
    if cfg.is_active:
        try:
            await manager.connect(cfg)
        except Exception as exc:
            logging.getLogger(__name__).error("MCP 连接失败 [%s]: %s", cfg.name, exc, exc_info=True)
            raise HTTPException(502, "连接 MCP 服务器失败，请检查配置")
    else:
        await manager.disconnect(server_id)

    data = _config_to_dict(cfg)
    data["connected"] = manager.is_connected(server_id)
    return data


@router.get("/{server_id}/tools")
async def list_mcp_server_tools(
    server_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cfg = await _get_config(db, current_user, server_id)
    manager = get_mcp_manager()
    if not manager.is_connected(server_id):
        if not cfg.is_active:
            raise HTTPException(400, "MCP 服务器未启用")
        try:
            await manager.connect(cfg)
        except Exception as exc:
            logging.getLogger(__name__).error("MCP 连接失败 [%s]: %s", cfg.name, exc, exc_info=True)
            raise HTTPException(502, "连接 MCP 服务器失败，请检查配置")

    tools = await manager.list_tools(server_id)
    return {
        "server_id": server_id,
        "server_name": cfg.name,
        "tools": [
            {"name": t.name, "description": t.description, "input_schema": t.input_schema}
            for t in tools
        ],
    }


@router.post("/{server_id}/test")
async def test_mcp_server(
    server_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cfg = await _get_config(db, current_user, server_id)
    manager = get_mcp_manager()
    try:
        result = await manager.test_connection(cfg)
    except Exception as exc:
        logging.getLogger(__name__).error("MCP 连接测试失败 [%s]: %s", cfg.name, exc, exc_info=True)
        raise HTTPException(502, "MCP 连接测试失败，请检查服务器配置")
    return result


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------

async def _get_config(
    db: AsyncSession, user: User, server_id: int
) -> McpServerConfig:
    result = await db.execute(
        select(McpServerConfig).where(McpServerConfig.id == server_id)
    )
    cfg = result.scalar_one_or_none()
    if not cfg:
        raise HTTPException(404, "MCP 服务器不存在")

    if cfg.workspace_id:
        await _check_workspace_membership(db, cfg.workspace_id, user)
    elif cfg.user_id != user.id:
        raise HTTPException(404, "MCP 服务器不存在")

    return cfg
