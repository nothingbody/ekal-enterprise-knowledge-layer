import os
import json
import zipfile
import tempfile
import shutil
import re
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models.user import User
from app.models.knowledge_base import KnowledgeBase
from app.models.document import Document, DocumentChunk, DocumentStatus
from app.core.security import get_current_user
from app.config import settings
from app.services.access_service import require_kb_access
from app.tasks.document_tasks import process_document_task

router = APIRouter()


@router.post("/{kb_id}/export")
async def export_kb(
    kb_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    kb_access = await require_kb_access(db, kb_id, current_user.id, "manage")
    kb = kb_access["kb"]

    docs_result = await db.execute(select(Document).where(Document.kb_id == kb_id))
    docs = docs_result.scalars().all()

    chunks_result = await db.execute(select(DocumentChunk).where(DocumentChunk.kb_id == kb_id))
    chunks = chunks_result.scalars().all()

    tmp_dir = tempfile.mkdtemp()
    zip_path = os.path.join(tmp_dir, f"kb_{kb_id}_{kb.name}.zip")

    try:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            kb_meta = {
                "name": kb.name,
                "description": kb.description,
                "chunk_strategy": getattr(kb, 'chunk_strategy', 'fixed'),
                "chunk_size": getattr(kb, 'chunk_size', 500),
                "chunk_overlap": getattr(kb, 'chunk_overlap', 50),
                "search_mode": getattr(kb, 'search_mode', 'hybrid'),
                "welcome_message": getattr(kb, 'welcome_message', None),
                "suggested_questions": getattr(kb, 'suggested_questions', None),
                "prompt_template": getattr(kb, 'prompt_template', None),
            }
            zf.writestr("kb_meta.json", json.dumps(kb_meta, ensure_ascii=False, indent=2))

            doc_list = []
            for doc in docs:
                doc_list.append({
                    "id": doc.id,
                    "filename": doc.filename,
                    "file_type": doc.file_type,
                    "chunk_count": doc.chunk_count,
                })
                if doc.file_path and os.path.exists(doc.file_path):
                    zf.write(doc.file_path, f"files/{doc.filename}")
            zf.writestr("documents.json", json.dumps(doc_list, ensure_ascii=False, indent=2))

            chunk_list = []
            for chunk in chunks:
                chunk_list.append({
                    "doc_id": chunk.doc_id,
                    "content": chunk.content,
                    "chunk_index": chunk.chunk_index,
                })
            zf.writestr("chunks.json", json.dumps(chunk_list, ensure_ascii=False, indent=2))

        from starlette.background import BackgroundTask
        return FileResponse(
            zip_path,
            media_type="application/zip",
            filename=f"kb_{kb.name}.zip",
            background=BackgroundTask(shutil.rmtree, tmp_dir, True),
        )
    except Exception as e:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise HTTPException(500, f"导出失败: {str(e)}")


@router.post("/import")
async def import_kb(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Import a knowledge base from a previously exported ZIP file."""
    if not file.filename.endswith(".zip"):
        raise HTTPException(400, "请上传 .zip 格式的知识库导出文件")

    tmp_dir = tempfile.mkdtemp()
    zip_path = os.path.join(tmp_dir, "import.zip")
    try:
        content = await file.read()
        with open(zip_path, "wb") as f:
            f.write(content)

        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()
            if "kb_meta.json" not in names:
                raise HTTPException(400, "无效的知识库导出文件：缺少 kb_meta.json")

            # ZIP bomb protection: check total decompressed size
            _MAX_DECOMPRESSED_SIZE = 500 * 1024 * 1024  # 500 MB
            total_size = sum(info.file_size for info in zf.infolist())
            if total_size > _MAX_DECOMPRESSED_SIZE:
                raise HTTPException(400, f"导入文件解压后过大 ({total_size // 1024 // 1024}MB > 500MB)，已拒绝")

            kb_meta = json.loads(zf.read("kb_meta.json"))
            docs_data = json.loads(zf.read("documents.json")) if "documents.json" in names else []
            chunks_data = json.loads(zf.read("chunks.json")) if "chunks.json" in names else []

            # Create knowledge base
            kb = KnowledgeBase(
                user_id=current_user.id,
                name=kb_meta.get("name", "导入的知识库"),
                description=kb_meta.get("description"),
                chunk_strategy=kb_meta.get("chunk_strategy", "fixed"),
                chunk_size=kb_meta.get("chunk_size", 500),
                chunk_overlap=kb_meta.get("chunk_overlap", 50),
                search_mode=kb_meta.get("search_mode", "hybrid"),
                welcome_message=kb_meta.get("welcome_message"),
                suggested_questions=kb_meta.get("suggested_questions"),
                prompt_template=kb_meta.get("prompt_template"),
            )
            db.add(kb)
            await db.flush()

            # Save original files and create documents
            old_id_to_new = {}  # old_doc_id -> new Document
            upload_dir = os.path.join(settings.UPLOAD_DIR, str(kb.id))
            os.makedirs(upload_dir, exist_ok=True)

            # Validate ZIP entries for path traversal
            for entry in names:
                if entry.startswith('/') or '..' in entry:
                    raise HTTPException(400, "导入文件包含不安全的路径，已拒绝")

            for doc_info in docs_data:
                old_doc_id = doc_info["id"]
                raw_filename = doc_info.get("filename", "")
                # Sanitize filename: strip path separators and dangerous characters
                filename = os.path.basename(raw_filename)
                filename = re.sub(r'[<>:"|?*\\]', '_', filename)
                if not filename or filename.startswith('.'):
                    filename = f"imported_doc_{old_doc_id}"
                file_type = doc_info.get("file_type", "unknown")

                file_path = ""
                file_size = 0
                archive_path = f"files/{raw_filename}"
                if archive_path in names:
                    dest = os.path.join(upload_dir, filename)
                    # Final safety check: ensure dest is within upload_dir
                    real_dest = os.path.realpath(dest)
                    real_upload = os.path.realpath(upload_dir)
                    if not real_dest.startswith(real_upload):
                        continue
                    with open(dest, "wb") as out_f:
                        out_f.write(zf.read(archive_path))
                    file_path = dest
                    file_size = os.path.getsize(dest)

                doc = Document(
                    kb_id=kb.id,
                    filename=filename,
                    file_path=file_path,
                    file_size=file_size,
                    file_type=file_type,
                    chunk_count=doc_info.get("chunk_count", 0),
                    status=DocumentStatus.COMPLETED,
                )
                db.add(doc)
                await db.flush()
                old_id_to_new[old_doc_id] = doc

            # Create chunks
            total_chunks = 0
            for chunk_info in chunks_data:
                old_doc_id = chunk_info["doc_id"]
                new_doc = old_id_to_new.get(old_doc_id)
                if not new_doc:
                    continue
                chunk = DocumentChunk(
                    doc_id=new_doc.id,
                    kb_id=kb.id,
                    content=chunk_info["content"],
                    chunk_index=chunk_info.get("chunk_index", 0),
                )
                db.add(chunk)
                total_chunks += 1

            kb.doc_count = len(old_id_to_new)
            kb.chunk_count = total_chunks
            await db.commit()

        return {
            "message": "导入成功",
            "kb_id": kb.id,
            "kb_name": kb.name,
            "doc_count": len(old_id_to_new),
            "chunk_count": total_chunks,
            "note": "请为该知识库配置 Embedding 模型后，文档将自动进行向量化。",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"导入失败: {str(e)}")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
