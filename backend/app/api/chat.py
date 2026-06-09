import json
import os
import tempfile
import shutil
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from pydantic import BaseModel, Field
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from app.database import get_db
from app.models.user import User
from app.models.chat_history import ChatMessage, ChatConversation
from app.core.security import get_current_user
from app.schemas.chat import (
    ChatRequest, ConversationResponse, ChatMessageResponse, ConversationRename,
    MessageFeedbackRequest, SearchRequest, MultiKBSearchRequest, RetrievalResult,
    BatchDeleteRequest, FeedbackResponse, UsageTrendResponse, PaginatedConversations,
)
from app.services.chat_service import (
    PUBLIC_APP_TITLE_PREFIX,
    stream_chat, list_conversations, get_conversation_messages, delete_conversation,
)
from app.services.access_service import require_kb_access
from app.services.retrieval_service import retrieve, retrieve_multi_kb

router = APIRouter()


@router.post("/completions")
async def chat_completions(
    data: ChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await require_kb_access(db, data.kb_id, current_user.id, "read")
    return StreamingResponse(
        stream_chat(db, current_user.id, data),
        media_type="text/event-stream",
    )


@router.get("/conversations", response_model=PaginatedConversations)
async def get_conversations(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await list_conversations(db, current_user.id, page, page_size)


@router.get("/conversations/search")
async def search_conversations(
    q: str = Query(..., min_length=1, max_length=200),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Full-text search across conversation messages for the current user."""
    from sqlalchemy import distinct, or_
    import re

    # Escape LIKE wildcard characters to prevent unintended pattern matching
    escaped_q = re.sub(r'([%_\\])', r'\\\1', q)
    keyword = f"%{escaped_q}%"

    # Find conversations where any message matches
    conv_ids_q = (
        select(distinct(ChatMessage.conversation_id))
        .join(ChatConversation, ChatMessage.conversation_id == ChatConversation.id)
        .where(
            ChatConversation.user_id == current_user.id,
            ~ChatConversation.title.like(f"{PUBLIC_APP_TITLE_PREFIX}%"),
            or_(
                ChatMessage.content.ilike(keyword),
                ChatConversation.title.ilike(keyword),
            ),
        )
    )

    from sqlalchemy import func
    total = (await db.execute(
        select(func.count()).select_from(conv_ids_q.subquery())
    )).scalar() or 0

    conv_ids = (await db.execute(
        conv_ids_q.order_by(ChatMessage.conversation_id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )).scalars().all()

    if not conv_ids:
        return {"items": [], "total": total}

    # Fetch conversation details
    convs = (await db.execute(
        select(ChatConversation)
        .where(ChatConversation.id.in_(conv_ids))
        .order_by(ChatConversation.created_at.desc())
    )).scalars().all()

    # Bulk-fetch all matching messages for the page's conversations in ONE query,
    # then group by conversation_id in Python (avoids N+1 pattern).
    from collections import defaultdict
    all_matching_msgs = (await db.execute(
        select(ChatMessage)
        .where(
            ChatMessage.conversation_id.in_(conv_ids),
            ChatMessage.content.ilike(keyword),
        )
        .order_by(ChatMessage.conversation_id, ChatMessage.created_at)
    )).scalars().all()

    msgs_by_conv: dict = defaultdict(list)
    for msg in all_matching_msgs:
        if len(msgs_by_conv[msg.conversation_id]) < 3:
            msgs_by_conv[msg.conversation_id].append(msg)

    items = []
    lower_q = q.lower()
    for conv in convs:
        snippets = []
        for msg in msgs_by_conv.get(conv.id, []):
            content = msg.content
            lower_content = content.lower()
            idx = lower_content.find(lower_q)
            if idx >= 0:
                start = max(0, idx - 40)
                end = min(len(content), idx + len(q) + 40)
                snippet = ("..." if start > 0 else "") + content[start:end] + ("..." if end < len(content) else "")
            else:
                snippet = content[:80] + ("..." if len(content) > 80 else "")
            snippets.append({"role": msg.role, "snippet": snippet})

        items.append({
            "id": conv.id,
            "title": conv.title,
            "kb_id": conv.kb_id,
            "created_at": str(conv.created_at),
            "matching_messages": snippets,
        })

    return {"items": items, "total": total}


@router.put("/conversations/{conversation_id}")
async def rename_conversation(
    conversation_id: int,
    data: ConversationRename,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    title = data.title.strip()
    result = await db.execute(
        select(ChatConversation).where(
            ChatConversation.id == conversation_id,
            ChatConversation.user_id == current_user.id,
            ~ChatConversation.title.like(f"{PUBLIC_APP_TITLE_PREFIX}%"),
        )
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(404, "对话不存在")
    await db.execute(
        update(ChatConversation).where(ChatConversation.id == conversation_id).values(title=title)
    )
    await db.commit()
    return {"message": "标题已更新", "title": title}


@router.patch("/conversations/{conversation_id}/pin")
async def toggle_pin(
    conversation_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Toggle pin status of a conversation."""
    result = await db.execute(
        select(ChatConversation).where(
            ChatConversation.id == conversation_id,
            ChatConversation.user_id == current_user.id,
        )
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(404, "对话不存在")
    new_pinned = not conv.is_pinned
    await db.execute(
        update(ChatConversation)
        .where(ChatConversation.id == conversation_id)
        .values(is_pinned=new_pinned)
    )
    await db.commit()
    return {"is_pinned": new_pinned}


@router.get("/conversations/{conversation_id}/messages", response_model=List[ChatMessageResponse])
async def get_messages(
    conversation_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await get_conversation_messages(db, conversation_id, current_user.id)


@router.post("/search")
async def search_knowledge(
    data: SearchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await require_kb_access(db, data.kb_id, current_user.id, "read")
    metadata: dict = {}
    results = await retrieve(db, data.kb_id, data.query, data.top_k, score_threshold=data.score_threshold, user_id=current_user.id, metadata_out=metadata)
    return {"results": results, "reranker_used": metadata.get("reranker_used", False)}


@router.post("/search/multi-kb", response_model=List[RetrievalResult])
async def search_multi_kb(
    data: MultiKBSearchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await retrieve_multi_kb(db, data.kb_ids, data.query, data.top_k, current_user.id, score_threshold=data.score_threshold)


@router.post("/messages/{message_id}/feedback", response_model=FeedbackResponse)
async def message_feedback(
    message_id: int,
    data: MessageFeedbackRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    feedback = data.feedback
    feedback_reason = data.feedback_reason

    if feedback_reason and feedback:
        from app.schemas.chat import VALID_FEEDBACK_REASONS
        valid = VALID_FEEDBACK_REASONS.get(feedback, [])
        if feedback_reason not in valid:
            raise HTTPException(400, f"无效的反馈原因，可选: {', '.join(valid)}")

    msg_result = await db.execute(
        select(ChatMessage)
        .join(ChatConversation, ChatMessage.conversation_id == ChatConversation.id)
        .where(
            ChatMessage.id == message_id,
            ChatConversation.user_id == current_user.id,
            ~ChatConversation.title.like(f"{PUBLIC_APP_TITLE_PREFIX}%"),
        )
    )
    if not msg_result.scalar_one_or_none():
        raise HTTPException(404, "消息不存在")

    values = {"feedback": feedback, "feedback_reason": feedback_reason if feedback else None}
    await db.execute(
        update(ChatMessage).where(ChatMessage.id == message_id).values(**values)
    )

    # Update linked trajectory reward if exists
    if feedback:
        try:
            from app.models.trajectory import RAGTrajectory
            traj_result = await db.execute(
                select(RAGTrajectory).where(RAGTrajectory.message_id == message_id)
            )
            traj = traj_result.scalar_one_or_none()
            if traj:
                traj.user_feedback = feedback
                traj.reward_score = 1.0 if feedback == "like" else 0.0
        except Exception as _traj_exc:
            import logging as _tlog
            _tlog.getLogger(__name__).warning("Trajectory feedback update failed (msg_id=%s): %s", message_id, _traj_exc)

    await db.commit()
    return {"message": "反馈已记录"}


@router.post("/messages/{message_id}/regenerate")
async def regenerate_message(
    message_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    msg_result = await db.execute(select(ChatMessage).where(ChatMessage.id == message_id))
    msg = msg_result.scalar_one_or_none()
    if not msg or msg.role != "assistant":
        raise HTTPException(404, "消息不存在")

    conv_result = await db.execute(
        select(ChatConversation).where(
            ChatConversation.id == msg.conversation_id,
            ChatConversation.user_id == current_user.id,
            ~ChatConversation.title.like(f"{PUBLIC_APP_TITLE_PREFIX}%"),
        )
    )
    conv = conv_result.scalar_one_or_none()
    if not conv:
        raise HTTPException(403, "无权操作")

    if conv.kb_id:
        await require_kb_access(db, conv.kb_id, current_user.id, "read")

    prev_result = await db.execute(
        select(ChatMessage).where(
            ChatMessage.conversation_id == msg.conversation_id,
            ChatMessage.role == "user",
            ChatMessage.id < msg.id,
        ).order_by(ChatMessage.id.desc()).limit(1)
    )
    prev_msg = prev_result.scalar_one_or_none()
    if not prev_msg:
        raise HTTPException(400, "找不到对应的用户消息")

    if not conv.llm_model_id:
        raise HTTPException(400, "对话未绑定 LLM 模型，无法重新生成")

    # Delete both the stale assistant message AND the preceding user message.
    # stream_chat will re-save the user message and generate a fresh assistant reply,
    # keeping the conversation history clean (no duplicate user messages).
    await db.delete(msg)
    await db.delete(prev_msg)
    await db.commit()

    chat_req = ChatRequest(
        conversation_id=conv.id,
        kb_id=conv.kb_id,
        llm_model_id=conv.llm_model_id,
        question=prev_msg.content,
    )
    return StreamingResponse(
        stream_chat(db, current_user.id, chat_req),
        media_type="text/event-stream",
    )


class EditMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=10000)


@router.put("/messages/{message_id}/edit")
async def edit_message(
    message_id: int,
    data: EditMessageRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Edit a user message and regenerate all subsequent responses.

    Deletes the edited message and ALL messages after it, then streams
    a new response using the edited content.
    """
    msg_result = await db.execute(select(ChatMessage).where(ChatMessage.id == message_id))
    msg = msg_result.scalar_one_or_none()
    if not msg or msg.role != "user":
        raise HTTPException(404, "用户消息不存在")

    conv_result = await db.execute(
        select(ChatConversation).where(
            ChatConversation.id == msg.conversation_id,
            ChatConversation.user_id == current_user.id,
        )
    )
    conv = conv_result.scalar_one_or_none()
    if not conv:
        raise HTTPException(403, "无权操作")

    if conv.kb_id:
        await require_kb_access(db, conv.kb_id, current_user.id, "read")

    if not conv.llm_model_id:
        raise HTTPException(400, "对话未绑定 LLM 模型，无法重新生成")

    # Delete edited message and ALL subsequent messages
    from sqlalchemy import delete as sa_delete
    await db.execute(
        sa_delete(ChatMessage).where(
            ChatMessage.conversation_id == msg.conversation_id,
            ChatMessage.id >= msg.id,
        )
    )
    await db.commit()

    chat_req = ChatRequest(
        conversation_id=conv.id,
        kb_id=conv.kb_id,
        llm_model_id=conv.llm_model_id,
        question=data.content.strip(),
    )
    return StreamingResponse(
        stream_chat(db, current_user.id, chat_req),
        media_type="text/event-stream",
    )


# 撤回时限：2 分钟（类似 QQ）
RECALL_MAX_SECONDS = 120


@router.post("/messages/{message_id}/recall")
async def recall_message(
    message_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """撤回用户消息（2 分钟内），并删除紧随其后的助手回复。返回原内容供重新编辑。"""
    msg_result = await db.execute(
        select(ChatMessage)
        .join(ChatConversation, ChatMessage.conversation_id == ChatConversation.id)
        .where(
            ChatMessage.id == message_id,
            ChatMessage.role == "user",
            ChatConversation.user_id == current_user.id,
            ~ChatConversation.title.like(f"{PUBLIC_APP_TITLE_PREFIX}%"),
        )
    )
    msg = msg_result.scalar_one_or_none()
    if not msg:
        raise HTTPException(404, "消息不存在或无权撤回")

    now = datetime.now(timezone.utc)
    created = msg.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    if (now - created).total_seconds() > RECALL_MAX_SECONDS:
        raise HTTPException(400, f"超过 {RECALL_MAX_SECONDS // 60} 分钟无法撤回")

    content = msg.content

    # 删除紧随其后的助手消息（若存在）
    next_result = await db.execute(
        select(ChatMessage)
        .where(
            ChatMessage.conversation_id == msg.conversation_id,
            ChatMessage.role == "assistant",
            ChatMessage.id > msg.id,
        )
        .order_by(ChatMessage.id.asc())
        .limit(1)
    )
    next_msg = next_result.scalar_one_or_none()
    if next_msg:
        await db.delete(next_msg)
    await db.delete(msg)
    await db.commit()

    return {"message": "已撤回", "content": content}


@router.post("/conversations/{conversation_id}/export")
async def export_conversation(
    conversation_id: int,
    format: str = Query("markdown", pattern="^(markdown|json)$"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    messages = await get_conversation_messages(db, conversation_id, current_user.id)
    if not messages:
        raise HTTPException(404, "对话不存在")

    if format == "json":
        items = []
        for m in messages:
            refs = None
            if m.references:
                try:
                    refs = json.loads(m.references)
                except (json.JSONDecodeError, TypeError):
                    refs = m.references
            items.append({
                "role": m.role,
                "content": m.content,
                "references": refs,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            })
        from fastapi.responses import JSONResponse
        return JSONResponse(
            content=items,
            headers={"Content-Disposition": f"attachment; filename=conversation_{conversation_id}.json"},
        )

    lines = []
    for m in messages:
        role_label = "用户" if m.role == "user" else "助手"
        timestamp = m.created_at.strftime("%Y-%m-%d %H:%M:%S") if m.created_at else ""
        lines.append(f"### {role_label}  \n*{timestamp}*\n\n{m.content}\n")
        if m.role == "assistant" and m.references:
            try:
                refs = json.loads(m.references)
                if isinstance(refs, list) and refs:
                    lines.append("**引用来源：**\n")
                    for i, ref in enumerate(refs, 1):
                        doc_name = ref.get("doc_name", "未知文档")
                        chunk_idx = ref.get("chunk_index", "")
                        score = ref.get("score")
                        score_str = f" (相关度: {score:.2f})" if score is not None else ""
                        lines.append(f"- [{i}] {doc_name} 片段 {chunk_idx}{score_str}")
                    lines.append("")
            except (json.JSONDecodeError, TypeError):
                pass
    content = "\n".join(lines)

    from fastapi.responses import Response
    return Response(
        content=content,
        media_type="text/markdown",
        headers={"Content-Disposition": f"attachment; filename=conversation_{conversation_id}.md"},
    )


@router.delete("/conversations/{conversation_id}")
async def remove_conversation(
    conversation_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    success = await delete_conversation(db, conversation_id, current_user.id)
    if not success:
        raise HTTPException(status_code=404, detail="对话不存在")
    return {"message": "删除成功"}


@router.post("/conversations/batch-delete")
async def batch_delete_conversations(
    data: BatchDeleteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from sqlalchemy import delete as sa_delete

    ids = data.ids
    if not ids:
        return {"message": "已删除 0 个对话", "deleted": 0}

    # Find conversations owned by this user (exclude public app conversations)
    result = await db.execute(
        select(ChatConversation.id).where(
            ChatConversation.id.in_(ids),
            ChatConversation.user_id == current_user.id,
            ~ChatConversation.title.like(f"{PUBLIC_APP_TITLE_PREFIX}%"),
        )
    )
    valid_ids = list(result.scalars().all())
    if not valid_ids:
        return {"message": "已删除 0 个对话", "deleted": 0}

    # Bulk delete messages then conversations in two statements
    await db.execute(sa_delete(ChatMessage).where(ChatMessage.conversation_id.in_(valid_ids)))
    await db.execute(sa_delete(ChatConversation).where(ChatConversation.id.in_(valid_ids)))
    await db.commit()
    return {"message": f"已删除 {len(valid_ids)} 个对话", "deleted": len(valid_ids)}


@router.get("/usage")
async def get_usage_summary(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return token usage summary for the current user.

    Inspired by OpenClaw /usage command: surfaces inputTokens, outputTokens
    aggregated across all conversations, optionally grouped by LLM model.
    """
    from sqlalchemy import func as sa_func
    from app.models.model_config import ModelConfig

    # Total across all conversations
    totals = (
        await db.execute(
            select(
                sa_func.coalesce(sa_func.sum(ChatConversation.total_input_tokens), 0),
                sa_func.coalesce(sa_func.sum(ChatConversation.total_output_tokens), 0),
                sa_func.count(ChatConversation.id),
            ).where(
                ChatConversation.user_id == current_user.id,
                ~ChatConversation.title.like(f"{PUBLIC_APP_TITLE_PREFIX}%"),
            )
        )
    ).one()

    total_input, total_output, conv_count = totals

    # Per-model breakdown
    rows = (
        await db.execute(
            select(
                ChatConversation.llm_model_id,
                sa_func.coalesce(sa_func.sum(ChatConversation.total_input_tokens), 0).label("input_tokens"),
                sa_func.coalesce(sa_func.sum(ChatConversation.total_output_tokens), 0).label("output_tokens"),
                sa_func.count(ChatConversation.id).label("conversations"),
            )
            .where(
                ChatConversation.user_id == current_user.id,
                ~ChatConversation.title.like(f"{PUBLIC_APP_TITLE_PREFIX}%"),
            )
            .group_by(ChatConversation.llm_model_id)
        )
    ).all()

    # Enrich with model display names
    model_ids = [r.llm_model_id for r in rows if r.llm_model_id]
    model_names: dict[int, str] = {}
    if model_ids:
        model_rows = (
            await db.execute(
                select(ModelConfig.id, ModelConfig.display_name).where(
                    ModelConfig.id.in_(model_ids)
                )
            )
        ).all()
        model_names = {r.id: r.display_name for r in model_rows}

    by_model = [
        {
            "model_id": r.llm_model_id,
            "model_name": model_names.get(r.llm_model_id, "未知模型") if r.llm_model_id else "未配置",
            "input_tokens": r.input_tokens,
            "output_tokens": r.output_tokens,
            "total_tokens": r.input_tokens + r.output_tokens,
            "conversations": r.conversations,
        }
        for r in rows
    ]

    return {
        "total_input_tokens": total_input,
        "total_output_tokens": total_output,
        "total_tokens": total_input + total_output,
        "conversation_count": conv_count,
        "by_model": by_model,
    }


@router.get("/usage/trend", response_model=UsageTrendResponse)
async def get_usage_trend(
    days: int = 30,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return daily message count and token usage for the past N days."""
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import func as sa_func, cast, Date

    since = datetime.now(timezone.utc) - timedelta(days=days)

    rows = (
        await db.execute(
            select(
                cast(ChatMessage.created_at, Date).label("date"),
                sa_func.coalesce(sa_func.sum(ChatMessage.token_count), 0).label("tokens"),
                sa_func.count(ChatMessage.id).label("message_count"),
            )
            .join(ChatConversation, ChatMessage.conversation_id == ChatConversation.id)
            .where(
                ChatConversation.user_id == current_user.id,
                ChatMessage.created_at >= since,
                ChatMessage.role == "assistant",
            )
            .group_by(cast(ChatMessage.created_at, Date))
            .order_by(cast(ChatMessage.created_at, Date))
        )
    ).all()

    trend = [
        {
            "date": str(r.date),
            "tokens": r.tokens,
            "message_count": r.message_count,
        }
        for r in rows
    ]

    return {"days": days, "trend": trend}


_ALLOWED_EXTENSIONS = {
    ".pdf", ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".csv",
    ".txt", ".md", ".markdown", ".json", ".xml", ".yaml", ".yml",
    ".html", ".log", ".py", ".js", ".ts", ".java", ".c", ".cpp",
    ".go", ".rs", ".rb", ".php", ".sh", ".sql",
}


@router.post("/analyze-file")
async def analyze_uploaded_file(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """Upload a file for in-chat analysis without adding it to any knowledge base."""
    if not file.filename:
        raise HTTPException(400, "文件名不能为空")

    suffix = Path(file.filename).suffix.lower()
    if suffix not in _ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"不支持的文件格式: {suffix}")

    if file.size and file.size > 20 * 1024 * 1024:
        raise HTTPException(400, "文件大小不能超过 20MB")

    from app.config import settings
    upload_dir = Path(settings.UPLOAD_DIR) / "temp_analysis"
    upload_dir.mkdir(parents=True, exist_ok=True)

    import uuid
    safe_name = f"{uuid.uuid4().hex[:12]}_{file.filename}"
    file_path = upload_dir / safe_name
    try:
        with open(file_path, "wb") as f:
            content = await file.read()
            if len(content) > 20 * 1024 * 1024:
                raise HTTPException(400, "文件大小不能超过 20MB")
            f.write(content)

        from app.core.tools.builtin.file_analyzer import FileAnalyzerTool
        tool = FileAnalyzerTool()
        result = await tool.execute(file_path=str(file_path), task="raw")

        return {
            "file_name": file.filename,
            "file_size": len(content),
            "content": result.to_message_content() if result.success else None,
            "error": result.error if not result.success else None,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, f"文件分析失败: {str(exc)}")
    finally:
        if file_path.exists():
            file_path.unlink(missing_ok=True)


@router.post("/summarize-file")
async def summarize_uploaded_file(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload a file and get an AI-generated summary."""
    if not file.filename:
        raise HTTPException(400, "文件名不能为空")

    suffix = Path(file.filename).suffix.lower()
    if suffix not in _ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"不支持的文件格式: {suffix}")

    from app.config import settings
    upload_dir = Path(settings.UPLOAD_DIR) / "temp_analysis"
    upload_dir.mkdir(parents=True, exist_ok=True)

    import uuid
    safe_name = f"{uuid.uuid4().hex[:12]}_{file.filename}"
    file_path = upload_dir / safe_name
    try:
        with open(file_path, "wb") as f:
            content = await file.read()
            f.write(content)

        from app.core.tools.builtin.file_analyzer import FileAnalyzerTool
        tool = FileAnalyzerTool()
        result = await tool.execute(file_path=str(file_path), task="raw")

        if not result.success:
            raise HTTPException(500, result.error or "文件提取失败")

        file_text = result.to_message_content()[:12000]

        from app.services.model_service import get_default_model
        from app.core.llm_client import chat_completion
        model_config = await get_default_model(db, current_user.id, "llm")
        if not model_config:
            raise HTTPException(400, "请先配置默认 LLM 模型")

        messages = [
            {"role": "system", "content": "你是一个文档分析助手。请为用户上传的文件生成简洁的中文摘要，包含关键要点。"},
            {"role": "user", "content": f"请为以下文件内容生成摘要和要点提取：\n\n{file_text}"},
        ]
        summary = await chat_completion(model_config, messages)

        return {
            "file_name": file.filename,
            "summary": summary,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, f"文件摘要生成失败: {str(exc)}")
    finally:
        if file_path.exists():
            file_path.unlink(missing_ok=True)


@router.post("/process-file")
async def process_file_with_ai(
    file: UploadFile = File(...),
    instruction: str = Query(..., description="处理指令，如：翻译、修改格式、增加列等"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload a file (Excel/CSV/text), let AI process it per instruction, return modified file."""
    if not file.filename:
        raise HTTPException(400, "文件名不能为空")

    suffix = Path(file.filename).suffix.lower()
    if suffix not in {".xlsx", ".xls", ".csv", ".txt", ".md", ".json"}:
        raise HTTPException(400, f"文件处理目前支持 Excel/CSV/TXT/MD/JSON 格式，不支持 {suffix}")

    from app.config import settings
    upload_dir = Path(settings.UPLOAD_DIR) / "temp_analysis"
    upload_dir.mkdir(parents=True, exist_ok=True)

    import uuid
    safe_name = f"{uuid.uuid4().hex[:12]}_{file.filename}"
    file_path = upload_dir / safe_name

    try:
        with open(file_path, "wb") as f:
            raw = await file.read()
            if len(raw) > 20 * 1024 * 1024:
                raise HTTPException(400, "文件大小不能超过 20MB")
            f.write(raw)

        from app.core.tools.builtin.file_analyzer import FileAnalyzerTool
        tool = FileAnalyzerTool()
        extract_result = await tool.execute(file_path=str(file_path), task="raw")
        if not extract_result.success:
            raise HTTPException(500, extract_result.error or "文件读取失败")

        file_text = extract_result.to_message_content()[:12000]

        from app.services.model_service import get_default_model
        from app.core.llm_client import chat_completion
        model_config = await get_default_model(db, current_user.id, "llm")
        if not model_config:
            raise HTTPException(400, "请先配置默认 LLM 模型")

        if suffix in (".xlsx", ".xls", ".csv"):
            system_prompt = (
                "你是一个数据处理助手。用户会提供一个表格文件的内容和处理指令。"
                "请根据指令修改数据，输出完整的 CSV 格式结果（用逗号分隔）。"
                "只输出 CSV 数据本身，不要添加代码块标记或说明文字。"
            )
        else:
            system_prompt = (
                "你是一个文件处理助手。用户会提供文件内容和处理指令。"
                "请根据指令修改内容，输出完整的修改后结果。"
                "只输出修改后的文件内容，不要添加额外说明。"
            )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"文件内容:\n{file_text}\n\n处理指令: {instruction}"},
        ]
        processed = await chat_completion(model_config, messages)

        output_suffix = ".csv" if suffix in (".xlsx", ".xls", ".csv") else suffix
        output_name = Path(file.filename).stem + "_processed" + output_suffix

        from fastapi.responses import Response
        return Response(
            content=processed.encode("utf-8-sig") if output_suffix == ".csv" else processed.encode("utf-8"),
            media_type="application/octet-stream",
            headers={"Content-Disposition": f'attachment; filename="{output_name}"'},
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, f"文件处理失败: {str(exc)}")
    finally:
        if file_path.exists():
            file_path.unlink(missing_ok=True)
