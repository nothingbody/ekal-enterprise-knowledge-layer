import os
import shutil
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, Query, UploadFile, File
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete

from app.database import get_db
from app.models.user import User
from app.models.document import Document
from app.models.chat_history import ChatConversation, ChatMessage
from app.models.database_source import DatabaseSource
from app.models.operation_log import OperationLog
from app.core.security import get_current_user, get_admin_user
from app.config import settings
from app.services.chat_service import PUBLIC_APP_TITLE_PREFIX
from app.services.access_service import list_accessible_kb_ids

router = APIRouter()


class LanSharingUpdate(BaseModel):
    enabled: bool


def _personal_conversation_filters(user_id: int):
    return [
        ChatConversation.user_id == user_id,
        ~ChatConversation.title.like(f"{PUBLIC_APP_TITLE_PREFIX}%"),
    ]


def _personal_operation_log_filters(user_id: int):
    return [
        OperationLog.user_id == user_id,
        OperationLog.action != "public_chat",
    ]


@router.get("/lan-ip")
async def get_lan_ip(_: User = Depends(get_current_user)):
    """Return the machine's LAN IP for sharing links."""
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return {"lan_ip": ip}
    except Exception:
        return {"lan_ip": None}


def _lan_sharing_config_path() -> Path:
    return Path(os.environ.get("DESKTOP_DATA_DIR", "data")) / "lan_sharing.json"


def _read_configured_lan_sharing() -> bool:
    import json
    path = _lan_sharing_config_path()
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            return bool(data.get("enabled", settings.LAN_SHARING_DEFAULT))
    except Exception:
        pass
    return bool(settings.LAN_SHARING_DEFAULT)


def _current_lan_sharing_enabled() -> bool:
    return os.environ.get("LAN_SHARING_ENABLED", "").lower() in {"1", "true", "yes", "on"}


@router.get("/lan-sharing")
async def get_lan_sharing(_: User = Depends(get_current_user)):
    return {
        "enabled": _current_lan_sharing_enabled(),
        "configured_enabled": _read_configured_lan_sharing(),
        "requires_restart": _current_lan_sharing_enabled() != _read_configured_lan_sharing(),
    }


@router.put("/lan-sharing")
async def update_lan_sharing(data: LanSharingUpdate, _: User = Depends(get_current_user)):
    import json
    path = _lan_sharing_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"enabled": data.enabled}), encoding="utf-8")
    return {
        "enabled": _current_lan_sharing_enabled(),
        "configured_enabled": data.enabled,
        "requires_restart": _current_lan_sharing_enabled() != data.enabled,
    }


@router.get("/tunnel-info")
async def get_tunnel_info(_: User = Depends(get_current_user)):
    """Return tunnel URL and LAN IP for share link generation."""
    import socket
    lan_ip = None
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        lan_ip = s.getsockname()[0]
        s.close()
    except Exception:
        pass

    # Read tunnel URL from file (written by Electron main.js via IPC)
    tunnel_url = None
    try:
        tunnel_file = Path(os.environ.get("DESKTOP_DATA_DIR", "data")) / ".tunnel_url"
        if tunnel_file.exists():
            tunnel_url = tunnel_file.read_text().strip() or None
    except Exception:
        pass

    return {
        "tunnel_url": tunnel_url,
        "lan_ip": lan_ip,
        "lan_sharing_enabled": _current_lan_sharing_enabled(),
    }


@router.get("/readiness")
async def get_system_readiness(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Check if the system is ready for use: models configured, KB created, etc."""
    from app.models.model_config import ModelConfig, ModelType

    user_id = current_user.id
    accessible_kb_ids = await list_accessible_kb_ids(db, user_id, "read")
    personal_conversation_filters = _personal_conversation_filters(user_id)

    llm_count = (await db.execute(
        select(func.count(ModelConfig.id)).where(
            ModelConfig.user_id == user_id, ModelConfig.model_type == ModelType.LLM
        )
    )).scalar() or 0

    embedding_count = (await db.execute(
        select(func.count(ModelConfig.id)).where(
            ModelConfig.user_id == user_id, ModelConfig.model_type == ModelType.EMBEDDING
        )
    )).scalar() or 0

    kb_count = len(accessible_kb_ids)

    doc_count = 0
    if accessible_kb_ids:
        doc_count = (await db.execute(
            select(func.count(Document.id)).where(Document.kb_id.in_(accessible_kb_ids))
        )).scalar() or 0

    conv_count = (await db.execute(
        select(func.count(ChatConversation.id)).where(*personal_conversation_filters)
    )).scalar() or 0

    steps = [
        {"key": "llm", "label": "配置 LLM 模型", "done": llm_count > 0,
         "hint": "前往「模型管理」添加一个 LLM 模型（如 GPT-4o、DeepSeek）", "route": "/models"},
        {"key": "embedding", "label": "配置 Embedding 模型", "done": embedding_count > 0,
         "hint": "前往「模型管理」添加一个 Embedding 模型（如 text-embedding-3-small）", "route": "/models"},
        {"key": "kb", "label": "创建知识库", "done": kb_count > 0,
         "hint": "前往「知识库」创建你的第一个知识库", "route": "/knowledge"},
        {"key": "doc", "label": "上传文档", "done": doc_count > 0,
         "hint": "进入知识库，上传文档或连接数据库", "route": "/knowledge"},
        {"key": "chat", "label": "开始对话", "done": conv_count > 0,
         "hint": "前往「智能对话」体验 RAG 问答", "route": "/chat"},
    ]

    completed = sum(1 for s in steps if s["done"])
    return {
        "ready": completed == len(steps),
        "completed": completed,
        "total": len(steps),
        "steps": steps,
        "desktop_mode": settings.DESKTOP_MODE,
        "share_base_url": getattr(settings, "CENTRAL_SERVER_URL", "").rstrip("/") or "",
    }


@router.get("/admin-stats")
async def get_admin_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_admin_user),
):
    """Admin-only: global system statistics across all users."""
    total_users = (await db.execute(select(func.count(User.id)))).scalar() or 0
    total_conversations = (await db.execute(
        select(func.count(ChatConversation.id))
    )).scalar() or 0
    total_messages = (await db.execute(
        select(func.count(ChatMessage.id))
    )).scalar() or 0
    total_tokens = (await db.execute(
        select(func.coalesce(func.sum(ChatMessage.token_count), 0))
    )).scalar() or 0
    return {
        "total_users": total_users,
        "total_conversations": total_conversations,
        "total_messages": total_messages,
        "total_tokens": total_tokens,
    }


@router.get("/stats")
async def get_system_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user_id = current_user.id
    accessible_kb_ids = await list_accessible_kb_ids(db, user_id, "read")
    personal_conversation_filters = _personal_conversation_filters(user_id)

    kb_count = len(accessible_kb_ids)

    doc_count = 0
    db_source_count = 0
    if accessible_kb_ids:
        doc_count = (await db.execute(
            select(func.count(Document.id)).where(Document.kb_id.in_(accessible_kb_ids))
        )).scalar() or 0
        db_source_count = (await db.execute(
            select(func.count(DatabaseSource.id)).where(DatabaseSource.kb_id.in_(accessible_kb_ids))
        )).scalar() or 0

    conv_count = (await db.execute(
        select(func.count(ChatConversation.id)).where(*personal_conversation_filters)
    )).scalar() or 0

    msg_count = (await db.execute(
        select(func.count(ChatMessage.id))
        .join(ChatConversation, ChatMessage.conversation_id == ChatConversation.id)
        .where(*personal_conversation_filters)
    )).scalar() or 0

    total_tokens = (await db.execute(
        select(func.sum(ChatMessage.token_count))
        .join(ChatConversation, ChatMessage.conversation_id == ChatConversation.id)
        .where(*personal_conversation_filters)
    )).scalar() or 0

    like_count = (await db.execute(
        select(func.count(ChatMessage.id))
        .join(ChatConversation, ChatMessage.conversation_id == ChatConversation.id)
        .where(*personal_conversation_filters, ChatMessage.feedback == "like")
    )).scalar() or 0

    dislike_count = (await db.execute(
        select(func.count(ChatMessage.id))
        .join(ChatConversation, ChatMessage.conversation_id == ChatConversation.id)
        .where(*personal_conversation_filters, ChatMessage.feedback == "dislike")
    )).scalar() or 0

    return {
        "knowledge_base_count": kb_count,
        "document_count": doc_count,
        "database_source_count": db_source_count,
        "conversation_count": conv_count,
        "message_count": msg_count,
        "total_tokens": total_tokens,
        "like_count": like_count,
        "dislike_count": dislike_count,
    }


@router.get("/logs")
async def get_operation_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    action: str = None,
    resource_type: str = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    filters = _personal_operation_log_filters(current_user.id)
    if action:
        filters.append(OperationLog.action == action)
    if resource_type:
        filters.append(OperationLog.resource_type == resource_type)

    total = (await db.execute(
        select(func.count(OperationLog.id)).where(*filters)
    )).scalar() or 0

    result = await db.execute(
        select(OperationLog)
        .where(*filters)
        .order_by(OperationLog.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    logs = result.scalars().all()
    items = [{
        "id": log.id, "action": log.action,
        "resource_type": log.resource_type, "resource_id": log.resource_id,
        "detail": log.detail,
        "prompt_tokens": log.prompt_tokens, "completion_tokens": log.completion_tokens,
        "total_tokens": log.total_tokens, "latency_ms": log.latency_ms,
        "created_at": str(log.created_at),
    } for log in logs]
    return {"items": items, "total": total}


@router.get("/logs/filters")
async def get_log_filters(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    filters = _personal_operation_log_filters(current_user.id)
    actions = (await db.execute(
        select(OperationLog.action).where(*filters).distinct()
    )).scalars().all()
    resource_types = (await db.execute(
        select(OperationLog.resource_type).where(
            *filters,
            OperationLog.resource_type.isnot(None)
        ).distinct()
    )).scalars().all()
    return {"actions": sorted(actions), "resource_types": sorted(resource_types)}


@router.get("/usage-trend")
async def get_usage_trend(
    days: int = 7,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user_id = current_user.id
    start_date = datetime.now() - timedelta(days=days - 1)
    personal_conversation_filters = _personal_conversation_filters(user_id)

    date_col = func.date(ChatMessage.created_at)
    msg_result = await db.execute(
        select(
            date_col.label("date"),
            func.count(ChatMessage.id).label("count"),
            func.coalesce(func.sum(ChatMessage.token_count), 0).label("tokens"),
        )
        .join(ChatConversation, ChatMessage.conversation_id == ChatConversation.id)
        .where(*personal_conversation_filters, ChatMessage.created_at >= start_date)
        .group_by(date_col)
        .order_by(date_col)
    )
    rows = msg_result.all()
    date_map = {str(r.date): {"messages": r.count, "tokens": r.tokens} for r in rows}

    result = []
    for i in range(days):
        d = (start_date + timedelta(days=i)).strftime("%Y-%m-%d")
        entry = date_map.get(d, {"messages": 0, "tokens": 0})
        result.append({"date": d, "messages": entry["messages"], "tokens": entry["tokens"]})
    return result


@router.get("/config")
async def get_system_config(current_user: User = Depends(get_current_user)):
    return {
        "default_chunk_size": settings.DEFAULT_CHUNK_SIZE,
        "default_chunk_overlap": settings.DEFAULT_CHUNK_OVERLAP,
        "default_top_k": settings.DEFAULT_TOP_K,
        "chunk_strategies": ["fixed", "paragraph", "recursive", "heading"],
        "search_modes": ["vector", "keyword", "hybrid"],
    }


@router.delete("/logs/cleanup")
async def cleanup_old_logs(
    retention_days: int = Query(90, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_admin_user),
):
    cutoff = datetime.now() - timedelta(days=retention_days)
    result = await db.execute(
        delete(OperationLog).where(OperationLog.created_at < cutoff)
    )
    await db.commit()
    return {"deleted": result.rowcount, "retention_days": retention_days}


@router.get("/backup")
async def backup_data(current_user: User = Depends(get_admin_user)):
    """Create a ZIP backup of all application data (desktop mode only)."""
    if not settings.DESKTOP_MODE:
        from fastapi import HTTPException
        raise HTTPException(400, "备份功能仅在桌面模式下可用")

    import asyncio
    import sqlite3
    from starlette.background import BackgroundTask

    data_dir = Path(os.environ.get("DESKTOP_DATA_DIR", "data")).resolve()
    upload_dir = Path(settings.UPLOAD_DIR).resolve()

    tmp = tempfile.mkdtemp()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_base = os.path.join(tmp, f"backup_{ts}")

    def _create_backup():
        backup_dir = Path(zip_base)
        backup_dir.mkdir(parents=True, exist_ok=True)
        db_file = data_dir / "rag.db"
        if db_file.exists():
            dst = str(backup_dir / "rag.db")
            src_conn = sqlite3.connect(str(db_file))
            dst_conn = sqlite3.connect(dst)
            try:
                src_conn.backup(dst_conn)
            finally:
                dst_conn.close()
                src_conn.close()
        chroma_dir = data_dir / "chroma"
        if chroma_dir.is_dir():
            shutil.copytree(str(chroma_dir), str(backup_dir / "chroma"))
        if upload_dir.is_dir():
            shutil.copytree(str(upload_dir), str(backup_dir / "uploads"))
        return shutil.make_archive(zip_base, "zip", tmp, f"backup_{ts}")

    zip_path = await asyncio.to_thread(_create_backup)

    def _cleanup():
        shutil.rmtree(tmp, ignore_errors=True)

    return FileResponse(
        zip_path,
        media_type="application/zip",
        filename=f"RAG应用平台_备份_{ts}.zip",
        background=BackgroundTask(_cleanup),
    )


@router.post("/restore")
async def restore_data(
    file: UploadFile = File(...),
    current_user: User = Depends(get_admin_user),
):
    """Restore application data from a ZIP backup (desktop mode only).

    Replaces SQLite DB, ChromaDB data, and uploaded files with contents
    from the backup archive. The server must be restarted after restore.
    """
    if not settings.DESKTOP_MODE:
        raise HTTPException(400, "恢复功能仅在桌面模式下可用")

    import asyncio
    import zipfile

    if not file.filename or not file.filename.endswith(".zip"):
        raise HTTPException(400, "请上传 ZIP 格式的备份文件")

    data_dir = Path(os.environ.get("DESKTOP_DATA_DIR", "data")).resolve()
    upload_dir = Path(settings.UPLOAD_DIR).resolve()

    tmp = tempfile.mkdtemp()
    zip_path = os.path.join(tmp, "restore.zip")
    try:
        with open(zip_path, "wb") as f:
            content = await file.read()
            f.write(content)

        if not zipfile.is_zipfile(zip_path):
            raise HTTPException(400, "文件不是有效的 ZIP 备份")

        # Close all database connections before replacing the file
        from app.database import engine as _db_engine
        await _db_engine.dispose()

        def _do_restore():
            extract_dir = os.path.join(tmp, "extracted")
            with zipfile.ZipFile(zip_path, "r") as zf:
                for info in zf.infolist():
                    target = os.path.realpath(os.path.join(extract_dir, info.filename))
                    if not target.startswith(os.path.realpath(extract_dir)):
                        raise ValueError(f"ZIP 文件包含非法路径: {info.filename}")
                zf.extractall(extract_dir)

            backup_root = extract_dir
            entries = os.listdir(extract_dir)
            if len(entries) == 1 and os.path.isdir(os.path.join(extract_dir, entries[0])):
                backup_root = os.path.join(extract_dir, entries[0])

            restored = []

            db_src = os.path.join(backup_root, "rag.db")
            if os.path.isfile(db_src):
                data_dir.mkdir(parents=True, exist_ok=True)
                db_dst = str(data_dir / "rag.db")
                db_bak = db_dst + ".pre_restore"
                if os.path.exists(db_dst):
                    shutil.copy2(db_dst, db_bak)
                # Remove WAL/SHM files to prevent journal corruption
                for suffix in (".db-wal", ".db-shm"):
                    wal_file = db_dst.replace(".db", suffix)
                    if os.path.exists(wal_file):
                        os.remove(wal_file)
                shutil.copy2(db_src, db_dst)
                restored.append("database")

            chroma_src = os.path.join(backup_root, "chroma")
            if os.path.isdir(chroma_src):
                chroma_dst = str(data_dir / "chroma")
                if os.path.isdir(chroma_dst):
                    shutil.rmtree(chroma_dst)
                shutil.copytree(chroma_src, chroma_dst)
                restored.append("chroma")

            uploads_src = os.path.join(backup_root, "uploads")
            if os.path.isdir(uploads_src):
                upload_dst = str(upload_dir)
                if os.path.isdir(upload_dst):
                    shutil.rmtree(upload_dst)
                shutil.copytree(uploads_src, upload_dst)
                restored.append("uploads")

            return restored

        restored = await asyncio.to_thread(_do_restore)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    return {
        "message": "恢复成功，请重启应用以使更改生效",
        "restored_components": restored,
        "requires_restart": True,
    }


@router.get("/tasks/{task_id}")
async def get_task_status(task_id: str, current_user: User = Depends(get_admin_user)):
    """Celery 任务状态可能含敏感结果；仅管理员可查询任意 task_id。"""
    from app.celery_app import celery as celery_app
    result = celery_app.AsyncResult(task_id)
    response = {
        "task_id": task_id,
        "status": result.status,
        "ready": result.ready(),
    }
    if result.ready():
        if result.successful():
            response["result"] = str(result.result) if result.result else None
        else:
            response["error"] = str(result.result) if result.result else "未知错误"
    return response


@router.get("/server-logs")
async def get_server_logs(
    lines: int = Query(200, ge=1, le=5000),
    current_user: User = Depends(get_admin_user),
):
    """Read the last N lines of the application log file (desktop mode only)."""
    if not settings.DESKTOP_MODE:
        from fastapi import HTTPException
        raise HTTPException(400, "日志查看功能仅在桌面模式下可用")

    import asyncio
    from collections import deque

    data_dir = Path(os.environ.get("DESKTOP_DATA_DIR", "data"))
    log_candidates = [
        data_dir / "app.log",
        data_dir / "rag.log",
        Path("app.log"),
    ]

    log_path = None
    for candidate in log_candidates:
        if candidate.is_file():
            log_path = candidate
            break

    if not log_path:
        return {"lines": [], "file": None, "message": "未找到日志文件"}

    def _read_tail():
        tail = deque(maxlen=lines)
        try:
            with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    tail.append(line.rstrip("\n"))
        except Exception:
            return []
        return list(tail)

    content = await asyncio.to_thread(_read_tail)
    return {
        "lines": content,
        "file": str(log_path),
        "total_lines": len(content),
    }


@router.get("/cloud-status")
async def get_cloud_status(current_user: User = Depends(get_current_user)):
    """Return the cloud connection status and central server info."""
    from app.cloud.client import is_cloud_enabled
    from app.cloud.sync import get_cloud_token, get_device_id

    if not is_cloud_enabled():
        return {"enabled": False, "server_url": None, "connected": False, "device_id": None}

    server_url = settings.CENTRAL_SERVER_URL
    token = get_cloud_token()
    connected = token is not None

    cloud_user = None
    if connected:
        try:
            from app.cloud.client import cloud_get_me
            cloud_user = await cloud_get_me(token)
        except Exception:
            connected = False

    return {
        "enabled": True,
        "server_url": server_url,
        "connected": connected,
        "device_id": get_device_id(),
        "cloud_user": cloud_user,
    }
