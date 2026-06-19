"""Ergaenzt SOP-Standard-Workflow Development mit 3-5-Kriterien-Anforderung.

Step #1 (Worker Assignment): Worker erstellt 3-5 testbare Erfolgskriterien.
Step #4 (CIO Final-Review): CIO prueft alle Kriterien, Freigabe nur bei allen OK.
"""
import sys
import os
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from sqlalchemy.orm.attributes import flag_modified
from app.db.base import SessionLocal
from app.models.sop import SOPStep


AI_INSTRUCTION_STEP1 = """# 1. Worker Assignment (CIO weist Worker zu + Kriterien werden definiert)

## Ziel
Der CIO weist den Task einem relevanten Worker zu UND der Worker (oder CIO)
erstellt 3-5 messbare, testbare Erfolgskriterien, die spaeter als Checkliste
im Detail-Panel angezeigt werden.

## Vorgehen
1. **Worker-Zuweisung**: Weise den Task dem passenden Worker zu (pi-coder, pi-tester, etc.)
2. **Kriterien erstellen (PFLICHT)**: Erstelle 3-5 messbare, testbare Erfolgskriterien als Bullet-Points.
   Die Kriterien werden in `task.success_criteria` gespeichert und 1:1 als Checkliste im
   Detail-Panel angezeigt.

## Regeln fuer gute Erfolgskriterien (User-Direktive 17.06.2026)

Jedes Kriterium MUSS:
1. **Testbar sein** - Man muss klar pruefen koennen, ob es erfuellt ist
2. **Messbar sein** - Quantitative Werte wo moeglich (z.B. "Coverage > 80%", "Response < 200ms")
3. **Konkret sein** - Keine vagen Aussagen wie "funktioniert gut"
4. **Verifizierbar sein** - Ein Tester muss es ohne Rueckfragen pruefen koennen

## Beispiele fuer gute Kriterien
- "User kann sich mit Google einloggen"
- "Login-Button funktioniert auf Mobile + Desktop"
- "Bestehende Unit-Tests laufen alle gruen"
- "Coverage fuer auth.py > 80%"
- "API antwortet in < 200ms bei 1000 RPS"
- "Keine offenen TODOs im Code"

## Output-Format
Schreibe die Kriterien als JSON-Liste in task.success_criteria:
```json
[
  "User kann sich mit Google einloggen",
  "Login-Button funktioniert auf Mobile + Desktop",
  "Bestehende Unit-Tests laufen alle gruen",
  "Coverage fuer auth.py > 80%"
]
```

## Was passiert, wenn die Kriterien fehlen?
- Der Worker kann nicht wissen, wann der Task "fertig" ist
- Der Tester kann nicht objektiv pruefen
- Der CIO kann bei der Freigabe nicht entscheiden
- Der Task bleibt in einer Endlosschleife

## WICHTIG
Diese Kriterien sind das "Definition of Done" - sie beantworten die Frage
"Wie wissen wir, dass es funktioniert?". Ohne sie ist der Task nicht abgeschlossen.
"""

AI_INSTRUCTION_STEP4 = """# 4. CIO Final-Review (Freigabe)

## Ziel
Der CIO prueft, ob das Ergebnis ALLE Erfolgskriterien erfuellt und gibt
den Task frei (Done) oder zurueck (Loop-Back zu Step #1).

## Vorgehen
1. **Lese task.success_criteria** - das sind die Kriterien aus Step #1
2. **Pruefe JEDES Kriterium** einzeln:
   - Erfuellt? -> Checkbox abhaken
   - Nicht erfuellt? -> Kommentar warum, Loop-Back zu Step #1
3. **Entscheidung**:
   - ALLE Kriterien erfuellt -> task.status = done, Freigabe
   - EIN Kriterium nicht erfuellt -> task.status = todo, Loop-Back zu Step #1

## PFLICHT: Kriterien-Check
Bevor die Freigabe erfolgt, MUSS der CIO bestaetigen:
- [ ] Alle 3-5 Kriterien aus task.success_criteria sind erfuellt
- [ ] Keine offenen TODOs im Code
- [ ] Keine bekannten Bugs
- [ ] Tests sind gruen

## Wenn Kriterien fehlen oder unvollstaendig sind
Falls task.success_criteria leer oder < 3 Kriterien:
- FORDERE Worker auf, die Kriterien zu ergaenzen
- Loop-Back zu Step #1
- Task ist NICHT ready fuer Freigabe

## WICHTIG
Diese Pruefung ist der letzte Quality-Gate. Der CIO ist dafuer verantwortlich,
dass NUR Task mit allen erfuellten Kriterien in "done" gehen.
"""


def main():
    db = SessionLocal()
    try:
        # Step #1 (Worker Assignment) - Kriterien erstellen
        step1 = db.query(SOPStep).filter(
            SOPStep.sop_id == "7c86692be939", SOPStep.step_order == 1
        ).first()
        if step1:
            ap = dict(step1.action_params or {})
            ap["ai_instructions_md"] = AI_INSTRUCTION_STEP1
            step1.action_params = ap
            flag_modified(step1, "action_params")
            print(f"OK: Step #1 (Worker Assignment) - ai_instructions_md: {len(AI_INSTRUCTION_STEP1)}b")

        # Step #4 (CIO Final-Review) - Kriterien pruefen
        step4 = db.query(SOPStep).filter(
            SOPStep.sop_id == "7c86692be939", SOPStep.step_order == 4
        ).first()
        if step4:
            ap = dict(step4.action_params or {})
            ap["ai_instructions_md"] = AI_INSTRUCTION_STEP4
            step4.action_params = ap
            flag_modified(step4, "action_params")
            print(f"OK: Step #4 (CIO Final-Review) - ai_instructions_md: {len(AI_INSTRUCTION_STEP4)}b")

        db.commit()
        print()
        print("FERTIG: SOP-Standard-Workflow Development hat jetzt Kriterien-Anweisungen")
        print()
        print("Step #1: Worker erstellt 3-5 testbare Erfolgskriterien in task.success_criteria")
        print("Step #4: CIO prueft ALLE Kriterien, Freigabe nur bei allen OK")
    finally:
        db.close()


if __name__ == "__main__":
    main()
