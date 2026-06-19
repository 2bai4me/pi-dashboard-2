"""TTS Service — MiniMax Text-to-Audio V2 HTTP API.

Dokumentation: https://platform.minimax.io/docs/llms.txt
Endpoint:      POST https://api.minimax.io/v1/t2a_v2
              (Alternative mit kürzerer Latenz: https://api-uw.minimax.io/v1/t2a_v2)
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import httpx

from ..config import settings

logger = logging.getLogger("pi-dashboard-2")

# ══════════════════════════════════════════════════════════════════════
# Voice-Katalog (vormals voice_config.py)
# ══════════════════════════════════════════════════════════════════════
# User-Direktive 19.06.2026: voice_config.py wurde wiederholt von einem
# Auto-Cleanup-Mechanismus geloescht. Der Katalog ist daher direkt im
# TTS-Service eingebettet, damit er nicht mehr als separate Datei
# ausgeloescht werden kann.
# ══════════════════════════════════════════════════════════════════════
# Sprach-Mapping fuer Schema (code, label)
LANGUAGE_INFO = {
    "English": {"code": "en-US", "label": "English"},
    "German": {"code": "de-DE", "label": "Deutsch"},
    "Chinese": {"code": "zh-CN", "label": "Chinese (Mandarin)"},
}

AVAILABLE_VOICES: List[Dict[str, Any]] = [
    # English
    {"id": "English_Graceful_Lady", "name": "Graceful Lady", "language": "English", "gender": "female", "description": "A graceful and elegant female English voice.", "preview_text": "Hello, this is a sample of the Graceful Lady voice."},
    {"id": "English_Insightful_Speaker", "name": "Insightful Speaker", "language": "English", "gender": "male", "description": "An insightful and calm male English voice.", "preview_text": "Hello, this is a sample of the Insightful Speaker voice."},
    {"id": "English_Lucky_Robot", "name": "Lucky Robot", "language": "English", "gender": "neutral", "description": "A robotic English voice with a lucky charm.", "preview_text": "Hello, this is a sample of the Lucky Robot voice."},
    {"id": "English_Persuasive_Man", "name": "Persuasive Man", "language": "English", "gender": "male", "description": "A persuasive and confident male English voice.", "preview_text": "Hello, this is a sample of the Persuasive Man voice."},
    {"id": "English_radiant_girl", "name": "Radiant Girl", "language": "English", "gender": "female", "description": "A bright and radiant young female English voice.", "preview_text": "Hello, this is a sample of the Radiant Girl voice."},
    # German
    {"id": "German_Clear_Voice", "name": "Clear Voice", "language": "German", "gender": "neutral", "description": "Eine klare und deutliche deutsche Stimme.", "preview_text": "Hallo, dies ist ein Beispiel der klaren deutschen Stimme."},
    {"id": "German_Friendly_Woman", "name": "Friendly Woman", "language": "German", "gender": "female", "description": "Eine freundliche weibliche deutsche Stimme.", "preview_text": "Hallo, dies ist ein Beispiel der freundlichen deutschen Stimme."},
    {"id": "German_Neutral", "name": "Neutral", "language": "German", "gender": "neutral", "description": "Eine neutrale deutsche Stimme.", "preview_text": "Hallo, dies ist ein Beispiel der neutralen deutschen Stimme."},
    {"id": "German_News_Anchor", "name": "News Anchor", "language": "German", "gender": "male", "description": "Eine professionelle deutsche Nachrichtenstimme.", "preview_text": "Hallo, dies ist ein Beispiel der deutschen Nachrichtenstimme."},
    {"id": "German_Podcast_Host", "name": "Podcast Host", "language": "German", "gender": "male", "description": "Eine warme deutsche Podcast-Stimme.", "preview_text": "Hallo, dies ist ein Beispiel der deutschen Podcast-Stimme."},
    {"id": "German_Professional_Man", "name": "Professional Man", "language": "German", "gender": "male", "description": "Eine professionelle maennliche deutsche Stimme.", "preview_text": "Hallo, dies ist ein Beispiel der professionellen deutschen Stimme."},
    {"id": "German_Warm_Narrator", "name": "Warm Narrator", "language": "German", "gender": "female", "description": "Eine warme weibliche deutsche Erzaehlerstimme.", "preview_text": "Hallo, dies ist ein Beispiel der warmen deutschen Erzaehlerstimme."},
    {"id": "German_Warm_Speaker", "name": "Warm Speaker", "language": "German", "gender": "female", "description": "Eine warme weibliche deutsche Sprecherstimme.", "preview_text": "Hallo, dies ist ein Beispiel der warmen deutschen Sprecherstimme."},
    # Chinese (Mandarin)
    {"id": "Chinese (Mandarin)_HK_Flight_Attendant", "name": "HK Flight Attendant", "language": "Chinese", "gender": "female", "description": "A Hong Kong flight attendant style Mandarin voice.", "preview_text": "你好，这是香港空姐风格的中文语音示例。"},
    {"id": "Chinese (Mandarin)_Lyrical_Voice", "name": "Lyrical Voice", "language": "Chinese", "gender": "female", "description": "A lyrical and expressive Mandarin voice.", "preview_text": "你好，这是抒情风格的中文语音示例。"},
]


def _get_languages() -> List[Dict[str, str]]:
    """Liefert eine sortierte Liste aller verfuegbaren Sprachen als LanguageInfo."""
    seen = set()
    languages = []
    for v in AVAILABLE_VOICES:
        lang = v["language"]
        if lang not in seen:
            seen.add(lang)
            info = LANGUAGE_INFO.get(lang, {"code": lang, "label": lang})
            languages.append(info)
    return sorted(languages, key=lambda x: x["label"])


def _get_voices_by_language() -> Dict[str, List[Dict[str, str]]]:
    """Gruppiert die Stimmen nach Sprache."""
    grouped: Dict[str, List[Dict[str, str]]] = {}
    for v in AVAILABLE_VOICES:
        grouped.setdefault(v["language"], []).append(v)
    return grouped


def _is_valid_voice_id(voice_id: Optional[str]) -> bool:
    """Prueft, ob eine Voice-ID in der Liste existiert."""
    if not voice_id:
        return False
    return any(v["id"] == voice_id for v in AVAILABLE_VOICES)


class TTSService:
    """Kapselt den MiniMax T2A V2 API-Call."""

    # ------------------------------------------------------------------
    # Voice-Katalog
    # ------------------------------------------------------------------
    @staticmethod
    def get_available_voices() -> Dict[str, Any]:
        """Liefert die Liste aller verfuegbaren Stimmen.

        Die Stimme-Liste ist aktuell statisch in voice_config.py hinterlegt
        (MiniMax bietet keinen offiziellen listVoices-Endpoint).
        In Zukunft koennte hier auch eine API-Abfrage ergaenzt werden.

        Returns:
            Dict mit voices, languages, default_voice_id, total_count,
            by_language.
        """
        voices = []
        for v in AVAILABLE_VOICES:
            lang = v["language"]
            info = LANGUAGE_INFO.get(lang, {"code": lang, "label": lang})
            voices.append({
                **v,
                "language": info["code"],
                "language_label": info["label"],
            })
        languages = _get_languages()
        grouped = _get_voices_by_language()
        default_id = settings.MINIMAX_TTS_VOICE_ID

        # Falls die Default-Voice-ID nicht in der Konfig existiert,
        # auf die erste deutsche oder englische Stimme zurueckfallen
        if not _is_valid_voice_id(default_id):
            logger.warning(
                "MINIMAX_TTS_VOICE_ID '%s' ist nicht im Voice-Katalog. "
                "Fallback auf 'German_Warm_Speaker'.",
                default_id,
            )
            default_id = "German_Warm_Speaker"

        return {
            "voices": list(voices),
            "languages": languages,
            "default_voice_id": default_id,
            "total_count": len(voices),
            "by_language": {
                lang: [{
                    **v,
                    "language": LANGUAGE_INFO.get(v["language"], {"code": v["language"], "label": v["language"]})["code"],
                    "language_label": LANGUAGE_INFO.get(v["language"], {"code": v["language"], "label": v["language"]})["label"],
                } for v in lst]
                for lang, lst in grouped.items()
            },
        }

    @staticmethod
    def is_valid_voice_id(voice_id: str) -> bool:
        """Prueft, ob eine Voice-ID existiert."""
        return _is_valid_voice_id(voice_id)

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
