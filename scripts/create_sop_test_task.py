"""Erstellt einen Task fuer den SOP-Prozess-Test.

Der Task ist absichtlich NICHT selbst umgesetzt - er wird durch den
Standard-Workflow Development SOP (7c86692be939) automatisch verarbeitet.

Phasen des SOP-Prozesses (5s sichtbar pro Phase):
1. Triage (5s) -> CIO prueft
2. ToDo (5s) -> PI-Coder uebernimmt
3. InProgress (5s) -> PI-Coder arbeitet
4. Review -> PI-Tester prueft -> assigned_role=cio
5. Done -> CIO finalisiert
"""
import sys
import os
import secrets

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.db.base import SessionLocal
from app.models.task import Task
from app.models.sop import SOPInstance
from app.models.history import TaskHistory
from app.models.project import Project

PROJECT_ID = "d5976e76247c"
DEFAULT_SOP_ID = "7c86692be939"  # Standard-Workflow Development

TASK_TITLE = "[BUG] SOP-Auswahl zeigt 'Standard SOP' statt aktuelle SOP im Board (links von Live-Indikator)"

TASK_DESCRIPTION = """## Bug-Beschreibung

Im Board-Header (oder einer anderen UI-Stelle) wird links vom Live-Indikator
ein Feld fuer die SOP-Auswahl angezeigt. Aktuell zeigt dieses Feld "Standard SOP"
an, auch wenn der User eine andere SOP fuer das Board ausgewaehlt hat.

## Erwartetes Verhalten

- Das SOP-Auswahlfeld zeigt die aktuell ausgewaehlte SOP fuer das Board an
- NICHT den generischen Text "Standard SOP"
- Die Anzeige ist die `sop_id` (oder der `name`) der `Project.default_sop_id` des jeweiligen Boards
- Wenn der User die SOP wechselt, aendert sich die Anzeige sofort

## Reproduktion

1. Oeffne ein Board im Kanban
2. Schau auf das SOP-Feld (links von Live-Indikator)
3. Es zeigt "Standard SOP" statt der tatsaechlich gewaehlten SOP

## Akzeptanzkriterien

- [ ] Das SOP-Feld zeigt den Namen der aktuell gewaehlten SOP (z.B. "Standard-Workflow Development")
- [ ] NICHT der statische Text "Standard SOP"
- [ ] Bei Wechsel der SOP aendert sich die Anzeige sofort
- [ ] Wenn keine SOP gewaehlt ist, wird "Keine SOP" oder aehnlich angezeigt

## Kontext

- Betrifft die UI-Anzeige im Board-Header
- Die SOP-Auswahl ist im Project-Model als `default_sop_id` gespeichert
- Der Bug wurde bei der initialen Erstellung des Board-Views eingefuehrt

## Performance-Tracking

Da dieser Task als Test fuer den SOP-Prozess dient, bitte jede Phase dokumentieren
(Triage, ToDo, InProgress, Review, Done). Die 5-Sekunden-Verzoegerungen zwischen
den Phasen erlauben es dem User, die Kachel in jeder Phase zu sehen.
"""

SUCCESS_CRITERIA = [
    "Das SOP-Feld zeigt den Namen der aktuell gewaehlten SOP (NICHT 'Standard SOP')",
    "Bei Wechsel der SOP aendert sich die Anzeige sofort",
    "Wenn keine SOP gewaehlt ist, wird 'Keine SOP' oder aehnlich angezeigt",
    "Die Anzeige funktioniert fuer alle Boards im System",
]


def main():
    db = SessionLocal()
    try:
        # Pruefe ob default_sop_id gesetzt ist
        proj = db.get(Project, PROJECT_ID)
        if not proj:
            print("FEHLER: Projekt nicht gefunden")
            return
        if not proj.default_sop_id:
            print("WARNUNG: Projekt hat keine default_sop_id - Task wird trotzdem angelegt")

        # Task erstellen
        t = Task(
            id=secrets.token_hex(6),
            project_id=PROJECT_ID,
            title=TASK_TITLE,
            description=TASK_DESCRIPTION,
            status="triage",
            priority=60,
            category="bugfix",
            assigned_role="CIO",
            success_criteria=SUCCESS_CRITERIA,
            tags=["bugfix", "ui", "board", "sop-selection", "process-test"],
            task_type="bugfix",
        )
        db.add(t)
        db.flush()
        task_id = t.id

        # SOP-Instance starten
        sop_inst = SOPInstance(
            id=secrets.token_hex(6),
            sop_id=DEFAULT_SOP_ID,
            task_id=task_id,
            project_id=PROJECT_ID,
            current_step_id=None,
            status="running",
        )
        db.add(sop_inst)
        db.flush()

        # History-Eintrag
        th = TaskHistory(
            task_id=task_id,
            event="task_created",
            agent="user",
            details={
                "reason": "manual creation (SOP-process-test)",
                "sop_instance_id": sop_inst.id,
                "sop_id": DEFAULT_SOP_ID,
                "note": "Process-Test: User beobachten den Task durch alle Phasen (5s pro Phase)",
            },
        )
        db.add(th)
        db.commit()

        print("=" * 70)
        print("OK: TASK FUER SOP-PROZESS-TEST ERSTELLT")
        print("=" * 70)
        print()
        print(f"Task-ID:    {task_id}")
        print(f"Title:      {t.title[:80]}")
        print(f"Status:     {t.status}")
        print(f"Priority:   {t.priority}")
        print(f"Project:    {t.project_id}")
        print(f"SOP-Inst:   {sop_inst.id}")
        print(f"Default-SOP: {proj.name} ({proj.default_sop_id})")
        print()
        print("=" * 70)
        print("PROZESS-ABLAUF (User beobachtet)")
        print("=" * 70)
        print()
        print("Phase 1: TRIAGE (5s sichtbar)")
        print("  -> Der User sieht die Kachel in der Triage-Spalte")
        print("  -> Nach 5s bewertet der CIO den Task")
        print("  -> Wenn OK: Task geht zu ToDo")
        print()
        print("Phase 2: TODO (5s sichtbar)")
        print("  -> Der User sieht die Kachel in der ToDo-Spalte")
        print("  -> Nach 5s uebernimmt ein PI-Coder den Task")
        print("  -> Task geht zu InProgress")
        print()
        print("Phase 3: IN_PROGRESS (5s sichtbar)")
        print("  -> Der User sieht die Kachel in der InProgress-Spalte")
        print("  -> Nach 5s beginnt der PI-Coder mit der Arbeit")
        print("  -> Wenn fertig: Task geht zu Review")
        print()
        print("Phase 4: REVIEW (assigned_role=cio bei OK)")
        print("  -> Der User sieht die Kachel in der Review-Spalte")
        print("  -> Ein PI-Tester prueft den Code")
        print("  -> Wenn OK: assigned_role wird auf 'cio' gesetzt (Status bleibt review)")
        print()
        print("Phase 5: DONE")
        print("  -> Der CIO prueft das finale Ergebnis")
        print("  -> Wenn OK: Task geht zu Done")
        print()
        print("=" * 70)
        print("SOP-VERIFIKATION")
        print("=" * 70)
        print()
        print("Der SOP 'Standard-Workflow Development' hat 6 Steps:")
        print("  #0 CIO Triage Review")
        print("  #1 Worker Assignment")
        print("  #2 Worker Implementation (pi-coder)")
        print("  #3 Tester Code-Review (pi-tester)")
        print("  #4 CIO Final-Review")
        print("  #5 Done")
        print()
        print("ABER: Schritt 1 'Worker Assignment' setzt voraus, dass der")
        print("CIO einen Worker manuell zuweist. Im Auto-Workflow sollte der")
        print("Worker automatisch gewaehlt werden. Ggf. SOP anpassen.")

    finally:
        db.close()


if __name__ == "__main__":
    main()
