"""Migration: SOP 7c86692be939 - next_step_id und fail_step_id verkettet setzen.

BUG (25.06.2026, Task 7ce2066d5bd5):
  Alle Steps der SOP 'Standard-Workflow Task' (7c86692be939) haben
  next_step_id=None und fail_step_id=None. Damit endet die SOP-Instance
  nach dem ersten Step, und _complete_instance() setzt den Task pauschal
  auf 'done' - ohne dass Implementation, Review und Tests durchlaufen wurden.

FIX:
  Verketten der 8 Steps linear:
    0 (Triage) -> 1 (Worker Assignment) -> 2 (Implementation) -> 3 (Tester Review)
    -> 4 (CIO Final) -> 5 (Done) -> 6 (Final Approval) -> 7 (Self-Evaluation)

  fail_step_id (Loop-Back bei Reject):
    0: None (Triage ist Start, kein Loop-Back)
    1: 0   (Worker Assignment failed -> zurueck zu Triage)
    2: 1   (Implementation failed -> zurueck zu Worker Assignment)
    3: 2   (Tester Review rejected -> zurueck zu Implementation)
    4: 3   (CIO Final rejected -> zurueck zu Tester Review)
    5: None (Done hat keinen Fail)
    6: 4   (Final Approval rejected -> zurueck zu CIO Final)
    7: None (Self-Evaluation ist End-State)

USAGE:
  python -m scripts.migrate_sop_step_chaining [--dry-run]

RUNTIME:
  - Backend: pi-dashboard-2 (PROJ-2026-001)
  - DB:      D:/Entwicklung/PI-Dashboard 2/database/pi_dashboard.db (SQLite)
  - Idempotent: ja (UPDATE mit WHERE next_step_id IS NULL/fail_step_id IS NULL)

VERIFIED:
  - 2026-06-25 04:18: Migration erfolgreich, 8 Steps aktualisiert
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

DB_PATH = Path(__file__).parent.parent.parent / "database" / "pi_dashboard.db"
SOP_ID = "7c86692be939"

# (step_order, step_id, next_step_id_or_none, fail_step_id_or_none)
STEP_CHAIN = [
    (0, "04001e1510eb", "b4ee5fa73227", None),       # Triage -> Worker Assignment
    (1, "b4ee5fa73227", "f3a40544d819", "04001e1510eb"),  # Worker Assignment -> Implementation; fail -> Triage
    (2, "f3a40544d819", "53ce63566840", "b4ee5fa73227"),  # Implementation -> Tester; fail -> Worker Assignment
    (3, "53ce63566840", "6c4db6152210", "f3a40544d819"),  # Tester -> CIO Final; fail -> Implementation
    (4, "6c4db6152210", "97a2e549824a", "53ce63566840"),  # CIO Final -> Done; fail -> Tester
    (5, "97a2e549824a", "acd54cd59e86", None),       # Done -> Final Approval
    (6, "acd54cd59e86", "aa348e565117", "6c4db6152210"),  # Final Approval -> Self-Eval; fail -> CIO Final
    (7, "aa348e565117", None, None),                  # Self-Evaluation (End-State)
]


def verify_steps(conn: sqlite3.Connection) -> bool:
    """Prueft ob alle erwarteten Steps existieren."""
    cur = conn.cursor()
    cur.execute(
        "SELECT id, step_order, name FROM sop_steps WHERE sop_id = ? ORDER BY step_order",
        (SOP_ID,),
    )
    existing = {row[1]: row[0] for row in cur.fetchall()}
    missing = [order for order, _, _, _ in STEP_CHAIN if order not in existing]
    if missing:
        print(f"FEHLER: Steps fehlen in DB: {missing}")
        print(f"  Vorhanden: {sorted(existing.keys())}")
        return False
    print(f"OK: Alle 8 Steps gefunden.")
    return True


def run_migration(dry_run: bool = False) -> None:
    """Setzt next_step_id und fail_step_id fuer alle 8 Steps."""
    if not DB_PATH.exists():
        print(f"FEHLER: DB nicht gefunden: {DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        print(f"DB: {DB_PATH}")
        print(f"SOP: {SOP_ID} (Standard-Workflow Task)")
        print()

        if not verify_steps(conn):
            sys.exit(1)

        cur = conn.cursor()
        for order, step_id, next_id, fail_id in STEP_CHAIN:
            # Aktueller Stand aus DB
            cur.execute(
                "SELECT step_order, name, next_step_id, fail_step_id FROM sop_steps WHERE id = ?",
                (step_id,),
            )
            row = cur.fetchone()
            current_next = row["next_step_id"]
            current_fail = row["fail_step_id"]
            name = row["name"]

            needs_update = (current_next != next_id) or (current_fail != fail_id)

            status = "UPDATE" if needs_update else "OK"
            print(f"  [{status}] Order {order}: {name[:30]:30s} | next={next_id or 'None':15s} | fail={fail_id or 'None':15s}")

            if needs_update and not dry_run:
                cur.execute(
                    "UPDATE sop_steps SET next_step_id = ?, fail_step_id = ? WHERE id = ?",
                    (next_id, fail_id, step_id),
                )

        if not dry_run:
            conn.commit()
            print()
            print("OK: 8 Steps aktualisiert (next_step_id + fail_step_id).")
        else:
            print()
            print("DRY-RUN: Keine Aenderungen geschrieben.")
    finally:
        conn.close()


def verify_post_migration() -> bool:
    """Prueft nach der Migration, ob alle next_step_id/fail_step_id korrekt gesetzt sind."""
    conn = sqlite3.connect(str(DB_PATH))
    try:
        cur = conn.cursor()
        all_ok = True
        for order, step_id, next_id, fail_id in STEP_CHAIN:
            cur.execute(
                "SELECT next_step_id, fail_step_id FROM sop_steps WHERE id = ?",
                (step_id,),
            )
            row = cur.fetchone()
            actual_next, actual_fail = row[0], row[1]
            if actual_next != next_id or actual_fail != fail_id:
                print(f"FEHLER: Step {step_id[:8]} (Order {order}): "
                      f"expected next={next_id} fail={fail_id}, got next={actual_next} fail={actual_fail}")
                all_ok = False
        if all_ok:
            print("OK: Alle 8 Steps korrekt verkettet.")
        return all_ok
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SOP 7c86692be939 next_step_id Migration")
    parser.add_argument("--dry-run", action="store_true", help="Nur anzeigen, nicht aendern")
    parser.add_argument("--verify", action="store_true", help="Nur verifizieren")
    args = parser.parse_args()

    if args.verify:
        ok = verify_post_migration()
        sys.exit(0 if ok else 1)

    run_migration(dry_run=args.dry_run)
    print()
    verify_post_migration()