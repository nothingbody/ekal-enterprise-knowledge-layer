"""Text-to-Speech API — synthesize speech from text."""

import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.core.security import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter()


class TTSRequest(BaseModel):
    text: str
    voice: str = "zh-CN-XiaoxiaoNeural"


@router.post("/synthesize")
async def synthesize_speech(
    data: TTSRequest,
    current_user: User = Depends(get_current_user),
):
    text = data.text.strip()
    if not text:
        raise HTTPException(400, "文本不能为空")
    if len(text) > 5000:
        raise HTTPException(400, "文本长度不能超过 5000 字符")

    try:
        from app.services.tts_service import synthesize_audio
        audio_generator = synthesize_audio(text, data.voice)
        return StreamingResponse(audio_generator, media_type="audio/mpeg")
    except ImportError:
        raise HTTPException(501, "TTS 服务未安装，请安装 edge-tts: pip install edge-tts")
    except Exception as exc:
        logger.error("TTS synthesis failed: %s", exc)
        raise HTTPException(500, f"语音合成失败: {exc}")
