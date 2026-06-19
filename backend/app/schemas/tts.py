"""TTS Schemas — MiniMax Text-to-Audio V2."""
from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field, field_validator


class TTSRequest(BaseModel):
    """POST /api/tts/speak — Text in Sprache umwandeln."""

    text: str = Field(
        ...,
        min_length=1,
        max_length=10000,
        description="Text, der vorgelesen werden soll (< 10.000 Zeichen).",
    )
    voice_id: Optional[str] = Field(
        None,
        description="MiniMax Voice ID. Default kommt aus .env (MINIMAX_TTS_VOICE_ID).",
    )
    speed: float = Field(
        1.0,
        ge=0.5,
        le=2.0,
        description="Sprechgeschwindigkeit: 0.5 = langsam, 2.0 = schnell.",
    )
    vol: float = Field(
        1.0,
        gt=0,
        le=10,
        description="Lautstärke: 0.1 – 10.0.",
    )
    pitch: int = Field(
        0,
        ge=-12,
        le=12,
        description="Tonhöhe: -12 (tiefer) bis +12 (höher).",
    )
    language_boost: Optional[str] = Field(
        "auto",
        description="Spracherkennung: 'auto', 'German', 'English', ...",
    )
    output_format: str = Field(
        "url",
        description="Ausgabeformat: 'url' (24h gültig) oder 'hex' (roher Hex-String).",
    )
    subtitle_enable: bool = Field(
        False,
        description="Untertitel mit erzeugen (experimentell).",
    )

    @field_validator("output_format")
    @classmethod
    def _validate_output_format(cls, v: str) -> str:
        if v not in ("url", "hex"):
            raise ValueError("output_format muss 'url' oder 'hex' sein")
        return v


class TTSResponse(BaseModel):
    """Antwort vom TTS-Endpoint."""

    ok: bool = True
    audio_url: Optional[str] = None
    audio_hex: Optional[str] = None
    audio_format: str = "mp3"
    duration_ms: int = 0
    usage_characters: int = 0
    word_count: int = 0
    trace_id: Optional[str] = None
    status_msg: str = "success"


# === Voice-Konfiguration Schemas (User-Direktive 19.06.2026) ===

class VoiceInfoSchema(BaseModel):
    """Beschreibung einer TTS-Stimme (siehe voice_config.py)."""

    id: str = Field(..., description="Eindeutige Voice-ID fuer API-Calls.")
    name: str = Field(..., description="Anzeigename der Stimme.")
    language: str = Field(..., description="Sprachcode (z.B. 'de-DE').")
    language_label: str = Field(..., description="Anzeigename der Sprache.")
    gender: str = Field(..., description="Geschlecht: male/female/neutral/child.")
    description: str = Field(..., description="Kurze Beschreibung der Stimme.")
    preview_text: str = Field(..., description="Beispiel-Text zum Vorhoeren.")


class LanguageInfo(BaseModel):
    """Eine verfuegbare Sprache."""

    code: str = Field(..., description="Sprachcode (z.B. 'de-DE').")
    label: str = Field(..., description="Anzeigename der Sprache.")


class VoiceListResponse(BaseModel):
    """GET /api/tts/voices — Liste aller verfuegbaren Stimmen."""

    voices: List[VoiceInfoSchema] = Field(
        ...,
        description="Liste aller verfuegbaren Stimmen.",
    )
    languages: List[LanguageInfo] = Field(
        ...,
        description="Verfuegbare Sprachen (gruppiert).",
    )
    default_voice_id: str = Field(
        ...,
        description="Default-Stimme aus .env (MINIMAX_TTS_VOICE_ID).",
    )
    total_count: int = Field(..., description="Anzahl Stimmen gesamt.")
    by_language: dict = Field(
        ...,
        description="Stimmen gruppiert nach Sprache: { 'de-DE': [...], 'en-US': [...], ... }",
    )
