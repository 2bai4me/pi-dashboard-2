"""TTS Service — MiniMax Text-to-Audio V2 HTTP API.

Dokumentation: https://platform.minimax.io/docs/llms.txt
Endpoint:      POST https://api.minimax.io/v1/t2a_v2
              (Alternative mit kürzerer Latenz: https://api-uw.minimax.io/v1/t2a_v2)
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import httpx

from ..config import settings

logger = logging.getLogger("pi-dashboard-2")


class TTSService:
    """Kapselt den MiniMax T2A V2 API-Call."""

    @staticmethod
    def _build_payload(
        text: str,
        voice_id: Optional[str] = None,
        speed: float = 1.0,
        vol: float = 1.0,
        pitch: int = 0,
        language_boost: Optional[str] = "auto",
        output_format: str = "url",
        subtitle_enable: bool = False,
    ) -> Dict[str, Any]:
        """Baut den Request-Body für MiniMax T2A V2."""

        payload: Dict[str, Any] = {
            "model": settings.MINIMAX_TTS_MODEL,
            "text": text,
            "stream": False,
            "language_boost": language_boost or "auto",
            "output_format": output_format,
            "voice_setting": {
                "voice_id": voice_id or settings.MINIMAX_TTS_VOICE_ID,
                "speed": speed,
                "vol": vol,
                "pitch": pitch,
            },
            "audio_setting": {
                "sample_rate": 32000,
                "bitrate": 128000,
                "format": "mp3",
                "channel": 1,
            },
        }
        if subtitle_enable:
            payload["subtitle_enable"] = True
            payload["subtitle_type"] = "sentence"
        return payload

    @classmethod
    async def speak(
        cls,
        text: str,
        voice_id: Optional[str] = None,
        speed: float = 1.0,
        vol: float = 1.0,
        pitch: int = 0,
        language_boost: Optional[str] = "auto",
        output_format: str = "url",
        subtitle_enable: bool = False,
    ) -> Dict[str, Any]:
        """Wandelt Text in Audio um.

        Returns:
            Dict mit audio_url/audio_hex, duration_ms, usage_characters, ...
        Raises:
            RuntimeError bei API-Fehlern.
        """

        if not settings.MINIMAX_API_KEY:
            raise RuntimeError("MINIMAX_API_KEY nicht konfiguriert")

        url = settings.MINIMAX_TTS_API_URL
        payload = cls._build_payload(
            text=text,
            voice_id=voice_id,
            speed=speed,
            vol=vol,
            pitch=pitch,
            language_boost=language_boost,
            output_format=output_format,
            subtitle_enable=subtitle_enable,
        )

        headers = {
            "Authorization": f"Bearer {settings.MINIMAX_API_KEY}",
            "Content-Type": "application/json",
        }

        logger.info(
            "TTS-Anfrage: %d Zeichen, voice=%s, model=%s, format=%s",
            len(text),
            payload["voice_setting"]["voice_id"],
            payload["model"],
            output_format,
        )

        async with httpx.AsyncClient(timeout=120.0) as client:
            try:
                resp = await client.post(url, json=payload, headers=headers)
            except httpx.HTTPError as e:
                logger.error("MiniMax TTS HTTP-Fehler: %s", e)
                raise RuntimeError(f"MiniMax TTS HTTP-Fehler: {e}") from e

        try:
            data = resp.json()
        except Exception as e:
            logger.error("MiniMax TTS Response ist kein JSON: %s", resp.text)
            raise RuntimeError(f"Ungültige MiniMax-Antwort: {resp.status_code}") from e

        # MiniMax kann bei Fehlern trotzdem HTTP 200 liefern, base_resp prüfen
        base_resp = data.get("base_resp") or {}
        status_code = base_resp.get("status_code", 0)
        status_msg = base_resp.get("status_msg", "unknown")

        if status_code != 0:
            logger.error("MiniMax TTS API-Fehler %s: %s", status_code, status_msg)
            raise RuntimeError(f"MiniMax TTS API-Fehler {status_code}: {status_msg}")

        if resp.status_code != 200:
            logger.error("MiniMax TTS HTTP %s: %s", resp.status_code, data)
            raise RuntimeError(f"MiniMax TTS HTTP {resp.status_code}: {data}")

        tts_data = data.get("data") or {}
        extra = data.get("extra_info") or {}

        out: Dict[str, Any] = {
            "ok": True,
            "audio_url": tts_data.get("audio") if output_format == "url" else None,
            "audio_hex": tts_data.get("audio") if output_format == "hex" else None,
            "audio_format": extra.get("audio_format", "mp3"),
            "duration_ms": extra.get("audio_length", 0),
            "usage_characters": extra.get("usage_characters", 0),
            "word_count": extra.get("word_count", 0),
            "trace_id": data.get("trace_id"),
            "status_msg": status_msg,
        }

        if subtitle_enable:
            out["subtitle_file"] = tts_data.get("subtitle_file")

        logger.info(
            "TTS-Erfolg: trace_id=%s duration_ms=%s usage_chars=%s",
            out["trace_id"],
            out["duration_ms"],
            out["usage_characters"],
        )
        return out
