"""Fuellt Step 2 der ISCP-SOP komplett aus und fuegt Subagent-Steps (3-9) hinzu.

Ausfuehrung:
  cd backend && ./.venv/Scripts/python.exe ../scripts/fill_step2_and_subagents.py
"""
import sys
import os

# Backend-Pfad hinzufuegen
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.db.base import SessionLocal
from app.models.sop import SOP, SOPStep

ISCP_ID = "f563552f72eb"
STEP2_ID = "6a1fc3fe2dbb"  # aktueller "Worker: Detaillierte Spec ausarbeiten"


def update_step2(db):
    """Aktualisiert Step 2 mit allen relevanten Feldern (pi-coder Orchestrator)."""
    s = db.query(SOPStep).filter(SOPStep.id == STEP2_ID).first()
    if not s:
        print(f"FEHLER: Step {STEP2_ID} nicht gefunden")
        return None

    # === Basis-Felder ===
    s.name = "Spec-Orchestrierung: Subagent-Aufgaben planen und verteilen"
    s.agent = "pi-coder"
    s.phase = "Task"
    s.trigger = "step_completed"
    s.action = "llm_call"
    s.delay_s = 8.0
    s.raci_r = "pi-coder"
    s.raci_a = "pi-coder"
    s.raci_c = "cio,ceo-digital"
    s.raci_i = "ceo-digital"

    # === Description (Markdown) ===
    s.description = """## Spec-Orchestrierung durch pi-coder

**Verantwortlich:** pi-coder (mit Subagent-Schwarm)
**Input:** context.project_goal (3-Satz-Beschreibung) + context.cio_questions (Detail-Antworten)
**Output:** Vollstaendige Spec in context.final_spec_markdown

### Vorgehen
1. **Spec-Struktur planen** — basierend auf Template-Kategorie (IT/Marketing/Finance/Business) die relevanten Abschnitte festlegen.
2. **Subagent-Schwarm aufsetzen** — fuer jeden Abschnitt einen dedizierten Subagent spawnen (siehe subagent_requirements).
3. **Abhaengigkeiten definieren** — Subagenten koennen parallel laufen, ausser sie brauchen Output eines anderen.
4. **Quality-Gates** — Jeder Subagent-Output wird via Success-Criteria geprueft.
5. **Spec finalisieren** — Markdown zusammenfuegen, in OpenBrain persistieren, Task abschliessen.

### Erwartetes Ergebnis
- Vollstaendige Spec in Markdown-Format
- Spec enthaelt alle 7 Pflicht-Abschnitte (Executive Summary, Requirements, Stakeholders, Timeline, Risks, Success Criteria, Definition of Done)
- Mindestens 3 konkrete, testbare Akzeptanzkriterien pro Feature
- Mindestens 5 NFRs (Performance, Security, Scalability, Availability, Compliance)
- Spec ist review-faeig (keine TODOs, keine offenen Fragen)
"""

    # === AI-Instructions (action_params.ai_instructions_md) ===
    import json
    s.action_params = s.action_params or {}
    s.action_params["ai_instructions_md"] = """# Spec-Orchestrierung — pi-coder

## Ziel
Erstelle eine vollstaendige Spezifikation fuer das vom User definierte Projekt. Verteile die
Arbeit an dedizierte Subagenten (siehe subagent_requirements).

## Vorgehen
1. **Template-Auswahl** anhand context.template_category:
   - `it`        -> IT-Projekt Spec (SRS + BRD Light, IEEE-830-Style)
   - `finance`   -> Finance/Accounting Spec (BRD mit Compliance-Block)
   - `marketing` -> Marketing Spec (MRD + PRD)
   - `business`  -> Business Spec (BRD generisch)
2. **Spec-Outline** aus dem passenden OpenBrain-Template laden (siehe standards_refs).
3. **Subagent-Schwarm starten** — fuer jeden der 6 Spec-Abschnitte einen Subagent spawnen.
4. **Quality-Gate** vor Uebergabe an Finalizer: alle Abschnitte vorhanden, keine TODOs.
5. **Handoff** an Subagent `spec-finalizer` (Step 9), der die Spec zusammenbaut.

## Kontext-Schluessel
- `context.project_goal` — 3-Satz-Projektbeschreibung (aus Step 0)
- `context.template_category` — it|finance|marketing|business (aus Step 1)
- `context.cio_questions` — Detail-Antworten des Users (aus Step 1)
- `context.section_*` — Output der einzelnen Subagenten
- `context.final_spec_markdown` — Endprodukt (vom Finalizer geschrieben)

## Wichtige Regeln
- **Niemals raten** — wenn Information fehlt, Subagent `spec-clarify` starten (User-Input-Tool)
- **Standards beachten** — siehe standards_refs (OpenBrain-Templates)
- **Traceability** — jedes Requirement bekommt eine ID (FR-001, NFR-001, etc.)
- **Akzeptanzkriterien** — jedes Feature bekommt 3-5 GIVEN-WHEN-THEN Kriterien
"""

    # === Success Criteria ===
    s.success_criteria = [
        "Spec-Struktur ist geplant (welche Abschnitte es gibt, steht fest)",
        "Alle 6 Subagenten fuer Spec-Abschnitte wurden gespawnt",
        "Jeder Subagent-Output hat das spezifizierte Markdown-Format",
        "Quality-Gate bestanden: keine TODOs, alle Pflicht-Abschnitte vorhanden",
        "Handoff an Finalizer (Step 9) erfolgreich",
    ]

    # === Subagent-Requirements (Schwarm-Definition) ===
    s.subagent_requirements = [
        {
            "id": "spec-structure",
            "role": "pi-coder-spec-structure",
            "responsibility": "Erstellt die Spec-Outline (Abschnittsnamen + Reihenfolge) basierend auf Template-Kategorie",
            "depends_on": [],
            "output_key": "context.section_outline",
        },
        {
            "id": "spec-executive",
            "role": "pi-coder-spec-executive",
            "responsibility": "Schreibt Executive Summary + Problem Statement + Solution Overview (~500 Woerter)",
            "depends_on": ["spec-structure"],
            "output_key": "context.section_executive",
        },
        {
            "id": "spec-requirements",
            "role": "pi-coder-spec-requirements",
            "responsibility": "Sammelt alle Functional + Non-Functional Requirements mit IDs, Prioritaet, Akzeptanzkriterien",
            "depends_on": ["spec-structure"],
            "output_key": "context.section_requirements",
        },
        {
            "id": "spec-stakeholders",
            "role": "pi-coder-spec-stakeholders",
            "responsibility": "Stakeholder-Analyse + RACI-Matrix + Success Criteria / KPIs",
            "depends_on": ["spec-structure"],
            "output_key": "context.section_stakeholders",
        },
        {
            "id": "spec-timeline",
            "role": "pi-coder-spec-timeline",
            "responsibility": "Timeline mit Milestones, Deliverables, Abhaengigkeiten, Gantt-Liste",
            "depends_on": ["spec-structure"],
            "output_key": "context.section_timeline",
        },
        {
            "id": "spec-risks",
            "role": "pi-coder-spec-risk",
            "responsibility": "Risks (Tech/Skills/Business/Env), Constraints, Assumptions, Mitigation",
            "depends_on": ["spec-structure"],
            "output_key": "context.section_risks",
        },
    ]

    # === Standards-References (OpenBrain) ===
    s.standards_refs = [
        "openbrain:vorlage-it-projekt-anforderungsdokument",
        "openbrain:vorlage-marketing-anforderungsdokument",
        "openbrain:vorlage-finance-anforderungsdokument",
        "openbrain:vorlage-business-anforderungsdokument",
    ]

    # === Task-Types ===
    s.task_types = ["spec_orchestration", "subagent_spawning", "markdown_generation"]

    # === Change-Requirements ===
    s.change_requirements = [
        "Spec muss in Markdown-Format sein (kein HTML, kein JSON)",
        "Alle Sections muessen mit `## Section-Name` beginnen",
        "Jedes Requirement bekommt eine eindeutige ID (FR-001, NFR-001, ...)",
        "Akzeptanzkriterien im GIVEN-WHEN-THEN-Format",
        "Keine offenen Fragen / TODOs in der finalen Spec",
    ]

    # === Input-Tool: nicht noetig (Step 1 hat schon alle Details abgefragt) ===
    s.input_tool_required = False

    db.commit()
    db.refresh(s)
    print(f"OK: Step 2 aktualisiert: {s.id} | {s.name}")
    return s


def add_subagent_step(db, sop_id, after_step_id, position, name, agent, action,
                      description, output_key, role, delay_s=5.0):
    """Fuegt einen Subagent-Step nach after_step_id ein."""
    import uuid

    # Bestimme step_order
    after = db.query(SOPStep).filter(SOPStep.id == after_step_id).first()
    if not after:
        print(f"FEHLER: after_step_id {after_step_id} nicht gefunden")
        return None

    target_order = after.step_order + 1

    # Nachfolgende Steps verschieben
    later = db.query(SOPStep).filter(
        SOPStep.sop_id == sop_id,
        SOPStep.step_order >= target_order
    ).all()
    for ls in later:
        ls.step_order += 1

    new_step = SOPStep(
        id=uuid.uuid4().hex[:12],
        sop_id=sop_id,
        step_order=target_order,
        name=name,
        phase="Sub-SOP",
        trigger="subagent_spawn",
        action=action,
        action_params={"output_key": output_key, "role": role},
        agent=agent,
        raci_r=agent,
        raci_a="pi-coder",
        raci_c="cio",
        raci_i="ceo-digital",
        description=description,
        delay_s=delay_s,
        success_criteria=[],
        subagent_requirements=[],
        standards_refs=[],
        task_types=["subagent_execution"],
        change_requirements=[],
        input_tool_required=False,
    )
    db.add(new_step)
    db.flush()

    # next_step_id vom Vorgaenger aktualisieren
    after.next_step_id = new_step.id
    db.commit()
    db.refresh(new_step)
    print(f"OK: Step #{new_step.step_order} hinzugefuegt: {new_step.id} | {new_step.name}")
    return new_step


def add_finalizer_step(db, sop_id, after_step_id):
    """Fuegt den Finalizer-Step (Step 9) hinzu, der die Spec zusammenbaut."""
    import uuid
    import json

    after = db.query(SOPStep).filter(SOPStep.id == after_step_id).first()
    if not after:
        return None
    target_order = after.step_order + 1

    # Nachfolgende Steps verschieben
    later = db.query(SOPStep).filter(
        SOPStep.sop_id == sop_id,
        SOPStep.step_order >= target_order
    ).all()
    for ls in later:
        ls.step_order += 1

    desc = """## Spec-Finalizer — Markdown zusammenfuegen + persistieren

**Verantwortlich:** pi-coder (Finalizer)
**Input:** context.section_* (alle 6 Subagent-Outputs)
**Output:** context.final_spec_markdown + Datei in /docs/specs/

### Vorgehen
1. **Sammle** alle context.section_*-Werte (outline, executive, requirements, stakeholders, timeline, risks)
2. **Zusammenfuegen** in festgelegter Reihenfolge mit Inhaltsverzeichnis am Anfang
3. **Validierung**:
   - Hat Spec mindestens 5 NFRs?
   - Hat jedes Feature Akzeptanzkriterien?
   - Sind alle Sections vorhanden?
4. **Speichern** in /docs/specs/{project_name}.md
5. **OpenBrain-Capture** als reference (Typ: spec)
6. **Task auf done** setzen
7. **User benachrichtigen** mit Download-Link

### Erwartetes Ergebnis
- Vollstaendige Spec als Markdown-Datei auf der Platte
- Spec im OpenBrain als referenzierbares Dokument
- Task-Status `done` mit Verweis auf die Spec-Datei
"""

    new_step = SOPStep(
        id=uuid.uuid4().hex[:12],
        sop_id=sop_id,
        step_order=target_order,
        name="Spec-Finalizer: Markdown zusammenbauen + persistieren",
        phase="End",
        trigger="step_completed",
        action="llm_call",
        action_params={
            "ai_instructions_md": """# Spec-Finalizer

## Ziel
Baue die Spec aus den 6 Subagent-Outputs zusammen, validiere sie und speichere sie als Markdown.

## Vorgehen
1. Lese context.section_outline, _executive, _requirements, _stakeholders, _timeline, _risks
2. Erzeuge Inhaltsverzeichnis (TOC) aus der Outline
3. Baue Spec in dieser Reihenfolge zusammen:
   - Title + Status + Version + Date
   - TOC
   - 1. Executive Summary (from _executive)
   - 2. Requirements (from _requirements)
   - 3. Stakeholders & RACI (from _stakeholders)
   - 4. Timeline & Milestones (from _timeline)
   - 5. Risks, Constraints, Assumptions (from _risks)
   - 6. Definition of Done
4. Validiere: 5+ NFRs, alle FRs haben Akzeptanzkriterien
5. Schreibe nach context.final_spec_markdown
6. Speichere Datei in /docs/specs/{project_slug}.md
7. OpenBrain-Capture: speichere Spec als reference
8. Setze task.status = "done" und SOP-Instance auf completed
""",
        },
        agent="pi-coder",
        raci_r="pi-coder",
        raci_a="ceo-digital",
        raci_c="cio",
        raci_i="ceo-digital",
        description=desc,
        delay_s=5.0,
        success_criteria=[
            "Alle 6 Subagent-Outputs wurden zusammengefuegt",
            "Inhaltsverzeichnis wurde am Anfang eingefuegt",
            "Spec hat mindestens 5 NFRs (Non-Functional Requirements)",
            "Jedes Feature hat Akzeptanzkriterien im GIVEN-WHEN-THEN-Format",
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
        input_tool_required=False,
    )
    db.add(new_step)
    db.flush()
    after.next_step_id = new_step.id
    db.commit()
    db.refresh(new_step)
    print(f"OK: Finalizer-Step #{new_step.step_order} hinzugefuegt: {new_step.id} | {new_step.name}")
    return new_step


def main():
    db = SessionLocal()
    try:
        # === 1. Step 2 aktualisieren (Orchestrator) ===
        s2 = update_step2(db)
        if not s2:
            return

        # === 2. Subagent-Steps hinzufuegen (3-8) ===
        last_id = s2.id
        subagents = [
            {
                "name": "Subagent: Spec-Struktur (Outline)",
                "agent": "pi-coder-spec-structure",
                "action": "llm_call",
                "description": """## Subagent: Spec-Struktur / Outline

**Rolle:** pi-coder-spec-structure
**Input:** context.template_category (it|finance|marketing|business), context.project_goal
**Output:** context.section_outline (Liste der Spec-Abschnitte)

### Vorgehen
1. Lade das passende Template aus OpenBrain (siehe standards_refs in Step 2)
2. Waehle die 5-8 relevantesten Abschnitte aus dem Template
3. Sortiere sie logisch (vom Allgemeinen zum Detail)
4. Schreibe pro Abschnitt 1-Satz-Beschreibung, was dort hinkommt
5. Output als Markdown-Liste

### Erwartetes Ergebnis
- Markdown-Liste mit 5-8 Abschnitten
- Jeder Abschnitt hat Titel + 1-Satz-Beschreibung
- Reihenfolge ist logisch (Executive zuerst, Details spaeter)
""",
                "output_key": "section_outline",
                "role": "pi-coder-spec-structure",
                "success_criteria": [
                    "Outline enthaelt 5-8 Abschnitte",
                    "Jeder Abschnitt hat eine kurze Beschreibung",
                    "Reihenfolge ist logisch und vollstaendig",
                ],
            },
            {
                "name": "Subagent: Executive Summary",
                "agent": "pi-coder-spec-executive",
                "action": "llm_call",
                "description": """## Subagent: Executive Summary

**Rolle:** pi-coder-spec-executive
**Input:** context.project_goal, context.section_outline
**Output:** context.section_executive (Markdown)

### Vorgehen
1. Schreibe Executive Summary (200-400 Woerter) mit:
   - Problem Statement (Was ist das Problem? Warum ist es wichtig?)
   - Solution Overview (Was bauen wir? Wie loest es das Problem?)
   - Value Proposition (Welchen Mehrwert bringt es? Fuer wen?)
2. Strukturiere mit H3-Ueberschriften

### Erwartetes Ergebnis
- Markdown-Section mit 3 klar getrennten H3-Blocks
- 200-400 Woerter, businesslike Sprache
- Keine TODOs, keine offenen Fragen
""",
                "output_key": "section_executive",
                "role": "pi-coder-spec-executive",
                "success_criteria": [
                    "Problem Statement ist klar benannt (1-2 Saetze)",
                    "Solution Overview beschreibt WAS und WIE",
                    "Value Proposition ist messbar (KPI, Einsparung, etc.)",
                ],
            },
            {
                "name": "Subagent: Anforderungen (Functional + Non-Functional)",
                "agent": "pi-coder-spec-requirements",
                "action": "llm_call",
                "description": """## Subagent: Anforderungen

**Rolle:** pi-coder-spec-requirements
**Input:** context.project_goal, context.section_outline
**Output:** context.section_requirements (Markdown mit FR-XXX, NFR-XXX IDs)

### Vorgehen
1. **Functional Requirements** (FR-001, FR-002, ...) — Was muss das System tun?
   - Pro Feature 3-5 Akzeptanzkriterien im GIVEN-WHEN-THEN-Format
   - MoSCoW-Prioritaet (Must/Should/Could/Won't)
2. **Non-Functional Requirements** (NFR-001, ...) — Wie gut muss es sein?
   - Mindestens 5 NFRs aus: Performance, Security, Scalability, Availability, Compliance, Maintainability
   - Pro NFR konkrete Metrik (z.B. "p99 < 200ms", "99.9% Uptime")

### Erwartetes Ergebnis
- 5-15 Functional Requirements mit eindeutigen IDs
- Mindestens 5 Non-Functional Requirements mit Metriken
- Alle Anforderungen haben Akzeptanzkriterien
- Out-of-Scope-Liste (was explizit NICHT dazugehoert)
""",
                "output_key": "section_requirements",
                "role": "pi-coder-spec-requirements",
                "success_criteria": [
                    "5-15 FRs mit eindeutigen IDs (FR-001, FR-002, ...)",
                    "5+ NFRs mit messbaren Metriken",
                    "Jede Anforderung hat 3-5 Akzeptanzkriterien (GIVEN-WHEN-THEN)",
                    "Out-of-Scope-Liste ist explizit aufgefuehrt",
                ],
            },
            {
                "name": "Subagent: Stakeholder + RACI + Success Criteria",
                "agent": "pi-coder-spec-stakeholders",
                "action": "llm_call",
                "description": """## Subagent: Stakeholder + RACI

**Rolle:** pi-coder-spec-stakeholders
**Input:** context.project_goal, context.template_category
**Output:** context.section_stakeholders (Markdown)

### Vorgehen
1. **Stakeholder-Liste** — Wer ist betroffen? (User, Sponsor, Tech-Team, Operations, Compliance, Management)
   - Pro Stakeholder: Name/Rolle, Verantwortungsbereich, Erwartungen, Kontakt-Frequenz
2. **RACI-Matrix** — Wer ist R/A/C/I fuer jedes Feature / jeden Process?
   - R = Responsible (macht es)
   - A = Accountable (genehmigt)
   - C = Consulted (wird gefragt)
   - I = Informed (wird informiert)
3. **Success Criteria / KPIs** — Woran messen wir Erfolg?
   - 3-5 messbare KPIs (z.B. "Time-to-Market < 3 Monate", "User-Adoption > 60%")

### Erwartetes Ergebnis
- Stakeholder-Tabelle (mind. 5 Stakeholder)
- RACI-Matrix als Tabelle
- 3-5 messbare KPIs mit Zielwert
""",
                "output_key": "section_stakeholders",
                "role": "pi-coder-spec-stakeholders",
                "success_criteria": [
                    "Mindestens 5 Stakeholder identifiziert",
                    "RACI-Matrix ist vollstaendig (R, A, C, I pro Aktivitaet)",
                    "3-5 messbare KPIs mit Zielwerten definiert",
                ],
            },
            {
                "name": "Subagent: Timeline + Milestones",
                "agent": "pi-coder-spec-timeline",
                "action": "llm_call",
                "description": """## Subagent: Timeline + Milestones

**Rolle:** pi-coder-spec-timeline
**Input:** context.section_requirements, context.template_category
**Output:** context.section_timeline (Markdown)

### Vorgehen
1. **Phasen** — Welche grossen Phasen hat das Projekt?
   - z.B. "Discovery (2 Wo)", "Design (3 Wo)", "Implementation (8 Wo)", "Testing (2 Wo)", "Rollout (1 Wo)"
2. **Milestones** — Was sind die wichtigsten Meilensteine pro Phase?
   - Pro Milestone: Datum (oder Woche), Deliverable, Verantwortlich
3. **Abhaengigkeiten** — Welche Milestones blocken andere?
4. **Gantt-Liste** — Vereinfachte Gantt-Tabelle (Phase, Start, Ende, Daver)

### Erwartetes Ergebnis
- 3-7 Phasen mit klarer Daver
- 5-10 Milestones mit Deliverables
- Abhaengigkeiten explizit benannt
- Gantt-Tabelle als Markdown
""",
                "output_key": "section_timeline",
                "role": "pi-coder-spec-timeline",
                "success_criteria": [
                    "3-7 Phasen mit realistischer Daver definiert",
                    "5-10 Milestones mit konkreten Deliverables",
                    "Abhaengigkeiten zwischen Milestones sind benannt",
                    "Gantt-Tabelle im Markdown-Format",
                ],
            },
            {
                "name": "Subagent: Risks + Constraints + Assumptions",
                "agent": "pi-coder-spec-risk",
                "action": "llm_call",
                "description": """## Subagent: Risks + Constraints + Assumptions

**Rolle:** pi-coder-spec-risk
**Input:** context.project_goal, context.section_requirements
**Output:** context.section_risks (Markdown)

### Vorgehen
1. **Risks** — Was kann schiefgehen? (Risikomatrix)
   - Pro Risk: ID, Kategorie (Tech/Skills/Business/Env), Wahrscheinlichkeit, Impact, Mitigation
2. **Constraints** — Welche Rahmenbedingungen schraenken ein?
   - z.B. "Budget: max 100k EUR", "Team-Groesse: 3 Entwickler", "Time-to-Market: Q3"
3. **Assumptions** — Welche Annahmen treffen wir?
   - z.B. "User haben Chrome-Browser", "API wird vom Backend-Team bis Woche 4 geliefert"
4. **Mitigation-Plan** — Fuer jedes Top-3-Risk: konkrete Massnahmen

### Erwartetes Ergebnis
- Risikomatrix mit 5-10 Risiken (Wahrscheinlichkeit x Impact)
- 3-5 Constraints mit Begruendung
- 3-5 Assumptions explizit gelistet
- Mitigation-Plan fuer die Top-3-Risiken
""",
                "output_key": "section_risks",
                "role": "pi-coder-spec-risk",
                "success_criteria": [
                    "5-10 Risiken mit ID, Kategorie, Wahrscheinlichkeit, Impact",
                    "3-5 Constraints mit Begruendung",
                    "3-5 Assumptions explizit aufgelistet",
                    "Mitigation-Plan fuer die Top-3-Risiken",
                ],
            },
        ]

        for i, sa in enumerate(subagents, start=3):
            new_s = add_subagent_step(
                db,
                sop_id=ISCP_ID,
                after_step_id=last_id,
                position=i,
                name=sa["name"],
                agent=sa["agent"],
                action=sa["action"],
                description=sa["description"],
                output_key=sa["output_key"],
                role=sa["role"],
            )
            if new_s:
                # Success-Criteria nachtraeglich setzen (im add_subagent_step nicht unterstuetzt)
                new_s.success_criteria = sa["success_criteria"]
                new_s.standards_refs = [
                    "openbrain:vorlage-it-projekt-anforderungsdokument",
                    "openbrain:vorlage-business-anforderungsdokument",
                ]
                new_s.task_types = ["subagent_spec_section"]
                db.commit()
                last_id = new_s.id

        # === 3. Finalizer-Step (Step 9) hinzufuegen ===
        finalizer = add_finalizer_step(db, ISCP_ID, last_id)

        print()
        print("=" * 60)
        print("FERTIG — ISCP-SOP hat jetzt folgende Struktur:")
        print("=" * 60)
        all_steps = db.query(SOPStep).filter(
            SOPStep.sop_id == ISCP_ID
        ).order_by(SOPStep.step_order).all()
        for s in all_steps:
            next_id = (s.next_step_id or "(ende)")[:12]
            print(f"  #{s.step_order:2d} | {s.id[:12]} | {s.agent[:25]:25} | {s.name[:50]}")
            print(f"        | next: {next_id}")
        print(f"\nTotal Steps: {len(all_steps)}")

    finally:
        db.close()


if __name__ == "__main__":
    main()
