"""SQLAlchemy Base + Session-Management."""
from __future__ import annotations

from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session

from ..config import settings


# SQLAlchemy 2.0 Style: DeclarativeBase statt declarative_base()
class Base(DeclarativeBase):
    """Basis für alle SQLAlchemy-Models."""
    pass


# Engine-Setup
# SQLite braucht check_same_thread=False für FastAPI (Multi-Thread)
connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(
    settings.DATABASE_URL,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    echo=settings.DB_ECHO,
    connect_args=connect_args,
    # PostgreSQL-spezifisch (kein Effekt auf SQLite)
    pool_pre_ping=True,
)

# Session-Factory
SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
    class_=Session,
)


def get_db() -> Generator[Session, None, None]:
    """FastAPI-Dependency: yields eine DB-Session, schließt sie am Ende."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Erstellt alle Tabellen (nur für Dev — in Prod via Alembic)."""
    # Import aller Models, damit sie bei Base.metadata registriert sind
    from ..models import project, task, history, transition, sop, role, token_usage, pricing  # noqa: F401
    from ..models import improvement  # noqa: F401  # User-Direktive 17.06.2026 (Self-Improvement)
    from ..models import agent_question  # noqa: F401  # User-Direktive 17.06.2026 (User<->Agent Interaktionstool)
    from ..models import board_operator  # noqa: F401  # User-Direktive 17.06.2026 (Live-Board Watchdog)
    from ..models import task_draft  # noqa: F401  # User-Direktive 18.06.2026 (Iterativer Task-Refinement-Workflow)

    Base.metadata.create_all(bind=engine)
