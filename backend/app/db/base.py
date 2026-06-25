"""SQLAlchemy Base + Session-Management."""
from __future__ import annotations

from typing import Generator
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session

from ..config import settings


# SQLAlchemy 2.0 Style: DeclarativeBase statt declarative_base()
class Base(DeclarativeBase):
    """Basis für alle SQLAlchemy-Models."""
    pass


# Engine-Setup
# SQLite braucht check_same_thread=False für FastAPI (Multi-Thread)
# CLEANUP-AUDIT 23.06.2026: WAL-Mode + busy_timeout=30s verhindern
# "database is locked"-Fehler bei konkurrierenden Writes (Auto-Triage-Operator + POST).
connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args = {
        "check_same_thread": False,
        # 30s Timeout: SQLite wartet bei Lock-Konflikt statt sofort HTTP 500 zu werfen.
        "timeout": 30.0,
    }

engine = create_engine(
    settings.DATABASE_URL,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    echo=settings.DB_ECHO,
    connect_args=connect_args,
    # PostgreSQL-spezifisch (kein Effekt auf SQLite)
    pool_pre_ping=True,
)

# CLEANUP-AUDIT 23.06.2026: Event-Listener registrieren BEVOR Connections genutzt werden.
# Aktiviert WAL-Mode + busy_timeout fuer JEDE neue SQLite-Connection im Pool.
from sqlalchemy import event  # noqa: E402

@event.listens_for(engine, "connect", once=False)
def _set_sqlite_pragma(dbapi_connection, connection_record):
    """Aktiviert WAL-Mode (Write-Ahead-Log) und setzt busy_timeout.

    WAL erlaubt:
    - Mehrere Reader parallel (kein Lock fuer SELECT)
    - 1 Writer ohne andere zu blockieren
    - Bessere Crash-Recovery

    busy_timeout: Wie lange SQLite auf freien Lock wartet (in Sekunden).
    """
    try:
        cursor = dbapi_connection.cursor()
        # WAL-Mode: Write-Ahead-Log statt Rollback-Journal
        cursor.execute("PRAGMA journal_mode=WAL")
        # busy_timeout in MS (30000ms = 30s)
        cursor.execute("PRAGMA busy_timeout=30000")
        # Synchronous=NORMAL: Etwas unsicherer als FULL, aber viel schneller
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()
    except Exception as e:
        # Bei Fehler: nicht crashen, loggen
        import logging
        logging.getLogger("pi-dashboard-2.db").warning(f"PRAGMA-Setup fehlgeschlagen: {e}")

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
    """Initialisiert die Datenbank.

    In der Entwicklung werden alle Tabellen via Base.metadata.create_all()
    erstellt. In Produktion wird das Schema ausschliesslich durch Alembic-
    Migrationen verwaltet; hier wird nur geprueft, ob die erwarteten
    Tabellen existieren.
    """
    # Import aller Models, damit sie bei Base.metadata registriert sind
    from ..models import project, task, history, transition, sop, role, token_usage, pricing  # noqa: F401
    from ..models import improvement  # noqa: F401  # User-Direktive 17.06.2026 (Self-Improvement)
    from ..models import agent_question  # noqa: F401  # User-Direktive 17.06.2026 (User<->Agent Interaktionstool)
    from ..models import board_operator  # noqa: F401  # User-Direktive 17.06.2026 (Live-Board Watchdog)
    from ..models import architecture_rule  # noqa: F401  # Standardvorgaben fuer Schritt 0
    from ..models import process_template  # noqa: F401  # BPMN-Templates fuer Task-Aggregation
    from ..models import brainstorm  # noqa: F401  # Requirements-Engineering
    from ..models import provider_credential  # noqa: F401  # Zentrale API-Key-Verwaltung

    if settings.ENV == "production":
        _ensure_tables_exist()
        return

    Base.metadata.create_all(bind=engine)


def _ensure_tables_exist() -> None:
    """Prueft, dass alle erwarteten Tabellen in der Datenbank vorhanden sind.

    Wird in Produktion verwendet, um zu verhindern, dass Tabellen
    automatisch erstellt werden. Alembic ist dafuer zustaendig.
    """
    inspector = inspect(engine)
    existing = set(inspector.get_table_names())
    expected = set(Base.metadata.tables.keys())
    missing = expected - existing
    if missing:
        raise RuntimeError(
            f"Production: missing database tables: {sorted(missing)}. "
            "Run 'alembic upgrade head' before starting the application."
        )
