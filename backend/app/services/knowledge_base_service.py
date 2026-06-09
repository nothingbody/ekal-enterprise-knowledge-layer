from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func

from app.models.document import Document, DocumentChunk, DocumentStatus
from app.models.knowledge_base import KnowledgeBase


async def refresh_kb_counts(db: AsyncSession, kb_id: int):
    doc_count = (await db.execute(
        select(func.count(Document.id)).where(
            Document.kb_id == kb_id,
            Document.status == DocumentStatus.COMPLETED,
            Document.deleted_at.is_(None),
        )
    )).scalar() or 0

    chunk_count = (await db.execute(
        select(func.count(DocumentChunk.id))
        .select_from(DocumentChunk)
        .join(Document, Document.id == DocumentChunk.doc_id)
        .where(
            DocumentChunk.kb_id == kb_id,
            Document.status == DocumentStatus.COMPLETED,
            Document.deleted_at.is_(None),
        )
    )).scalar() or 0

    await db.execute(
        update(KnowledgeBase)
        .where(KnowledgeBase.id == kb_id)
        .values(doc_count=doc_count, chunk_count=chunk_count)
    )
    await db.commit()
