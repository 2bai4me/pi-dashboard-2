"""Pi Dashboard 2.0 — Konfiguration (Pydantic v2)."""
from __future__ import annotations

import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    # === Auth ===
    AUTH_ENABLED: bool = False
    JWT_SECRET: str = "change-me-to-a-random-32-byte-base64-secret"
    JWT_TTL_HOURS: int = 24
    ADMIN_USER: str = "admin"
    ADMIN_PASSWORD: str = "admin"

    # === OpenBrain ===
    OPENBRAIN_URL: str = ""
    OPENBRAIN_ACCESS_KEY: str = ""

    # === MiniMax / TTS ===
    MINIMAX_API_KEY: str = ""
    MINIMAX_TTS_API_URL: str = "https://api.minimax.io/v1/t2a_v2"
    MINIMAX_TTS_VOICE_ID: str = "English_Insightful_Speaker"
    MINIMAX_TTS_MODEL: str = "speech-2.8-hd"

    # === CORS ===
    CORS_ORIGINS: list[str] = [
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

    model_config = SettingsConfigDict(
        env_file=BACKEND_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


settings = Settings()
