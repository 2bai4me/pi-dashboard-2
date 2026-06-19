#!/usr/bin/env python3
"""Cleanup-Script fuer haengende SOP-Instances.

Problem (Architektur-Analyse 18.06.2026):
    18 von 22 SOP-Instances hingen im Status 'running', weil die
    `instance_completed`-Transition nach einem Step nicht sauber durchlief.
    Die Engine macht einen Step (5s delay + run + rules), aber das
    advance()/complete() wurde nicht in allen Faellen aufgerufen.

Logik:
    1. Lade alle SOP-Instances mit status='running'.
    2. Pro Instance:
       a) JOIN mit tasks: task_id, task_status.
       b) Wenn task_status='done' UND Instance aelter als cutoff
          -> status='completed', reason='task_done_but_instance_stuck'
       c) Wenn task_status in (rueckfrage, review, in_progress, todo)
          UND Instance aelter als cutoff
          -> status='failed', reason='abandoned_timeout'
       d) Wenn Task orphaned (nicht in DB)
          -> status='failed', reason='orphaned_task'
       e) Sonst (Instance zu jung) -> ueberspringen
    3. Pro Bereinigung: sop_executions-Audit-Event.
    4. Idempotent: zweiter Lauf meldet '0 zu bereinigen'.

Usage:
    python scripts/cleanup_stuck_sop_instances.py                  # Real-Run, default cutoff=1.0h
    python scripts/cleanup_stuck_sop_instances.py --dry-run        # Nur print
    python scripts/cleanup_stuck_sop_instances.py --cutoff-hours 0.5
    python scripts/cleanup_stuck_sop_instances.py --reason manually_abandoned

Output:
    - Anzahl bereinigter Instances (by reason)
    - Liste der betroffenen Instance-IDs
    - Exit-Code 0 bei Erfolg, 1 bei Fehler
"""
from __future__ import annotations

import argparse
import logging
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("cleanup-stuck-sop-instances")


# === DB-Pfad konfigurierbar ===
DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "database" / "pi_dashboard.db"

# === Status-Mapping ===
STUCK_TASK_STATUSES = ("rueckfrage", "review", "in_progress", "todo")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Cleanup haengender SOP-Instances")
    p.add_argument(
        "--cutoff-hours", type=float, default=1.0,
        help="Instances, die laenger als X Stunden im Status 'running' sind, gelten als stuck (default: 1.0)",
    )
    p.add_argument(
        "--dry-run", action="store_true",
        help="Nur anzeigen, was passieren wuerde — keine DB-Aenderungen",
    )
    p.add_argument(
        "--reason", type=str, default=None,
        help="Custom reason fuer alle Bereinigungen (ueberschreibt automatische Reasons)",
    )
    p.add_argument(
        "--db-path", type=str, default=str(DEFAULT_DB_PATH),
        help=f"SQLite-DB-Pfad (default: {DEFAULT_DB_PATH})",
    )
    return p.parse_args()


def find_stuck_instances(conn: sqlite3.Connection, cutoff_hours: float) -> list[dict]:
    """Lade alle stuck Instances mit JOIN-Infos."""
    cur = conn.cursor()
    cutoff_dt = (datetime.utcnow() - timedelta(hours=cutoff_hours)).isoformat()
    cur.execute(
        """
        SELECT si.id, si.task_id, si.project_id, si.started_at,
               t.status AS task_status, t.title AS task_title
        FROM sop_instances si
        LEFT JOIN tasks t ON si.task_id = t.id
        WHERE si.status = 'running'
          AND si.started_at < ?
        ORDER BY si.started_at
        """,
        (cutoff_dt,),
    )
    rows = cur.fetchall()
    instances = []
    for r in rows:
        instance_id, task_id, project_id, started_at, task_status, task_title = r
        # Age in Stunden
        try:
            started_dt = datetime.fromisoformat(started_at.split(".")[0])
            age_h = (datetime.utcnow() - started_dt).total_seconds() / 3600
        except (ValueError, TypeError):
            age_h = -1.0
        # Reason bestimmen
        if task_id and task_status is None:
            reason = "orphaned_task"
        elif task_status == "done":
            reason = "task_done_but_instance_stuck"
        elif task_status in STUCK_TASK_STATUSES:
            reason = "abandoned_timeout"
        else:
            reason = "unknown_stuck_state"
        instances.append({
            "id": instance_id,
            "task_id": task_id,
            "project_id": project_id,
            "started_at": started_at,
            "age_h": age_h,
            "task_status": task_status,
            "task_title": task_title,
            "reason": reason,
        })
    return instances


def cleanup_instance(
    conn: sqlite3.Connection, instance: dict, dry_run: bool, custom_reason: str | None,
) -> bool:
    """Bereinigt eine einzelne Instance. Returns True wenn Bereinigung stattfand."""
    reason = custom_reason or instance["reason"]
    is_failed = reason != "task_done_but_instance_stuck"
    new_status = "failed" if is_failed else "completed"
    completed_at = datetime.utcnow().isoformat()

    if dry_run:
        logger.info(
            f"  [DRY-RUN] {instance['id'][:12]} | age={instance['age_h']:.1f}h | "
            f"task={instance['task_status'] or 'ORPHANED'} | "
            f"reason={reason} -> {new_status}"
        )
        return True

    cur = conn.cursor()
    # 1) Instance-Status updaten
    cur.execute(
        """
        UPDATE sop_instances
        SET status = ?, completed_at = ?, context = json_set(
            COALESCE(context, '{}'),
            '$.cleanup_reason', ?,
            '$.cleanup_at', ?,
            '$.cleanup_age_h', ?
        )
        WHERE id = ? AND status = 'running'
        """,
        (new_status, completed_at, reason, completed_at, instance["age_h"], instance["id"]),
    )
    if cur.rowcount == 0:
        logger.warning(f"  {instance['id'][:12]} konnte nicht aktualisiert werden (rowcount=0)")
        return False

    # 2) Audit-Event in sop_executions
    current_step_id = cur.execute(
        "SELECT current_step_id FROM sop_instances WHERE id = ?", (instance["id"],),
    ).fetchone()
    step_id = current_step_id[0] if current_step_id else None
    cur.execute(
        """
        INSERT INTO sop_executions (
            instance_id, step_id, ts, event, agent, details, duration_ms, success
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            instance["id"], step_id, completed_at,
            "instance_failed" if is_failed else "instance_completed",
            "system.cleanup_script",
            f'{{"reason": "{reason}", "age_h": {instance["age_h"]:.2f}, '
            f'"task_status": "{instance["task_status"] or "ORPHANED"}", '
            f'"task_title": "{(instance["task_title"] or "").replace(chr(34), chr(39))[:100]}"}}',
            None, not is_failed,
        ),
    )
    logger.info(
        f"  {instance['id'][:12]} | age={instance['age_h']:.1f}h | "
        f"task={instance['task_status'] or 'ORPHANED'} | "
        f"reason={reason} -> {new_status} ✓"
    )
    return True


def main() -> int:
    args = parse_args()
    logger.info("=" * 70)
    logger.info("CLEANUP: Stuck SOP-Instances")
    logger.info(f"  DB-Path:      {args.db_path}")
    logger.info(f"  Cutoff:       {args.cutoff_hours}h")
    logger.info(f"  Dry-Run:      {args.dry_run}")
    logger.info(f"  Custom-Reason: {args.reason or '(auto)'}")
    logger.info("=" * 70)

    if not Path(args.db_path).exists():
        logger.error(f"DB nicht gefunden: {args.db_path}")
        return 1

    conn = sqlite3.connect(args.db_path)
    try:
        stuck = find_stuck_instances(conn, args.cutoff_hours)
        logger.info(f"Gefunden: {len(stuck)} stuck Instances (status='running', age > {args.cutoff_hours}h)")

        if not stuck:
            logger.info("Keine stuck Instances — nichts zu tun.")
            return 0

        # By reason zaehlen
        by_reason: dict[str, int] = {}
        for inst in stuck:
            by_reason[inst["reason"]] = by_reason.get(inst["reason"], 0) + 1
        logger.info("Verteilung:")
        for reason, count in sorted(by_reason.items()):
            logger.info(f"  {reason:35} {count:3}")

        logger.info("-" * 70)
        logger.info("Bereinige:")

        cleaned = 0
        for inst in stuck:
            if cleanup_instance(conn, inst, args.dry_run, args.reason):
                cleaned += 1

        if args.dry_run:
            logger.info("-" * 70)
            logger.info(f"[DRY-RUN] Wuerde {cleaned} Instances bereinigen — keine DB-Aenderungen.")
            conn.rollback()
        else:
            conn.commit()
            logger.info("-" * 70)
            logger.info(f"ERFOLG: {cleaned} Instances bereinigt.")

        # Verifizieren
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM sop_instances WHERE status = 'running'")
        remaining = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM sop_instances WHERE status = 'completed'")
        completed_total = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM sop_instances WHERE status = 'failed'")
        failed_total = cur.fetchone()[0]
        logger.info("=" * 70)
        logger.info("DB-Status nach Cleanup:")
        logger.info(f"  running:    {remaining}")
        logger.info(f"  completed:  {completed_total}")
        logger.info(f"  failed:     {failed_total}")
        logger.info("=" * 70)
        return 0
    except Exception as e:
        logger.error(f"FEHLER: {e}", exc_info=True)
        conn.rollback()
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
