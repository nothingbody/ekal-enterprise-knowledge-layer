"""Text-to-Speech service — generates audio from text using edge-tts."""

import io
import logging
from typing import AsyncGenerator

logger = logging.getLogger(__name__)


async def synthesize_audio(text: str, voice: str = "zh-CN-XiaoxiaoNeural") -> AsyncGenerator[bytes, None]:
    try:
        import edge_tts
    except ImportError:
        raise ImportError("edge-tts 未安装，请运行: pip install edge-tts")

    communicate = edge_tts.Communicate(text, voice)
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            yield chunk["data"]


def list_voices() -> list[dict]:
    try:
        import edge_tts
        import asyncio
        voices = asyncio.run(edge_tts.list_voices())
        chinese_voices = [
            {"name": v["ShortName"], "gender": v["Gender"], "locale": v["Locale"]}
            for v in voices
            if v["Locale"].startswith("zh-")
        ]
        return chinese_voices
    except Exception:
        return [
            {"name": "zh-CN-XiaoxiaoNeural", "gender": "Female", "locale": "zh-CN"},
            {"name": "zh-CN-YunxiNeural", "gender": "Male", "locale": "zh-CN"},
            {"name": "zh-CN-YunjianNeural", "gender": "Male", "locale": "zh-CN"},
            {"name": "zh-CN-XiaoyiNeural", "gender": "Female", "locale": "zh-CN"},
        ]
