"""Fuellt ai_instructions_md fuer alle Subagent-Steps + CIO-Review-Step 1.

Bisher fehlten die KI-Anweisungen fuer:
  - #1  cio  CIO-Review
  - #3  pi-coder-spec-structure
  - #4  pi-coder-spec-executive
  - #5  pi-coder-spec-requirements
  - #6  pi-coder-spec-stakeholders
  - #7  pi-coder-spec-timeline
  - #8  pi-coder-spec-risk

Ausfuehrung:
  cd backend && ./.venv/Scripts/python.exe ../scripts/fill_ai_instructions.py
"""
import sys
import os
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.db.base import SessionLocal
from app.models.sop import SOPStep
from sqlalchemy.orm.attributes import flag_modified

ISCP_ID = "f563552f72eb"

AI_INSTRUCTIONS = {
    # === Step 1: CIO-Review (Zielbeschreibung validieren) ===
    "bf49ebcf65d1": """# CIO Review 1 — Zielbeschreibung validieren + Detail-Fragen

## Ziel
Pruefe die initiale Zielbeschreibung des Users (3 Saetze) auf Vollstaendigkeit und stelle ueber das User-Input-Tool alle offenen Detail-Fragen.

## Vorgehen
1. **Lese** context.project_goal (3-Satz-Beschreibung aus Step 0)
2. **Validierung**:
   - Satz 1: Problem/Notwendigkeit klar benannt?
   - Satz 2: Loesung/Produkt konkret beschrieben?
   - Satz 3: Ergebnis/Mehrwert messbar?
3. **Klassifizierung**: IT | Finance | Marketing | Business
4. **Gap-Analyse**: Identifiziere fehlende Aspekte:
   - Zielgruppe (Wer?)
   - Budget (Wieviel?)
   - Timeline (Bis wann?)
   - Abhaengigkeiten (Von wem/was?)
   - Risiken (Was koennte schiefgehen?)
   - Stakeholder (Wer ist beteiligt?)
   - Compliance (Welche Regeln?)
5. **User-Fragen**: Formuliere fuer jeden Gap eine konkrete Frage
6. **Output**: Setze context.cio_questions = [Liste der Fragen]

## Wichtig
- **Nicht raten** — lieber eine offene Frage als eine falsche Annahme
- **Kontext aus OpenBrain** nutzen (siehe standards_refs in Step 1)
- **Konstruktiv** — zeige bei jeder Frage, was die Antwort bewirkt
""",

    # === Step 3: Subagent spec-structure ===
    "af97bc7ad8b1": """# Subagent: Spec-Struktur / Outline

## Rolle
pi-coder-spec-structure — du bist der Architekt der Spec-Struktur.

## Ziel
Erstelle eine Spec-Outline (5-8 Abschnitte) basierend auf der Template-Kategorie.

## Input
- context.template_category: it | finance | marketing | business
- context.project_goal: 3-Satz-Beschreibung
- OpenBrain-Templates: siehe standards_refs

## Vorgehen
1. **Lade** das passende OpenBrain-Template (siehe standards_refs in Step 2)
2. **Waehle 5-8 Abschnitte** aus dem Template, die fuer dieses Projekt relevant sind
   - Pflicht: Executive Summary, Requirements, Stakeholders, Timeline, Risks
   - Optional je nach Kategorie: Compliance (Finance), Technical Architecture (IT), etc.
3. **Sortiere** logisch (vom Allgemeinen zum Detail):
   - Title + Status
   - Executive Summary
   - Anforderungen
   - Stakeholder + RACI
   - Timeline + Milestones
   - Risks + Constraints
   - (Optional) Compliance / Architecture
   - Definition of Done
4. **Beschrifte** jeden Abschnitt mit 1 Satz, was dort hinkommt
5. **Output** als Markdown-Liste in context.section_outline

## Format
```markdown
## Section-Name
Kurze 1-Satz-Beschreibung, was hier hinkommt.
```

## Wichtig
- **Nicht zu viele Sections** (max 8) — Qualitaet > Quantitaet
- **Logische Reihenfolge** — Stakeholder vor Timeline, weil Timeline Stakeholder-Abhaengigkeiten hat
- **Konsistent** — alle Section-Namen in derselben Sprache und im selben Stil
""",

    # === Step 4: Subagent spec-executive ===
    "7b402be2a214": """# Subagent: Executive Summary

## Rolle
pi-coder-spec-executive — du bist der Stratege, der das grosse Bild zeichnet.

## Ziel
Schreibe eine Executive Summary (200-400 Worte) mit Problem Statement, Solution Overview und Value Proposition.

## Input
- context.project_goal: 3-Satz-Beschreibung
- context.section_outline: Struktur (zur Orientierung)
- context.template_category: it | finance | marketing | business

## Vorgehen
1. **Problem Statement** (3-5 Saetze):
   - Was ist das konkrete Problem? (Schmerz, Ineffizienz, Markt-Luecke)
   - Wer ist betroffen? (Zielgruppe, Markt-Groesse)
   - Was sind die Folgen, wenn nichts passiert? (Kosten, verlorene Chancen)
2. **Solution Overview** (3-5 Saetze):
   - Was bauen wir? (Produkt, Service, Prozess)
   - Wie loest es das Problem? (Schluessel-Mechanismus, USPs)
   - Was sind die Kern-Features? (3-5 Bullet-Points)
3. **Value Proposition** (2-3 Saetze):
   - Welchen messbaren Mehrwert bringt es? (Zeit-Ersparnis, Kosten-Reduktion, Umsatz-Steigerung)
   - Fuer wen? (Primärer Nutzer, Sekundaerer Nutzer)
   - Wann ist es verfuegbar? (Time-to-Market)
4. **Output** in context.section_executive als Markdown mit 3 H3-Blocks

## Format
```markdown
### Problem Statement
...

### Solution Overview
...

### Value Proposition
...
```

## Wichtig
- **Zielgruppensprache** — schreibe fuer C-Level, nicht fuer Entwickler
- **Messbar** — Value Proposition braucht konkrete Zahlen
- **Keine TODOs** — alle Aussagen muessen vollstaendig sein
- **Keine Marketing-Floskeln** — sei konkret und ehrlich
""",

    # === Step 5: Subagent spec-requirements ===
    "40ddf52c601d": """# Subagent: Anforderungen (Functional + Non-Functional)

## Rolle
pi-coder-spec-requirements — du bist der Requirements-Engineer.

## Ziel
Sammle alle Functional + Non-Functional Requirements mit eindeutigen IDs, MoSCoW-Prioritaet und Akzeptanzkriterien.

## Input
- context.project_goal
- context.section_outline
- context.template_category
- context.cio_questions (Detail-Antworten des Users)
- context.cio_corrections (falls Loop-Back von CIO)

## Vorgehen

### Functional Requirements (FRs)
1. **Identifiziere 5-15 FRs** — was muss das System tun?
2. **Vergib IDs**: FR-001, FR-002, ...
3. **Formuliere testbar** mit "shall"-Sprache: "Das System soll..."
4. **Pro FR 3-5 Akzeptanzkriterien** im GIVEN-WHEN-THEN-Format
5. **MoSCoW-Prioritaet**:
   - Must: Pflicht, ohne geht es nicht
   - Should: wichtig, aber Release-1-blockierend
   - Could: nice-to-have
   - Won't: explizit nicht in diesem Release

### Non-Functional Requirements (NFRs)
1. **Mindestens 5 NFRs** aus: Performance, Security, Scalability, Availability, Compliance, Maintainability
2. **Vergib IDs**: NFR-001, NFR-002, ...
3. **Konkrete Metriken** statt vager Aussagen:
   - SCHLECHT: "Das System soll schnell sein"
   - GUT: "p99-Response-Time < 200ms bei 1000 RPS"
4. **Messbar**: Alle NFRs brauchen eine Metrik + Zielwert

### Out-of-Scope
- Liste explizit, was NICHT dazugehoert (verhindert Scope-Creep)

## Output in context.section_requirements
```markdown
## Functional Requirements
### FR-001: <Name> (Must)
Das System soll ...
**Akzeptanzkriterien:**
- GIVEN ... WHEN ... THEN ...
- ...

### FR-002: <Name> (Should)
...

## Non-Functional Requirements
### NFR-001: Performance
p99-Response-Time < 200ms bei 1000 RPS
...

## Out of Scope
- Feature X (kommt in v2.0)
- ...
```

## Wichtig
- **Loop-Back beachten**: Falls context.cio_corrections gesetzt ist, diese ZUERST einarbeiten!
- **IDs sind unveraenderlich** — nie eine ID wiederverwenden
- **Akzeptanzkriterien sind Pflicht** — ohne sie ist das Requirement nicht testbar
- **NFRs brauchen Metriken** — sonst sind sie wertlos
""",

    # === Step 6: Subagent spec-stakeholders ===
    "3c10192d9452": """# Subagent: Stakeholder + RACI + Success Criteria

## Rolle
pi-coder-spec-stakeholders — du bist der Org-Designer.

## Ziel
Identifiziere Stakeholder, baue RACI-Matrix, definiere Success-Kriterien (KPIs).

## Input
- context.project_goal
- context.template_category
- context.section_requirements (zur Konsistenz)

## Vorgehen

### Stakeholder-Analyse
1. **Identifiziere 5+ Stakeholder**:
   - Sponsor / Auftraggeber
   - Product Owner
   - Entwicklungsteam (Dev, Test, Ops)
   - End-User
   - Operations / Support
   - Management / C-Level
   - Compliance / Legal (je nach Kategorie)
2. **Pro Stakeholder dokumentiere**:
   - Name / Rolle
   - Verantwortungsbereich
   - Erwartungen / Interessen
   - Kontakt-Frequenz

### RACI-Matrix
Pro Aktivitaet / Feature: Wer ist R, A, C, I?
- R = Responsible (macht es)
- A = Accountable (genehmigt, genau 1 Person)
- C = Consulted (wird vor Entscheidung gefragt)
- I = Informed (wird nach Entscheidung informiert)

RACI-Regeln:
- Genau 1 A pro Aktivitaet
- Mindestens 1 R pro Aktivitaet
- C und I sind optional

### Success-Criteria / KPIs
- 3-5 messbare KPIs
- Pro KPI: Name, Berechnung, Zielwert, Mess-Frequenz
- Beispiele:
  - "Time-to-Market: 3 Monate (Zielwert), gemessen von Kickoff bis Rollout"
  - "User-Adoption: 60% nach 3 Monaten (Zielwert), gemessen via Login-Counts"
  - "Defect-Rate: < 0.5% (Zielwert), gemessen via Bug-Tracker"

## Output in context.section_stakeholders
```markdown
## Stakeholder

| Rolle | Name | Verantwortung | Erwartungen | Kontakt-Frequenz |
|-------|------|---------------|-------------|------------------|
| ... | ... | ... | ... | ... |

## RACI-Matrix

| Aktivitaet | R | A | C | I |
|------------|---|---|---|---|
| ... | ... | ... | ... | ... |

## Success Criteria (KPIs)

| KPI | Berechnung | Zielwert | Mess-Frequenz |
|-----|------------|----------|---------------|
| ... | ... | ... | ... |
```

## Wichtig
- **Stakeholder realistisch** — nicht 20 Personen, sondern die wichtigen 5-10
- **RACI vollstaendig** — jede Aktivitaet braucht R+A
- **KPIs messbar** — Zielwert + Mess-Methode + Frequenz
""",

    # === Step 7: Subagent spec-timeline ===
    "feb9822b3591": """# Subagent: Timeline + Milestones

## Rolle
pi-coder-spec-timeline — du bist der Projekt-Planer.

## Ziel
Erstelle eine realistische Timeline mit Phaasen, Milestones, Abhaengigkeiten und Gantt-Tabelle.

## Input
- context.project_goal
- context.section_requirements (Komplexitaet bestimmt Dauer)
- context.section_stakeholders (Stakeholder-Verfuegbarkeit)

## Vorgehen

### Phaasen
1. **Identifiziere 3-7 Phaasen**:
   - Discovery / Anforderungsanalyse (1-3 Wochen)
   - Design / Architektur (2-4 Wochen)
   - Implementation / Build (4-12 Wochen)
   - Testing / QA (2-4 Wochen)
   - Rollout / Go-Live (1-2 Wochen)
   - Hypercare / Stabilisierung (2-4 Wochen)
2. **Pro Phase**: Name, Daver, Hauptaktivitaeten

### Milestones
1. **5-10 Milestones** definieren — wichtige Checkpoints
2. **Pro Milestone**: Name, Datum (oder Woche), Deliverable, Verantwortlich
3. **Beispiele**:
   - M1: Kickoff-Completed (Woche 1)
   - M2: Requirements-Signed-Off (Woche 3)
   - M3: Architecture-Review-Passed (Woche 5)
   - M4: Alpha-Release (Woche 8)
   - M5: Beta-Release (Woche 11)
   - M6: GA-Release (Woche 14)

### Abhaengigkeiten
- Welche Milestones blocken andere?
- Welche externen Abhaengigkeiten gibt es? (z.B. "API vom Backend-Team bis Woche 4")

### Gantt-Tabelle
- Vereinfachte Gantt-Darstellung als Markdown-Tabelle
- Pro Phase: Start, Ende, Daver

## Output in context.section_timeline
```markdown
## Phaasen

| Phase | Daver | Start | Ende | Hauptaktivitaeten |
|-------|-------|-------|------|-------------------|
| ... | ... | ... | ... | ... |

## Milestones

| Milestone | Datum | Deliverable | Verantwortlich | Abhaengigkeiten |
|-----------|-------|-------------|----------------|------------------|
| M1: ... | Woche 1 | ... | ... | - |
| M2: ... | Woche 3 | ... | ... | M1 |

## Gantt

| Phase | W1 | W2 | W3 | W4 | W5 | ... |
|-------|----|----|----|----|----|-----|
| Discovery | ██ | ██ | ██ | | | |
| Design | | | | ██ | ██ | ... |
```

## Wichtig
- **Realistisch** — nicht 2 Wochen fuer ein 6-Monats-Projekt
- **Abhaengigkeiten explizit** — versteckte Blockaden vermeiden
- **Deliverables konkret** — "Dokument X" statt "Documentation"
""",

    # === Step 8: Subagent spec-risk ===
    "362738875378": """# Subagent: Risks + Constraints + Assumptions

## Rolle
pi-coder-spec-risk — du bist der Risk-Manager.

## Ziel
Identifiziere Risiken, dokumentiere Constraints und Assumptions, entwickle Mitigation-Plan.

## Input
- context.project_goal
- context.section_requirements
- context.section_timeline (Timeline-Risiken)
- context.section_stakeholders (Stakeholder-Risiken)

## Vorgehen

### Risk-Matrix
1. **Identifiziere 5-10 Risiken** in diesen Kategorien:
   - **Technical**: Tech-Stack nicht reif, Performance-Probleme, Security-Luecken
   - **Skills**: Team hat nicht die noetigen Skills, Key-Person-Dependency
   - **Business**: Anforderungen aendern sich, Sponsor verliert Interesse
   - **Environment**: Regulatorische Aenderungen, Markt-Veraenderungen
   - **Operational**: Deployment-Komplexitaet, 3rd-Party-Dependencies
2. **Pro Risk dokumentiere**:
   - ID: RISK-001, RISK-002, ...
   - Kategorie
   - Beschreibung
   - Wahrscheinlichkeit (Low/Medium/High)
   - Impact (Low/Medium/High)
   - Risk-Score = Wahrscheinlichkeit × Impact
   - Mitigation-Massnahme
3. **Top-3-Risiken** mit detailliertem Mitigation-Plan

### Constraints
- 3-5 Rahmenbedingungen, die das Projekt einschraenken:
  - Budget (z.B. "max 100k EUR")
  - Team-Groesse (z.B. "3 Entwickler")
  - Time-to-Market (z.B. "Q3 2026")
  - Technologie (z.B. "muss in Python geschrieben sein")
  - Compliance (z.B. "DSGVO-konform")

### Assumptions
- 3-5 Annahmen, die wir treffen (und die schiefgehen koennen):
  - "API wird vom Backend-Team bis Woche 4 geliefert"
  - "User haben Chrome/Edge als Browser"
  - "Cloud-Infrastruktur ist verfuegbar und kostet < X EUR/Monat"

## Output in context.section_risks
```markdown
## Risk-Matrix

| ID | Kategorie | Beschreibung | Wahrsch. | Impact | Score | Mitigation |
|----|-----------|--------------|----------|--------|-------|------------|
| RISK-001 | Technical | ... | High | High | 9 | ... |
| RISK-002 | Skills | ... | Medium | High | 6 | ... |
| ... | ... | ... | ... | ... | ... | ... |

## Constraints
- **Budget**: max 100k EUR (Begruendung: Q3-Plan freigegeben)
- **Team-Groesse**: 3 Entwickler + 1 Tester
- **Time-to-Market**: Q3 2026 (wegen Markt-Launch)
- ...

## Assumptions
- API vom Backend-Team bis Woche 4 verfuegbar
- User verwenden moderne Browser (Chrome/Edge/Firefox)
- Cloud-Infrastruktur hat < 100ms Latenz zwischen Services
- DSGVO-Anforderungen bleiben im Projekt-Zeitraum stabil

## Mitigation-Plan fuer Top-3-Risiken

### RISK-001: <Name>
**Beschreibung**: ...
**Fruehe Indikatoren**: ...
**Praeventive Massnahmen**: ...
**Reaktive Massnahmen (falls es eintritt)**: ...
**Owner**: ...
```

## Wichtig
- **Konkret** — "Server crash" ist zu vage, "Postgres-Connection-Pool exhausted bei >500 connections" ist konkret
- **Quantifiziert** — Wahrscheinlichkeit und Impact in konkreten Werten
- **Actionable Mitigation** — nicht "mehr Testen", sondern "Lasttests ab Woche 6 mit 2000 RPS"
""",
}


def main():
    db = SessionLocal()
    try:
        print("=" * 70)
        print("ai_instructions_md fuer Subagent-Steps + CIO-Review ergaenzen")
        print("=" * 70)
        for sid, ai_md in AI_INSTRUCTIONS.items():
            s = db.query(SOPStep).filter(SOPStep.id == sid).first()
            if not s:
                print(f"  SKIP: {sid} nicht gefunden")
                continue
            # WICHTIG: explizite Kopie + flag_modified, sonst persistiert SQLAlchemy die Aenderung nicht
            ap = dict(s.action_params or {})
            ap["ai_instructions_md"] = ai_md
            s.action_params = ap
            flag_modified(s, "action_params")
            print(f"  OK: #{s.step_order} {s.id[:12]} | +{len(ai_md)}b ai_instructions_md | {s.name[:45]}")
        db.commit()
        print()
        print("Final check:")
        steps = db.query(SOPStep).filter(SOPStep.sop_id == ISCP_ID).order_by(SOPStep.step_order).all()
        for s in steps:
            ai = (s.action_params or {}).get('ai_instructions_md') if s.action_params else None
            print(f"  #{s.step_order} | {s.id[:12]} | ai={len(ai) if ai else 0}b | {s.name[:40]}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
