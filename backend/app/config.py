"""Pi Dashboard 2.0 — Konfiguration (Pydantic v2)."""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

import json as _json
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


logger = logging.getLogger("pi-dashboard-2.config")


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

    # === MiniMax / TTS / LLM ===
    MINIMAX_API_KEY: str = ""
    KIMI_API_KEY: str = ""
    MINIMAX_TTS_API_URL: str = "https://api.minimax.io/v1/t2a_v2"
    MINIMAX_TTS_VOICE_ID: str = "English_Insightful_Speaker"
    MINIMAX_TTS_MODEL: str = "speech-2.8-hd"

    # === CORS ===
    # Format in .env: Komma-separierte Liste (z.B. "http://a,http://b")
    # oder JSON-Array (z.B. '["http://a","http://b"]')
    # Fix (v2.0-rc): Pydantic v2 parst JSON-Strings nicht automatisch → Custom Validator
    CORS_ORIGINS: list[str] = [
        "http://localhost:5181",  # v2.0 Frontend
        "http://127.0.0.1:5181",
        "http://localhost:5173",  # v1 Frontend (für Migration-Test)
    ]

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v):
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
            if self.JWT_SECRET in insecure_secrets:
                raise ValueError(
                    "AUTH_ENABLED=true, aber JWT_SECRET ist nicht gesetzt oder unsicher. "
                    "Bitte setze ein starkes JWT_SECRET in der .env (nicht der Default-Wert)."
                )
            if not self.ADMIN_PASSWORD or self.ADMIN_PASSWORD in insecure_secrets:
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
