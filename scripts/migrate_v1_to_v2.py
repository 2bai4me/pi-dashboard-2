"""Migration v1.x (JSON) → v2.0 (SQL).

Liest die JSON-Dateien aus v1.x und schreibt sie in die SQL-DB von v2.0.

Usage:
    python scripts/migrate_v1_to_v2.py
    python scripts/migrate_v1_to_v2.py --source "C:/Users/uwean/.pi/agent/kanban" --target "D:/Entwicklung/PI-Dashboard 2/database/pi_dashboard.db"
    python scripts/migrate_v1_to_v2.py --dry-run   # Nur anzeigen, nichts schreiben

Stand 15.06.2026: Initiale Version.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterator

# Projekt-Pfade
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.config import settings  # noqa: E402
from app.db.base import SessionLocal, init_db, engine  # noqa: E402
from app.models import Project, Task, TaskHistory, Role, TokenUsage, ModelPricing  # noqa: E402


def load_json(path: Path) -> Any:
    """Laedt eine JSON-Datei sicher."""
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        print(f"  WARN: {path.name} ist kein valides JSON, ueberspringe.")
        return None


def parse_iso(ts: str | None) -> datetime | None:
    """Parst ISO-Timestamp zu datetime."""
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def migrate_projects(session, projects_data: list[dict], stats: dict) -> Iterator[Project]:
    """Migriert projects.json → projects-Tabelle."""
    if not projects_data:
        return

    print(f"  Projects: {len(projects_data)} Eintraege...")
    for p in projects_data:
        project = Project(
            id=p["id"],
            name=p.get("name", "(unknown)"),
            description=p.get("description"),
            status=p.get("status", "active"),
            # v1 hatte kein mode/category → Defaults
            mode="preparation",
            category="new_request",
            created_at=parse_iso(p.get("created_at")) or datetime.utcnow(),
            updated_at=parse_iso(p.get("updated_at")) or datetime.utcnow(),
            closed_at=parse_iso(p.get("closed_at")),
        )
        session.add(project)
        stats["projects_added"] += 1
    session.flush()
    print(f"    -> {stats['projects_added']} Projects migriert")


def migrate_tasks(session, tasks_data: list[dict], stats: dict) -> None:
    """Migriert tasks.json → tasks-Tabelle."""
    if not tasks_data:
        return

    print(f"  Tasks: {len(tasks_data)} Eintraege...")
    valid_task_ids = set()
    for t in tasks_data:
        task = Task(
            id=t["id"],
            project_id=t.get("project_id") or None,
            parent_id=t.get("parent_id") or None,
            title=t.get("title", "(unknown)"),
            description=t.get("description"),
            status=t.get("status", "triage"),
            priority=int(t.get("priority", 50)),
            category=t.get("category", "new_request"),
            assigned_role=t.get("assigned_role"),
            assigned_subagent=t.get("assigned_subagent"),
            iteration_count=int(t.get("iteration_count", 0)),
            order=int(t.get("order", 0)),
            created_at=parse_iso(t.get("created_at")) or datetime.utcnow(),
            updated_at=parse_iso(t.get("updated_at")) or datetime.utcnow(),
            claimed_at=parse_iso(t.get("claimed_at")),
            emergency=bool(t.get("emergency", False)),
            pricing_snapshot=t.get("pricing_snapshot"),
            tags=t.get("tags", []),
            success_criteria=t.get("success_criteria", []),
            meta=t.get("meta", {}),
        )
        session.add(task)
        stats["tasks_added"] += 1
        valid_task_ids.add(t["id"])
    session.flush()
    print(f"    -> {stats['tasks_added']} Tasks migriert")


def migrate_history(session, tasks_data: list[dict], stats: dict) -> None:
    """Migriert History-Eintraege aus task.history → task_history-Tabelle."""
    print(f"  History...")
    count = 0
    for t in tasks_data:
        history = t.get("history", []) or []
        if not history:
            continue
        for h in history:
            # Tokens aus Top-Level oder details
            tokens_in = h.get("tokens_in")
            tokens_out = h.get("tokens_out")
            if tokens_in is None or tokens_out is None:
                details = h.get("details", {}) or {}
                tokens_in = tokens_in if tokens_in is not None else details.get("tokens_in", 0) or 0
                tokens_out = tokens_out if tokens_out is not None else details.get("tokens_out", 0) or 0
            cost = h.get("cost_usd")
            if cost is None:
                cost = (h.get("details", {}) or {}).get("cost_usd", 0) or 0

            entry = TaskHistory(
                task_id=t["id"],
                ts=parse_iso(h.get("ts")) or datetime.utcnow(),
                event=h.get("event", "unknown"),
                agent=h.get("agent"),
                model=h.get("model"),
                tokens_in=int(tokens_in),
                tokens_out=int(tokens_out),
                cost_usd=Decimal(str(cost)),
                details=h.get("details", {}),
            )
            session.add(entry)
            count += 1
    session.flush()
    stats["history_added"] = count
    print(f"    -> {count} History-Eintraege migriert")


def migrate_pricing(session, models_data: dict, stats: dict) -> None:
    """Migriert Provider-Preise aus models.json (falls vorhanden) → model_pricing."""
    if not models_data:
        return

    providers = (models_data or {}).get("providers", {})
    print(f"  Pricing: {len(providers)} Provider...")
    count = 0
    for prov_name, prov in providers.items():
        pricing_map = prov.get("pricing", {}) or {}
        for model_key, p in pricing_map.items():
            if model_key == "default":
                continue  # wird separat als is_default=True angelegt
            entry = ModelPricing(
                provider=prov_name,
                model_id=model_key,
                input_per_1m=Decimal(str(p.get("input_per_1m", 0))),
                output_per_1m=Decimal(str(p.get("output_per_1m", 0))),
                currency=p.get("currency", "USD"),
                source=p.get("source"),
                last_updated=parse_iso(p.get("last_updated")) or datetime.utcnow(),
                note=p.get("note"),
                is_default=False,
            )
            session.add(entry)
            count += 1
        # Provider-Default
        if "default" in pricing_map:
            d = pricing_map["default"]
            entry = ModelPricing(
                provider=prov_name,
                model_id="default",
                input_per_1m=Decimal(str(d.get("input_per_1m", 0))),
                output_per_1m=Decimal(str(d.get("output_per_1m", 0))),
                currency=d.get("currency", "USD"),
                source=d.get("source"),
                last_updated=parse_iso(d.get("last_updated")) or datetime.utcnow(),
                note=d.get("note"),
                is_default=True,
            )
            session.add(entry)
            count += 1
    session.flush()
    stats["pricing_added"] = count
    print(f"    -> {count} Pricing-Eintraege migriert")


def main():
    parser = argparse.ArgumentParser(description="Migration v1.x (JSON) -> v2.0 (SQL)")
    parser.add_argument(
        "--source",
        type=Path,
        default=Path.home() / ".pi" / "agent" / "kanban",
        help="Pfad zu v1.x JSON-Verzeichnis (default: ~/.pi/agent/kanban)",
    )
    parser.add_argument(
        "--target",
        type=Path,
        default=PROJECT_ROOT / "database" / "pi_dashboard.db",
        help="Pfad zur v2.0 SQLite-DB (default: database/pi_dashboard.db)",
    )
    parser.add_argument(
        "--models-source",
        type=Path,
        default=Path.home() / ".pi" / "agent" / "models.json",
        help="Pfad zu v1.x models.json (default: ~/.pi/agent/models.json)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Nur anzeigen, nichts schreiben",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("Pi Dashboard v1.x -> v2.0 Migration")
    print("=" * 60)
    print(f"Source (JSON): {args.source}")
    print(f"Target (SQL):  {args.target}")
    print(f"Models-Source: {args.models_source}")
    print(f"Dry-Run:       {args.dry_run}")
    print()

    # 1) DB initialisieren (Tabellen erstellen)
    if not args.dry_run:
        print("[1/4] DB-Initialisierung...")
        args.target.parent.mkdir(parents=True, exist_ok=True)
        init_db()
        print(f"    -> Tabellen erstellt in {args.target}")
    else:
        print("[1/4] DB-Initialisierung: SKIP (dry-run)")

    # 2) JSON-Dateien laden
    print()
    print("[2/4] JSON-Dateien laden...")
    projects_data = load_json(args.source / "projects.json") or []
    tasks_data = load_json(args.source / "tasks.json") or []
    models_data = load_json(args.models_source) or {}
    print(f"    Projects: {len(projects_data)}")
    print(f"    Tasks:    {len(tasks_data)}")
    print(f"    Models:   {len(models_data.get('providers', {}))} Provider")

    if args.dry_run:
        print()
        print("[DRY-RUN] Beendet ohne Schreibvorgaenge.")
        return

    # 3) Migration
    print()
    print("[3/4] Migration laeuft...")
    stats = {
        "projects_added": 0,
        "tasks_added": 0,
        "history_added": 0,
        "pricing_added": 0,
    }
    with SessionLocal() as session:
        try:
            migrate_projects(session, projects_data, stats)
            migrate_tasks(session, tasks_data, stats)
            migrate_history(session, tasks_data, stats)
            migrate_pricing(session, models_data, stats)
            migrate_history_and_tokenusage(session, cfg, stats)  # v1.1: History + TokenUsage
            session.commit()
        except Exception as e:
            session.rollback()
            print(f"    FEHLER: {e}")
            raise

    # 4) Statistik
    print()
    print("[4/4] Statistik:")
    print(f"    Projects:  +{stats['projects_added']}")
    print(f"    Tasks:     +{stats['tasks_added']}")
    print(f"    History:   +{stats['history_added']}")
    print(f"    Pricing:   +{stats['pricing_added']}")
    print()
    print("=" * 60)
    print("Migration erfolgreich abgeschlossen!")
    print(f"DB: {args.target}")
    print("=" * 60)


if __name__ == "__main__":
    main()


# === Erweiterung 15.06.2026: History + TokenUsage migrieren ===
def migrate_history_and_tokenusage(db, v1_data, stats):
    """Migriert task.history[] -> task_history-Tabelle und generiert TokenUsage.

    Beide Tabellen waren in v1 NICHT explizit vorhanden (History als JSON-Array
    in Task, Tokens nirgends erfasst). In v2.0 sind sie dedizierte Tabellen.
    """
    from app.models.history import TaskHistory
    from app.models.token_usage import TokenUsage
    from app.services.pricing_service import get_current_pricing, calc_cost_from_snapshot
    from decimal import Decimal
    from datetime import datetime

    history_count = 0
    token_count = 0
    for t in v1_data.get("tasks", []):
        # History migrieren (falls vorhanden)
        history_list = t.get("history", []) or []
        for h in history_list:
            entry = TaskHistory(
                task_id=t["id"],
                ts=datetime.fromisoformat(h["ts"].replace("Z", "+00:00")) if h.get("ts") else datetime.utcnow(),
                event=h.get("event", "unknown"),
                agent=h.get("agent"),
                model=h.get("model"),
                tokens_in=int(h.get("tokens_in", 0) or 0),
                tokens_out=int(h.get("tokens_out", 0) or 0),
                cost_usd=Decimal(str(h.get("cost_usd", 0) or 0)),
                details=h.get("details", {}),
            )
            db.add(entry)
            history_count += 1
        # TokenUsage aus v1 gibt es nicht — leeres Array
    db.commit()
    stats["history_migrated"] = history_count
    print(f"  History migriert: {history_count} Eintraege")
    return history_count
