"""Baut den iterativen CIO-Review-Zirkel in die ISCP-SOP ein.

Architektur nach dem Umbau:

  #0  CEO-digital   Zielbeschreibung
  #1  cio           Detail-Review (User-Fragen)
  #2  pi-coder      Orchestrator (plant Subagenten)
  #3  pi-coder-spec-structure    Subagent: Outline
  #4  pi-coder-spec-executive    Subagent: Executive Summary
  #5  pi-coder-spec-requirements Subagent: Requirements
  #6  pi-coder-spec-stakeholders Subagent: Stakeholders
  #7  pi-coder-spec-timeline     Subagent: Timeline
  #8  pi-coder-spec-risk         Subagent: Risks
  #9  cio           CIO Review 1: Widerspruchs-Check + Konsistenz
  #10 cio           CIO Review 2: Vollstaendigkeits-Check
  #11 pi-coder      Spec-Finalizer (persistieren)

Loop-Back-Mechanik:
- Subagenten (3-8) -> next_step_id = #9 (CIO Review 1)
- Review 1: 2 Rules
    - if context.cio_contradictions == 0 -> goto_step(#10)
    - if context.cio_contradictions > 0 -> goto_step(#5 requirements)  (Loop-Back)
- Review 2: 2 Rules
    - if context.cio_missing_count == 0 -> goto_step(#11 finalizer)
    - if context.cio_missing_count > 0 -> goto_step(#5 requirements)  (Loop-Back)
- Finalizer #11 -> next_step_id = null (Ende)
- Max iterations: 5 (Safety-Bruch, in context.max_iterations)

Ausfuehrung:
  cd backend && ./.venv/Scripts/python.exe ../scripts/setup_cio_review_loop.py
"""
import sys
import os
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.db.base import SessionLocal
from app.models.sop import SOP, SOPStep, SOPStepRule

ISCP_ID = "f563552f72eb"

# Aktuelle Step-IDs (Stand nach fill_step2_and_subagents.py)
STEP_OUTLINE      = "af97bc7ad8b1"  # #3
STEP_EXECUTIVE    = "7b402be2a214"  # #4
STEP_REQUIREMENTS = "40ddf52c601d"  # #5
STEP_STAKEHOLDERS = "3c10192d9452"  # #6
STEP_TIMELINE     = "feb9822b3591"  # #7
STEP_RISK         = "362738875378"  # #8
STEP_OLD_FINALIZER = "63f6c09db36e" # #9 (alter Finalizer — wird zu Review 1)


def restructure_steps(db):
    """Schritt 9 umbenennen (alter Finalizer -> Review 1), Schritte 10+11 anlegen."""
    # === 1) Alter Finalizer (Schritt 9) wird zu Review 1 ===
    review1 = db.query(SOPStep).filter(SOPStep.id == STEP_OLD_FINALIZER).first()
    if not review1:
        print(f"FEHLER: Alter Finalizer {STEP_OLD_FINALIZER} nicht gefunden")
        return None

    review1.name = "CIO Review 1: Sammeln + Widerspruchs-Check"
    review1.agent = "cio"
    review1.phase = "Task"
    review1.trigger = "step_completed"
    review1.action = "llm_call"
    review1.delay_s = 10.0
    review1.raci_r = "cio"
    review1.raci_a = "cio"
    review1.raci_c = "ceo-digital"
    review1.raci_i = "ceo-digital"
    review1.description = """## CIO Review 1 — Sammeln + Widerspruchs-Check

**Verantwortlich:** CIO
**Input:** context.section_* (alle 6 Subagent-Outputs)
**Output:** context.cio_review_1 = {
  "ok": bool,                     # True wenn keine Widersprueche
  "contradictions": [...],        # Liste der gefundenen Widersprueche
  "contradictions_count": int,    # Anzahl (fuer Rule-Eval)
  "checked_at": "ISO-8601"
}
**Loop-Back:** Bei Widerspruechen -> zurueck zu Subagent requirements (#5)

### Vorgehen
1. **Sammle** alle context.section_*-Werte (outline, executive, requirements, stakeholders, timeline, risks)
2. **Konsistenz-Check** — pruefe quer durch alle Sektionen:
   - **Numerische Konsistenz**: Stimmen Zahlen ueberein? (z.B. "5 Features" in Exec, aber 4 FRs in Requirements?)
   - **Terminologie-Konsistenz**: Gleiche Begriffe fuer gleiche Dinge? (z.B. "User" vs "Anwender" vs "Kunde")
   - **Logische Konsistenz**: Widersprechen sich Aussagen? (z.B. "Echtzeit" + "Batch-Verarbeitung taeglich")
   - **Stakeholder-Konsistenz**: RACI vollstaendig? (kein R ohne A)
   - **Timeline-Konsistenz**: Meilensteine passen zu Phaasen? Dependencies erfuellbar?
3. **Dokumentiere** jeden Widerspruch als konkretes Issue:
   - section_a, section_b, aussage_a, aussage_b, vorschlag (was soll korrigiert werden)
4. **Entscheidung**:
   - contradictions_count == 0 -> ok=true, Rule springt zu Review 2 (#10)
   - contradictions_count > 0 -> ok=false, Rule springt zurueck zu Subagent requirements (#5) mit Liste der Korrekturen

### Erwartetes Ergebnis
- context.cio_review_1 ist gesetzt
- Bei Widerspruechen: konkrete Korrektur-Liste fuer Subagenten
- Bei OK: Freigabe fuer Vollstaendigkeits-Check
"""

    review1.expected_result = "Alle Subagent-Outputs gesammelt, auf Widersprueche geprueft, Entscheidung in context.cio_review_1 dokumentiert. Bei OK: Loop zu Review 2. Bei Widerspruechen: Loop zurueck zu Subagenten."

    review1.success_criteria = [
        "Alle 6 Subagent-Outputs wurden gesammelt",
        "Numerische Konsistenz wurde geprueft (z.B. Feature-Count, FR-IDs)",
        "Terminologie-Konsistenz wurde geprueft (gleiche Begriffe fuer gleiche Dinge)",
        "Logische Konsistenz wurde geprueft (keine Widersprueche)",
        "Stakeholder-Konsistenz wurde geprueft (RACI vollstaendig)",
        "Timeline-Konsistenz wurde geprueft (Meilensteine vs Phaasen)",
        "context.cio_review_1 ist gesetzt mit ok=true|false + Liste der Widersprueche",
        "Bei Widerspruechen: Korrektur-Anweisungen fuer Subagenten in context.cio_corrections",
    ]

    review1.subagent_requirements = []
    review1.standards_refs = [
        "openbrain:vorlage-business-anforderungsdokument",
        "openbrain:architecture-consistency-rules",
    ]
    review1.task_types = ["quality_gate", "consistency_check", "loop_back_controller"]
    review1.change_requirements = [
        "Bei Widerspruechen: NICHT direkt aendern, sondern an Subagent zurueckgeben",
        "Korrektur-Liste muss konkret und umsetzbar sein",
        "Maximal 5 Iterationen (sonst eskaliert der Prozess)",
    ]
    review1.action_params = review1.action_params or {}
    review1.action_params["ai_instructions_md"] = """# CIO Review 1 — Sammeln + Widerspruchs-Check

## Ziel
Sammle alle 6 Subagent-Outputs und pruefe auf Widersprueche. Entscheide, ob die Spec konsistent ist oder ob Subagenten nachjustieren muessen.

## Vorgehen
1. **Sammle** context.section_outline, _executive, _requirements, _stakeholders, _timeline, _risks
2. **Konsistenz-Checks** (alle 5 Dimensionen):
   - Numerisch: Stimmen Anzahlen ueberein? (FR-Count, Stakeholder-Count, Milestone-Count)
   - Terminologisch: Gleiche Begriffe fuer gleiche Dinge? (Synonym-Detection)
   - Logisch: Widersprechen sich Aussagen? (z.B. "Echtzeit" + "Batch")
   - Stakeholder: RACI vollstaendig? (R+A immer definiert, max 1 A pro Aktivitaet)
   - Timeline: Meilensteine <= Phaasenende? Dependencies erfuellbar?
3. **Setze context.cio_review_1**:
   ```json
   {
     "ok": true/false,
     "contradictions": [
       {"dimension": "numerisch|terminologisch|logisch|stakeholder|timeline",
        "section_a": "executive",
        "section_b": "requirements",
        "issue": "Executive sagt 5 Features, aber nur 4 FRs definiert",
        "suggestion": "Entweder Feature 5 ergaenzen oder Anzahl korrigieren"
       }
     ],
     "contradictions_count": <int>,
     "checked_at": "<ISO>"
   }
   ```
4. **Iterationszaehler pruefen**: context.iteration_count
   - Falls iteration_count >= 5: ok=true setzen (Force-Completion)
   - Sonst normal entscheiden

## Wichtig
- **Niemals direkt aendern** — der CIO sammelt nur, korrigiert nicht
- **Konkret sein** — "Feature 5 fehlt" statt "irgendwas stimmt nicht"
- **Konstruktiv** — immer einen Korrektur-Vorschlag mitliefern
"""

    # Alte Rules loeschen (falls vorhanden)
    db.query(SOPStepRule).filter(SOPStepRule.step_id == review1.id).delete()
    db.commit()
    db.refresh(review1)

    # === 2) Review 2 (Schritt 10) NEU anlegen ===
    review2 = SOPStep(
        id=uuid.uuid4().hex[:12],
        sop_id=ISCP_ID,
        step_order=10,
        name="CIO Review 2: Vollstaendigkeits-Check",
        phase="Task",
        trigger="step_completed",
        action="llm_call",
        action_params={
            "ai_instructions_md": """# CIO Review 2 — Vollstaendigkeits-Check

## Ziel
Pruefe, ob die Spec alle noetigen Abschnitte enthaelt und keine Luecken hat. Bei Luecken: zurueck zu Subagenten mit Luecken-Liste.

## Vorgehen
1. **Sammle** context.section_*
2. **Pruefe Vollstaendigkeit** anhand der Outline (context.section_outline):
   - Hat jede Section mindestens 200 Woerter substantiellen Inhalt?
   - Hat Requirements-Section mindestens 5 FRs und 5 NFRs?
   - Hat Stakeholders-Section mindestens 5 Stakeholder?
   - Hat Timeline-Section mindestens 3 Phaasen?
   - Hat Risk-Section mindestens 5 Risiken?
   - Hat jede Section Akzeptanzkriterien oder Definition-of-Done-Kriterien?
3. **Setze context.cio_review_2**:
   ```json
   {
     "ok": true/false,
     "missing_sections": ["requirements-missing-nfr-005", ...],
     "missing_count": <int>,
     "checked_at": "<ISO>"
   }
   ```
4. **Iterationszaehler pruefen**: context.iteration_count
   - Falls iteration_count >= 5: ok=true (Force-Completion)
"""
        },
        agent="cio",
        raci_r="cio",
        raci_a="cio",
        raci_c="ceo-digital",
        raci_i="ceo-digital",
        description="""## CIO Review 2 — Vollstaendigkeits-Check

**Verantwortlich:** CIO
**Input:** context.section_*, context.section_outline (Soll-Outline)
**Output:** context.cio_review_2 = {
  "ok": bool,
  "missing_sections": [...],  # Liste der fehlenden / unvollstaendigen Bereiche
  "missing_count": int,
  "checked_at": "ISO-8601"
}
**Loop-Back:** Bei Luecken -> zurueck zu Subagent requirements (#5)

### Vorgehen
1. **Soll-vs-Ist-Vergleich** mit der Outline (context.section_outline)
2. **Vollstaendigkeits-Kriterien pro Section**:
   - Executive Summary: 200-400 Woerter, 3 H3-Blocks
   - Requirements: 5+ FRs + 5+ NFRs + Akzeptanzkriterien + Out-of-Scope
   - Stakeholders: 5+ Stakeholder + RACI-Matrix + 3-5 KPIs
   - Timeline: 3+ Phaasen + 5+ Milestones + Gantt
   - Risks: 5+ Risiken + Constraints + Assumptions + Mitigation
   - Outline: 5-8 Abschnitte mit Beschreibungen
3. **Dokumentiere Luecken** mit section_id, feld, anforderung, vorschlag
4. **Entscheidung**:
   - missing_count == 0 -> ok=true, Rule springt zu Finalizer (#11)
   - missing_count > 0 -> ok=false, Rule springt zurueck zu Subagenten mit Luecken-Liste
""",
        expected_result="Vollstaendigkeit geprueft, Entscheidung in context.cio_review_2. Bei OK: Loop zu Finalizer. Bei Luecken: Loop zurueck zu Subagenten.",
        success_criteria=[
            "Soll-vs-Ist-Vergleich mit Outline wurde durchgefuehrt",
            "Jede Section wurde auf Vollstaendigkeit geprueft",
            "Mindest-Woerterzahlen und Mindest-Anzahlen (FRs, NFRs, Stakeholder, etc.) wurden validiert",
            "context.cio_review_2 ist gesetzt mit ok=true|false + missing_sections",
            "Bei Luecken: konkrete Luecken-Liste fuer Subagenten",
        ],
        subagent_requirements=[],
        standards_refs=["openbrain:vorlage-business-anforderungsdokument"],
        task_types=["quality_gate", "completeness_check", "loop_back_controller"],
        change_requirements=[
            "Vollstaendigkeits-Kriterien muessen messbar sein (Anzahlen, Woerter)",
            "Bei Luecken: Korrektur-Liste muss section-spezifisch sein",
        ],
        delay_s=8.0,
        input_tool_required=False,
    )
    db.add(review2)
    db.flush()

    # === 3) Finalizer (Schritt 11) NEU anlegen ===
    finalizer = SOPStep(
        id=uuid.uuid4().hex[:12],
        sop_id=ISCP_ID,
        step_order=11,
        name="Spec-Finalizer: Markdown zusammenbauen + persistieren",
        phase="End",
        trigger="step_completed",
        action="llm_call",
        action_params={
            "ai_instructions_md": """# Spec-Finalizer

## Ziel
Baue die Spec aus den 6 Subagent-Outputs zusammen, validiere sie, speichere sie als Markdown.

## Vorgehen
1. Lese context.section_outline, _executive, _requirements, _stakeholders, _timeline, _risks
2. Baue Spec in dieser Reihenfolge zusammen:
   - Title + Status + Version + Date
   - Inhaltsverzeichnis (aus Outline)
   - 1. Executive Summary
   - 2. Requirements
   - 3. Stakeholders + RACI
   - 4. Timeline + Milestones
   - 5. Risks + Constraints + Assumptions
   - 6. Review-Historie (alle Review-Runs)
   - 7. Definition of Done
3. Validiere: 5+ NFRs, alle FRs haben Akzeptanzkriterien
4. Schreibe nach context.final_spec_markdown
5. Speichere Datei in /docs/specs/{project_slug}.md
6. OpenBrain-Capture: speichere Spec als reference
7. Setze task.status = "done" und SOP-Instance auf completed
"""
        },
        agent="pi-coder",
        raci_r="pi-coder",
        raci_a="ceo-digital",
        raci_c="cio",
        raci_i="ceo-digital",
        description="""## Spec-Finalizer — Markdown zusammenbauen + persistieren

**Verantwortlich:** pi-coder (Finalizer)
**Input:** context.section_*, context.cio_review_1, context.cio_review_2, context.iteration_count
**Output:** context.final_spec_markdown + Datei in /docs/specs/{project_slug}.md

### Vorgehen
1. **Sammle** alle context.section_*-Werte + Review-Historie
2. **Zusammenfuegen** in festgelegter Reihenfolge mit Inhaltsverzeichnis
3. **Review-Historie einbauen** (Anzahl Iterationen, gefundene Widersprueche, etc.)
4. **Validierung**:
   - Mindestens 5 NFRs?
   - Alle FRs haben Akzeptanzkriterien?
   - Alle Sections vorhanden?
5. **Speichern** in /docs/specs/{project_slug}.md
6. **OpenBrain-Capture** als reference (Typ: spec)
7. **Task auf done** setzen
8. **User benachrichtigen** mit Download-Link

### Erwartetes Ergebnis
- Vollstaendige Spec als Markdown-Datei auf der Platte
- Spec im OpenBrain als referenzierbares Dokument
- Task-Status `done` mit Verweis auf die Spec-Datei
- Review-Historie in der Spec dokumentiert (Transparenz)
""",
        expected_result="Vollstaendige Spec-Markdown-Datei gespeichert unter /docs/specs/, Inhaltsverzeichnis eingefuegt, OpenBrain-Capture erstellt, Task-Status done. Review-Historie ist in der Spec enthalten.",
        success_criteria=[
            "Alle 6 Subagent-Outputs wurden zusammengefuegt",
            "Inhaltsverzeichnis wurde am Anfang eingefuegt",
            "Spec hat mindestens 5 NFRs (Non-Functional Requirements)",
            "Jedes Feature hat Akzeptanzkriterien im GIVEN-WHEN-THEN-Format",
            "Review-Historie wurde in die Spec eingebaut (Anzahl Iterationen, Issues)",
            "Spec wurde als Markdown-Datei unter /docs/specs/ gespeichert",
            "OpenBrain-Capture wurde erstellt (Typ: reference)",
            "Task-Status ist 'done' mit Spec-Datei-Pfad",
        ],
        subagent_requirements=[],
        standards_refs=[
            "openbrain:vorlage-it-projekt-anforderungsdokument",
            "openbrain:vorlage-business-anforderungsdokument",
        ],
        task_types=["spec_finalization", "markdown_assembly", "file_persistence"],
        change_requirements=[
            "Spec-Datei muss UTF-8 encoded sein",
            "Markdown-Format mit korrekter H1/H2/H3-Hierarchie",
            "Dateiname: /docs/specs/{project_slug}-{date}.md",
        ],
        delay_s=5.0,
        input_tool_required=False,
    )
    db.add(finalizer)
    db.flush()
    db.commit()

    print(f"OK: Review 1 (Schritt 9) umbenannt: {review1.id}")
    print(f"OK: Review 2 (Schritt 10) NEU:    {review2.id}")
    print(f"OK: Finalizer (Schritt 11) NEU:  {finalizer.id}")
    return review1, review2, finalizer


def wire_up_routing(db, review1, review2, finalizer):
    """Verdrahtet die Subagenten + Review-Steps mit next_step_id und Rules."""
    subagent_ids = [STEP_OUTLINE, STEP_EXECUTIVE, STEP_REQUIREMENTS,
                    STEP_STAKEHOLDERS, STEP_TIMELINE, STEP_RISK]

    # === 1) Subagenten (3-8): next_step_id -> Review 1 ===
    for sid in subagent_ids:
        s = db.query(SOPStep).filter(SOPStep.id == sid).first()
        if s:
            s.next_step_id = review1.id
    db.commit()
    print(f"OK: 6 Subagenten (3-8) -> next_step_id = Review 1 ({review1.id[:12]})")

    # === 2) Review 1: 2 Rules fuer Loop-Back ===
    # Rule 1: ok -> Review 2
    rule1 = SOPStepRule(
        id=uuid.uuid4().hex[:12],
        step_id=review1.id,
        rule_order=0,
        description="Wenn keine Widersprueche gefunden wurden -> gehe zu Review 2",
        condition_field="cio_review_1_ok",
        condition_operator="is_true",
        condition_value=True,
        action_type="goto_step",
        action_target=review2.id,
        action_params={},
    )
    # Rule 2: Widersprueche -> Loop-Back zu Subagent requirements
    rule2 = SOPStepRule(
        id=uuid.uuid4().hex[:12],
        step_id=review1.id,
        rule_order=1,
        description="Wenn Widersprueche gefunden wurden -> gehe zurueck zu Subagent requirements (#5) fuer Korrekturen",
        condition_field="cio_review_1_ok",
        condition_operator="is_false",
        condition_value=False,
        action_type="goto_step",
        action_target=STEP_REQUIREMENTS,
        action_params={
            "loop_back": True,
            "iteration_increment": True,
            "max_iterations": 5,
            "corrections_field": "cio_corrections",
        },
    )
    db.add(rule1)
    db.add(rule2)
    db.commit()
    print(f"OK: Review 1 hat 2 Rules (ok->Review 2, not-ok->Subagent #5)")

    # === 3) Review 2: 2 Rules ===
    # Rule 1: komplett -> Finalizer
    rule3 = SOPStepRule(
        id=uuid.uuid4().hex[:12],
        step_id=review2.id,
        rule_order=0,
        description="Wenn keine Luecken gefunden wurden -> gehe zu Finalizer (#11)",
        condition_field="cio_review_2_ok",
        condition_operator="is_true",
        condition_value=True,
        action_type="goto_step",
        action_target=finalizer.id,
        action_params={},
    )
    # Rule 2: Luecken -> Loop-Back
    rule4 = SOPStepRule(
        id=uuid.uuid4().hex[:12],
        step_id=review2.id,
        rule_order=1,
        description="Wenn Luecken gefunden wurden -> gehe zurueck zu Subagent requirements (#5)",
        condition_field="cio_review_2_ok",
        condition_operator="is_false",
        condition_value=False,
        action_type="goto_step",
        action_target=STEP_REQUIREMENTS,
        action_params={
            "loop_back": True,
            "iteration_increment": True,
            "max_iterations": 5,
            "missing_field": "cio_missing_sections",
        },
    )
    db.add(rule3)
    db.add(rule4)
    db.commit()
    print(f"OK: Review 2 hat 2 Rules (ok->Finalizer, not-ok->Subagent #5)")

    # === 4) Review 1: next_step_id = Review 2 (default, falls keine Rule feuert) ===
    review1.next_step_id = review2.id
    review1.fail_step_id = None
    db.commit()

    # === 5) Review 2: next_step_id = Finalizer ===
    review2.next_step_id = finalizer.id
    review2.fail_step_id = None
    db.commit()

    # === 6) Finalizer: next_step_id = None (Ende) ===
    finalizer.next_step_id = None
    finalizer.fail_step_id = None
    db.commit()
    print(f"OK: Default-routing gesetzt (Review1->Review2, Review2->Finalizer, Finalizer->END)")


def main():
    db = SessionLocal()
    try:
        print("=" * 70)
        print("CIO Review Loop Setup fuer ISCP-SOP")
        print("=" * 70)

        # 1) Steps umorganisieren
        result = restructure_steps(db)
        if not result:
            return
        review1, review2, finalizer = result

        # 2) Routing verdrahten
        wire_up_routing(db, review1, review2, finalizer)

        print()
        print("=" * 70)
        print("FERTIG — ISCP-SOP mit CIO Review-Loop:")
        print("=" * 70)
        all_steps = db.query(SOPStep).filter(
            SOPStep.sop_id == ISCP_ID
        ).order_by(SOPStep.step_order).all()
        for s in all_steps:
            next_id = (s.next_step_id or "(ende)")[:12]
            n_rules = len(s.rules or [])
            print(f"  #{s.step_order:2d} | {s.id[:12]} | {s.agent[:25]:25} | {s.name[:45]}")
            print(f"        | next: {next_id} | rules: {n_rules}")

        # BPMN-Diagram-Cache invalidieren (force re-render)
        print()
        print("BPMN wird beim naechsten API-Call neu generiert (auto).")
    finally:
        db.close()


if __name__ == "__main__":
    main()
