"""Erstellt den Development SOP als Standard-Workflow.

Architektur (8 Schritte + 4 Loop-Back-Rules):

  #0  USER-Aufgabeneingang
      -> User legt Task in Triage an (status=triage)

  #1  CIO-Eingangspruefung (Triage)
      Pruefungen:
        - Task richtig bei diesem Board?
        - Aufgabe ausreichend beschrieben?
        - Negative Einflusse auf Stabilitaet/Sicherheit?
        - Wunschkriterium klar (was/wie)?
        - Rollen klar?
      3 Optionen:
        A) Ablehnen: last_rejection_reason setzen, status=rejected
        B) Rueckfrage: AgentQuestion erstellen, Task wartet auf User-Antwort
        C) OK: dev_sop_phase=worker_understanding, status=todo, Bearbeiter waehlen

  #2  Bearbeiter-Uebernahme + Analyse (ToDo -> InProgress)
      Bearbeiter uebernimmt Task, analysiert, schreibt sein Understanding
      in task.worker_understanding. dev_sop_phase=worker_understanding.

  #3  CIO-Bestaetigung des Understandings (Gate)
      CIO vergleicht Auftrag mit worker_understanding.
      2 Optionen:
        A) Bestaetigt: worker_understanding_confirmed=true, Phase=implementing
        B) Nicht bestaetigt: zurueck zu #2 (Bearbeiter muss nachjustieren)

  #4  Implementierung (InProgress)
      Bearbeiter implementiert. Bei Rueckfragen: AgentQuestion mit Empfaenger
      + Phase=user_input_blocked. Wartet auf Antwort in derselben Session.

  #5  Code-Review (Review)
      Reviewer untersucht Code: Verbesserungen, Fehler, Schwachstellen, Security.
      2 Optionen:
        A) OK: review_findings=leer, Phase=bza
        B) Findings: review_findings setzen, zurueck zu #2 (gleicher Bearbeiter)
      Loop-Back: review_iteration_count++
      Max 5 Iterationen, sonst eskalieren.

  #6  CIO-BZA (Review)
      Bereit zur Abnahme. CIO prueft Ergebnis.
      2 Optionen:
        A) Freigabe: status=done, dev_sop_phase=done
        B) Maengelliste: bza_findings setzen, zurueck zu #2 (gleicher Bearbeiter)
      Loop-Back: bza_iteration_count++

  #7  Done (End)
      Task abgeschlossen.

Performance-Tracking: Jeder Phasen-Wechsel wird via TaskTransition dokumentiert
mit agent, reason, details, performance_metrics (iteration_count, phase_dauer).
"""
import sys
import os
import json
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from sqlalchemy.orm.attributes import flag_modified
from app.db.base import SessionLocal
from app.models.sop import SOP, SOPStep, SOPStepRule


def main():
    db = SessionLocal()
    try:
        print("=" * 70)
        print("DEVELOPMENT SOP erstellen")
        print("=" * 70)

        # === 1) SOP anlegen ===
        dev_sop = SOP(
            id=uuid.uuid4().hex[:12],
            name="Development SOP (Standard-Workflow)",
            description=(
                "Standard-Workflow fuer Software-Entwicklung mit Quality-Gates. "
                "User-Direktive 17.06.2026: 8 Schritte + 4 Loop-Back-Rules, "
                "Performance-Tracking pro Phase, iterative Verbesserung. "
                "Phasen: Triage -> Worker-Understanding -> Implementierung -> "
                "Code-Review -> BZA -> Done."
            ),
            category="development",
            version=1,
            is_template=True,
            default_delay_s=5.0,
            bpmn_xml=None,
            uml_sequence_diagram=None,
        )
        db.add(dev_sop)
        db.flush()
        print(f"OK: SOP erstellt: {dev_sop.id} | {dev_sop.name}")

        # === 2) Steps anlegen ===
        steps_data = [
            {
                "step_order": 0,
                "name": "0. User-Aufgabeneingang",
                "agent": "user",
                "phase": "Task",
                "trigger": "manual",
                "action": "noop",
                "delay_s": 0.0,
                "description": (
                    "## User-Aufgabeneingang\n\n"
                    "**Trigger:** Neuer Task wird angelegt (POST /api/kanban/tasks)\n"
                    "**Initial-Status:** triage\n"
                    "**Initial-Phase:** dev_sop_phase=triage\n\n"
                    "Der User fuellt Titel + Description + Success-Criteria aus. "
                    "Sobald der Task angelegt ist, geht er automatisch in den "
                    "CIO-Eingangspruefung-Schritt (Step 1)."
                ),
                "expected_result": (
                    "Task angelegt mit status=triage, dev_sop_phase=triage. "
                    "SOP-Instance startet, fuehrt Step 1 (CIO-Eingangspruefung) aus."
                ),
                "success_criteria": [
                    "Task hat Titel, Description, Success-Criteria",
                    "Task ist dem richtigen Board/Projekt zugeordnet",
                    "Priority ist gesetzt",
                ],
                "input_tool_required": False,
                "ai_instructions_md": (
                    "# 0. User-Aufgabeneingang\n\n"
                    "## Ziel\n"
                    "Sammle die initiale User-Anforderung und lege den Task in Triage an.\n\n"
                    "## Vorgehen\n"
                    "1. Frage den User nach: Titel, Description, Acceptance Criteria, Prioritaet, Project\n"
                    "2. Lege den Task via POST /api/kanban/tasks an mit status=triage\n"
                    "3. Starte die SOP-Instance (POST /api/sops/{dev_sop_id}/start) -> fuehrt Step 1 aus\n"
                ),
            },
            {
                "step_order": 1,
                "name": "1. CIO-Eingangspruefung (Triage)",
                "agent": "cio",
                "phase": "Task",
                "trigger": "step_completed",
                "action": "llm_call",
                "delay_s": 5.0,
                "description": (
                    "## CIO-Eingangspruefung\n\n"
                    "**Verantwortlich:** CIO\n"
                    "**Input:** Task (Title, Description, Success-Criteria)\n"
                    "**Output:** Entscheidung: ablehnen / rueckfragen / freigeben\n\n"
                    "### Pruefungen (5 Dimensionen)\n"
                    "1. **Board-Korrektheit:** Gehoert der Task zu diesem Board/Projekt?\n"
                    "2. **Beschreibungs-Vollstaendigkeit:** Ist die Aufgabe ausreichend beschrieben, "
                    "damit ein Worker sie umsetzen kann? (min 200 Woerter, Use Cases, Akzeptanzkriterien)\n"
                    "3. **Stabilitaet/Sicherheit:** Enthaelt die Anforderung Dinge, die die "
                    "App-Stabilitaet oder -Security negativ beeinflussen?\n"
                    "4. **Wunschkriterium-Klarheit:** Ist klar WAS erreicht werden soll "
                    "(Ergebnis) und WIE (Ansatz, Technologie, Constraints)?\n"
                    "5. **Rollen-Klarheit:** Ist klar, welche Rollen (pi-coder, pi-tester, "
                    "pi-reviewer, pi-fixer) fuer die Umsetzung gebraucht werden?\n\n"
                    "### 3 Optionen\n"
                    "A) **Ablehnen** (nicht freigeben): last_rejection_reason setzen, status=rejected\n"
                    "B) **Rueckfrage:** AgentQuestion erstellen mit fehlenden Punkten\n"
                    "C) **OK:** Worker-Rolle waehlen, status=todo, dev_sop_phase=worker_understanding"
                ),
                "expected_result": (
                    "CIO hat alle 5 Dimensionen geprueft. Eine der 3 Optionen wurde ausgewaehlt. "
                    "Task hat entsprechenden Status und Phase."
                ),
                "success_criteria": [
                    "5 Pruefungs-Dimensionen wurden bewertet",
                    "Eine der 3 Optionen (ablehnen/rueckfragen/freigeben) wurde gewaehlt",
                    "Bei Ablehnung: last_rejection_reason ist gesetzt",
                    "Bei Rueckfrage: AgentQuestion wurde erstellt",
                    "Bei Freigabe: Worker-Rolle wurde zugewiesen, dev_sop_phase=worker_understanding",
                ],
                "input_tool_required": True,
                "input_tool_type": "text",
                "input_tool_prompt": (
                    "Pruefungsergebnis: Welche Punkte sind unklar oder fehlen? (Mehrfachauswahl moeglich)\n"
                    "Optionen: 1) Board-Korrektheit 2) Beschreibungs-Vollstaendigkeit "
                    "3) Stabilitaet/Sicherheit 4) Wunschkriterium-Klarheit 5) Rollen-Klarheit"
                ),
                "input_tool_description": (
                    "Der CIO hat die initiale Pruefung durchgefuehrt und einige Punkte "
                    "sind unklar. Bitte ergaenze die fehlenden Informationen."
                ),
                "input_tool_recommendation": (
                    "Empfehlung: Beantworte die Punkte einzeln und konkret. "
                    "Nutze GIVEN-WHEN-THEN fuer Akzeptanzkriterien."
                ),
                "input_tool_context_key": "cio_clarifications",
                "ai_instructions_md": (
                    "# 1. CIO-Eingangspruefung\n\n"
                    "## Ziel\n"
                    "Pruefe die initiale User-Anforderung auf 5 Dimensionen und entscheide.\n\n"
                    "## Vorgehen\n"
                    "1. Lese Task.title, description, success_criteria\n"
                    "2. Pruefe jede der 5 Dimensionen (siehe Description)\n"
                    "3. Erstelle eine Liste der Findings pro Dimension\n"
                    "4. Waehle eine der 3 Optionen:\n"
                    "   - **Ablehnen**: wenn Aufgabe fundamental nicht passt\n"
                    "     -> setze last_rejection_reason, status=rejected\n"
                    "   - **Rueckfrage**: wenn 1-3 Punkte unklar sind\n"
                    "     -> erstelle AgentQuestion mit type=text, context.task_id\n"
                    "   - **OK**: wenn alles klar ist\n"
                    "     -> waehle Worker-Rolle, status=todo, dev_sop_phase=worker_understanding\n\n"
                    "## Wichtig\n"
                    "- **Konkret sein**: nicht 'mehr Details noetig', sondern 'Akzeptanzkriterien fehlen'\n"
                    "- **Konstruktiv**: zeige was fehlt, nicht was schlecht ist\n"
                ),
            },
            {
                "step_order": 2,
                "name": "2. Bearbeiter-Uebernahme + Auftragsbestaetigung",
                "agent": "pi-coder",
                "phase": "Task",
                "trigger": "step_completed",
                "action": "llm_call",
                "delay_s": 5.0,
                "description": (
                    "## Bearbeiter-Uebernahme + Auftragsbestaetigung\n\n"
                    "**Verantwortlich:** Bearbeiter (z.B. pi-coder, pi-tester, pi-reviewer)\n"
                    "**Input:** Task mit allen CIO-freigegebenen Infos\n"
                    "**Output:** task.worker_understanding = Auftragsbestaetigung in eigenen Worten\n\n"
                    "### Vorgehen\n"
                    "1. Bearbeiter uebernimmt Task (status: todo -> in_progress)\n"
                    "2. Analysiert die Aufgabe gruendlich\n"
                    "3. Formuliert das Verstaendnis in eigenen Worten\n"
                    "4. Schreibt es in task.worker_understanding (NEUES FELD)\n"
                    "5. Setzt task.worker_understanding_at = now()\n"
                    "6. dev_sop_phase = worker_understanding\n\n"
                    "### Wichtig\n"
                    "**Bearbeiter schliesst die Session NICHT**, sondern wartet auf "
                    "Feedback vom CIO (Schritt 3)."
                ),
                "expected_result": (
                    "Task hat status=in_progress, dev_sop_phase=worker_understanding. "
                    "task.worker_understanding ist gefuellt mit der Auftragsbestaetigung des "
                    "Bearbeiters in seinen eigenen Worten. "
                    "task.worker_understanding_at ist gesetzt."
                ),
                "success_criteria": [
                    "Status: todo -> in_progress",
                    "task.worker_understanding ist gefuellt (min 50 Woerter)",
                    "task.worker_understanding_at ist gesetzt",
                    "dev_sop_phase = worker_understanding",
                    "Bearbeiter wartet auf Feedback in der Session (schliesst NICHT)",
                ],
                "input_tool_required": False,
                "ai_instructions_md": (
                    "# 2. Bearbeiter-Uebernahme + Auftragsbestaetigung\n\n"
                    "## Ziel\n"
                    "Bearbeiter uebernimmt den Task und formuliert sein Verstaendnis der Aufgabe in eigenen Worten.\n\n"
                    "## Vorgehen\n"
                    "1. Lese task.title, description, success_criteria\n"
                    "2. Analysiere: Was ist die Kern-Aufgabe? Welche Akzeptanzkriterien? Welche Edge-Cases?\n"
                    "3. Formuliere dein Verstaendnis in EIGENEN WORTEN (nicht abschreiben!)\n"
                    "4. Setze task.worker_understanding = dein Verstaendnis\n"
                    "5. Setze task.worker_understanding_at = now()\n"
                    "6. Setze task.status = in_progress\n"
                    "7. Setze task.dev_sop_phase = worker_understanding\n\n"
                    "## Wichtig\n"
                    "- **NICHT die Original-Beschreibung abschreiben**\n"
                    "- **In eigenen Worten** formulieren (zeigt Verstaendnis)\n"
                    "- **Konkrete Beispiele** fuer Akzeptanzkriterien nennen\n"
                    "- **Edge-Cases** mitdenken\n"
                    "- **WICHTIG**: Session bleibt OFFEN, du wartest auf Feedback vom CIO\n"
                ),
            },
            {
                "step_order": 3,
                "name": "3. CIO-Bestaetigung des Understandings (Gate)",
                "agent": "cio",
                "phase": "Task",
                "trigger": "step_completed",
                "action": "llm_call",
                "delay_s": 5.0,
                "description": (
                    "## CIO-Bestaetigung des Understandings (Gate)\n\n"
                    "**Verantwortlich:** CIO\n"
                    "**Input:** task.worker_understanding (Auftragsbestaetigung des Bearbeiters)\n"
                    "**Output:** worker_understanding_confirmed = true/false\n\n"
                    "### Vorgehen\n"
                    "1. CIO vergleicht seinen Original-Auftrag mit task.worker_understanding\n"
                    "2. Prueft: Hat der Bearbeiter den Task richtig verstanden?\n"
                    "3. **Optionen:**\n"
                    "   - **Bestaetigt**: worker_understanding_confirmed = true, "
                    "     dev_sop_phase = implementing, weiter zu Schritt 4\n"
                    "   - **Nicht bestaetigt**: zurueck zu Schritt 2 (Bearbeiter muss nachjustieren)\n\n"
                    "### Wichtig\n"
                    "Wenn der Bearbeiter den Task nicht richtig verstanden hat, ist eine "
                    "fruehe Korrektur besser als spaete. Lieber einmal mehr hin und her, "
                    "als dass der Bearbeiter etwas Falsches implementiert."
                ),
                "expected_result": (
                    "CIO hat das Understanding geprueft. "
                    "worker_understanding_confirmed = true (bestätigt) oder false (Loop-Back zu Schritt 2). "
                    "Bei Bestaetigung: dev_sop_phase = implementing."
                ),
                "success_criteria": [
                    "Original-Auftrag mit worker_understanding wurde verglichen",
                    "worker_understanding_confirmed wurde gesetzt",
                    "Bei Bestaetigung: dev_sop_phase = implementing",
                    "Bei Ablehnung: Loop-Back zu Schritt 2",
                ],
                "input_tool_required": False,
                "ai_instructions_md": (
                    "# 3. CIO-Bestaetigung des Understandings\n\n"
                    "## Ziel\n"
                    "Pruefe, ob der Bearbeiter den Task richtig verstanden hat, bevor er implementiert.\n\n"
                    "## Vorgehen\n"
                    "1. Lese task.description (Original-Auftrag)\n"
                    "2. Lese task.worker_understanding (Bearbeiter-Verstaendnis)\n"
                    "3. Vergleiche: Hat der Bearbeiter die Kern-Aufgabe richtig erfasst?\n"
                    "4. Pruefe: Sind die Akzeptanzkriterien korrekt interpretiert?\n"
                    "5. Pruefe: Sind Edge-Cases beruecksichtigt?\n\n"
                    "## Entscheidung\n"
                    "- **OK**: worker_understanding_confirmed = true, dev_sop_phase = implementing\n"
                    "  -> weiter zu Schritt 4 (Implementierung)\n"
                    "- **NICHT OK**: worker_understanding_confirmed = false\n"
                    "  -> zurueck zu Schritt 2 (Bearbeiter muss nachjustieren)\n\n"
                    "## Wichtig\n"
                    "- Fruehe Korrektur ist besser als spaete (schoen implementiert, aber falsch verstanden)\n"
                    "- Lieber einmal mehr hin und her\n"
                    "- Sei konstruktiv in der Rueckmeldung\n"
                ),
            },
            {
                "step_order": 4,
                "name": "4. Implementierung (mit iterativen Rueckfragen)",
                "agent": "pi-coder",
                "phase": "Task",
                "trigger": "step_completed",
                "action": "llm_call",
                "delay_s": 10.0,
                "description": (
                    "## Implementierung\n\n"
                    "**Verantwortlich:** Bearbeiter (z.B. pi-coder)\n"
                    "**Input:** Bestaetigtes Verstaendnis aus Schritt 3\n"
                    "**Output:** Implementierter Code + Tests\n\n"
                    "### Vorgehen\n"
                    "1. Bearbeiter implementiert gemaess dem bestaetigten Verstaendnis\n"
                    "2. Schreibt Tests parallel zur Implementation\n"
                    "3. Bei **Rueckfragen** waehrend der Implementierung:\n"
                    "   - Erstellt AgentQuestion (type=text) mit Empfaenger (z.B. CIO, CEO-digital, pi-reviewer)\n"
                    "   - Setzt task.status = rueckfrage\n"
                    "   - Wartet in der Session auf Antwort (schliesst NICHT)\n"
                    "4. Bei Antwort: weiter mit Implementation\n"
                    "5. Wenn fertig: status = review, dev_sop_phase = review\n\n"
                    "### Wichtig\n"
                    "**Der Bearbeiter wartet in der Session auf Feedback und schliesst nicht.** "
                    "Iterative Schleife: Implementierung -> Rueckfrage -> Antwort -> Implementierung -> ... "
                    "bis alles umgesetzt ist."
                ),
                "expected_result": (
                    "Code + Tests sind implementiert. "
                    "task.status = review, dev_sop_phase = review. "
                    "Alle offenen Rueckfragen wurden beantwortet."
                ),
                "success_criteria": [
                    "Code wurde gemaess Verstaendnis implementiert",
                    "Tests wurden geschrieben",
                    "Alle Rueckfragen wurden beantwortet",
                    "task.status = review, dev_sop_phase = review",
                ],
                "input_tool_required": False,
                "ai_instructions_md": (
                    "# 4. Implementierung\n\n"
                    "## Ziel\n"
                    "Implementiere die Aufgabe gemaess dem bestaetigten Verstaendnis.\n\n"
                    "## Vorgehen\n"
                    "1. Lese task.worker_understanding (das bestaetigte Verstaendnis)\n"
                    "2. Plane die Implementation in kleinen, testbaren Schritten\n"
                    "3. Implementiere Code + Tests parallel (TDD empfohlen)\n"
                    "4. Bei Rueckfragen:\n"
                    "   - **Empfaenger benennen** (CIO fuer Architektur, CEO fuer User-Fragen, "
                    "     pi-reviewer fuer technische Tiefe)\n"
                    "   - AgentQuestion erstellen mit Empfaenger in context.recipient\n"
                    "   - task.status = rueckfrage\n"
                    "   - WICHTIG: Session bleibt OFFEN, du wartest auf Antwort\n"
                    "5. Bei Antwort: weiter implementieren\n"
                    "6. Wenn fertig: status = review, dev_sop_phase = review\n\n"
                    "## Wichtig\n"
                    "- **Iterativ arbeiten**: kleine Schritte, immer testbar\n"
                    "- **Tests nicht vergessen**: coverage sollte >= 80% sein\n"
                    "- **Bei Unsicherheit**: fragen statt raten\n"
                    "- **Session bleibt OFFEN** waehrend Rueckfragen\n"
                ),
            },
            {
                "step_order": 5,
                "name": "5. Code-Review (intensive Pruefung)",
                "agent": "pi-reviewer",
                "phase": "Task",
                "trigger": "step_completed",
                "action": "llm_call",
                "delay_s": 15.0,
                "description": (
                    "## Code-Review\n\n"
                    "**Verantwortlich:** pi-reviewer (Code-Reviewer)\n"
                    "**Input:** Implementierter Code + Tests\n"
                    "**Output:** review_findings (Liste) oder leer (OK)\n\n"
                    "### Vorgehen\n"
                    "1. Reviewer liest den Code intensiv durch\n"
                    "2. Prueft auf:\n"
                    "   - **Verbesserungen** (Lesbarkeit, Architektur, Performance)\n"
                    "   - **Fehler** (Logik, Edge-Cases, Race-Conditions)\n"
                    "   - **Schwachstellen** (Anti-Patterns, Tech-Debt)\n"
                    "   - **Security-Issues** (OWASP Top 10, Input-Validation, Auth, Crypto)\n"
                    "   - **Tests** (Coverage, Edge-Cases, Test-Quality)\n"
                    "3. **Bei Findings:**\n"
                    "   - review_findings = Liste der Findings (mit Pfad, Zeile, Problem, Vorschlag)\n"
                    "   - review_iteration_count++\n"
                    "   - Loop-Back zu Schritt 2 (gleicher Bearbeiter nimmt wieder auf)\n"
                    "4. **Ohne Findings:**\n"
                    "   - review_findings = leer\n"
                    "   - dev_sop_phase = bza (CIO-Abnahme)\n\n"
                    "### Wichtig\n"
                    "Max 5 Review-Iterationen, sonst eskalieren. "
                    "Pro Iteration lernt der Bearbeiter aus den Findings."
                ),
                "expected_result": (
                    "Code wurde auf 4 Dimensionen geprueft (Verbesserungen, Fehler, "
                    "Schwachstellen, Security). Entweder OK (leere Findings, Phase=bza) "
                    "oder Findings (Loop-Back zu Schritt 2)."
                ),
                "success_criteria": [
                    "Code wurde auf Verbesserungen geprueft",
                    "Code wurde auf Fehler geprueft",
                    "Code wurde auf Schwachstellen geprueft",
                    "Code wurde auf Security-Issues geprueft (OWASP Top 10)",
                    "Tests wurden geprueft (Coverage, Quality)",
                    "review_findings wurde gesetzt (oder leer bei OK)",
                ],
                "input_tool_required": False,
                "ai_instructions_md": (
                    "# 5. Code-Review\n\n"
                    "## Ziel\n"
                    "Pruefe den implementierten Code auf Qualitaet, Fehler, Schwachstellen und Security.\n\n"
                    "## Vorgehen\n"
                    "1. Lese den implementierten Code + Tests\n"
                    "2. Pruefe 4 Dimensionen:\n"
                    "   - **Verbesserungen**: Lesbarkeit, Architektur, Performance, Maintainability\n"
                    "   - **Fehler**: Logik, Edge-Cases, Race-Conditions, Off-by-one\n"
                    "   - **Schwachstellen**: Anti-Patterns, Code-Smells, Tech-Debt\n"
                    "   - **Security**: OWASP Top 10, Input-Validation, Auth, Crypto, Logging\n"
                    "3. Erstelle review_findings als JSON-Liste:\n"
                    "   ```json\n"
                    "   [{\n"
                    "     \"file\": \"src/api/users.py\",\n"
                    "     \"line\": 42,\n"
                    "     \"category\": \"security\",\n"
                    "     \"severity\": \"high\",\n"
                    "     \"issue\": \"SQL-Injection moeglich\",\n"
                    "     \"suggestion\": \"Verwende Parameterized Queries\"\n"
                    "   }]\n"
                    "   ```\n"
                    "4. **Bei Findings**:\n"
                    "   - task.review_findings = JSON-Liste\n"
                    "   - task.review_iteration_count++\n"
                    "   - Loop-Back zu Schritt 2 (Bearbeiter nimmt wieder auf)\n"
                    "5. **Ohne Findings**:\n"
                    "   - task.review_findings = leere Liste\n"
                    "   - task.dev_sop_phase = bza (Bereit zur Abnahme)\n\n"
                    "## Wichtig\n"
                    "- **Konstruktiv**: nicht nur meckern, sondern Loesung vorschlagen\n"
                    "- **Priorisiert**: critical > high > medium > low\n"
                    "- **Max 5 Iterationen** (sonst eskalieren an CEO)\n"
                ),
            },
            {
                "step_order": 6,
                "name": "6. CIO-Abnahme (BZA)",
                "agent": "cio",
                "phase": "Task",
                "trigger": "step_completed",
                "action": "llm_call",
                "delay_s": 10.0,
                "description": (
                    "## CIO-Abnahme (BZA = Bereit zur Abnahme)\n\n"
                    "**Verantwortlich:** CIO\n"
                    "**Input:** Review-freigegebener Code (review_findings = leer)\n"
                    "**Output:** Freigabe (status=done) oder Maengelliste (Loop-Back)\n\n"
                    "### Vorgehen\n"
                    "1. CIO prueft, ob das Ergebnis erreicht wurde:\n"
                    "   - Sind alle Akzeptanzkriterien erfuellt?\n"
                    "   - Sind die Wunschkriterien umgesetzt?\n"
                    "   - Sind die Review-Findings adressiert?\n"
                    "2. **Bei Freigabe**:\n"
                    "   - task.status = done\n"
                    "   - task.dev_sop_phase = done\n"
                    "   - Performance-Metriken finalisieren\n"
                    "3. **Bei Maengeln**:\n"
                    "   - bza_findings = Liste der Maengel\n"
                    "   - bza_iteration_count++\n"
                    "   - Loop-Back zu Schritt 2 (gleicher Bearbeiter, alles nochmal)\n"
                    "   - Alle nachfolgenden Schritte werden wieder durchlaufen\n\n"
                    "### Wichtig\n"
                    "Iterative Schleife: BZA -> Maengel -> Implementierung -> Review -> BZA -> ... "
                    "bis CIO alles freigibt und der Task in DONE laeuft."
                ),
                "expected_result": (
                    "CIO hat das Ergebnis geprueft. "
                    "Entweder Freigabe (status=done, dev_sop_phase=done) "
                    "oder Maengelliste (bza_findings, Loop-Back zu Schritt 2)."
                ),
                "success_criteria": [
                    "Akzeptanzkriterien wurden validiert",
                    "Wunschkriterien wurden geprueft",
                    "Review-Findings wurden adressiert",
                    "Bei Freigabe: status=done, dev_sop_phase=done",
                    "Bei Maengeln: bza_findings wurde gesetzt",
                ],
                "input_tool_required": False,
                "ai_instructions_md": (
                    "# 6. CIO-Abnahme (BZA)\n\n"
                    "## Ziel\n"
                    "Pruefe das Ergebnis und gib frei oder erstelle Maengelliste.\n\n"
                    "## Vorgehen\n"
                    "1. Lese task.description (Original-Anforderungen)\n"
                    "2. Lese task.success_criteria (Akzeptanzkriterien)\n"
                    "3. Pruefe das tatsaechliche Ergebnis:\n"
                    "   - Sind alle Akzeptanzkriterien erfuellt?\n"
                    "   - Sind die Wunschkriterien umgesetzt?\n"
                    "   - Sind die Review-Findings adressiert?\n\n"
                    "## Entscheidung\n"
                    "- **Freigabe**:\n"
                    "  - task.status = done\n"
                    "  - task.dev_sop_phase = done\n"
                    "  - Performance-Metriken finalisieren\n"
                    "  - Task ist komplett abgeschlossen\n"
                    "- **Maengel**:\n"
                    "  - bza_findings = JSON-Liste der Maengel\n"
                    "  - bza_iteration_count++\n"
                    "  - Loop-Back zu Schritt 2 (gleicher Bearbeiter)\n\n"
                    "## Wichtig\n"
                    "- Sei **streng** aber **fair**: das ist die Endkontrolle\n"
                    "- **Konstruktiv**: zeige was fehlt, nicht nur 'schlecht'\n"
                    "- **Max 3 BZA-Iterationen** (sonst eskalieren an CEO)\n"
                ),
            },
            {
                "step_order": 7,
                "name": "7. Done (End)",
                "agent": "system",
                "phase": "End",
                "trigger": "step_completed",
                "action": "noop",
                "delay_s": 0.0,
                "description": (
                    "## Done (End)\n\n"
                    "**Status:** task.status = done\n"
                    "**Phase:** dev_sop_phase = done\n\n"
                    "Der Task ist komplett abgeschlossen. Performance-Metriken werden "
                    "finalisiert und in der TaskTransition-Tabelle dokumentiert. "
                    "Der gleiche Bearbeiter wird fuer die naechste Iteration informiert."
                ),
                "expected_result": (
                    "Task ist auf done gesetzt, dev_sop_phase=done. "
                    "Alle Performance-Metriken (Anzahl Iterationen, Gesamt-Dauer) "
                    "sind in der TaskTransition-Tabelle dokumentiert."
                ),
                "success_criteria": [
                    "task.status = done",
                    "task.dev_sop_phase = done",
                    "Performance-Metriken sind dokumentiert",
                ],
                "input_tool_required": False,
                "ai_instructions_md": (
                    "# 7. Done (End)\n\n"
                    "Der Task ist komplett abgeschlossen. Keine weiteren Aktionen noetig.\n\n"
                    "## Performance-Metriken (automatisch erfasst)\n"
                    "- Anzahl Phasen-Wechsel\n"
                    "- Anzahl Review-Iterationen\n"
                    "- Anzahl BZA-Iterationen\n"
                    "- Gesamt-Dauer pro Phase\n"
                    "- Anzahl AgentQuestions (Rueckfragen)\n\n"
                    "Diese Metriken werden in der TaskTransition-Tabelle gespeichert "
                    "und koennen spaeter fuer Prozess-Optimierungen analysiert werden."
                ),
            },
        ]

        step_ids = {}  # step_order -> step_id
        for sd in steps_data:
            step_id = uuid.uuid4().hex[:12]
            step_ids[sd["step_order"]] = step_id
            s = SOPStep(
                id=step_id,
                sop_id=dev_sop.id,
                step_order=sd["step_order"],
                name=sd["name"],
                phase=sd["phase"],
                trigger=sd["trigger"],
                action=sd["action"],
                action_params={
                    "ai_instructions_md": sd.get("ai_instructions_md", ""),
                } if sd.get("ai_instructions_md") else {},
                agent=sd["agent"],
                raci_r=sd["agent"],
                raci_a="cio",
                raci_c="ceo-digital",
                raci_i="ceo-digital",
                description=sd["description"],
                expected_result=sd["expected_result"],
                success_criteria=sd.get("success_criteria", []),
                subagent_requirements=[],
                standards_refs=[
                    "openbrain:vorlage-it-projekt-anforderungsdokument",
                    "openbrain:vorlage-business-anforderungsdokument",
                ],
                task_types=["development_workflow"],
                change_requirements=[],
                delay_s=sd["delay_s"],
                input_tool_required=sd.get("input_tool_required", False),
                input_tool_type=sd.get("input_tool_type"),
                input_tool_prompt=sd.get("input_tool_prompt"),
                input_tool_description=sd.get("input_tool_description"),
                input_tool_recommendation=sd.get("input_tool_recommendation"),
                input_tool_options=None,
                input_tool_options_config=None,
                input_tool_context_key=sd.get("input_tool_context_key"),
                next_step_id=None,  # wird nachher gesetzt
                fail_step_id=None,
            )
            db.add(s)
            print(f"  Step #{sd['step_order']}: {step_id} | {sd['name'][:50]}")
        db.flush()

        # === 3) next_step_id Chain aufbauen (linear) ===
        for i in range(len(step_ids) - 1):
            cur_id = step_ids[i]
            next_id = step_ids[i + 1]
            cur = db.query(SOPStep).filter(SOPStep.id == cur_id).first()
            if cur:
                cur.next_step_id = next_id
        # Letzter Step (Done): kein next
        db.commit()

        # === 4) Rules fuer Loop-Back hinzufuegen ===
        # Step 3 (CIO-Bestaetigung): bei nicht bestaetigt -> zurueck zu Step 2
        r1 = SOPStepRule(
            id=uuid.uuid4().hex[:12],
            step_id=step_ids[3],
            rule_order=0,
            description="Wenn CIO das Understanding nicht bestaetigt -> zurueck zu Schritt 2 (Bearbeiter justiert nach)",
            condition_field="worker_understanding_confirmed",
            condition_operator="is_false",
            condition_value=False,
            action_type="goto_step",
            action_target=step_ids[2],
            action_params={
                "loop_back": True,
                "reason": "cio_understanding_not_confirmed",
            },
        )
        # Step 5 (Code-Review): bei Findings -> zurueck zu Step 2
        r2 = SOPStepRule(
            id=uuid.uuid4().hex[:12],
            step_id=step_ids[5],
            rule_order=0,
            description="Wenn Code-Review Findings hat -> zurueck zu Schritt 2 (Bearbeiter korrigiert)",
            condition_field="review_findings_count",
            condition_operator="gt",
            condition_value=0,
            action_type="goto_step",
            action_target=step_ids[2],
            action_params={
                "loop_back": True,
                "reason": "review_findings",
                "max_iterations": 5,
            },
        )
        r2_default = SOPStepRule(
            id=uuid.uuid4().hex[:12],
            step_id=step_ids[5],
            rule_order=1,
            description="Wenn Code-Review keine Findings hat -> weiter zu BZA (Schritt 6)",
            condition_field="review_findings_count",
            condition_operator="is_zero",
            condition_value=0,
            action_type="goto_step",
            action_target=step_ids[6],
            action_params={},
        )
        # Step 6 (BZA): bei Maengeln -> zurueck zu Schritt 2
        r3 = SOPStepRule(
            id=uuid.uuid4().hex[:12],
            step_id=step_ids[6],
            rule_order=0,
            description="Wenn BZA Maengel findet -> zurueck zu Schritt 2 (Bearbeiter korrigiert, alle Schritte neu)",
            condition_field="bza_findings_count",
            condition_operator="gt",
            condition_value=0,
            action_type="goto_step",
            action_target=step_ids[2],
            action_params={
                "loop_back": True,
                "reason": "bza_findings",
                "max_iterations": 3,
            },
        )
        r3_default = SOPStepRule(
            id=uuid.uuid4().hex[:12],
            step_id=step_ids[6],
            rule_order=1,
            description="Wenn BZA freigibt -> weiter zu Done (Schritt 7)",
            condition_field="bza_findings_count",
            condition_operator="is_zero",
            condition_value=0,
            action_type="goto_step",
            action_target=step_ids[7],
            action_params={},
        )
        # Step 1 (CIO-Eingangspruefung): bei Rueckfrage -> zurueck zu Step 1 (User antwortet, dann nochmal)
        r4 = SOPStepRule(
            id=uuid.uuid4().hex[:12],
            step_id=step_ids[1],
            rule_order=0,
            description="Wenn User auf Rueckfrage geantwortet hat -> nochmal pruefen",
            condition_field="cio_clarifications_answered",
            condition_operator="is_true",
            condition_value=True,
            action_type="goto_step",
            action_target=step_ids[1],
            action_params={"re_evaluate": True},
        )
        r4_default = SOPStepRule(
            id=uuid.uuid4().hex[:12],
            step_id=step_ids[1],
            rule_order=1,
            description="Default: Wenn keine Rueckfrage noetig -> weiter zu Schritt 2 (Bearbeiter-Uebernahme)",
            condition_field="cio_clarifications_needed",
            condition_operator="is_false",
            condition_value=False,
            action_type="goto_step",
            action_target=step_ids[2],
            action_params={},
        )

        for r in [r1, r2, r2_default, r3, r3_default, r4, r4_default]:
            db.add(r)
        db.commit()

        print()
        print("=" * 70)
        print("FERTIG - Development SOP erstellt")
        print("=" * 70)
        print(f"  SOP-ID:        {dev_sop.id}")
        print(f"  Name:          {dev_sop.name}")
        print(f"  Steps:         8 (0-7)")
        print(f"  Rules:         7 (4 Loop-Backs + 3 Defaults)")
        print(f"  Loop-Backs:    Step 3->2, Step 5->2, Step 6->2, Step 1->1")
        print()
        # Final-Status
        all_steps = db.query(SOPStep).filter(SOPStep.sop_id == dev_sop.id).order_by(SOPStep.step_order).all()
        for s in all_steps:
            nxt = (s.next_step_id or "(ende)")[:12]
            print(f"    #{s.step_order} | {s.id} | {s.agent:12} | {s.name[:45]:45} -> {nxt}")
            for r in (s.rules or []):
                print(f"        | Rule: {r.condition_field} {r.condition_operator} -> {r.action_type}({(r.action_target or '-')[:12]})")

    finally:
        db.close()


if __name__ == "__main__":
    main()
