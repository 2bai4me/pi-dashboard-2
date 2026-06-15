"""Alembic Env — Pi Dashboard 2.0.

Verwendet die settings aus app.config, damit DATABASE_URL konsistent
mit dem FastAPI-Backend ist (Single Source of Truth).

JSONType-TypeDecorator wird via render_item() als sa.JSON() gerendert,
damit Alembic-Migrationen saubere, DB-portable SQL-Anweisungen generieren
(keine TypeDecorator-Instanzen im File).
"""
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool, JSON
from sqlalchemy.dialects.sqlite import JSON as SQLiteJSON

from alembic import context

# App-Config + Models importieren
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.config import settings
from app.db.base import Base
from app.models import (  # noqa: F401 — registration via import
    Project, Task, TaskHistory, Role, TokenUsage, ModelPricing,
)

# Alembic Config
config = context.config

# DATABASE_URL aus App-Settings (Single Source of Truth)
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

# Logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Target-Metadata fuer Autogenerate
target_metadata = Base.metadata


def render_item(type_, obj, autogen_context):
    """Override: JSONType als sa.JSON() rendern (nicht als TypeDecorator-Instanz)."""
    # Erkennt unseren JSONType anhand des Klassennamens
    if type_ == "type" and obj.__class__.__name__ == "JSONType":
        # sa.JSON() in der Migration verwenden
        autogen_context.imports.add("from sqlalchemy import JSON")
        return "sa.JSON()"
    # Default: SQLAlchemy's eigenes Rendering
    return False


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (nur SQL-Output, keine Engine)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,  # Wichtig fuer SQLite (ALTER TABLE)
        render_item=render_item,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (mit Engine + Connection)."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,  # SQLite-Kompatibilitaet
            render_item=render_item,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
