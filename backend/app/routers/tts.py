"""TTS Router — Text-to-Speech Endpoint für Pi Dashboard 2.0.

Integriert MiniMax T2A V2 HTTP API.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db.base import get_db
from ..auth import require_auth
from ..schemas.tts import TTSRequest, TTSResponse
from ..services.tts_service import TTSService

logger = logging.getLogger("pi-dashboard-2")

router = APIRouter(prefix="/api/tts", tags=["tts"])


@router.post("/speak", response_model=TTSResponse)
async def speak(
    req: TTSRequest,
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    """Wandelt beliebigen Text in gesprochene Sprache um.

    Liefert eine temporäre Audio-URL (24h gültig) oder einen Hex-String
    zurück, je nach `output_format`.
    """
    try:
        result = await TTSService.speak(
            text=req.text,
            voice_id=req.voice_id,
            speed=req.speed,
            vol=req.vol,
            pitch=req.pitch,
            language_boost=req.language_boost,
            output_format=req.output_format,
            subtitle_enable=req.subtitle_enable,
        )
        return TTSResponse(**result)
    except RuntimeError as e:
        logger.error("TTS-Fehler: %s", e)
        raise HTTPException(502, str(e)) from e
    except Exception as e:
        logger.exception("Unerwarteter TTS-Fehler")
        raise HTTPException(500, f"TTS-Fehler: {e}") from e
