"""Auto-Backup-Scheduler (Hintergrund-Task).

Erstellt taeglich ein SQLite-Backup und loescht alte Backups nach Retention-Periode.

Production-Grade: Bei PostgreSQL wuerde man pg_dump + WAL-Archiving nutzen.
"""
from __future__ import annotations

import asyncio
import logging
import shutil
from datetime import datetime, timedelta
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from .config import settings

logger = logging.getLogger("pi-dashboard-2.backup-scheduler")


async def create_backup_task() -> dict:
    """Erstellt ein Backup der aktuellen DB.

    Returns: {ok, path, size_mb, created_at, deleted_old}
    """
    import sqlite3
    from .config import settings
    db_path = settings.DATABASE_URL.replace("sqlite:///", "")
    backup_dir = Path("database/backups")
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    backup_path = backup_dir / f"pi_dashboard-{timestamp}.db"

    src = sqlite3.connect(db_path)
    dst = sqlite3.connect(str(backup_path))
    try:
        with dst:
            src.backup(dst)
    finally:
        src.close()
        dst.close()

    # Retention: Backups aelter als 7 Tage loeschen
    deleted = 0
    cutoff = datetime.utcnow() - timedelta(days=7)
    for old_backup in backup_dir.glob("pi_dashboard-*.db"):
        if old_backup == backup_path:
            continue
        try:
            # Filename: pi_dashboard-YYYYMMDD-HHMMSS.db
            ts_str = old_backup.stem.split("-", 1)[1]  # YYYYMMDD-HHMMSS
            old_dt = datetime.strptime(ts_str, "%Y%m%d-%H%M%S")
            if old_dt < cutoff:
                old_backup.unlink()
                deleted += 1
        except (ValueError, IndexError):
            continue  # Skip malformed files

    size_mb = backup_path.stat().st_size / (1024 * 1024)
    logger.info(f"Auto-Backup erstellt: {backup_path} ({size_mb:.2f} MB, deleted_old={deleted})")
    return {
        "ok": True,
        "path": str(backup_path),
        "size_mb": round(size_mb, 3),
        "created_at": datetime.utcnow().isoformat(),
        "deleted_old": deleted,
    }


_scheduler: AsyncIOScheduler | None = None


def start_scheduler() -> None:
    """Startet den Auto-Backup-Scheduler (taeglich um 02:00 UTC)."""
    global _scheduler
    if _scheduler is not None:
        logger.warning("Backup-Scheduler laeuft bereits")
        return

    _scheduler = AsyncIOScheduler()
    # Taeglich um 02:00 UTC
    _scheduler.add_job(
        create_backup_task,
        CronTrigger(hour=2, minute=0, timezone="UTC"),
        id="daily_backup",
        name="Daily SQLite Backup",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info("Auto-Backup-Scheduler gestartet (taeglich 02:00 UTC)")


def stop_scheduler() -> None:
    """Stoppt den Scheduler (z.B. bei Shutdown)."""
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("Auto-Backup-Scheduler gestoppt")
