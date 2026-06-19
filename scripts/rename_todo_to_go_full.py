"""Vollstaendige Umbenennung: Status-Key 'todo' -> 'go'.

Aenderungen:
1. DB: Alle Tasks mit status='todo' auf 'go' setzen (idempotent)
2. Backend-Code: Status-Werte in Status-Updates aendern
3. Phasen-Mappings in sops.py
4. NICHT aendern: 'todo' als Keyword/Platzhalter (workflow.py:325)
"""
import sys
import os
import re

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from sqlalchemy.orm.attributes import flag_modified
from app.db.base import SessionLocal
from app.models.task import Task


def main():
    db = SessionLocal()
    try:
        # 1) DB: Tasks mit status='todo' -> status='go'
        tasks = db.query(Task).filter(Task.status == "todo").all()
        print(f"=== DB-Migration: {len(tasks)} Tasks mit Status='todo' ===")
        for t in tasks:
            t.status = "go"
        db.commit()
        print(f"  -> {len(tasks)} Tasks auf Status='go' gesetzt")
        print()

        # 2) Verifikation
        todo_count = db.query(Task).filter(Task.status == "todo").count()
        go_count = db.query(Task).filter(Task.status == "go").count()
        print(f"=== Verifikation ===")
        print(f"  Status='todo': {todo_count} (sollte 0 sein)")
        print(f"  Status='go':   {go_count}")

    finally:
        db.close()


if __name__ == "__main__":
    main()
