"""Pi Dashboard 2.0 — Konfiguration (Pydantic v2)."""
from __future__ import annotations

import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


# Projekt-Wurzel: D:/Entwicklung/PI-Dashboard 2/
BACKEND_ROOT = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_ROOT.parent


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

    # === CORS ===
    CORS_ORIGINS: list[str] = [
        "http://localhost:5181",  # v2.0 Frontend
        "http://127.0.0.1:5181",
        "http://localhost:5173",  # v1 Frontend (für Migration-Test)
    ]

    # === Migration ===
    V1_DATA_PATH: Path = Path(os.getenv("PI_AGENT_DIR", str(Path.home() / ".pi" / "agent"))) / "kanban"

    # === Logging ===
    LOG_LEVEL: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=BACKEND_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


settings = Settings()
