"""Pi Dashboard 2.0 — Konfiguration (Pydantic v2)."""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

import json as _json
from typing import Annotated

from pydantic import Field, field_validator, model_validator, BeforeValidator
from pydantic_settings import BaseSettings, SettingsConfigDict


logger = logging.getLogger("pi-dashboard-2.config")


def _parse_cors_origins(v):
    """Parst CORS_ORIGINS aus .env in eine Liste von Strings.

    Akzeptiert:
      - JSON-Array:  '[\"http://a\",\"http://b\"]'
      - Komma-Liste:  'http://a,http://b'
      - Bereits Liste: ["http://a", "http://b"]
      - Einzelwert:    'http://a'
    """
    if isinstance(v, str):
        v = v.strip()
        if not v:
            return ["http://localhost:5181"]
        if v.startswith("[") and v.endswith("]"):
            try:
                return _json.loads(v)
            except _json.JSONDecodeError:
                pass
        return [x.strip() for x in v.split(",") if x.strip()]
    if isinstance(v, list):
        return v
    return ["http://localhost:5181"]


# Projekt-Wurzel: D:/Entwicklung/PI-Dashboard 2/
BACKEND_ROOT = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_ROOT.parent


# === JSON Config Paths (Module-Level Helpers) ===
def get_models_json_path() -> Path:
    """Pfad zur models.json (Provider/Modell-Konfiguration)."""
    s = Settings()
    candidates = [
        BACKEND_ROOT / "models.json",
        s.PI_AGENT_DIR / "models.json",
    ]
    for c in candidates:
        if c.exists():
            return c
    return candidates[0]  # default


def get_auth_json_path() -> Path:
    """Pfad zur auth.json (API-Keys)."""
    return Settings().PI_AGENT_DIR / "auth.json"


def get_settings_json_path() -> Path:
    """Pfad zur settings.json (enabled models, default model)."""
    return Settings().PI_AGENT_DIR / "settings.json"


class Settings(BaseSettings):
    """Konfiguration via .env (im Backend-Root)."""

    # === Server ===
    HOST: str = "127.0.0.1"
    PORT: int = 9220  # 2.0 = anderer Port als v1 (9219)

    # === Database ===
    # SQLite-Default: database/pi_dashboard.db im Projekt-Root
    DATABASE_URL: str = f"sqlite:///{PROJECT_ROOT / 'database' / 'pi_dashboard.db'}"
    # Für PostgreSQL: DATABASE_URL=postgresql+psycopg://user:pw@localhost/pi_dashboard

    # Connection-Pool
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10
    DB_ECHO: bool = False  # SQL-Logging (nur für Dev)

    # === PI-Agent-Pfade (Migration + Integration) ===
    PI_AGENT_DIR: Path = Path(os.getenv("PI_AGENT_DIR", str(Path.home() / ".pi" / "agent")))
    PI_BIN: str = "pi"
    PI_CODING_AGENT_PKG: str = "@earendil-works/pi-coding-agent"

    # === Sub-Agent-Spawner (RCE-Haertung) ===
    # Optionaler Pfad zur spawn.sh. Wenn nicht gesetzt, werden Standard-Kandidaten geprueft.
    SPAWN_SH_PATH: Optional[Path] = None

    # === Auth ===
    AUTH_ENABLED: bool = True
    JWT_SECRET: str = Field(..., min_length=16)
    JWT_ALGORITHM: str = "HS256"
    JWT_TTL_HOURS: int = 24
    ADMIN_USER: str = "admin"
    ADMIN_PASSWORD: str = ""

    # === OpenBrain ===
    OPENBRAIN_URL: str = ""
    OPENBRAIN_ACCESS_KEY: str = ""

    # === SMproducer 3.0 OpenBrain MCP Bridge ===
    SMPRODUCER_MCP_URL: str = "tcp://127.0.0.1:3050"
    SMPRODUCER_MCP_API_KEY: str = "ob-dev-key-2026"
    SMPRODUCER_MCP_TIMEOUT_S: float = 30.0

    # === ME4 External Services (OpenBrain MCP over ZMQ) ===
    ME4_TRANSCRIPT_ZMQ: str = "tcp://127.0.0.1:5556"
    ME4_TRANSCRIPT_API_KEY: str = ""
    ME4_SPEECH_SPLITTER_ZMQ: str = "tcp://127.0.0.1:5560"
    ME4_SPEECH_SPLITTER_API_KEY: str = ""
    ME4_NOTEBOOKLM_ZMQ: str = "tcp://127.0.0.1:5558"
    ME4_NOTEBOOKLM_API_KEY: str = ""

    # === MCP-over-ZMQ Bus ===
    PI_MCP_ROUTER_ENDPOINT: str = "tcp://127.0.0.1:5555"
    PI_MCP_PUB_ENDPOINT: str = "tcp://127.0.0.1:5556"
    PI_MCP_API_KEY: str = ""  # Optional: Shared-Key-Auth fuer externe Sub-Agenten

    # === MiniMax / TTS / LLM ===
    MINIMAX_API_KEY: str = ""
    KIMI_API_KEY: str = ""
    MINIMAX_TTS_API_URL: str = "https://api.minimax.io/v1/t2a_v2"
    MINIMAX_TTS_VOICE_ID: str = "English_Insightful_Speaker"
    MINIMAX_TTS_MODEL: str = "speech-2.8-hd"

    # === CORS ===
    # Format in .env: Komma-separierte Liste (z.B. "http://a,http://b")
    # oder JSON-Array (z.B. '["http://a","http://b"]')
    # Fix (v2.0-rc): BeforeValidator sorgt dafuer, dass pydantic_settings
    # den Wert nicht vorher als JSON-Array zu parsen versucht.
    CORS_ORIGINS: Annotated[
        list[str],
        BeforeValidator(_parse_cors_origins),
    ] = [
        "http://localhost:5181",  # v2.0 Frontend
        "http://127.0.0.1:5181",
        "http://localhost:5173",  # v1 Frontend (für Migration-Test)
    ]

    # === Migration ===
    V1_DATA_PATH: Path = Path(os.getenv("PI_AGENT_DIR", str(Path.home() / ".pi" / "agent"))) / "kanban"

    # === Rate-Limiting (Production-Ready) ===
    # Beispiel: RATE_LIMIT_PER_MINUTE=60 setzt 60 Req/Minute pro IP
    RATE_LIMIT_PER_MINUTE: int = 0  # 0 = disabled (dev), production: 60-600

    # === Logging ===
    LOG_LEVEL: str = "INFO"

    # === Environment ===
    # Erlaubte Werte: development, production, testing
    # In production wird Base.metadata.create_all() NICHT ausgefuehrt.
    ENV: str = "development"

    @model_validator(mode="after")
    def _warn_plaintext_admin_password(self):
        """Warnt, wenn ADMIN_PASSWORD nicht bcrypt-gehasht ist."""
        pw = self.ADMIN_PASSWORD
        if pw and not pw.startswith("$"):
            logger.warning(
                "ADMIN_PASSWORD ist im Klartext hinterlegt. "
                "Hashe es fuer Production mit bcrypt (z.B. scripts/hash_admin_pw.py)."
            )
        return self

    @model_validator(mode="after")
    def _validate_auth_secrets(self):
        """Wenn Auth aktiviert ist, muessen sichere Secrets konfiguriert sein."""
        if self.AUTH_ENABLED:
            insecure_secrets = {
                "",
                "__CHANGE_ME__",
                "change-me-to-a-random-32-byte-base64-secret",
            }
            if (
                not self.JWT_SECRET
                or self.JWT_SECRET in insecure_secrets
                or "__CHANGE_ME__" in self.JWT_SECRET
            ):
                raise ValueError(
                    "AUTH_ENABLED=true, aber JWT_SECRET ist nicht gesetzt oder unsicher. "
                    "Bitte setze ein starkes JWT_SECRET in der .env (mindestens 16 Zeichen)."
                )
            if (
                not self.ADMIN_PASSWORD
                or self.ADMIN_PASSWORD in insecure_secrets
                or "__CHANGE_ME__" in self.ADMIN_PASSWORD
            ):
                raise ValueError(
                    "AUTH_ENABLED=true, aber ADMIN_PASSWORD ist nicht gesetzt oder unsicher. "
                    "Bitte setze ein starkes ADMIN_PASSWORD in der .env."
                )
        return self

    model_config = SettingsConfigDict(
        env_file=BACKEND_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


settings = Settings()
