from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.database import get_db
from app.models.database_source import DatabaseSource
from app.models.model_config import ModelConfig, ModelType
from app.models.user import User
from app.schemas.database_source import (
    CreateKbWithDatabaseRequest,
    DatabaseSourceCreate,
    DatabaseSourceResponse,
    DatabaseSourceTableResponse,
    DatabaseSourceTestRequest,
    DatabaseSourceUpdate,
    DatabaseServerConnectRequest,
)
from app.services.access_service import require_kb_access
from app.services.database_source_service import (
    create_database_source,
    delete_database_source_record,
    get_database_source,
    list_database_source_tables,
    list_database_sources,
    list_sync_runs,
    list_server_databases,
    serialize_database_source,
    test_database_source_connection,
    update_database_source_record,
)
from app.tasks.database_source_tasks import sync_database_source_task
from app.core.task_runner import dispatch as dispatch_task

router = APIRouter()


async def _get_source_with_access(
    db: AsyncSession,
    source_id: int,
    user_id: int,
    mode: str = "read",
) -> DatabaseSource:
    source = await get_database_source(db, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="数据库源不存在")
    await require_kb_access(db, source.kb_id, user_id, mode)
    return source


async def _resolve_embedding_model_id(
    db: AsyncSession,
    user_id: int,
    embedding_model_id: int | None,
) -> int:
    result = await db.execute(
        select(ModelConfig)
        .where(ModelConfig.user_id == user_id, ModelConfig.model_type == ModelType.EMBEDDING)
        .order_by(ModelConfig.is_default.desc(), ModelConfig.id.asc())
    )
    models = result.scalars().all()

    if not models:
        raise HTTPException(status_code=400, detail="请先配置 Embedding 模型")

    if embedding_model_id is not None:
        for model in models:
            if model.id == embedding_model_id:
                return model.id
        raise HTTPException(status_code=400, detail="Embedding 模型不存在或无权使用")

    default_model = next((model for model in models if model.is_default), None)
    return (default_model or models[0]).id


@router.get("/scan")
async def scan_local_db_sources(
    current_user: User = Depends(get_current_user),
):
    """Scan localhost for running database services and list discovered databases."""
    import asyncio
    from app.services.database_source_service import scan_local_databases
    try:
        results = await asyncio.to_thread(scan_local_databases)
        return {"databases": results}
    except Exception as exc:
        import logging as _logging
        _logging.getLogger(__name__).error("本地数据库扫描失败: %s", exc)
        raise HTTPException(status_code=500, detail="扫描本地数据库失败，请检查系统权限和网络状态")


@router.post("/list-databases")
async def list_databases_on_server(
    data: DatabaseServerConnectRequest,
    current_user: User = Depends(get_current_user),
):
    """连接数据库服务器，列出所有数据库（类似 Navicat）。"""
    import asyncio
    try:
        databases = await asyncio.to_thread(
            list_server_databases,
            db_type=data.db_type,
            host=data.host,
            port=data.port,
            username=data.username,
            password=data.password,
        )
        return {"databases": databases, "message": f"发现 {len(databases)} 个数据库"}
    except Exception as exc:
        import logging as _logging
        _logging.getLogger(__name__).warning("列出数据库失败: %s", exc)
        msg = str(exc)
        if "password authentication failed" in msg or "Access denied" in msg:
            msg = "数据库认证失败，请检查用户名和密码"
        elif "could not connect" in msg or "Connection refused" in msg or "Can't connect" in msg:
            msg = "无法连接到数据库服务器，请检查主机和端口"
        elif "timeout" in msg.lower() or "timed out" in msg.lower():
            msg = "连接超时，请检查网络或数据库服务器状态"
        raise HTTPException(status_code=400, detail=msg)


@router.post("/test")
async def test_database_source(
    data: DatabaseSourceTestRequest,
    current_user: User = Depends(get_current_user),
):
    temp_source = DatabaseSource(
        db_type=data.db_type,
        host=data.host,
        port=data.port,
        database_name=data.database_name,
        schema_name=data.schema_name,
        username=data.username,
        password_encrypted=data.password,
        row_limit=data.row_limit,
    )
    try:
        return await test_database_source_connection(temp_source)
    except Exception as exc:
        import logging as _logging
        _logging.getLogger(__name__).warning("数据库连接测试失败: %s", exc)
        msg = str(exc)
        if "password authentication failed" in msg or "Access denied" in msg:
            msg = "数据库认证失败，请检查用户名和密码"
        elif "could not connect" in msg or "Connection refused" in msg or "connection to server" in msg or "Can't connect" in msg:
            msg = "无法连接到数据库服务器，请检查主机和端口"
        elif "does not exist" in msg or "Unknown database" in msg:
            msg = "数据库不存在，请检查数据库名称"
        elif "timeout" in msg.lower() or "timed out" in msg.lower():
            msg = "连接超时，请检查网络或数据库服务器状态"
        else:
            msg = "连接失败，请检查配置参数是否正确"
        raise HTTPException(status_code=400, detail=msg)


@router.post("/", response_model=DatabaseSourceResponse)
async def add_database_source(
    data: DatabaseSourceCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await require_kb_access(db, data.kb_id, current_user.id, "manage")
    try:
        return await create_database_source(db, data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/create-with-kb")
async def create_kb_with_database(
    data: CreateKbWithDatabaseRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a knowledge base and attach a database source in one step."""
    from app.models.knowledge_base import KnowledgeBase
    from app.schemas.database_source import DatabaseSourceCreate

    resolved_embedding_model_id = await _resolve_embedding_model_id(
        db,
        current_user.id,
        data.embedding_model_id,
    )

    kb = KnowledgeBase(
        user_id=current_user.id,
        name=data.kb_name.strip(),
        description=data.kb_description or "",
        embedding_model_id=resolved_embedding_model_id,
    )
    db.add(kb)
    await db.commit()
    await db.refresh(kb)

    source_data = DatabaseSourceCreate(
        kb_id=kb.id,
        name=data.source_name or data.kb_name,
        db_type=data.db_type,
        host=data.host,
        port=data.port,
        database_name=data.database_name,
        schema_name=data.schema_name,
        username=data.username,
        password=data.password,
        table_names=data.table_names,
        row_limit=data.row_limit,
    )
    try:
        source_resp = await create_database_source(db, source_data)
    except ValueError as exc:
        await db.delete(kb)
        await db.commit()
        raise HTTPException(status_code=400, detail=str(exc))

    dispatch_task(sync_database_source_task, source_resp["id"])

    return {
        "kb_id": kb.id,
        "kb_name": kb.name,
        "source": source_resp,
        "message": "知识库和数据库源已创建，同步任务已启动",
        "sync_started": True,
    }


@router.get("/", response_model=List[DatabaseSourceResponse])
async def get_all_database_sources(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all database sources across all accessible knowledge bases."""
    from app.services.access_service import list_accessible_kb_ids
    kb_ids = await list_accessible_kb_ids(db, current_user.id, "read")
    if not kb_ids:
        return []
    from sqlalchemy import select as sa_select
    result = await db.execute(
        sa_select(DatabaseSource)
        .where(DatabaseSource.kb_id.in_(kb_ids))
        .order_by(DatabaseSource.created_at.desc())
    )
    return [serialize_database_source(s) for s in result.scalars().all()]


@router.get("/kb/{kb_id}", response_model=List[DatabaseSourceResponse])
async def get_database_sources(
    kb_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await require_kb_access(db, kb_id, current_user.id, "read")
    return await list_database_sources(db, kb_id)


@router.get("/{source_id}", response_model=DatabaseSourceResponse)
async def get_database_source_detail(
    source_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    source = await _get_source_with_access(db, source_id, current_user.id, "read")
    return serialize_database_source(source)


@router.put("/{source_id}", response_model=DatabaseSourceResponse)
async def edit_database_source(
    source_id: int,
    data: DatabaseSourceUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    source = await _get_source_with_access(db, source_id, current_user.id, "manage")
    if data.kb_id and data.kb_id != source.kb_id:
        await require_kb_access(db, data.kb_id, current_user.id, "manage")
    try:
        return await update_database_source_record(db, source, data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/{source_id}")
async def remove_database_source(
    source_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    source = await _get_source_with_access(db, source_id, current_user.id, "manage")
    await delete_database_source_record(db, source)
    return {"message": "删除成功"}


@router.post("/{source_id}/test")
async def test_saved_database_source(
    source_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    source = await _get_source_with_access(db, source_id, current_user.id, "manage")
    try:
        return await test_database_source_connection(source)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/{source_id}/tables", response_model=List[DatabaseSourceTableResponse])
async def get_database_source_tables(
    source_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    source = await _get_source_with_access(db, source_id, current_user.id, "manage")
    try:
        return await list_database_source_tables(source)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/{source_id}/sync")
async def trigger_database_source_sync(
    source_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    source = await _get_source_with_access(db, source_id, current_user.id, "manage")
    if source.status and (source.status.value if hasattr(source.status, "value") else source.status) == "syncing":
        raise HTTPException(status_code=400, detail="该数据源正在同步中，请等待完成后再试")
    dispatch_task(sync_database_source_task, source.id)
    return {"message": "同步任务已启动"}


@router.get("/{source_id}/sync-runs")
async def get_sync_runs(
    source_id: int,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    source = await _get_source_with_access(db, source_id, current_user.id, "read")
    return await list_sync_runs(db, source.id, limit=min(limit, 100))
