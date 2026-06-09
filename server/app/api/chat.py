import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database import get_db
from app.core.utils import escape_like
from app.models.user import User
from app.models.chat import ChatConversation, ChatMessage
from app.schemas import (
    ConversationCreate, ConversationResponse, ConversationUpdate,
    MessageCreate, MessageResponse, MessageFeedback, PaginatedResponse,
)
from app.core.security import get_current_user

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/conversations/search", response_model=PaginatedResponse)
async def search_conversations(
    q: str = Query("", min_length=1),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    filters = [
        ChatConversation.user_id == current_user.id,
        ChatConversation.deleted_at.is_(None),
        ChatConversation.title.ilike(f"%{escape_like(q)}%"),
    ]
    total = (await db.execute(select(func.count(ChatConversation.id)).where(*filters))).scalar() or 0
    result = await db.execute(
        select(ChatConversation).where(*filters)
        .order_by(ChatConversation.updated_at.desc())
        .offset((page - 1) * page_size).limit(page_size)
    )
    items = [ConversationResponse.model_validate(c).model_dump() for c in result.scalars().all()]
    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size)


class BatchDeleteRequest(BaseModel):
    ids: list[int] = Field(min_length=1)


@router.post("/conversations/batch-delete")
async def batch_delete_conversations(
    data: BatchDeleteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ids = data.ids
    from datetime import datetime, timezone
    from sqlalchemy import update
    now = datetime.now(timezone.utc)
    result = await db.execute(
        update(ChatConversation)
        .where(
            ChatConversation.id.in_(ids),
            ChatConversation.user_id == current_user.id,
            ChatConversation.deleted_at.is_(None),
        )
        .values(deleted_at=now)
    )
    await db.commit()
    return {"deleted": result.rowcount, "total": len(ids)}


@router.get("/conversations", response_model=PaginatedResponse)
async def list_conversations(
    workspace_id: Optional[int] = None,
    kb_id: Optional[int] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    filters = [ChatConversation.user_id == current_user.id, ChatConversation.deleted_at.is_(None)]
    if workspace_id:
        filters.append(ChatConversation.workspace_id == workspace_id)
    if kb_id:
        filters.append(ChatConversation.kb_id == kb_id)

    total = (await db.execute(select(func.count(ChatConversation.id)).where(*filters))).scalar() or 0
    result = await db.execute(
        select(ChatConversation).where(*filters)
        .order_by(ChatConversation.updated_at.desc())
        .offset((page - 1) * page_size).limit(page_size)
    )
    items = [ConversationResponse.model_validate(c).model_dump() for c in result.scalars().all()]
    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size)


@router.post("/conversations", response_model=ConversationResponse)
async def create_conversation(
    data: ConversationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conv = ChatConversation(
        user_id=current_user.id,
        workspace_id=data.workspace_id,
        kb_id=data.kb_id,
        title=data.title or "新对话",
        llm_model=data.llm_model,
    )
    db.add(conv)
    await db.commit()
    await db.refresh(conv)
    return ConversationResponse.model_validate(conv)


@router.get("/conversations/{conv_id}", response_model=ConversationResponse)
async def get_conversation(
    conv_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conv = (await db.execute(
        select(ChatConversation).where(
            ChatConversation.id == conv_id,
            ChatConversation.user_id == current_user.id,
            ChatConversation.deleted_at.is_(None),
        )
    )).scalar_one_or_none()
    if not conv:
        raise HTTPException(404, "对话不存在")
    return ConversationResponse.model_validate(conv)


@router.put("/conversations/{conv_id}", response_model=ConversationResponse)
async def update_conversation(
    conv_id: int,
    data: ConversationUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conv = (await db.execute(
        select(ChatConversation).where(
            ChatConversation.id == conv_id,
            ChatConversation.user_id == current_user.id,
            ChatConversation.deleted_at.is_(None),
        )
    )).scalar_one_or_none()
    if not conv:
        raise HTTPException(404, "对话不存在")
    if data.title is not None:
        conv.title = data.title
    await db.commit()
    await db.refresh(conv)
    return ConversationResponse.model_validate(conv)


@router.delete("/conversations/{conv_id}")
async def delete_conversation(
    conv_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conv = (await db.execute(
        select(ChatConversation).where(
            ChatConversation.id == conv_id,
            ChatConversation.user_id == current_user.id,
            ChatConversation.deleted_at.is_(None),
        )
    )).scalar_one_or_none()
    if not conv:
        raise HTTPException(404, "对话不存在")
    from datetime import datetime, timezone
    conv.deleted_at = datetime.now(timezone.utc)
    await db.commit()
    return {"message": "对话已删除"}


@router.get("/conversations/{conv_id}/messages")
async def list_messages(
    conv_id: int,
    limit: int = Query(50, ge=1, le=200),
    before_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conv = (await db.execute(
        select(ChatConversation).where(
            ChatConversation.id == conv_id,
            ChatConversation.user_id == current_user.id,
            ChatConversation.deleted_at.is_(None),
        )
    )).scalar_one_or_none()
    if not conv:
        raise HTTPException(404, "对话不存在")

    filters = [ChatMessage.conversation_id == conv_id]
    if before_id:
        filters.append(ChatMessage.id < before_id)

    result = await db.execute(
        select(ChatMessage).where(*filters)
        .order_by(ChatMessage.id.desc())
        .limit(limit)
    )
    messages = list(reversed(result.scalars().all()))
    return [MessageResponse.model_validate(m).model_dump() for m in messages]


@router.post("/conversations/{conv_id}/messages", response_model=MessageResponse)
async def send_message(
    conv_id: int,
    data: MessageCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conv = (await db.execute(
        select(ChatConversation).where(
            ChatConversation.id == conv_id,
            ChatConversation.user_id == current_user.id,
            ChatConversation.deleted_at.is_(None),
        )
    )).scalar_one_or_none()
    if not conv:
        raise HTTPException(404, "对话不存在")

    user_msg = ChatMessage(
        conversation_id=conv_id,
        role="user",
        content=data.content,
    )
    db.add(user_msg)
    await db.commit()
    await db.refresh(user_msg)
    return MessageResponse.model_validate(user_msg)


@router.post("/messages/{message_id}/feedback")
async def message_feedback(
    message_id: int,
    data: MessageFeedback,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    msg = (await db.execute(select(ChatMessage).where(ChatMessage.id == message_id))).scalar_one_or_none()
    if not msg:
        raise HTTPException(404, "消息不存在")
    conv = (await db.execute(
        select(ChatConversation).where(
            ChatConversation.id == msg.conversation_id,
            ChatConversation.user_id == current_user.id,
        )
    )).scalar_one_or_none()
    if not conv:
        raise HTTPException(403, "无权操作此消息")
    msg.feedback = data.feedback
    await db.commit()
    return {"message": "反馈已记录"}


@router.post("/conversations/{conv_id}/chat")
async def chat_with_llm(
    conv_id: int,
    data: MessageCreate,
    stream: bool = Query(False),
    model_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not model_id:
        raise HTTPException(400, "请指定 model_id 参数")

    conv = (await db.execute(
        select(ChatConversation).where(
            ChatConversation.id == conv_id,
            ChatConversation.user_id == current_user.id,
            ChatConversation.deleted_at.is_(None),
        )
    )).scalar_one_or_none()
    if not conv:
        raise HTTPException(404, "对话不存在")

    user_msg = ChatMessage(
        conversation_id=conv_id,
        role="user",
        content=data.content,
    )
    db.add(user_msg)
    await db.flush()

    history = (await db.execute(
        select(ChatMessage).where(ChatMessage.conversation_id == conv_id)
        .order_by(ChatMessage.id.asc())
    )).scalars().all()

    messages = [{"role": m.role, "content": m.content} for m in history]

    from app.services.llm_gateway import chat_completion, chat_completion_stream

    try:
        if stream:
            await db.commit()

            async def stream_and_save():
                full_content = ""
                async for chunk_line in chat_completion_stream(db, model_id, messages):
                    yield chunk_line
                    if chunk_line.startswith("data: ") and chunk_line.strip() != "data: [DONE]":
                        import json
                        try:
                            c = json.loads(chunk_line[6:])
                            delta = c.get("choices", [{}])[0].get("delta", {}).get("content", "")
                            full_content += delta
                        except (json.JSONDecodeError, IndexError, KeyError):
                            pass

                if full_content:
                    from app.database import async_session
                    async with async_session() as save_db:
                        save_db.add(ChatMessage(
                            conversation_id=conv_id,
                            role="assistant",
                            content=full_content,
                        ))
                        await save_db.commit()

            return StreamingResponse(stream_and_save(), media_type="text/event-stream")

        result = await chat_completion(db, model_id, messages)
        content = result.get("choices", [{}])[0].get("message", {}).get("content", "")

        assistant_msg = ChatMessage(
            conversation_id=conv_id,
            role="assistant",
            content=content,
            token_count=result.get("usage", {}).get("total_tokens", 0),
        )
        db.add(assistant_msg)

        usage = result.get("usage", {})
        conv.total_input_tokens += usage.get("prompt_tokens", 0)
        conv.total_output_tokens += usage.get("completion_tokens", 0)
        await db.commit()
        await db.refresh(assistant_msg)

        return MessageResponse.model_validate(assistant_msg)

    except ValueError as exc:
        await db.commit()
        raise HTTPException(400, str(exc))
    except Exception as exc:
        await db.commit()
        logger.error("Chat error: %s", exc)
        raise HTTPException(502, f"LLM 调用失败: {exc}")
