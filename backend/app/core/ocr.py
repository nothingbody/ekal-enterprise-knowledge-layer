"""LLM multimodal OCR — use vision-capable LLMs to extract text from images and scanned PDFs.

Supports:
- Direct image files (PNG, JPG, JPEG, TIFF, BMP, WEBP)
- Scanned / image-only PDFs (rendered page-by-page via PyMuPDF)
- Embedded images inside DOCX / PPTX documents
- OpenAI-compatible vision API (base64 data URI in image_url)
- Anthropic native image content blocks
"""
import base64
import logging
import mimetypes
from pathlib import Path
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.model_config import ModelConfig, ModelType

logger = logging.getLogger(__name__)

# Supported image extensions for OCR
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".webp"}

# Mapping from extension to MIME type for base64 data URIs
_EXT_MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".tiff": "image/tiff",
    ".tif": "image/tiff",
    ".bmp": "image/bmp",
    ".webp": "image/webp",
}

OCR_SYSTEM_PROMPT = (
    "你是一个专业的 OCR 文字识别助手。请仔细识别图片中的所有文字内容，"
    "包括标题、正文、表格、列表等。保持原始的段落结构和格式。"
    "只输出识别到的文字内容，不要添加任何解释或评论。"
    "如果图片中没有文字，请回复\"[无文字内容]\"。"
)


def _encode_image_base64(file_path: str) -> tuple[str, str]:
    """Read an image file and return (base64_data, mime_type)."""
    path = Path(file_path)
    ext = path.suffix.lower()
    mime = _EXT_MIME.get(ext) or mimetypes.guess_type(file_path)[0] or "image/png"
    with open(file_path, "rb") as f:
        data = base64.b64encode(f.read()).decode("utf-8")
    return data, mime


def _encode_bytes_base64(image_bytes: bytes, mime: str = "image/png") -> str:
    """Encode raw image bytes to base64."""
    return base64.b64encode(image_bytes).decode("utf-8")


def _is_anthropic(model_config: ModelConfig) -> bool:
    provider = model_config.provider
    if hasattr(provider, "value"):
        provider = provider.value
    return str(provider).lower() == "anthropic"


def _build_vision_messages_openai(b64_data: str, mime: str) -> list[dict]:
    """Build OpenAI-compatible vision messages with base64 data URI.

    Compatible with OpenAI, 通义千问 (DashScope), 智谱 GLM-4V,
    月之暗面 Kimi, Ollama (llava/minicpm-v), and other providers
    that accept the standard OpenAI vision format.
    """
    return [
        {"role": "system", "content": OCR_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{mime};base64,{b64_data}",
                    },
                },
                {"type": "text", "text": "请识别并提取这张图片中的所有文字内容。"},
            ],
        },
    ]


def _build_vision_messages_anthropic(b64_data: str, mime: str) -> list[dict]:
    """Build Anthropic-native vision messages."""
    return [
        {
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": mime,
                        "data": b64_data,
                    },
                },
                {"type": "text", "text": "请识别并提取这张图片中的所有文字内容。"},
            ],
        },
    ]


async def get_ocr_model(db: AsyncSession, user_id: int) -> Optional[ModelConfig]:
    """Find the best LLM model for OCR.

    Priority:
    1. Global OCR_MODEL_ID from settings (if non-zero)
    2. User's default LLM model (is_default=True)
    3. Any LLM model owned by the user
    """
    # 1. Global override
    if settings.OCR_MODEL_ID:
        result = await db.execute(
            select(ModelConfig).where(ModelConfig.id == settings.OCR_MODEL_ID)
        )
        model = result.scalar_one_or_none()
        if model:
            return model

    # 2. User's default LLM
    result = await db.execute(
        select(ModelConfig).where(
            ModelConfig.user_id == user_id,
            ModelConfig.model_type == ModelType.LLM,
            ModelConfig.is_default == True,  # noqa: E712
        )
    )
    model = result.scalar_one_or_none()
    if model:
        return model

    # 3. Any user LLM
    result = await db.execute(
        select(ModelConfig)
        .where(
            ModelConfig.user_id == user_id,
            ModelConfig.model_type == ModelType.LLM,
        )
        .limit(1)
    )
    return result.scalar_one_or_none()


async def ocr_image(file_path: str, model_config: ModelConfig) -> str:
    """Extract text from a single image file using LLM vision.

    Args:
        file_path: Path to the image file.
        model_config: An LLM ModelConfig with vision capability.

    Returns:
        Extracted text content.
    """
    from app.core.llm_client import chat_completion

    b64_data, mime = _encode_image_base64(file_path)

    if _is_anthropic(model_config):
        messages = _build_vision_messages_anthropic(b64_data, mime)
        # Prepend system prompt as a system message for Anthropic
        messages.insert(0, {"role": "system", "content": OCR_SYSTEM_PROMPT})
    else:
        messages = _build_vision_messages_openai(b64_data, mime)

    result = await chat_completion(model_config, messages, stream=False)
    text = result if isinstance(result, str) else ""
    logger.info("OCR 完成: %s → %d 字符", Path(file_path).name, len(text))
    return text


async def _ocr_image_bytes(image_bytes: bytes, mime: str, model_config: ModelConfig, page_label: str = "") -> str:
    """Extract text from raw image bytes using LLM vision."""
    from app.core.llm_client import chat_completion

    b64_data = _encode_bytes_base64(image_bytes, mime)

    if _is_anthropic(model_config):
        messages = _build_vision_messages_anthropic(b64_data, mime)
        messages.insert(0, {"role": "system", "content": OCR_SYSTEM_PROMPT})
    else:
        messages = _build_vision_messages_openai(b64_data, mime)

    result = await chat_completion(model_config, messages, stream=False)
    text = result if isinstance(result, str) else ""
    if page_label:
        logger.debug("OCR 页面 %s → %d 字符", page_label, len(text))
    return text


def extract_docx_images(file_path: str) -> list[tuple[bytes, str]]:
    """Extract embedded images from a DOCX file.

    DOCX files are ZIP archives; images live under ``word/media/``.

    Returns:
        List of (image_bytes, mime_type) tuples.
    """
    import zipfile

    images: list[tuple[bytes, str]] = []
    _SUPPORTED_IMG_EXTS = {".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".webp", ".gif"}

    try:
        with zipfile.ZipFile(file_path, "r") as zf:
            for name in zf.namelist():
                if not name.startswith("word/media/"):
                    continue
                ext = Path(name).suffix.lower()
                if ext not in _SUPPORTED_IMG_EXTS:
                    continue
                mime = _EXT_MIME.get(ext, "image/png")
                images.append((zf.read(name), mime))
    except Exception as exc:
        logger.warning("DOCX 图片提取失败 (%s): %s", Path(file_path).name, exc)

    return images


def extract_pptx_images(file_path: str) -> list[tuple[bytes, str]]:
    """Extract embedded images from a PPTX file.

    PPTX files are ZIP archives; images live under ``ppt/media/``.
    """
    import zipfile

    images: list[tuple[bytes, str]] = []
    _SUPPORTED_IMG_EXTS = {".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".webp", ".gif"}

    try:
        with zipfile.ZipFile(file_path, "r") as zf:
            for name in zf.namelist():
                if not name.startswith("ppt/media/"):
                    continue
                ext = Path(name).suffix.lower()
                if ext not in _SUPPORTED_IMG_EXTS:
                    continue
                mime = _EXT_MIME.get(ext, "image/png")
                images.append((zf.read(name), mime))
    except Exception as exc:
        logger.warning("PPTX 图片提取失败 (%s): %s", Path(file_path).name, exc)

    return images


async def ocr_embedded_images(
    images: list[tuple[bytes, str]],
    model_config: ModelConfig,
    source_label: str = "",
) -> str:
    """OCR a list of embedded images and return combined text.

    Args:
        images: List of (image_bytes, mime_type) from extract_docx_images / extract_pptx_images.
        model_config: Vision-capable LLM.
        source_label: Label for logging (e.g. filename).

    Returns:
        Combined OCR text from all images that contain text.
    """
    if not images:
        return ""

    text_parts: list[str] = []
    for idx, (img_bytes, mime) in enumerate(images, 1):
        page_text = await _ocr_image_bytes(
            img_bytes, mime, model_config,
            page_label=f"{source_label} img {idx}/{len(images)}",
        )
        if page_text and page_text.strip() and page_text.strip() != "[无文字内容]":
            text_parts.append(page_text.strip())

    combined = "\n\n".join(text_parts)
    if combined:
        logger.info(
            "嵌入图片 OCR 完成: %s, %d 张图片, %d 字符",
            source_label, len(images), len(combined),
        )
    return combined


async def ocr_pdf_pages(file_path: str, model_config: ModelConfig) -> str:
    """Extract text from a scanned / image-only PDF by rendering each page.

    Uses PyMuPDF to render pages as PNG images, then sends each to the LLM.

    Args:
        file_path: Path to the PDF file.
        model_config: An LLM ModelConfig with vision capability.

    Returns:
        Combined text from all pages.
    """
    import fitz

    doc = fitz.open(file_path)
    page_count = len(doc)
    max_pages = settings.OCR_MAX_PAGES

    if page_count > max_pages:
        logger.warning(
            "PDF %s 共 %d 页，超过 OCR 上限 %d 页，仅处理前 %d 页",
            Path(file_path).name, page_count, max_pages, max_pages,
        )

    pages_to_process = min(page_count, max_pages)
    text_parts: list[str] = []

    for i in range(pages_to_process):
        page = doc[i]
        # Render page at 200 DPI for good OCR quality
        mat = fitz.Matrix(200 / 72, 200 / 72)
        pix = page.get_pixmap(matrix=mat)
        img_bytes = pix.tobytes("png")
        # Release pixmap immediately to prevent memory accumulation on large PDFs
        del pix

        page_text = await _ocr_image_bytes(
            img_bytes, "image/png", model_config,
            page_label=f"{i + 1}/{pages_to_process}",
        )
        del img_bytes  # Release image bytes after OCR
        if page_text and page_text.strip() and page_text.strip() != "[无文字内容]":
            text_parts.append(f"## 第 {i + 1} 页\n{page_text.strip()}")

    doc.close()

    full_text = "\n\n".join(text_parts)
    logger.info(
        "PDF OCR 完成: %s, %d/%d 页, %d 字符",
        Path(file_path).name, pages_to_process, page_count, len(full_text),
    )
    return full_text
