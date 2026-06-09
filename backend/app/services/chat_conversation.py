"""Conversation CRUD and chat history retrieval."""
from typing import List

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func as sa_func

from app.models.chat_history import ChatConversation, ChatMessage
from app.schemas.chat import ChatRequest, ConversationResponse, ChatMessageResponse
from app.services.chat_constants import PUBLIC_APP_TITLE_PREFIX
from app.services.chat_helpers import (
    is_public_chat_request, build_public_app_title, is_public_app_title,
)


async def get_or_create_conversation(
    db: AsyncSession,
    user_id: int,
    chat_req: ChatRequest,
) -> ChatConversation:
    if chat_req.conversation_id:
        where_conditions = [
            ChatConversation.id == chat_req.conversation_id,
            ChatConversation.user_id == user_id,
        ]
        if chat_req.published_app_id and chat_req.visitor_id:
            where_conditions.extend([
                ChatConversation.kb_id == chat_req.kb_id,
                ChatConversation.title.like(f"{PUBLIC_APP_TITLE_PREFIX}{chat_req.published_app_id}:{chat_req.visitor_id}]%"),
            ])
        result = await db.execute(
            select(ChatConversation).where(*where_conditions)
        )
        conv = result.scalar_one_or_none()
        if conv:
            return conv

    title = chat_req.question[:50]
    if is_public_chat_request(chat_req):
        title = build_public_app_title(chat_req)

    conv = ChatConversation(
        user_id=user_id,
        kb_id=chat_req.kb_id,
        title=title,
        llm_model_id=chat_req.llm_model_id,
    )
    db.add(conv)
    await db.commit()
    await db.refresh(conv)
    return conv


async def get_chat_history(db: AsyncSession, conversation_id: int, limit: int = 10) -> list:
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.conversation_id == conversation_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(limit)
    )
    messages = list(reversed(result.scalars().all()))
    return [{"role": m.role, "content": m.content} for m in messages]


async def list_conversations(
    db: AsyncSession, user_id: int, page: int = 1, page_size: int = 50
) -> dict:
    base_filter = [
        ChatConversation.user_id == user_id,
        ~ChatConversation.title.like(f"{PUBLIC_APP_TITLE_PREFIX}%"),
    ]

    total = (await db.execute(
        select(sa_func.count(ChatConversation.id)).where(*base_filter)
    )).scalar() or 0

    result = await db.execute(
        select(ChatConversation)
        .where(*base_filter)
        .order_by(ChatConversation.is_pinned.desc(), ChatConversation.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = [ConversationResponse.model_validate(c) for c in result.scalars().all()]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


async def get_conversation_messages(
    db: AsyncSession, conversation_id: int, user_id: int
) -> List[ChatMessageResponse]:
    conv_result = await db.execute(
        select(ChatConversation).where(
            ChatConversation.id == conversation_id,
            ChatConversation.user_id == user_id,
        )
    )
    conv = conv_result.scalar_one_or_none()
    if not conv or is_public_app_title(conv.title):
        return []

    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.conversation_id == conversation_id)
        .order_by(ChatMessage.created_at.asc())
    )
    return [ChatMessageResponse.model_validate(m) for m in result.scalars().all()]


async def delete_conversation(db: AsyncSession, conversation_id: int, user_id: int) -> bool:
    result = await db.execute(
        select(ChatConversation).where(
            ChatConversation.id == conversation_id,
            ChatConversation.user_id == user_id,
        )
    )
    conv = result.scalar_one_or_none()
    if not conv or is_public_app_title(conv.title):
        return False

    await db.execute(delete(ChatMessage).where(ChatMessage.conversation_id == conversation_id))
    await db.delete(conv)
    await db.commit()
    return True
