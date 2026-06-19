"""SelfImprovement: Knowledge hub & framework comparison for self-improving agents.

Liefert die Recherche zu Self-Improvement-Frameworks (GenericAgent, EvoAgentX,
Midas Agent, DGM, HGM, etc.) sowie einen konkreten Aktionsplan fuer die
PI-Architektur (PI-Haupt-Agent + swarm-spawner Sub-Agents).

Zusaetzlich (User-Direktive 17.06.2026): Schwachstellen-Dokumentation
mit automatischer Subagent-Analyse (MiniMax M3).
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import require_auth
from ..db.base import get_db
from ..models.improvement import Weakness, WeaknessAnalysis
from ..models.task import Task
from ..models.project import Project

logger = logging.getLogger("pi-dashboard-2")

router = APIRouter(prefix="/api/selfimprovement", tags=["selfimprovement"])


FRAMEWORKS = [
    {
        "name": "GenericAgent",
        "stars": "12.8K",
        "description": "Self-evolving agent framework. 3K lines seed code wächst einen Skill-Tree. 9 atomare Tools, ~100 Zeilen Agent Loop.",
        "url": "https://github.com/lsdefine/GenericAgent",
        "approach": "Skill crystallization: Jede gelöste Aufgabe wird als Skill gespeichert. Nächstes Mal direkter Recall statt Neuberechnung.",
        "key_insight": "MiniMax-M3 + Ollama Gemma4 kompatibel. ~30K context window (sehr token-effizient). Layered Memory (L0-L4).",
        "applicable": True,
        "rationale": "Kann mit deinen vorhandenen MiniMax/Ollama-Modellen laufen. Selbst-evolvierender Skill-Tree passt perfekt zu deinen swarm-spawner Rollen.",
    },
    {
        "name": "EvoAgentX",
        "stars": "3K",
        "description": "Framework for building, evaluating, and evolving LLM agent workflows in an automated, modular, goal-driven manner.",
        "url": "https://github.com/EvoAgentX/EvoAgentX",
        "approach": "Self-evolution engine mit TextGrad, MIPRO, AFlow, EvoPrompt Algorithmen. Workflows werden automatisch generiert und optimiert.",
        "key_insight": "Human-in-the-Loop (HITL), Memory Module (short+long term), Built-in Tools (Search, Code, Browser, DB). MCP-kompatibel.",
        "applicable": True,
        "rationale": "Enthält AFlow (MCTS-basierte Workflow-Evolution) — könnte deine context-workflow Extension ersetzen oder ergänzen.",
    },
    {
        "name": "AgentEvolver (ModelScope)",
        "stars": "1K",
        "description": "End-to-end self-evolving training framework: self-questioning, self-navigating, self-attributing.",
        "url": "https://github.com/modelscope/AgentEvolver",
        "approach": "GRPO + Self-Questioning (autonome Task-Generierung), Self-Navigating (cross-task experience), Self-Attributing (fine-grained credit assignment).",
        "key_insight": "7B Modell erreicht 60%+ auf SWE-bench. 3 Self-Evolving Mechanisms aus einer Hand.",
        "applicable": False,
        "rationale": "Requires custom model training (GRPO). Für dich zu heavy, aber die Ideen (Self-Questioning für Task-Generierung) sind adaptierbar.",
    },
    {
        "name": "Agent0 (UNC/Salesforce)",
        "stars": "1.2K",
        "description": "Self-evolving agents from ZERO data. Curriculum Agent + Executor Agent. ICML'26.",
        "url": "https://github.com/aiming-lab/Agent0",
        "approach": "Curriculum Agent schlägt Aufgaben vor, Executor Agent lernt sie mit Tools zu lösen. Symbiotic competition.",
        "key_insight": "+18% auf math reasoning, +24% general reasoning. Zero external data. Funktioniert mit Qwen, Gemma, etc.",
        "applicable": True,
        "rationale": "Das Curriculum-Agent-Prinzip passt perfekt: Dein Haupt-PI (MiniMax) als Curriculum Agent, Sub-Agenten (Ollama) als Executors.",
    },
    {
        "name": "AutoAgent (HKU)",
        "stars": "9.3K",
        "description": "Fully-automated zero-code LLM agent framework. Baut Agenten aus natürlicher Sprache.",
        "url": "https://github.com/HKUDS/AutoAgent",
        "approach": "Agent Editor + Workflow Editor per Natural Language. Self-Play Agent Customization.",
        "key_insight": "Deep Research Mode (multi-agent). Container-basierte Isolation für Code-Ausführung.",
        "applicable": False,
        "rationale": "Zu high-level für deine bestehende Architektur, aber die Zero-Code-Idee für Rapid Prototyping interessant.",
    },
    {
        "name": "Lumos",
        "stars": "Neu",
        "description": "Self-evolving coding agent mit Trajectory Logging, Evaluator, Optimizer und Harness Packages.",
        "url": "https://github.com/SallyKAN/lumos",
        "approach": "Observe → Evaluate → Optimize → Distribute. Interceptor-System (10 Lifecycle Points). Memory Synthesis mit 3-Tier Decay.",
        "key_insight": "Harness Packages bündeln optimiertes Agent-Verhalten. Trajectory als First-Class Data für Evaluation.",
        "applicable": True,
        "rationale": "Das Interceptor-System (10 Lifecycle Points mit Onion Model) ist perfekt für deine context-workflow Extension.",
    },
    {
        "name": "Darwin Gödel Machine",
        "stars": "Projekt",
        "description": "Open-ended evolution of self-improving agents. Iteriert Code, validiert mit SWE-bench.",
        "url": "https://github.com/HarleyCoops/dgm",
        "approach": "Agent modifiziert eigenen Code, validiert Änderungen mit Coding Benchmarks. Polyglot + SWE-bench Evaluation.",
        "key_insight": "Self-modification Loop: Agent → Code ändern → Benchmark → Keep/Revert → Repeat.",
        "applicable": False,
        "rationale": "Zu akademisch/forschungsorientiert, aber das Keep/Revert-Prinzip ist in den Karpathy-Auto-Research-Loop eingeflossen.",
    },
    {
        "name": "Huxley-Gödel Machine",
        "stars": "356 (ICLR 2026 Oral)",
        "description": "Approximation des theoretischen Gödel Machine. Clade-basierte Self-Modification.",
        "url": "https://github.com/metauto-ai/HGM",
        "approach": "Estimates promise of entire subtrees (clades) to decide which self-modifications to expand.",
        "key_insight": "ICLR 2026 Oral Paper. Gödel Machine ist die theoretisch optimale Self-Improving Machine.",
        "applicable": False,
        "rationale": "Reine Forschung, aber die Clade-Idee ist interessant: Gruppe verwandter Verbesserungen evaluieren.",
    },
    {
        "name": "SII CLI (GAIR-NLP/SJTU)",
        "stars": "34",
        "description": "Cognitive Agentic Intelligence Ecosystem. Self-evolution durch Data Flywheel + Model Training.",
        "url": "https://github.com/GAIR-NLP/SII-CLI",
        "approach": "Data Flywheel: Automatic Query Synthesis → Simulated Agent Interaction → Continuous Reinforcement.",
        "key_insight": "Domain-Specific SFT + Vibe Coding + Research Workflows. Five-Module Architecture.",
        "applicable": False,
        "rationale": "Model-Training-Fokus. Zu heavy für dein Setup, aber die Data Flywheel Idee ist gut.",
    },
    {
        "name": "Self-Improving Coding Agent",
        "stars": "312",
        "description": "Agent der an seinem eigenen Codebase arbeitet. Benchmark → Improve → Re-Benchmark Loop.",
        "url": "https://github.com/MaximeRobeyns/self_improving_coding_agent",
        "approach": "ICLR 2025 Workshop Paper. Docker-isolated. Agent evaluiert sich selbst auf Benchmarks, dann verbessert er seinen eigenen Code.",
        "key_insight": "Meta-improvement: Der Agent verbessert nicht nur seine Outputs, sondern seine eigene Architektur.",
        "applicable": False,
        "rationale": "Forschung. Aber Meta-Improvement ist der nächste Schritt nach deinem swarm-spawner.",
    },
    {
        "name": "Midas Agent",
        "stars": "Neu",
        "description": "Coding agent der aus Fehlern lernt. Lesson Library + DAG Workflows + Importance Voting.",
        "url": "https://github.com/zysilm/midas-agent",
        "approach": "ExpeL-style self-reflection. Lessons werden extrahiert, via Embedding gespeichert und bei ähnlichen Issues wieder eingespielt.",
        "key_insight": "65% Pass Rate auf SWE-bench mit MiniMax-M2.5. 25% weniger Tokens durch Lesson Injection.",
        "applicable": True,
        "rationale": "MiniMax-M2.5 + Lesson Library = direkt nutzbar. Importance Voting verhindert Lesson Bloat. Perfekt für deine Sub-Agenten.",
    },
]


STRATEGY = {
    "title": "Pi Agent Self-Improvement Strategy",
    "date": "2026-06-14",
    "current_architecture": {
        "main_agent": "PI (MiniMax-M3)",
        "sub_agents": "swarm-spawner (Ollama Gemma4 12b)",
        "extensions": ["context-workflow", "cost-tracker", "openbrain-bridge", "git-checkpoint"],
    },
    "phases": [
        {
            "phase": 1,
            "name": "Lesson Library (Midas-Ansatz)",
            "description": "Jeder Sub-Agent speichert Lessons aus Fehlschlägen. Bei neuen Tasks werden relevante Lessons via Embedding-Suche injiziert.",
            "implementation": "Erweitere swarm-spawner um Failure Analyzer. Speichere Lessons in OpenBrain. Nutze Sentence-Transformers für Semantic Search.",
            "effort": "2-3 Sessions",
            "impact": "Sub-Agenten werden mit jeder Iteration besser. Weniger Wiederholungsfehler.",
            "packages": "sentence-transformers, faiss-cpu (oder OpenBrain als Vector Store)",
        },
        {
            "phase": 2,
            "name": "Skill Tree Evolution (GenericAgent-Ansatz)",
            "description": "Jede erfolgreich gelöste Sub-Agent-Aufgabe wird als Skill im Skill-Tree kristallisiert. Nächstes Mal direkter Recall.",
            "implementation": "Erweitere context-workflow: Nach erfolgreichem write→test→review→fix→verify Zyklus wird der Lösungsweg als Skill gespeichert.",
            "effort": "3-5 Sessions",
            "impact": "Häufige Tasks werden in Sekunden statt Minuten gelöst. Token-Verbrauch sinkt dramatisch.",
            "packages": "Bestehende SKILL.md-Struktur + OpenBrain-Speicherung",
        },
        {
            "phase": 3,
            "name": "Curriculum Learning (Agent0-Ansatz)",
            "description": "Haupt-PI (Curriculum Agent) schlägt zunehmend schwierigere Tasks vor, Sub-Agenten (Executors) lernen sie zu lösen.",
            "implementation": "Baue einen Difficulty-Scorer für Tasks. Automatische Progression von einfach → komplex.",
            "effort": "5-8 Sessions",
            "impact": "Systematische Kompetenzentwicklung. Der Agent wird mit der Zeit objektiv besser.",
        },
        {
            "phase": 4,
            "name": "Meta-Improvement Loop (DGM/HGM-Ansatz)",
            "description": "Der Haupt-Agent modifiziert seine eigene Konfiguration (toolWhitelist, systemPrompt, timeout) und validiert die Änderung.",
            "implementation": "Baue einen Meta-Agent: A/B-Test von Konfig-Änderungen. Keep/Revert basierend auf Token-Effizienz und Success-Rate.",
            "effort": "8-12 Sessions",
            "impact": "Der Agent optimiert sich selbst. Kein manuelles Tuning mehr nötig.",
        },
        {
            "phase": 5,
            "name": "Architecture Evolution (EvoAgentX-Ansatz)",
            "description": "AFlow-ähnliche MCTS-basierte Workflow-Evolution. context-workflow wird automatisch restrukturiert.",
            "implementation": "Trial verschiedene Stage-Sequenzen. Finde die optimale Pipeline für jeden Task-Typ.",
            "effort": "10-15 Sessions",
            "impact": "Maximale Effizienz durch optimierte Workflow-Strukturen.",
        },
    ],
    "recommended_start": "Phase 1 (Lesson Library) — niedrigste Einstiegshürde, höchster ROI. Basis für alle weiteren Phasen.",
    "key_papers": [
        {"title": "ExpeL: LLM Agents That Learn from Experience", "url": "https://arxiv.org/abs/2308.10144"},
        {"title": "GenericAgent Technical Report", "url": "https://arxiv.org/abs/2604.17091"},
        {"title": "Agent0: Self-Evolving Agents from Zero Data", "url": "https://arxiv.org/abs/2511.16043"},
        {"title": "EvoAgentX Framework Paper", "url": "https://arxiv.org/abs/2507.03616"},
        {"title": "Self-Evolving AI Agents Survey", "url": "https://arxiv.org/abs/2508.07407"},
        {"title": "EvoAgentX Survey on Self-Evolving Agents", "url": "https://arxiv.org/abs/2508.07407"},
        {"title": "Darwin Gödel Machine", "url": "https://arxiv.org/abs/2505.22954"},
        {"title": "Huxley-Gödel Machine (ICLR 2026)", "url": "https://arxiv.org/abs/2510.21614"},
        {"title": "AutoAgent: Zero-Code LLM Agent Framework", "url": "https://arxiv.org/abs/2502.05957"},
    ],
}


@router.get("/frameworks")
async def list_frameworks(_user: str = Depends(require_auth)) -> list[dict]:
    """Liste aller recherchierten Self-Improvement Frameworks."""
    return FRAMEWORKS


@router.get("/strategy")
async def improvement_strategy(_user: str = Depends(require_auth)) -> dict:
    """Konkreter Aktionsplan fuer Self-Improvement in deiner Pi-Architektur."""
    return STRATEGY


# ══════════════════════════════════════════════════════════════════════
# Schwachstellen + Subagent-Analyse (User-Direktive 17.06.2026, Prio 90)
# ══════════════════════════════════════════════════════════════════════

class WeaknessCreate(BaseModel):
    title: str
    description: str
    project_id: str  # PFLICHT — bestimmt in welches Board der spaetere Task kommt
    severity: str = "medium"  # low|medium|high|critical
    category: str = "other"  # bug|ui|perf|security|arch|other
    created_by: str = "user"


class WeaknessUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    severity: Optional[str] = None
    category: Optional[str] = None
    status: Optional[str] = None


class AnalysisEdit(BaseModel):
    """Vom User editierter Vorschlag (Loesung)."""
    root_cause: Optional[str] = None
    solution_proposal: Optional[str] = None


# Standard-System-Prompt fuer Subagent-Schwachstellen-Analyse
ANALYSIS_SYSTEM_PROMPT = """Du bist ein erfahrener Software-Engineering-Analyst fuer das PI-Dashboard 2.0 System.

Deine Aufgabe: Analysiere die gemeldete Schwaechstelle und erstelle:

1. **root_cause** (Ursachenanalyse, 2-5 Saetze):
   - Was ist die wahrscheinlichste technische Ursache?
   - Welche Dateien/Komponenten sind vermutlich betroffen?
   - Welche Muster aus dem OpenBrain (Architecture Rules, RACI, Standard-Workflow) sind relevant?

2. **solution_proposal** (Loesungsvorschlag, konkret und umsetzbar):
   - Konkrete Code-Aenderungen mit Datei-Pfaden
   - Schritt-fuer-Schritt-Anleitung
   - Acceptance Criteria (testbar)
   - Geschaetzter Aufwand
   - Risiken/Nebenwirkungen

3. **praeventive_massnahmen** (zusaetzlich in root_cause oder als zusaetzlicher Abschnitt):
   - Wie kann dieser Fehler zukuenftig verhindert werden?
   - Welche Tests, Checks, SOPs sind sinnvoll?

Antworte AUSSCHLIESSLICH mit einem JSON-Objekt mit den Feldern:
{
  "root_cause": "...",
  "solution_proposal": "...",
  "preventive_measures": "..."
}

Keine zusaetzlichen Erklaerungen ausserhalb des JSON.
"""


@router.get("/weaknesses")
async def list_weaknesses(
    project_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 100,
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
) -> list[dict]:
    """Liste aller dokumentierten Schwaechstellen (optional gefiltert nach Projekt/Status)."""
    stmt = select(Weakness).order_by(Weakness.created_at.desc())
    if project_id:
        stmt = stmt.where(Weakness.project_id == project_id)
    if status:
        stmt = stmt.where(Weakness.status == status)
    stmt = stmt.limit(limit)
    items = list(db.execute(stmt).scalars())
    return [w.to_dict(include_analyses=True) for w in items]


@router.post("/weaknesses")
async def create_weakness(
    body: WeaknessCreate,
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
) -> dict:
    """Erstellt eine neue Schwaechstelle und startet SOFORT die Subagent-Analyse.

    Subagent verwendet IMMER MiniMax M3 (User-Direktive 17.06.2026).
    """
    from ..models.improvement import _gen_id  # type: ignore

    # === Projekt-Existenz pruefen (User-Direktive: PFLICHT) ===
    project = db.get(Project, body.project_id)
    if not project:
        raise HTTPException(404, f"Projekt {body.project_id} nicht gefunden. Bitte gueltige project_id angeben.")

    # === Weakness anlegen ===
    weakness = Weakness(
        id=_gen_id(),
        title=body.title,
        description=body.description,
        project_id=body.project_id,
        severity=body.severity,
        category=body.category,
        status="analyzing",
        created_by=body.created_by,
    )
    db.add(weakness)
    db.flush()

    # === Initiale Analysis anlegen (Status: analyzing) ===
    analysis = WeaknessAnalysis(
        id=_gen_id(),
        weakness_id=weakness.id,
        model="minimax-direct/minimax-m3",
        status="analyzing",
    )
    db.add(analysis)
    db.commit()
    db.refresh(weakness)
    db.refresh(analysis)

    # === Subagent-Analyse IM HINTERGRUND starten ===
    # (Wird im naechsten Schritt via /weaknesses/{id}/analyze angestossen)
    # ODER sofort hier:
    import asyncio
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    async def run_analysis():
        """Fuehrt die LLM-Analyse im Hintergrund durch."""
        from ..services.llm_service import chat_completion
        try:
            start = time.time()
            user_prompt = (
                f"Schwaechstelle: {body.title}\n\n"
                f"Beschreibung: {body.description}\n\n"
                f"Projekt: {project.name}\n"
                f"Kategorie: {body.category}\n"
                f"Severity: {body.severity}\n"
            )
            response = await chat_completion(
                messages=[
                    {"role": "system", "content": ANALYSIS_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                model="minimax-direct/minimax-m3",
                temperature=0.3,
                max_tokens=3000,
                response_format={"type": "json_object"},
                timeout_sec=300.0,
            )
            # JSON parsen
            try:
                # ggf. Markdown-Codeblock entfernen
                clean = response.strip()
                if clean.startswith("```"):
                    lines = clean.split("\n")
                    if lines[0].startswith("```"):
                        lines = lines[1:]
                    if lines and lines[-1].strip() == "```":
                        lines = lines[:-1]
                    clean = "\n".join(lines).strip()
                data = json.loads(clean)
                root_cause = data.get("root_cause", "")
                solution_proposal = data.get("solution_proposal", "")
                preventive = data.get("preventive_measures", "")
                # Loesungsvorschlag mit Praeventiv-Massnahmen anreichern
                if preventive and preventive not in solution_proposal:
                    solution_proposal += f"\n\n## Praeventive Massnahmen\n\n{preventive}"
            except Exception as parse_err:
                logger.warning(f"JSON-Parse fehlgeschlagen: {parse_err}, response: {response[:300]}")
                root_cause = "JSON-Parse fehlgeschlagen."
                solution_proposal = response  # Roh-Output als Vorschlag

            # In DB speichern
            with db.begin():
                ana = db.get(WeaknessAnalysis, analysis.id)
                if ana:
                    ana.root_cause = root_cause
                    ana.solution_proposal = solution_proposal
                    ana.status = "done"
                    ana.completed_at = datetime.utcnow()
                    ana.duration_ms = int((time.time() - start) * 1000)
                weak = db.get(Weakness, weakness.id)
                if weak:
                    weak.status = "done"
            logger.info(f"Analyse {analysis.id} fuer Weakness {weakness.id} abgeschlossen in {int((time.time() - start) * 1000)}ms")
        except Exception as e:
            logger.error(f"Analyse {analysis.id} fehlgeschlagen: {e}")
            with db.begin():
                ana = db.get(WeaknessAnalysis, analysis.id)
                if ana:
                    ana.status = "failed"
                    ana.error = str(e)[:500]
                weak = db.get(Weakness, weakness.id)
                if weak:
                    weak.status = "failed"

    # Background-Task starten (fire-and-forget)
    try:
        asyncio.create_task(run_analysis())
    except Exception as e:
        logger.warning(f"Background-Task konnte nicht gestartet werden: {e}")

    return weakness.to_dict(include_analyses=True)


@router.get("/weaknesses/{weakness_id}")
async def get_weakness(
    weakness_id: str,
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
) -> dict:
    """Detail einer Schwaechstelle + alle Analysen."""
    w = db.get(Weakness, weakness_id)
    if not w:
        raise HTTPException(404, f"Weakness {weakness_id} nicht gefunden")
    return w.to_dict(include_analyses=True)


@router.put("/weaknesses/{weakness_id}")
async def update_weakness(
    weakness_id: str,
    body: WeaknessUpdate,
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
) -> dict:
    """Bearbeitet Schwachstelle (Title/Description/Severity/Category/Status)."""
    w = db.get(Weakness, weakness_id)
    if not w:
        raise HTTPException(404, f"Weakness {weakness_id} nicht gefunden")
    if body.title is not None:
        w.title = body.title
    if body.description is not None:
        w.description = body.description
    if body.severity is not None:
        w.severity = body.severity
    if body.category is not None:
        w.category = body.category
    if body.status is not None:
        w.status = body.status
    w.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(w)
    return w.to_dict(include_analyses=True)


@router.put("/analyses/{analysis_id}")
async def edit_analysis(
    analysis_id: str,
    body: AnalysisEdit,
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
) -> dict:
    """User editiert den Loesungsvorschlag einer Analyse.

    Edit-History wird mitgespeichert (JSON-Array).
    """
    ana = db.get(WeaknessAnalysis, analysis_id)
    if not ana:
        raise HTTPException(404, f"Analysis {analysis_id} nicht gefunden")

    history = json.loads(ana.edit_history) if ana.edit_history else []
    if body.root_cause is not None and body.root_cause != ana.root_cause:
        history.append({
            "ts": datetime.utcnow().isoformat(),
            "field": "root_cause",
            "old": ana.root_cause,
            "new": body.root_cause,
            "by": "user",
        })
        ana.root_cause = body.root_cause
    if body.solution_proposal is not None and body.solution_proposal != ana.solution_proposal:
        history.append({
            "ts": datetime.utcnow().isoformat(),
            "field": "solution_proposal",
            "old": ana.solution_proposal[:200],
            "new": body.solution_proposal[:200],
            "by": "user",
        })
        ana.solution_proposal = body.solution_proposal

    ana.edit_history = json.dumps(history, ensure_ascii=False)
    db.commit()
    db.refresh(ana)
    return ana.to_dict()


@router.post("/weaknesses/{weakness_id}/reanalyze")
async def reanalyze_weakness(
    weakness_id: str,
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
) -> dict:
    """Startet eine NEUE Analyse (alte bleibt erhalten)."""
    w = db.get(Weakness, weakness_id)
    if not w:
        raise HTTPException(404, f"Weakness {weakness_id} nicht gefunden")
    project = db.get(Project, w.project_id)
    if not project:
        raise HTTPException(404, f"Projekt nicht gefunden")

    from ..models.improvement import _gen_id  # type: ignore
    new_analysis = WeaknessAnalysis(
        id=_gen_id(),
        weakness_id=weakness_id,
        model="minimax-direct/minimax-m3",
        status="analyzing",
    )
    db.add(new_analysis)
    w.status = "analyzing"
    db.commit()
    db.refresh(new_analysis)
    return new_analysis.to_dict()


@router.post("/weaknesses/{weakness_id}/create-task")
async def create_task_from_weakness(
    weakness_id: str,
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
) -> dict:
    """Erstellt einen Task AUS der Schwaechstelle (im richtigen Projekt/Board).

    Der Task-Inhalt wird aus dem aktuellen Loesungsvorschlag generiert.
    """
    w = db.get(Weakness, weakness_id)
    if not w:
        raise HTTPException(404, f"Weakness {weakness_id} nicht gefunden")

    latest_analysis = None
    if w.analyses:
        latest_analysis = sorted(w.analyses, key=lambda a: a.started_at, reverse=True)[0]

    description = f"**Aus Self-Improvement: {w.title}**\n\n"
    description += f"**Beschreibung:** {w.description}\n\n"
    description += f"**Severity:** {w.severity}\n"
    description += f"**Category:** {w.category}\n\n"
    if latest_analysis and latest_analysis.root_cause:
        description += f"**Ursache (Subagent MiniMax M3):**\n{latest_analysis.root_cause}\n\n"
    if latest_analysis and latest_analysis.solution_proposal:
        description += f"**Loesungsvorschlag (editierbar):**\n{latest_analysis.solution_proposal}\n\n"
    description += f"\n---\n*Auto-erstellt aus Schwachstelle `{w.id}` (User-Direktive 17.06.2026)*"

    severity_to_prio = {"low": 30, "medium": 50, "high": 75, "critical": 95}
    prio = severity_to_prio.get(w.severity, 50)

    from ..models.task import Task
    import secrets
    task = Task(
        id=secrets.token_hex(6),
        project_id=w.project_id,
        title=f"[SelfImp] {w.title}",
        description=description,
        status="triage",
        priority=prio,
        category=w.category if w.category in ("bug", "ui", "perf", "security", "arch") else "change",
        assigned_role="pi-coder",
        tags=["self-imp", f"weakness-{w.id}", f"severity-{w.severity}"],
        success_criteria=[
            "Ursache identifiziert und im Code behoben",
            "Tests geschrieben (bestaetigen den Fix)",
            "Praeventive Massnahmen implementiert (CI-Check, SOP, etc.)",
        ],
    )
    db.add(task)
    db.flush()

    if w.analyses:
        history = json.loads(w.analyses[0].edit_history) if w.analyses[0].edit_history else []
        history.append({
            "ts": datetime.utcnow().isoformat(),
            "event": "task_created",
            "task_id": task.id,
            "by": _user,
        })
        w.analyses[0].edit_history = json.dumps(history, ensure_ascii=False)

    w.status = "reviewed"
    db.commit()
    db.refresh(task)

    return {
        "ok": True,
        "task_id": task.id,
        "task": {
            "id": task.id,
            "title": task.title,
            "status": task.status,
            "priority": task.priority,
            "project_id": task.project_id,
        },
        "weakness_id": weakness_id,
    }

