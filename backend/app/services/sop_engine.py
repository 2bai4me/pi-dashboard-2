"""SOP-Engine — generischer Regelprozess-Interpreter.

User-Direktive 15.06.2026:
  Ersetzt den hartcodierten Workflow (TRIAGE -> GO -> IN_PROGRESS -> REVIEW ->
  BLOCK -> DONE) durch eine generische Engine, die beliebige SOPs
  (Standard Operating Procedures) ausfuehren kann.

Engine-Aufgaben:
  1. Trigger pruefen: feuert der aktuelle Step?
  2. Step ausfuehren: Action an Agent delegieren
  3. Rule auswerten: Wenn-Dann-Logik anwenden
  4. Transition: zum naechsten Step gehen (success/fail/sub-sop)
  5. Sub-SOP spawnen: action_type="spawn_sop"
  6. Audit: jede Aktion in sop_executions dokumentieren

Verwendung:
  engine = SOPEngine(db)
  instance = engine.create_instance(sop_id=..., project_id=..., task_id=...)
  engine.run_step(instance)  # fuehrt aktuellen Step aus
  engine.evaluate_rules(instance, step_result)
  engine.advance(instance)
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import secrets
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, Dict, Any, List, Tuple

from sqlalchemy import select, func as sqlfunc
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..models.sop import (
    SOP, SOPStep, SOPStepRule, SOPInstance, SOPExecution,
)
from ..models.task import Task
from ..models.project import Project
from ..models.role import Role
from ..models.history import TaskHistory
from ..schemas.sop_action import ALLOWED_ACTIONS as ALLOWED_SOP_ACTIONS, ACTION_PARAM_SCHEMAS
from .llm_service import chat_completion
from .task_service import TaskService

try:
    import httpx
except ImportError:  # pragma: no cover
    httpx = None  # type: ignore

logger = logging.getLogger("pi-dashboard-2.sop")


# === SOP-Ausfuehrungs-Guards (Security & Stability) ===
_DEFAULT_STEP_TIMEOUT_S: float = 300.0
_MAX_STEP_TIMEOUT_S: float = 600.0
_DEFAULT_MAX_COST_USD: float = 10.0
_DEFAULT_MAX_LLM_TOKENS: int = 1_000_000
_DEFAULT_MAX_STEP_ITERATIONS: int = 10


def _gen_id() -> str:
    return secrets.token_hex(6)


# === SOP-getriebene Agent-Ausfuehrung (User-Direktive 23.06.2026) ===
# Konzept:
#   SOP-Step = aufgabenspezifische Anweisung (user_prompt, ai_instructions_md)
#   Rolle   = aufgabenunabhaengige Persona (system_prompt, provider, model, api_key)
#   -> System-Prompt = role.system_prompt + step.ai_instructions_md
#   -> Model/Provider aus Role, nicht aus action_params
#   -> Jeder LLM-Call wird vollstaendig in task_history dokumentiert.

def _load_role_for_step(db: Session, step: SOPStep) -> Optional[Role]:
    """Laedt die Rolle (SubAgent/Org-Role) anhand step.agent aus der DB.

    Returns None, wenn keine Rolle mit dem Namen existiert.
    Der Aufrufer MUSS damit umgehen (Fallback-Logik).
    """
    if not step.agent:
        return None
    return db.execute(
        select(Role).where(Role.name == step.agent)
    ).scalar_one_or_none()


def _build_system_prompt(role: Optional[Role], params: Dict[str, Any]) -> str:
    """Baut den System-Prompt aus Rolle + SOP-Step.

    Reihenfolge (jeder Block durch '---' getrennt):
      1. role.system_prompt  -> Persona, Haltung, Verantwortung (aus roles-Tabelle)
      2. params.ai_instructions_md -> Workflow/Vorgehen/Output-Format (aus sop_steps)
      3. params.system_prompt -> Optionaler Override (nur wenn beides fehlt)

    Wichtig: Die Rolle liefert die PERSONA, die SOP liefert die AUFGABE.
    Niemals persona-spezifische Inhalte in die SOP packen, und umgekehrt.
    """
    parts: List[str] = []
    if role and role.system_prompt and role.system_prompt.strip():
        parts.append(role.system_prompt.strip())
    instructions = params.get("ai_instructions_md")
    if instructions and str(instructions).strip():
        parts.append(
            "## WORKFLOW-ANWEISUNGEN AUS DEM SOP-SCHritt\n"
            f"({_gen_id()} - vom System hinzugefuegt)\n\n"
            + str(instructions).strip()
        )
    if not parts:
        fallback = params.get("system_prompt")
        if fallback:
            parts.append(str(fallback))
        else:
            parts.append("Du bist ein hilfreicher Assistent.")
    return "\n\n---\n\n".join(parts)


def _resolve_model_from_role(role: Optional[Role], params: Dict[str, Any]) -> str:
    """Loest das zu verwendende Modell auf.

    Prioritaet:
      1. role.model  (Single Source of Truth aus roles-Tabelle)
      2. params.model (Override nur fuer Sonderfaelle)
      3. Default 'minimax-m3'
    """
    if role and role.model:
        return role.model
    return params.get("model") or "minimax-m3"


def _substitute_task_placeholders(
    db: Session,
    text: str,
    task: Optional[Any] = None,
    instance: Optional[Any] = None,
    step: Optional[Any] = None,
) -> str:
    """Ersetzt Platzhalter im Text mit echten Werten aus Task/Project/Step.

    Unterstuetzte Platzhalter (User-Direktive 24.06.2026):
      {task_id}, {task_title}, {task_description}, {task_status},
      {task_status_display}, {task_priority}, {task_tags},
      {success_criteria}, {task_meta}, {implementation_plan},
      {assigned_role}, {assigned_subagent},
      {project_id}, {project_name}, {project_number},
      {sop_id}, {sop_name},
      {step_id}, {step_name}, {step_order}, {step_agent}

    Fehlende Werte werden durch "[n/a]" ersetzt (statt LLM-Fehler).
    """
    if not text or "{" not in text:
        return text

    import re as _re
    # Kontext-Werte sammeln
    ctx: Dict[str, Any] = {}

    if task is not None:
        ctx["task_id"] = task.id or "[n/a]"
        ctx["task_title"] = task.title or "[n/a]"
        ctx["task_description"] = task.description or "[n/a]"
        ctx["task_status"] = task.status or "[n/a]"
        ctx["task_status_display"] = _get_status_display(task.status)
        ctx["task_priority"] = task.priority if task.priority is not None else "[n/a]"
        ctx["task_tags"] = json.dumps(task.tags or [], ensure_ascii=False)
        ctx["assigned_role"] = task.assigned_role or "[n/a]"
        ctx["assigned_subagent"] = task.assigned_subagent or "[n/a]"
        # Success Criteria
        sc = task.success_criteria or []
        if isinstance(sc, str):
            try:
                sc = json.loads(sc)
            except Exception:
                sc = []
        ctx["success_criteria"] = json.dumps(sc, indent=2, ensure_ascii=False)
        # Meta + Implementation-Plan
        ctx["task_meta"] = json.dumps(task.meta or {}, indent=2, default=str, ensure_ascii=False)
        ip = task.implementation_plan
        if isinstance(ip, str):
            try:
                ip = json.loads(ip)
            except Exception:
                ip = {}
        ctx["implementation_plan"] = json.dumps(ip or {}, indent=2, default=str, ensure_ascii=False)
        # Project
        if task.project_id:
            from ..models.project import Project
            proj = db.get(Project, task.project_id)
            if proj:
                ctx["project_id"] = proj.id
                ctx["project_name"] = proj.name
                ctx["project_number"] = proj.project_number or "[n/a]"

    if instance is not None:
        ctx["sop_id"] = instance.sop_id or "[n/a]"
        if instance.sop_id:
            sop = db.get(SOP, instance.sop_id)
            if sop:
                ctx["sop_name"] = sop.name or "[n/a]"

    if step is not None:
        ctx["step_id"] = step.id or "[n/a]"
        ctx["step_name"] = step.name or "[n/a]"
        ctx["step_order"] = step.step_order if step.step_order is not None else "[n/a]"
        ctx["step_agent"] = step.agent or "[n/a]"

    # Regex-Find: {key} oder {key:default}
    def replacer(m: "_re.Match[str]") -> str:
        key = m.group(1).strip()
        if key in ctx:
            val = ctx[key]
            if val is None:
                return "[n/a]"
            return str(val)
        return m.group(0)  # Unbekannte Platzhalter unveraendert lassen

    pattern = _re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)(?::[^}]*)?\}")
    return pattern.sub(replacer, text)


def _get_status_display(status: str) -> str:
    """Mapping Task-Status -> Anzeige-Name."""
    mapping = {
        "triage": "Triage",
        "todo": "GO",
        "in_progress": "In Progress",
        "review": "Review",
        "block": "Block",
        "rueckfrage": "Rückfrage",
        "done": "Done",
        "cancelled": "Cancelled",
        "failed": "Failed",
    }
    return mapping.get(status or "", status or "[n/a]")


def _log_llm_call_to_history(
    db: Session,
    *,
    task: Optional[Task],
    step: SOPStep,
    role: Optional[Role],
    user_prompt: str,
    system_prompt: str,
    response: Dict[str, Any],
    duration_ms: int,
    ok: bool,
    error: Optional[str] = None,
) -> Optional[TaskHistory]:
    """Schreibt den LLM-Call in task_history (Audit-Log).

    Pflicht-Felder pro Eintrag (User-Direktive 23.06.2026):
      - ts:            Timestamp (automatisch durch server_default)
      - agent:         Rollen-Name (z.B. 'CIO', 'pi-architect')
      - model:         Verwendetes Modell (z.B. 'gemma4:12b')
      - tokens_in/out: Token-Verbrauch
      - cost_usd:      Kosten (aus pricing_service berechnet)
      - details:       Vollstaendiger Kontext (Provider, Prompts, Response, Dauer)
    """
    if task is None:
        return None
    usage = response.get("usage", {}) if isinstance(response, dict) else {}
    tokens_in = int(usage.get("tokens_in", 0) or 0)
    tokens_out = int(usage.get("tokens_out", 0) or 0)

    # Cost-Berechnung via pricing_service (falls verfuegbar)
    cost_usd = Decimal("0")
    try:
        from .pricing_service import take_pricing_snapshot
        model_name = (role.model if role and role.model else "minimax-m3")
        snapshot = take_pricing_snapshot(
            db,
            model=model_name,
            provider=(role.provider if role else None),
            role_name=step.agent,
        )
        if snapshot:
            input_per_1m = float(snapshot.get("input_per_1m", 0) or 0)
            output_per_1m = float(snapshot.get("output_per_1m", 0) or 0)
            cost_usd = Decimal(str(
                (tokens_in / 1_000_000.0) * input_per_1m
                + (tokens_out / 1_000_000.0) * output_per_1m
            ))
    except Exception as cost_err:
        logger.debug(f"Cost-Berechnung fuer History fehlgeschlagen: {cost_err}")

    history_details: Dict[str, Any] = {
        "step_id": step.id,
        "step_name": step.name,
        "step_order": step.step_order,
        "provider": (role.provider if role else None),
        "model": (role.model if role else None),
        "role_id": (role.id if role else None),
        "role_type": (role.role_type if role else None),
        "api_key_id": (role.api_key_id if role else None),
        "duration_ms": duration_ms,
        "ok": ok,
        "system_prompt_chars": len(system_prompt),
        "user_prompt_chars": len(user_prompt),
        "response_chars": len(str(response.get("content", ""))),
    }
    # Prompts und Response als Preview in details (zur Nachvollziehbarkeit)
    history_details["user_prompt_preview"] = user_prompt[:500]
    history_details["system_prompt_preview"] = system_prompt[:500]
    if ok:
        history_details["response_preview"] = str(response.get("content", ""))[:1000]
    else:
        history_details["error"] = error or response.get("error", "unknown")

    h = TaskHistory(
        task_id=task.id,
        event="llm_call",
        agent=step.agent,
        model=(role.model if role and role.model else "minimax-m3"),
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cost_usd=cost_usd,
        details=history_details,
    )
    db.add(h)
    try:
        db.commit()
    except Exception as commit_err:
        logger.warning(f"History-Commit fehlgeschlagen: {commit_err}")
        db.rollback()
    return h


# === JSON-Extraktoren aus LLM-Response (User-Direktive 23.06.2026) ===
# Viele SOP-Prompts fordern JSON-Output mit Feldern wie ok/issues/questions.
# Diese Helper extrahieren strukturierte Werte aus dem Response-Text.
# Robust gegenueber: reinem JSON, JSON-in-Markdown-Block, Text-vor-JSON, kaputtem JSON.

import re as _re_json

_JSON_FENCE = _re_json.compile(r"```(?:json)?\s*(\{.*?\})\s*```", _re_json.DOTALL | _re_json.IGNORECASE)
_JSON_BARE = _re_json.compile(r"(\{[\s\S]*\})")


def _try_parse_json(text: str) -> Optional[Dict[str, Any]]:
    """Versucht JSON aus Text zu extrahieren (Code-Fence, dann bare-Objekt, dann Repair).

    Robust gegenueber (User-Direktive 24.06.2026):
      - Reines JSON
      - JSON in Markdown-Code-Block (```json ... ```)
      - Text vor/nach JSON
      - JSON mit fehlenden/abschliessenden Klammern
      - JSON mit nicht-escapten Anfuehrungszeichen in Strings (Repair-Versuch)
      - Trailing Commas
    """
    if not text:
        return None
    # 1) Code-Fence
    m = _JSON_FENCE.search(text)
    if m:
        candidate = m.group(1)
        result = _try_parse_json_attempt(candidate)
        if result is not None:
            return result
    # 2) Bare-Objekt im Text
    m = _JSON_BARE.search(text)
    if m:
        candidate = m.group(1)
        result = _try_parse_json_attempt(candidate)
        if result is not None:
            return result
    # 3) Gesamter Text
    return _try_parse_json_attempt(text.strip())


def _try_parse_json_attempt(text: str) -> Optional[Dict[str, Any]]:
    """Einzelner JSON-Parse-Versuch mit Repair-Logik."""
    if not text:
        return None
    import re as _re_local
    # Erst direkt versuchen
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        pass
    # Repair-Versuch 1: Trailing Commas entfernen
    repaired = _re_local.sub(r",\s*([}\]])", r"\1", text)
    try:
        return json.loads(repaired)
    except (ValueError, TypeError):
        pass
    # Repair-Versuch 2: Fehlende schliessende Klammern ergaenzen
    if repaired.count("{") > repaired.count("}"):
        repaired2 = repaired.rstrip().rstrip(",") + "}" * (repaired.count("{") - repaired.count("}"))
        try:
            return json.loads(repaired2)
        except (ValueError, TypeError):
            pass
    # Repair-Versuch 3: Nicht-escapte Anfuehrungszeichen in Strings
    try:
        lines = text.split("\n")
        fixed_lines = []
        for line in lines:
            if line.count('"') % 2 == 1 and not line.strip().endswith('"'):
                line = line.rstrip().rstrip(",") + '"'
            fixed_lines.append(line)
        repaired3 = "\n".join(fixed_lines)
        repaired3 = _re_local.sub(r",\s*([}\]])", r"\1", repaired3)
        return json.loads(repaired3)
    except (ValueError, TypeError):
        return None


def _extract_step_approved_from_response(response_text: str) -> bool:
    """Extrahiert step_approved / ok aus LLM-Response. Default: True (konservativ).

    Strategie:
      1. JSON parsen -> ok/issues/questions Felder lesen
      2. Fallback: Heuristik ueber Schluesselwoerter im Text
    """
    data = _try_parse_json(response_text)
    if data is not None:
        if "ok" in data:
            return bool(data["ok"])
        if "step_approved" in data:
            return bool(data["step_approved"])
        if "approved" in data:
            return bool(data["approved"])
    # Fallback: Text-Heuristik
    if not response_text:
        return True
    text_lower = response_text.lower()
    if any(tok in text_lower for tok in ["ok: false", "ok:false", "\"ok\": false", "\"ok\":false", "not ok", "nicht ok", "issues gefunden"]):
        return False
    return True


def _extract_issues_from_response(response_text: str) -> List[Dict[str, Any]]:
    """Extrahiert issues[] aus LLM-Response. Default: []."""
    data = _try_parse_json(response_text)
    if data is not None and isinstance(data.get("issues"), list):
        return list(data["issues"])
    return []


def _extract_questions_from_response(response_text: str) -> List[Dict[str, Any]]:
    """Extrahiert questions[] aus LLM-Response. Default: []."""
    data = _try_parse_json(response_text)
    if data is not None and isinstance(data.get("questions"), list):
        return list(data["questions"])
    return []


# === Engine-Hauptklasse ===

class SOPEngine:
    """Engine zum Ausfuehren von SOPs.

    Methoden:
      - list_sops(category=None)
      - get_sop(sop_id)
      - create_sop(name, description, steps, ...)
      - update_sop(sop_id, ...)
      - delete_sop(sop_id)
      - create_instance(sop_id, project_id, task_id, parent_instance_id)
      - run_step(instance) -> fuehrt aktuellen Step aus
      - evaluate_rules(instance, step_result) -> wertet Wenn-Dann aus
      - advance(instance, next_step_id) -> geht zum naechsten Step
      - spawn_sub_sop(parent_instance, sub_sop_id) -> startet Sub-SOP
      - complete(instance) -> markiert Instance als completed
      - fail(instance, reason) -> markiert Instance als failed
    """

    def __init__(self, db: Session):
        self.db = db

    # === Guard-Helper ===

    def _step_timeout_s(self, step: SOPStep) -> float:
        """Ermittelt das fuer diesen Step gueltige Execution-Timeout."""
        params = step.action_params or {}
        timeout = float(params.get("timeout_sec", _DEFAULT_STEP_TIMEOUT_S))
        return min(max(timeout, 0.001), _MAX_STEP_TIMEOUT_S)

    async def _validate_swarm_description(
        self,
        instance: SOPInstance,
        step: SOPStep,
        task: Optional[Task],
        params: Dict[str, Any],
        config: Any,  # SwarmConfig
    ) -> Dict[str, Any]:
        """LLM-Validierung der Swarm-Beschreibung (User-Direktive 24.06.2026).

        Konzept: Die Bausteine (Swarm-Spawner-Logik) bleiben erhalten.
        Aber die BESCHREIBUNG (was die Worker tun sollen) wird per LLM
        validiert, weil sie je nach SOP komplett anders aussehen kann.

        Pruefungen:
          - Sind die Worker-Prompts konsistent mit dem user_prompt?
          - Gibt es Konflikte zwischen den Worker-Varianten?
          - Passt die Rollen-Auswahl zur Aufgabe?
          - Fehlen kritische Anweisungen?

        Returns: {ok: bool, reasoning: str, issues: [...]}
        """
        # Worker-Prompts zusammenbauen
        workers_text = "\n\n".join(
            f"### Worker: {w.role} (Variante: {w.variant})\n{w.system_prompt or '(kein system_prompt definiert)'}"
            for w in config.workers
        )
        user_prompt = params.get("user_prompt", "")
        workflow = params.get("ai_instructions_md", "")
        validation_prompt = (
            f"## USER-PROMPT (aufgabenspezifisch aus SOP)\n{user_prompt}\n\n"
            f"## WORKFLOW (aus SOP ai_instructions_md)\n{workflow}\n\n"
            f"## WORKER-KONFIGURATION (aus SOP action_params.workers[])\n{workers_text}\n\n"
            f"## PRUEFUNG\n"
            f"Bewerte ob die Worker-Konfiguration konsistent mit der Aufgabe ist.\n"
            f"Liefere JSON: {{ok: bool, issues: [{{worker, problem, severity}}], reasoning: str}}\n"
            f"ok=true wenn keine schwerwiegenden Issues vorhanden."
        )
        validation_params = {
            "user_prompt": validation_prompt,
            "ai_instructions_md": (
                "## Rolle\nDu bist SOP-Validator.\n\n"
                "## Ziel\nPruefe ob die Swarm-Beschreibung (User-Prompt + Workflow + "
                "Worker-Prompts) konsistent und vollstaendig ist.\n\n"
                "## Output-Format\nJSON: {ok: bool, issues: [{worker, problem, severity}], reasoning: str}"
            ),
            "response_format": {"type": "json_object"},
            "max_tokens": 1500,
            "temperature": 0.1,
        }
        # Validierungs-Step: Agent ist der SOP-Lead (kann jede Rolle sein, hier generisch)
        # Wir nutzen die Rolle des eigentlichen Steps, weil der die Konfiguration kennt
        result = await self._llm_call_async(instance, step, task, validation_params)
        if not result.get("ok"):
            return {
                "ok": True,  # Bei LLM-Fehler: optimistisch (Bausteine bleiben funktional)
                "reasoning": "LLM-Validierung nicht moeglich - Beschreibung als akzeptabel angenommen",
                "issues": [],
            }
        content = result.get("response", {}).get("content", "")
        parsed = _try_parse_json(content) or {}
        return {
            "ok": bool(parsed.get("ok", True)),
            "reasoning": parsed.get("reasoning", ""),
            "issues": parsed.get("issues", []),
        }

    async def _evaluate_metrics_with_llm(
        self,
        instance: SOPInstance,
        step: SOPStep,
        task: Optional[Task],
        params: Dict[str, Any],
        action: str,
    ) -> Dict[str, Any]:
        """SOP-getriebene Metrik-Bewertung (fuer tester_code_review + cio_final_review).

        Konzept (User-Direktive 24.06.2026): Auch Metrik-Checks sind SOP-getrieben.
          - LLM bekommt die Metriken (aus task.meta) + Acceptance-Criteria (aus action_params)
          - System-Prompt kommt aus der Rolle (pi-tester/CIO je nach action)
          - Workflow + Pruef-Logik + Output-Format stehen in step.ai_instructions_md
          - LLM liefert JSON: {ok: bool, issues: [...], reasoning: str}

        Vorteil: User kann beliebige Metriken + Schwellen im SOP definieren,
        ohne dass der Code geaendert werden muss.
        """
        if task is None:
            return {"ok": False, "error": f"{action}: benoetigt einen Task"}

        # 1. Metriken aus task.meta extrahieren
        meta = task.meta if isinstance(task.meta, dict) else {}
        # 2. Acceptance-Criteria aus action_params
        acceptance = params.get("acceptance_criteria", [])
        # 3. Original user_prompt aus SOP (aufgabenspezifisch)
        base_user_prompt = params.get("user_prompt", "")

        # 4. user_prompt mit Metriken + Kriterien anreichern (deterministisch)
        # Der SOP-Autor bestimmt die TEXT-StruktUR, der LLM bewertet.
        metrics_json = json.dumps(meta, indent=2, default=str, ensure_ascii=False)
        criteria_json = json.dumps(acceptance, indent=2, ensure_ascii=False)
        enriched_user_prompt = (
            f"{base_user_prompt}\n\n"
            f"## TASK-METRIKEN (aus task.meta)\n"
            f"```json\n{metrics_json}\n```\n\n"
            f"## ACCEPTANCE-CRITERIA (aus SOP action_params)\n"
            f"```json\n{criteria_json}\n```\n\n"
            f"## DEINE AUFGABE\n"
            f"Bewerte anhand der Metriken, ob die Acceptance-Criteria erfuellt sind.\n"
            f"Liefere JSON: {{ok: bool, issues: [{{criterion, actual, expected, severity}}], reasoning: str}}"
        )

        # 5. LLM-Call (delegiert an _llm_call_async -> nutzt Rolle + SOP-Workflow)
        enriched_params = dict(params)
        enriched_params["user_prompt"] = enriched_user_prompt
        enriched_params["response_format"] = {"type": "json_object"}
        result = await self._llm_call_async(instance, step, task, enriched_params)

        if not result.get("ok"):
            return {
                "ok": False,
                "action": action,
                "task_id": task.id,
                "agent": step.agent,
                "error": result.get("error"),
            }

        # 6. JSON-Antwort parsen
        content = result.get("response", {}).get("content", "")
        parsed = _try_parse_json(content) or {}
        ok = bool(parsed.get("ok", False))
        issues = parsed.get("issues", []) or []
        reasoning = parsed.get("reasoning", "")

        return {
            "ok": ok,
            "action": action,
            "task_id": task.id,
            "current_status": task.status,
            "agent": step.agent,
            "step_approved": ok,
            "issues": issues,
            "reasoning": reasoning,
            "metrics_provided": list(meta.keys()),
            "criteria_count": len(acceptance),
            "model": result.get("model"),
            "duration_ms": result.get("duration_ms"),
        }

    async def _llm_call_async(
        self,
        instance: SOPInstance,
        step: SOPStep,
        task: Optional[Task],
        params: Dict[str, Any],
    ) -> Dict[str, Any]:
        """SOP-getriebener LLM-Call (Wiederverwendbar fuer llm_call + review_task).

        Konzept (User-Direktive 23.06.2026):
          - System-Prompt = role.system_prompt (Persona) + step.ai_instructions_md (Workflow)
          - Model/Provider aus Role (Single Source of Truth)
          - user_prompt enthaelt die aufgabenspezifische Anweisung aus dem SOP-Step
          - Jeder Call wird in task_history dokumentiert (Timestamp, Rolle, Modell, Cost)
        """
        # 1. Rolle laden
        role = _load_role_for_step(self.db, step)
        if role is None:
            logger.warning(
                f"_llm_call_async: Rolle '{step.agent}' nicht in roles-Tabelle gefunden. "
                f"Fallback ohne Persona."
            )

        # 2. user_prompt validieren
        user_prompt = params.get("user_prompt", "")
        if not user_prompt:
            return {
                "ok": False,
                "error": (
                    "_llm_call_async: user_prompt fehlt in action_params. "
                    "Aufgabenspezifische Anweisung MUSS im SOP-Step stehen."
                ),
            }

        # 2a. Template-Substitution (User-Direktive 24.06.2026)
        # Ersetzt Platzhalter wie {task_title}, {project_name} etc. mit echten Werten.
        # BEVOR der LLM-Call gemacht wird, damit das LLM die echten Daten sieht.
        user_prompt = _substitute_task_placeholders(
            self.db, user_prompt, task=task, instance=instance, step=step
        )
        # ai_instructions_md ebenfalls substituieren (Workflow-Anweisungen)
        if "ai_instructions_md" in params and params["ai_instructions_md"]:
            params["ai_instructions_md"] = _substitute_task_placeholders(
                self.db, params["ai_instructions_md"], task=task, instance=instance, step=step
            )

        # 3. System-Prompt + Model aufloesen
        system_prompt = _build_system_prompt(role, params)
        model_name = _resolve_model_from_role(role, params)
        max_tokens = min(int(params.get("max_tokens", 2000)), 16000)
        timeout_sec = min(
            float(params.get("timeout_sec", role.timeout_sec if role else 60.0)),
            float(role.timeout_sec if role and role.timeout_sec else 300.0),
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        try:
            t0 = time.time()
            response = await chat_completion(
                messages=messages,
                model=model_name,
                temperature=params.get("temperature", 0.3),
                max_tokens=max_tokens,
                response_format=params.get("response_format"),
                timeout_sec=timeout_sec,
                role=step.agent,
            )
            duration_ms = int((time.time() - t0) * 1000)
            logger.info(
                f"_llm_call_async step={step.id} agent={step.agent} model={model_name} "
                f"duration={duration_ms}ms ok=True"
            )
            # History-Eintrag
            _log_llm_call_to_history(
                self.db,
                task=task,
                step=step,
                role=role,
                user_prompt=user_prompt,
                system_prompt=system_prompt,
                response=response,
                duration_ms=duration_ms,
                ok=True,
            )
            return {
                "ok": True,
                "action": "llm_call",
                "agent": step.agent,
                "role_id": role.id if role else None,
                "provider": (role.provider if role else None),
                "model": model_name,
                "duration_ms": duration_ms,
                "response": response,
            }
        except (RuntimeError, ValueError, OSError, httpx.HTTPError) as e:
            logger.error(f"_llm_call_async failed for step {step.id} (agent={step.agent}): {e}")
            _log_llm_call_to_history(
                self.db,
                task=task,
                step=step,
                role=role,
                user_prompt=user_prompt,
                system_prompt=system_prompt,
                response={"content": "", "usage": {}},
                duration_ms=0,
                ok=False,
                error=str(e),
            )
            return {"ok": False, "error": f"_llm_call_async failed: {e}", "agent": step.agent}

    def _guard_limits(self, instance: SOPInstance, step: SOPStep) -> Optional[Dict[str, Any]]:
        """Prueft Budget- und Loop-Guard vor der Step-Ausfuehrung.

        Liefert ein Fehler-Dict, wenn ein Limit ueberschritten wurde, sonst None.
        """
        params = step.action_params or {}
        max_cost = float(params.get("max_cost_usd", _DEFAULT_MAX_COST_USD))
        max_tokens = int(params.get("max_llm_tokens", _DEFAULT_MAX_LLM_TOKENS))
        max_iterations = int(params.get("max_step_iterations", _DEFAULT_MAX_STEP_ITERATIONS))

        # Iterations-Guard: wie oft wurde dieser Step bereits ausgefuehrt?
        iteration_count = self.db.execute(
            select(sqlfunc.count(SOPExecution.id))
            .where(SOPExecution.instance_id == instance.id)
            .where(SOPExecution.step_id == step.id)
            .where(SOPExecution.event.in_(["step_started", "step_completed"]))
        ).scalar() or 0
        if iteration_count >= max_iterations:
            return {
                "ok": False,
                "error": (
                    f"Step iteration guard triggered: step {step.id} executed "
                    f"{iteration_count} times (limit {max_iterations})"
                ),
            }

        # Budget-Guard: kumulierte Kosten/Tokens fuer den zugehoerigen Task
        if instance.task_id:
            from ..models.token_usage import TokenUsage
            totals = self.db.execute(
                select(
                    sqlfunc.coalesce(sqlfunc.sum(TokenUsage.cost_usd), 0.0),
                    sqlfunc.coalesce(sqlfunc.sum(TokenUsage.tokens_in + TokenUsage.tokens_out), 0),
                ).where(TokenUsage.task_id == instance.task_id)
            ).one()
            total_cost = float(totals[0] or 0.0)
            total_tokens = int(totals[1] or 0)
            if total_cost >= max_cost:
                return {
                    "ok": False,
                    "error": (
                        f"Instance budget exceeded: cost ${total_cost:.4f} >= "
                        f"limit ${max_cost:.4f}"
                    ),
                }
            if total_tokens >= max_tokens:
                return {
                    "ok": False,
                    "error": (
                        f"Instance token budget exceeded: {total_tokens} tokens >= "
                        f"limit {max_tokens}"
                    ),
                }

        return None

    # === CRUD: SOPs ===

    def list_sops(self, category: Optional[str] = None) -> List[SOP]:
        stmt = select(SOP).order_by(SOP.name, SOP.version.desc())
        if category:
            stmt = stmt.where(SOP.category == category)
        return list(self.db.execute(stmt).scalars())

    def get_sop(self, sop_id: str) -> Optional[SOP]:
        return self.db.get(SOP, sop_id)

    def create_sop(
        self, name: str, description: str, category: str = "task",
        version: int = 1, parent_sop_id: Optional[str] = None,
        is_template: bool = False, default_delay_s: float = 5.0,
        steps: Optional[List[Dict[str, Any]]] = None,
        _trusted: bool = False,
    ) -> SOP:
        """Erstellt eine neue SOP inkl. Steps + Rules.

        steps: Liste von Dicts mit:
          {
            "name": "...", "phase": "Task", "trigger": "...",
            "action": "...", "action_params": {...}, "agent": "...",
            "expected_result": "...", "success_criteria": [...],
            "delay_s": 5.0, "description": "...",
            "rules": [
              {
                "condition_field": "...", "condition_operator": "eq",
                "condition_value": True,
                "action_type": "move_status", "action_target": "todo",
                "action_params": {...}, "description": "..."
              },
              ...
            ]
          }
        """
        sop = SOP(
            id=_gen_id(),
            name=name,
            description=description,
            category=category,
            version=version,
            parent_sop_id=parent_sop_id,
            is_template=is_template,
            default_delay_s=default_delay_s,
        )
        self.db.add(sop)
        self.db.flush()

        step_id_map: Dict[int, str] = {}  # index -> step_id
        created_steps: List[SOPStep] = []
        if steps:
            for idx, sd in enumerate(steps):
                action = sd.get("action", "noop")
                params = sd.get("action_params") or {}
                schema_cls = ACTION_PARAM_SCHEMAS.get(action)
                if schema_cls:
                    schema_cls.model_validate(params)

            for idx, sd in enumerate(steps):
                step = SOPStep(
                    id=_gen_id(),
                    sop_id=sop.id,
                    step_order=idx,
                    name=sd.get("name", f"Step {idx+1}"),
                    phase=sd.get("phase", "Task"),
                    trigger=sd.get("trigger", "manual"),
                    action=sd.get("action", "noop"),
                    action_params=sd.get("action_params", {}),
                    agent=sd.get("agent", "system"),
                    model=sd.get("model"),
                    expected_result=sd.get("expected_result"),
                    success_criteria=sd.get("success_criteria", []),
                    delay_s=sd.get("delay_s", default_delay_s),
                    description=sd.get("description"),
                )
                self.db.add(step)
                self.db.flush()
                step_id_map[idx] = step.id
                created_steps.append(step)

                # Rules
                for ridx, rd in enumerate(sd.get("rules", [])):
                    rule = SOPStepRule(
                        id=_gen_id(),
                        step_id=step.id,
                        rule_order=ridx,
                        description=rd.get("description"),
                        condition_field=rd.get("condition_field", ""),
                        condition_operator=rd.get("condition_operator", "eq"),
                        condition_value=rd.get("condition_value"),
                        action_type=rd.get("action_type", "noop"),
                        action_target=rd.get("action_target"),
                        action_params=rd.get("action_params", {}),
                    )
                    self.db.add(rule)

            # Sicherheitspruefung: alle erstellten Steps muessen gegen die
            # Engine-Whitelist erlaubt sein. Bei Verstoss wird alles zurueckgerollt.
            # _trusted=True erlaubt System-/Seed-SOPs mit Legacy-Actions.
            if not _trusted:
                for step in created_steps:
                    if step.action not in ALLOWED_SOP_ACTIONS:
                        self.db.rollback()
                        raise ValueError(f"Disallowed SOP action: {step.action}")

            # Verzweigungen setzen
            self.db.flush()
            for idx, sd in enumerate(steps):
                if idx in step_id_map:
                    step = self.db.get(SOPStep, step_id_map[idx])
                    if "next_step" in sd and sd["next_step"] is not None:
                        step.next_step_id = step_id_map.get(sd["next_step"])
                    if "fail_step" in sd and sd["fail_step"] is not None:
                        step.fail_step_id = step_id_map.get(sd["fail_step"])
                    if "on_sub_sop_step" in sd and sd["on_sub_sop_step"] is not None:
                        step.on_sub_sop_step_id = step_id_map.get(sd["on_sub_sop_step"])

        self.db.commit()
        self.db.refresh(sop)
        return sop

    def update_sop(self, sop_id: str, **fields) -> Optional[SOP]:
        sop = self.db.get(SOP, sop_id)
        if not sop:
            return None
        for k, v in fields.items():
            if v is not None and hasattr(sop, k):
                setattr(sop, k, v)
        sop.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(sop)
        return sop

    def delete_sop(self, sop_id: str) -> bool:
        sop = self.db.get(SOP, sop_id)
        if not sop:
            return False
        self.db.delete(sop)
        self.db.commit()
        return True

    # === Instances ===

    def list_instances(
        self, project_id: Optional[str] = None,
        task_id: Optional[str] = None, status: Optional[str] = None,
    ) -> List[SOPInstance]:
        stmt = select(SOPInstance).order_by(SOPInstance.started_at.desc())
        if project_id:
            stmt = stmt.where(SOPInstance.project_id == project_id)
        if task_id:
            stmt = stmt.where(SOPInstance.task_id == task_id)
        if status:
            stmt = stmt.where(SOPInstance.status == status)
        return list(self.db.execute(stmt).scalars())

    def get_instance(self, instance_id: str) -> Optional[SOPInstance]:
        return self.db.get(SOPInstance, instance_id)

    def create_instance(
        self, sop_id: str,
        project_id: Optional[str] = None,
        task_id: Optional[str] = None,
        parent_instance_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Optional[SOPInstance]:
        """Startet eine neue SOP-Instance. Setzt current_step_id auf den ersten Step."""
        sop = self.db.get(SOP, sop_id)
        if not sop:
            return None
        if not sop.steps:
            logger.warning(f"SOP {sop_id} hat keine Steps")
            return None
        first_step = sorted(sop.steps, key=lambda s: s.step_order)[0]
        inst = SOPInstance(
            id=_gen_id(),
            sop_id=sop_id,
            project_id=project_id,
            task_id=task_id,
            current_step_id=first_step.id,
            status="running",
            parent_instance_id=parent_instance_id,
            context=context or {},
        )
        self.db.add(inst)
        self.db.flush()
        # Audit: instance_started
        self._log_execution(
            inst, step_id=first_step.id, event="instance_started",
            agent="system",
            details={"sop_id": sop_id, "first_step": first_step.id,
                     "first_step_name": first_step.name,
                     "project_id": project_id, "task_id": task_id},
        )
        self.db.commit()
        self.db.refresh(inst)
        return inst

    # === Engine: Step ausfuehren ===

    async def run_step(self, instance: SOPInstance) -> Dict[str, Any]:
        """Fuehrt den aktuellen Step aus.

        Reihenfolge:
          1) Step laden
          2) User-Input-Tool pruefen (blockierend wenn required und Context leer)
          3) Trigger pruefen
          4) Audit: step_started
          5) asyncio.sleep(step.delay_s) (sichtbarer Delay)
          6) Action an Agent delegieren (delegate-Action)
          7) Audit: step_completed mit Ergebnis
          8) Rules auswerten -> naechster Step
        """
        if instance.status != "running":
            return {"ok": False, "error": f"Instance is {instance.status}, not running"}

        step = self.db.get(SOPStep, instance.current_step_id)
        if not step:
            return {"ok": False, "error": "Step not found"}

        # === Verantwortlichen Agent aus dem SOP-Step auf den Task uebertragen ===
        # Damit Board-Karten immer den aktuellen Step-Agenten zeigen (z.B. CIO in Triage).
        task = self.db.get(Task, instance.task_id) if instance.task_id else None
        if task and step.agent:
            task.assigned_role = step.agent
            self.db.commit()

        # === Action-Whitelist (Sicherheit) ===
        if step.action not in ALLOWED_SOP_ACTIONS:
            logger.error(
                f"Unknown or disallowed SOP action {step.action!r} in step {step.id} "
                f"(instance {instance.id})"
            )
            return {"ok": False, "error": f"Unknown or disallowed SOP action: {step.action}"}

        # === User-Input-Tool (User-Direktive 17.06.2026) ===
        # Wenn der Step ein Input-Tool erfordert UND der Context-Wert fehlt,
        # wird BLOCKIEREND auf die User-Antwort gewartet.
        if step.input_tool_required:
            ctx_key = step.input_tool_context_key or f"step_{step.step_order}_input"
            existing = (instance.context or {}).get(ctx_key)
            if not existing:
                # User-Input holen (blockierend)
                input_result = await self._await_user_input(instance, step, ctx_key)
                if not input_result:
                    return {
                        "ok": False,
                        "error": "User-Input-Tool hat keine Antwort erhalten (abgebrochen oder Timeout)",
                        "blocked": True,
                    }
                # Context-Variable setzen
                ctx = dict(instance.context or {})
                ctx[ctx_key] = input_result
                instance.context = ctx
                self.db.commit()
                # Audit
                self._log_execution(
                    instance, step_id=step.id, event="input_received",
                    agent="user", success=True,
                    details={"context_key": ctx_key, "input": input_result},
                )
                self.db.commit()

        # === Budget- & Loop-Guard ===
        limit_violation = self._guard_limits(instance, step)
        if limit_violation:
            logger.error(
                f"[sop-guard] Instance {instance.id[:8]} step {step.name!r}: "
                f"{limit_violation['error']}"
            )
            self._log_execution(
                instance, step_id=step.id, event="step_failed",
                agent=step.agent, success=False,
                details=limit_violation,
            )
            self.db.commit()
            return self.fail_instance(instance, limit_violation["error"])

        start_ts = datetime.now(timezone.utc)
        # Audit: step_started
        self._log_execution(
            instance, step_id=step.id, event="step_started",
            agent=step.agent,
            details={"step_name": step.name, "phase": step.phase,
                     "trigger": step.trigger, "action": step.action,
                     "action_params": step.action_params or {},
                     "delay_s": step.delay_s},
        )
        self.db.commit()

        # Sichtbarer Delay (User-Direktive: 5s Verzoegerung)
        if step.delay_s > 0:
            logger.info(
                f"[sop-step-delay] Instance {instance.id[:8]} step {step.name!r} "
                f"agent={step.agent!r}: waiting {step.delay_s}s"
            )
            await asyncio.sleep(step.delay_s)

        # Action ausfuehren (mit Timeout)
        timeout_s = self._step_timeout_s(step)
        try:
            step_result = await asyncio.wait_for(
                self._execute_action(instance, step), timeout=timeout_s
            )
        except asyncio.TimeoutError:
            logger.error(
                f"[sop-timeout] Instance {instance.id[:8]} step {step.name!r} "
                f"exceeded timeout {timeout_s}s"
            )
            self._log_execution(
                instance, step_id=step.id, event="step_failed",
                agent=step.agent, success=False,
                details={"error": f"step timeout after {timeout_s}s"},
            )
            self.db.commit()
            if step.fail_step_id:
                return self.advance(
                    instance, step.fail_step_id,
                    {"ok": False, "error": f"step timeout after {timeout_s}s"},
                )
            return self.fail_instance(instance, f"step timeout after {timeout_s}s")

        duration_ms = int((datetime.now(timezone.utc) - start_ts).total_seconds() * 1000)

        # Audit: step_completed
        self._log_execution(
            instance, step_id=step.id, event="step_completed",
            agent=step.agent, duration_ms=duration_ms, success=step_result.get("ok", True),
            details=step_result,
        )
        self.db.commit()

        # Rules auswerten
        next_step_id, action = self.evaluate_rules(instance, step, step_result)
        if next_step_id is None:
            # End-State: Instance abschliessen
            return self._complete_instance(instance, step, step_result)

        # Zum naechsten Step
        return self.advance(instance, next_step_id, step_result)

    async def run_single_step(self, instance: SOPInstance) -> Dict[str, Any]:
        """Fuehrt NUR den aktuellen Step aus, OHNE advance/complete.

        Unterschied zu run_step():
          - run_step() macht Step + advance() zur naechsten Step
          - run_single_step() macht nur den Step und pausiert die Instance
          - Der User kann dann entscheiden, ob erweitert wird (via run_step) oder nicht

        Perfekt fuer schrittweises Testen/Manuelle-Steuerung (User-Direktive 24.06.2026).
        Instance-Status nach Aufruf: 'paused' (statt 'running' -> 'completed'/'failed')

        Returns: {
            ok: bool,
            step_result: dict,        # Resultat der Action
            step_id: str,
            step_name: str,
            duration_ms: int,
            next_step_id: str | None,  # Was waere der naechste Step (VORSCHLAG, nicht ausgefuehrt)
            instance_status: str,      # 'paused'
        }
        """
        if instance.status not in ("running", "paused"):
            return {"ok": False, "error": f"Instance is {instance.status}, not running/paused"}

        step = self.db.get(SOPStep, instance.current_step_id)
        if not step:
            return {"ok": False, "error": "Step not found"}

        # === Verantwortlichen Agent auf den Task uebertragen ===
        task = self.db.get(Task, instance.task_id) if instance.task_id else None
        if task and step.agent:
            task.assigned_role = step.agent
            self.db.commit()

        # === Action-Whitelist ===
        if step.action not in ALLOWED_SOP_ACTIONS:
            logger.error(
                f"[run_single_step] Disallowed action {step.action!r} in step {step.id}"
            )
            return {"ok": False, "error": f"Disallowed action: {step.action}"}

        # === Budget- & Loop-Guard ===
        limit_violation = self._guard_limits(instance, step)
        if limit_violation:
            logger.error(f"[run_single_step] Guard: {limit_violation['error']}")
            return limit_violation

        # === Audit: step_started ===
        start_ts = datetime.now(timezone.utc)
        self._log_execution(
            instance, step_id=step.id, event="step_started",
            agent=step.agent,
            details={
                "step_name": step.name,
                "phase": step.phase,
                "trigger": step.trigger,
                "action": step.action,
                "action_params": step.action_params or {},
                "delay_s": step.delay_s,
                "mode": "single_step",  # Markierung: NICHT advance
            },
        )
        self.db.commit()

        # === Sichtbarer Delay ===
        if step.delay_s > 0:
            logger.info(
                f"[run_single_step] Instance {instance.id[:8]} step {step.name!r}: "
                f"waiting {step.delay_s}s"
            )
            await asyncio.sleep(step.delay_s)

        # === Action ausfuehren (mit Timeout) ===
        timeout_s = self._step_timeout_s(step)
        try:
            step_result = await asyncio.wait_for(
                self._execute_action(instance, step), timeout=timeout_s
            )
        except asyncio.TimeoutError:
            logger.error(
                f"[run_single_step] Instance {instance.id[:8]} step {step.name!r} "
                f"timeout {timeout_s}s"
            )
            return {"ok": False, "error": f"step timeout after {timeout_s}s"}

        duration_ms = int((datetime.now(timezone.utc) - start_ts).total_seconds() * 1000)

        # === Audit: step_completed ===
        self._log_execution(
            instance, step_id=step.id, event="step_completed",
            agent=step.agent, duration_ms=duration_ms,
            success=step_result.get("ok", True),
            details={**step_result, "mode": "single_step"},
        )

        # === Step-Result in Context speichern (fuer spaetere Inspection) ===
        ctx = dict(instance.context or {})
        # Key-Format: step_N_result (z.B. step_0_result)
        ctx[f"step_{step.step_order}_result"] = step_result
        # Rule-Result-keys auch speichern (was waere passiert)
        instance.context = ctx

        # === Instance pausieren (statt complete/advance) ===
        instance.status = "paused"
        self.db.commit()

        # === Vorschlag fuer naechsten Step (ohne Advance) ===
        try:
            next_step_id, _action = self.evaluate_rules(instance, step, step_result)
        except Exception as rule_err:
            logger.warning(f"[run_single_step] Rule-Eval-Fehler: {rule_err}")
            next_step_id = None

        next_step_name = None
        if next_step_id:
            next_step = self.db.get(SOPStep, next_step_id)
            if next_step:
                next_step_name = next_step.name

        logger.info(
            f"[run_single_step] Instance {instance.id[:8]} step {step.name!r} "
            f"agent={step.agent!r} done (ok={step_result.get('ok')}, {duration_ms}ms). "
            f"Instance PAUSED. Naechster Step waere: {next_step_name or 'END'}"
        )

        return {
            "ok": True,
            "mode": "single_step",
            "instance_id": instance.id,
            "step_id": step.id,
            "step_name": step.name,
            "step_order": step.step_order,
            "step_result": step_result,
            "duration_ms": duration_ms,
            "next_step_id": next_step_id,
            "next_step_name": next_step_name,
            "instance_status": "paused",
        }

    async def _await_user_input(
        self, instance: SOPInstance, step: SOPStep, ctx_key: str,
        timeout_s: float = 3600.0,
    ) -> Optional[Dict[str, Any]]:
        """Erstellt eine AgentQuestion und wartet BLOCKIEREND auf die User-Antwort.

        Long-Polling: prueft alle 2s den Status der AgentQuestion.
        Timeout: default 1h (User hat genug Zeit fuer komplexe Antworten).
        Returns: dict {text, choice, question_id, answered_at, answered_by} oder None.
        """
        from ..models.agent_question import AgentQuestion
        from ..db.base import SessionLocal as _SessionLocal

        # 1) AgentQuestion erstellen
        q = AgentQuestion(
            agent_id=f"sop-{instance.id[:8]}",
            agent_level="Worker",
            agent_label=f"SOP '{instance.sop.name}' (Step {step.step_order}: {step.name})",
            question_type=step.input_tool_type or "text",
            title=step.name,
            question=step.input_tool_prompt or "Bitte um Input fuer diesen SOP-Step.",
            description=step.input_tool_description,
            recommendation=step.input_tool_recommendation,
            options=json.loads(step.input_tool_options) if step.input_tool_options else [],
            options_config=step.input_tool_options_config,  # JSON-String (show_description, show_tts, etc.)
            context={
                "sop_instance_id": instance.id,
                "sop_id": instance.sop_id,
                "step_id": step.id,
                "step_order": step.step_order,
                "context_key": ctx_key,
                "project_id": instance.project_id,
                "task_id": instance.task_id,
            },
            priority="medium",
            status="pending",
        )
        # Eigene Session fuer AgentQuestion-Insert (Hauptsession blockt)
        with _SessionLocal() as qdb:
            qdb.add(q)
            qdb.commit()
            qdb.refresh(q)
            qid = q.id

        # === Auto-Status-Update: Wenn Question an Task gebunden ist,
        #     Task-Status auf 'rueckfrage' setzen (via Helper).
        #     Wichtig: Helper nutzt eigene Session, weil die Engine-Hauptsession blockt.
        if instance.task_id:
            try:
                from .agent_question_helpers import update_task_on_question
                with _SessionLocal() as helper_db:
                    update_task_on_question(
                        db=helper_db,
                        task_id=instance.task_id,
                        question_id=qid,
                        agent_id=q.agent_id,
                        agent_label=q.agent_label,
                    )
            except (SQLAlchemyError, ValueError, TypeError) as e:
                logger.warning(f"Helper update_task_on_question fehlgeschlagen: {e}")

        # Audit: input_requested
        self._log_execution(
            instance, step_id=step.id, event="input_requested",
            agent="user", success=True,
            details={"context_key": ctx_key, "question_id": qid,
                     "question_type": step.input_tool_type, "timeout_s": timeout_s},
        )
        self.db.commit()

        logger.info(
            f"[user-input] SOP-Instance {instance.id[:8]} Step {step.name!r}: "
            f"BLOCKING on user input (question={qid}, timeout={timeout_s}s)"
        )

        # 2) BLOCKIEREND auf Antwort warten
        start = datetime.now(timezone.utc)
        deadline = start.timestamp() + timeout_s
        try:
            while datetime.now(timezone.utc).timestamp() < deadline:
                await asyncio.sleep(2.0)
                # In eigener Session pruefen (Hauptsession ist durch step in use)
                with _SessionLocal() as qdb:
                    current = qdb.get(AgentQuestion, qid)
                    if not current:
                        logger.warning(f"[user-input] Question {qid} disappeared")
                        return None
                    if current.status == "answered":
                        return {
                            "text": current.answer_text,
                            "choice": current.answer_choice,
                            "question_id": current.id,
                            "answered_at": current.answered_at.isoformat() if current.answered_at else None,
                            "answered_by": current.answered_by,
                        }
                    if current.status == "cancelled":
                        logger.info(f"[user-input] Question {qid} cancelled by user/agent")
                        return None
            # Timeout erreicht
            logger.warning(f"[user-input] Question {qid} timed out after {timeout_s}s")
            # Frage als expired markieren
            with _SessionLocal() as qdb:
                current = qdb.get(AgentQuestion, qid)
                if current and current.status == "pending":
                    current.status = "expired"
                    qdb.commit()
            return None
        except asyncio.CancelledError:
            logger.info(f"[user-input] Wait for {qid} cancelled")
            raise

    async def _execute_action(self, instance: SOPInstance, step: SOPStep) -> Dict[str, Any]:
        """Delegiert die Action des Steps an den zustaendigen Service.

        Unterstuetzte Actions:
          - noop: nichts tun
          - review_task: Task in step.agent Review geben (Phase 'review')
          - approve_triage: setzt Task in GO (CIO-Approve)
          - assign_worker: setzt assigned_role
          - start_work: setzt status in_progress
          - submit_review: setzt status review
          - tester_review: tester approve/reject
          - cio_final_approve: setzt done
          - spawn_sop: startet Sub-SOP
          - move_status: generischer Status-Wechsel
        """
        # BUGFIX 22.06.2026: 'task' aus instance ableiten (analog zu run_step:377),
        # weil _execute_action frueher eine undefinierte 'task'-Variable referenzierte
        # (NameError: name 'task' is not defined bei Custom-Triage-Actions).
        task = self.db.get(Task, instance.task_id) if instance.task_id else None
        action = step.action
        params = step.action_params or {}

        if action == "noop":
            return {"ok": True, "action": "noop", "note": "no action performed"}

        # === ask_user (User-Direktive 24.06.2026) ===
        # Wartet BLOCKIEREND auf User-Input. Frage und Kontext kommen aus
        # step.input_tool_* (SOP-Definition) + step.ai_instructions_md.
        if action == "ask_user":
            if not task:
                return {"ok": False, "error": "ask_user benoetigt einen Task"}
            ctx_key = params.get("context_key", "user_input")
            timeout_s = float(params.get("timeout_sec", 3600.0))
            # SOP-Description in question_text einbetten (falls vorhanden)
            if step.input_tool_prompt is None and params.get("user_prompt"):
                step.input_tool_prompt = params["user_prompt"]
            answer = await self._await_user_input(instance, step, ctx_key, timeout_s=timeout_s)
            if answer is None:
                return {
                    "ok": False,
                    "action": "ask_user",
                    "task_id": task.id,
                    "agent": step.agent,
                    "error": "Timeout: User hat nicht innerhalb des Timeouts geantwortet",
                }
            return {
                "ok": True,
                "action": "ask_user",
                "task_id": task.id,
                "agent": step.agent,
                "user_input": answer,
                "step_approved": True,
            }

        # === Multi-Agent-Swarm (User-Direktive 22.06.2026) ===
        # Startet einen Swarm von SubAgents (parallel/competitive) fuer
        # hoechste Qualitaet durch Diversitaet und Konsens-Bewertung.
        if action == "spawn_swarm":
            # Bugfix 23.06.2026 (Task 61ab3dfe26d3): Task sofort auf in_progress,
            # damit die UI nicht faelschlicherweise in 'triage' stehen bleibt,
            # obwohl Code-Bearbeitung bereits laeuft.
            if task is not None and task.status == "triage":
                task.status = "in_progress"
                self.db.commit()
                self._log_execution(
                    instance, step_id=step.id,
                    event="task_status_changed_to_in_progress",
                    agent=step.agent,
                    details={"reason": "spawn_swarm_started"},
                )
            return await self._execute_spawn_swarm(instance, step, task, params)

        if action == "spawn_sop":
            sub_sop_id = params.get("sop_id")
            if not sub_sop_id:
                return {"ok": False, "error": "spawn_sop: sop_id missing in action_params"}
            sub_inst = self.spawn_sub_sop(instance, sub_sop_id, params.get("context", {}))
            if sub_inst:
                return {"ok": True, "action": "spawn_sop", "sub_instance_id": sub_inst.id,
                        "sop_id": sub_sop_id, "status": sub_inst.status}
            return {"ok": False, "error": "spawn_sop failed"}

        # === LLM-Call Action (SOP-getrieben, User-Direktive 23.06.2026) ===
        # Delegiert an _llm_call_async (gleiche Logik wie review_task).
        # Konzept:
        #   - System-Prompt = role.system_prompt (Persona) + step.ai_instructions_md (Workflow)
        #   - Model/Provider stammen aus der Role (Single Source of Truth)
        #   - user_prompt enthaelt die aufgabenspezifische Anweisung aus dem SOP-Step
        #   - Jeder Call wird vollstaendig in task_history dokumentiert
        if action == "llm_call":
            # Bugfix 23.06.2026: Task in in_progress sobald Agent arbeitet
            if task is not None and task.status == "triage":
                task.status = "in_progress"
                self.db.commit()
            return await self._llm_call_async(instance, step, task, params)

        # === Custom-Actions fuer CIO-Triage-SOP ===
        # Diese Actions fuehren die 4 Kriterien-Pruefungen aus und sammeln Issues.
        # Sie arbeiten mit der Task-Description, den Architecture-Rules, etc.
        if action in ("check_title", "check_description", "check_success_criteria",
                       "check_architecture", "check_consistency", "decide_triage",
                       "collect_issue"):
            return self._execute_triage_action(instance, step, task, action, params)

        # Alle Task-Status-bezogenen Actions

        # Alle Task-Status-bezogenen Actions
        if not task:
            return {"ok": False, "error": f"action {action!r} requires task_id on instance"}

        if action == "review_task":
            # SOP-getriebene Review-Action (User-Direktive 23.06.2026).
            # Konzept: Die hartcodierte _check_cio_heuristik() ist ENTFALLEN.
            # Stattdessen delegiert review_task an llm_call:
            #   - System-Prompt kommt aus roles.system_prompt (CIO-Persona)
            #   - Workflow-Anweisungen kommen aus step.ai_instructions_md
            #   - user_prompt enthaelt die aufgabenspezifische Review-Frage
            # Zusaetzlich wird der Decompose-Check (Phase Go) deterministisch ausgefuehrt,
            # weil das eine themenbasierte Heuristik ist, die nicht ins LLM gehoert.
            if not task:
                return {"ok": False, "error": "review_task benoetigt einen Task"}

            # 1. Decompose-Check (deterministisch, themenbasiert - kein LLM)
            decompose_result = None
            try:
                from ..services.task_decomposer import (
                    should_decompose, create_subtasks_from_decomposition,
                )
                decomp = should_decompose(task.title or "", task.description or "")
                if decomp.should_split:
                    subtask_ids = create_subtasks_from_decomposition(
                        parent_task_id=task.id,
                        decomposition=decomp,
                        project_id=task.project_id,
                    )
                    TaskService.set_status_sync(
                        self.db, task.id, "go",
                        agent=step.agent,
                        reason=f"decomposed:{len(subtask_ids)}_subtasks",
                        delay_s=0.0,
                    )
                    if not isinstance(task.meta, dict):
                        task.meta = {}
                    task.meta["decomposition"] = {
                        "themes": decomp.detected_themes,
                        "subtask_ids": subtask_ids,
                        "rationale": decomp.rationale,
                    }
                    self.db.commit()
                    decompose_result = {
                        "decomposed": True,
                        "subtask_count": len(subtask_ids),
                        "subtask_ids": subtask_ids,
                        "themes": decomp.detected_themes,
                    }
                    logger.info(
                        f"Task {task.id[:8]} decomposed into {len(subtask_ids)} subtasks "
                        f"(themes: {', '.join(decomp.detected_themes)})"
                    )
            except Exception as dec_err:
                logger.warning(f"review_task: Decompose-Check fehlgeschlagen: {dec_err}")

            # 2. LLM-Call (delegiert an _llm_call_async - nutzt Rolle + SOP-Prompts)
            llm_result = await self._llm_call_async(instance, step, task, params)

            if not llm_result.get("ok"):
                return {
                    "ok": False,
                    "action": "review_task",
                    "task_id": task.id,
                    "agent": step.agent,
                    "decomposition": decompose_result,
                    "error": llm_result.get("error"),
                }

            # 3. Step-Approved-Flag fuer Rule-Engine ableiten
            response_content = llm_result.get("response", {}).get("content", "")
            step_approved = _extract_step_approved_from_response(response_content)
            issues = _extract_issues_from_response(response_content)
            questions = _extract_questions_from_response(response_content)

            return {
                "ok": step_approved,
                "action": "review_task",
                "task_id": task.id,
                "current_status": task.status,
                "agent": step.agent,
                "decomposition": decompose_result,
                "issues": issues,
                "questions": questions,
                "step_approved": step_approved,
                "response_content": response_content,
            }

        # === Stufe 1: Konkrete Step-Handler (User-Direktive 18.06.2026) ===
        # Vorher: review_task (generisch) wurde fuer ALLE Review-Steps genutzt.
        # Jetzt: tester_code_review und cio_final_review delegieren an _llm_call_async.
        # Konzept (User-Direktive 24.06.2026): Auch Metrik-Checks sind SOP-getrieben.
        #   - LLM bekommt die Metriken aus task.meta + Acceptance-Criteria aus action_params
        #   - System-Prompt kommt aus der Rolle (pi-tester fuer tester_code_review,
        #     CIO fuer cio_final_review)
        #   - Workflow-Anweisungen + Pruef-Logik kommen aus step.ai_instructions_md
        #   - LLM liefert JSON {ok, issues[], reasoning}
        if action in ("tester_code_review", "cio_final_review"):
            return await self._evaluate_metrics_with_llm(
                instance, step, task, params, action
            )


        if action == "move_status":
            new_status = params.get("status")
            if not new_status:
                return {"ok": False, "error": "move_status: status missing"}
            t = await TaskService.change_status_with_delay(
                self.db, t=task, new_status=new_status,
                agent=step.agent, reason=f"sop:{instance.sop_id}:{step.id}",
                details={"sop_instance_id": instance.id, "sop_step_id": step.id,
                         "sop_step_name": step.name},
                delay_s=0.0,  # Bereits in run_step gewartet
            )
            return {"ok": True, "action": "move_status",
                    "task_id": task.id, "new_status": t.status}

        # Standard-Workflow-Actions (koppeln an TaskService)
        if action == "approve_triage":
            t = await TaskService.change_status_with_delay(
                self.db, t=task, new_status="todo",
                agent=step.agent, reason="sop:approve_triage",
                delay_s=0.0,
            )
            return {"ok": True, "action": "approve_triage",
                    "task_id": task.id, "new_status": t.status}

        if action == "assign_worker":
            worker = params.get("worker", step.agent)
            old = task.assigned_role
            task.assigned_role = worker
            task.updated_at = datetime.now(timezone.utc)
            self.db.commit()
            return {"ok": True, "action": "assign_worker",
                    "task_id": task.id, "from": old, "to": worker}

        if action == "start_work":
            task.claimed_at = datetime.now(timezone.utc)
            # Stufe 2: assigned_role = step.agent (z.B. pi-coder in Step 2)
            old_role = task.assigned_role
            task.assigned_role = step.agent
            self.db.commit()
            t = await TaskService.change_status_with_delay(
                self.db, t=task, new_status="in_progress",
                agent=step.agent, reason="sop:start_work",
                delay_s=0.0,
            )
            return {"ok": True, "action": "start_work",
                    "task_id": task.id, "new_status": t.status, "worker": task.assigned_role,
                    "role_changed": {"from": old_role, "to": task.assigned_role}}

        if action == "submit_review":
            old_role = task.assigned_role
            task.assigned_role = step.agent  # pi-coder bleibt (Step 2 -> review, Worker dokumentiert)
            self.db.commit()
            t = await TaskService.change_status_with_delay(
                self.db, t=task, new_status="review",
                agent=step.agent, reason="sop:submit_review",
                delay_s=0.0,
            )
            return {"ok": True, "action": "submit_review",
                    "task_id": task.id, "new_status": t.status}

        if action == "tester_approve":
            old_role = task.assigned_role
            task.assigned_role = "pi-tester"  # Step 3 = pi-tester
            self.db.commit()
            t = await TaskService.change_status_with_delay(
                self.db, t=task, new_status="block",
                agent="pi-tester", reason="sop:tester_approve",
                delay_s=0.0,
            )
            return {"ok": True, "action": "tester_approve",
                    "task_id": task.id, "new_status": t.status}

        if action == "tester_reject":
            old_role = task.assigned_role
            task.assigned_role = "pi-tester"  # Step 3 = pi-tester
            self.db.commit()
            t = await TaskService.change_status_with_delay(
                self.db, t=task, new_status="in_progress",
                agent="pi-tester", reason="sop:tester_reject",
                delay_s=0.0,
            )
            task.iteration_count = (task.iteration_count or 0) + 1
            self.db.commit()
            return {"ok": True, "action": "tester_reject",
                    "task_id": task.id, "new_status": t.status,
                    "iteration": task.iteration_count}

        if action == "cio_final_approve":
            old_role = task.assigned_role
            task.assigned_role = step.agent  # Step 4 = CIO
            self.db.commit()
            t = await TaskService.change_status_with_delay(
                self.db, t=task, new_status="done",
                agent=step.agent, reason="sop:cio_final_approve",
                delay_s=0.0,
            )
            return {"ok": True, "action": "cio_final_approve",
                    "task_id": task.id, "new_status": t.status}

        if action == "cio_final_reject":
            old_role = task.assigned_role
            task.assigned_role = step.agent  # Step 4 = CIO
            self.db.commit()
            target = params.get("target_status", "in_progress")
            t = await TaskService.change_status_with_delay(
                self.db, t=task, new_status=target,
                agent=step.agent, reason="sop:cio_final_reject",
                delay_s=0.0,
            )
            return {"ok": True, "action": "cio_final_reject",
                    "task_id": task.id, "new_status": t.status}

        # User-Direktive 23.06.2026: Self-Evaluation als Phase-7-Action.
        # Konsolidiert Swarm-Outputs in task.meta und setzt Task auf done.
        if action == "evaluate_outcome":
            if task is None:
                return {"ok": False, "error": "evaluate_outcome: no task"}
            self._persist_swarm_outputs_to_task(task)
            from .task_service import TaskService
            t = await TaskService.change_status_with_delay(
                self.db, t=task, new_status="done",
                agent=step.agent,
                reason=f"sop:evaluate_outcome:{instance.id}",
                delay_s=0.0,
            )
            # Score + Iteration-Counter aus task.meta in History loggen
            try:
                from ..models.history import TaskHistory
                th = TaskHistory(
                    task_id=task.id,
                    event="swarm_consolidated",
                    agent="system",
                    details={
                        "consensus_score": (task.meta or {}).get("consensus_score"),
                        "stages": list(((task.meta or {}).get("swarm_consolidated", {}) or {}).get("stages", {}).keys()),
                        "total_cost_usd": ((task.meta or {}).get("swarm_consolidated", {}) or {}).get("total_cost_usd", 0),
                    },
                )
                self.db.add(th)
                self.db.commit()
            except Exception:
                pass
            return {"ok": True, "action": "evaluate_outcome",
                    "task_id": task.id, "new_status": t.status,
                    "swarm_consolidated": bool((task.meta or {}).get("swarm_consolidated"))}

        # === User-Direktive 23.06.2026: Task-Decomposition (Phase Go) ===
        # Prueft ob Task zerlegt werden sollte (mehrere Themen in Anforderung).
        # Wenn ja: Subtasks erstellen, Parent bleibt in 'go'.
        # Wenn nein: kein Split, normal weiter.
        if action == "decompose_task":
            return self._execute_decompose_task(instance, step, task, params)

        return {"ok": False, "error": f"unknown action: {action!r}"}

    # === Rules: Wenn-Dann-Logik ===

    def evaluate_rules(
        self, instance: SOPInstance, step: SOPStep, step_result: Dict[str, Any]
    ) -> Tuple[Optional[str], Optional[str]]:
        """Wertet die Rules des Steps aus. Liefert (next_step_id, action).

        Reihenfolge:
          1) Hole alle Rules des Steps (sortiert nach rule_order)
          2) Pruefe Condition (condition_field aus instance.context, condition_value)
          3) Wenn Condition erfuellt: action ausfuehren, naechsten Step bestimmen
          4) Audit: rule_evaluated pro Rule
        """
        rules = sorted(step.rules or [], key=lambda r: r.rule_order)
        ctx = instance.context or {}
        # Step-Result in Context mergen
        for k, v in step_result.items():
            ctx[f"step_{k}"] = v

        for rule in rules:
            field_value = ctx.get(rule.condition_field)
            target_value = rule.condition_value
            op = rule.condition_operator
            # Stufe 1 (User-Direktive 18.06.2026): target_value darf ein dynamischer
            # Field-Prefix sein ("step_xxx" / "ctx_xxx"). Dann den Wert aus ctx lesen.
            if isinstance(target_value, str) and (
                target_value.startswith("step_") or target_value.startswith("ctx_")
            ):
                target_value = ctx.get(target_value)

            if self._eval_condition(field_value, op, target_value):
                # Rule feuert
                self._log_execution(
                    instance, step_id=step.id, event="rule_evaluated",
                    agent=step.agent, success=True,
                    details={"rule_id": rule.id, "matched": True,
                             "field": rule.condition_field,
                             "value": field_value,
                             "action": rule.action_type,
                             "action_target": rule.action_target},
                )

                # Action ausfuehren
                next_step_id = self._execute_rule_action(instance, step, rule, step_result)

                instance.context = ctx
                self.db.commit()
                return next_step_id, rule.action_type

            else:
                self._log_execution(
                    instance, step_id=step.id, event="rule_evaluated",
                    agent=step.agent, success=False,
                    details={"rule_id": rule.id, "matched": False,
                             "field": rule.condition_field,
                             "value": field_value,
                             "expected_op": op,
                             "expected_value": target_value},
                )

        # Keine Rule hat gefeuert
        # Default: next_step_id des Steps, falls vorhanden
        instance.context = ctx
        self.db.commit()
        return step.next_step_id, None

    def _eval_condition(self, field_value: Any, op: str, target_value: Any) -> bool:
        """Wertet eine Condition aus."""
        try:
            if op == "eq":
                return field_value == target_value
            if op == "ne":
                return field_value != target_value
            if op == "gt":
                return field_value is not None and field_value > target_value
            if op == "lt":
                return field_value is not None and field_value < target_value
            if op == "ge":
                return field_value is not None and field_value >= target_value
            if op == "le":
                return field_value is not None and field_value <= target_value
            if op == "in":
                return field_value in (target_value or [])
            if op == "not_in":
                return field_value not in (target_value or [])
            if op == "contains":
                return target_value in (field_value or "")
            if op == "is_true":
                return bool(field_value)
            if op == "is_false":
                return not bool(field_value)
            if op == "is_none":
                return field_value is None
            if op == "is_zero":
                return int(field_value) == 0
            if op == "gt":
                try:
                    return float(field_value) > float(target_value)
                except (TypeError, ValueError):
                    return False
            if op == "lt":
                try:
                    return float(field_value) < float(target_value)
                except (TypeError, ValueError):
                    return False
            if op == "gte":
                try:
                    return float(field_value) >= float(target_value)
                except (TypeError, ValueError):
                    return False
            if op == "lte":
                try:
                    return float(field_value) <= float(target_value)
                except (TypeError, ValueError):
                    return False
            if op == "eq":
                try:
                    return field_value == target_value
                except (TypeError, ValueError):
                    return False
            if op == "neq":
                try:
                    return field_value != target_value
                except (TypeError, ValueError):
                    return False
            return False
        except (TypeError, ValueError) as e:
            logger.warning(f"Condition-Eval fehlgeschlagen: {e}")
            return False

    # === Triage-spezifische Check-Actions ===
    # Diese Funktionen implementieren die 4 CIO-Triage-Kriterien
    # als registrierbare Actions. Sie lesen die Task-Daten, pruefen
    # und schreiben Issues in instance.meta['triage_issues'].
    def _execute_triage_action(
        self, instance: SOPInstance, step: SOPStep, task: Task,
        action: str, params: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Fuehrt die Triage-Check-Actions aus.

        Unterstuetzte Actions:
          - check_title: prueft Titel-Laenge und Inhalt
          - check_description: prueft Description-Laenge und Konflikt-Keywords
          - check_success_criteria: prueft ob welche definiert sind
          - check_architecture: prueft gegen OpenBrain-Standardvorgaben
          - check_consistency: prueft auf Widersprueche
          - decide_triage: finale Entscheidung (move_status todo/rueckfrage)
        """
        import json as _json
        from ..models.architecture_rule import ArchitectureRule

        # Meta-Init
        if not isinstance(instance.meta, dict):
            try:
                instance.meta = _json.loads(instance.meta) if instance.meta else {}
            except _json.JSONDecodeError:
                instance.meta = {}

        issues: list = instance.meta.setdefault("triage_issues", [])
        warnings: list = instance.meta.setdefault("triage_warnings", [])

        # === check_title ===
        if action == "check_title":
            title = task.title or ""
            if len(title.strip()) < 10:
                issues.append({
                    "type": "title_too_short",
                    "title": "Titel zu kurz oder fehlt",
                    "description": (
                        f"Der Titel des Tasks hat nur {len(title)} Zeichen (Minimum: 10). "
                        "Ein guter Titel beschreibt die KERN-Aufgabe in 5-15 Worten."
                    ),
                    "suggestions": [
                        "Formuliere den Titel als Aufgabe: 'Implementiere X' / 'Fixe Bug Y'",
                        "Inkludiere den Scope: Backend, Frontend, API, DB wenn relevant",
                    ],
                    "recommendation": "Schreibe den Titel als konkrete Aufgabe mit Scope-Indikator.",
                })
                return {"ok": False, "issues_count": len(issues), "title": title}
            return {"ok": True, "issues_count": len(issues), "title": title}

        # === check_description ===
        if action == "check_description":
            desc = task.description or ""
            if len(desc.strip()) < 50:
                issues.append({
                    "type": "description_too_short",
                    "title": "Description fehlt oder zu kurz",
                    "description": (
                        f"Die Description hat nur {len(desc)} Zeichen (Minimum: 50, ideal: 200+). "
                        "Ohne ausreichende Description weiss der Worker nicht, WAS implementiert werden soll."
                    ),
                    "suggestions": [
                        "Strukturierte Description: Ziel, Akzeptanz, Edge-Cases",
                        "Konkrete Beispiele: Input/Output, Vorher/Nachher",
                    ],
                    "recommendation": "Mindestens 200 Zeichen. Struktur: Ziel, Umsetzung, Akzeptanz.",
                })
                return {"ok": False, "issues_count": len(issues)}
            # Konflikt-Keywords
            conflict_kws = ["todo:", "tbd", "fixme", "??", "klären", "kl\u00e4ren", "unbekannt"]
            found = [kw for kw in conflict_kws if kw in desc.lower()]
            if found:
                issues.append({
                    "type": "conflict_keyword",
                    "title": f"Konflikt-Keywords gefunden: {', '.join(found)}",
                    "description": (
                        f"Die Description enthaelt unklare Platzhalter: {', '.join(found)}. "
                        "Diese verstoßen gegen unsere OpenBrain-Vorgabe 'Tasks muessen selbsterklaerend sein'."
                    ),
                    "suggestions": [
                        f"Ersetze '{found[0]}' durch die konkrete Information",
                        "Entferne FIXME-Marker oder lege separate Tasks an",
                    ],
                    "recommendation": "Gehe durch den Task und ersetze JEDES Konflikt-Keyword durch konkrete Information.",
                })
                return {"ok": False, "issues_count": len(issues), "conflicts": found}
            return {"ok": True, "issues_count": len(issues)}

        # === check_success_criteria ===
        if action == "check_success_criteria":
            sc = task.success_criteria or []
            if not isinstance(sc, list) or len(sc) < 1:
                issues.append({
                    "type": "no_success_criteria",
                    "title": "Keine Erfolgskriterien definiert",
                    "description": (
                        "Ohne Erfolgskriterien kann der Worker nicht wissen, wann der Task 'fertig' ist, "
                        "und der Tester kann nicht objektiv pruefen, ob der Task korrekt umgesetzt wurde."
                    ),
                    "suggestions": [
                        "Mindestens 1-3 messbare Erfolgskriterien definieren",
                        "Beispiel: 'Login funktioniert mit gueltigen Credentials', 'Tests geschrieben'",
                    ],
                    "recommendation": "Definiere klare, messbare Erfolgskriterien (Definition of Done).",
                })
                return {"ok": False, "issues_count": len(issues)}
            return {"ok": True, "issues_count": len(issues), "count": len(sc)}

        # === check_architecture ===
        if action == "check_architecture":
            desc = (task.description or "").lower()
            title = (task.title or "").lower()
            text = f"{title} {desc}"
            arch_stop = {
                "regel", "vorgabe", "standard", "beispiel", "eigen", "eigenstaendig",
                "auch", "sowie", "kein", "keine", "keinen", "vermeiden",
                "sollte", "muss", "darf", "wird",
            }
            try:
                rules = self.db.execute(
                    select(ArchitectureRule).where(ArchitectureRule.is_active == True)
                ).scalars().all()
            except SQLAlchemyError:
                return {"ok": True, "issues_count": len(issues), "note": "rules not loadable"}
            arch_issues = []
            for rule in rules:
                if not rule.description:
                    continue
                keywords = [w for w in re.findall(r"\b[a-z]{5,}\b", rule.description.lower()) if w not in arch_stop][:5]
                for kw in keywords:
                    neg_patterns = [
                        f"kein {kw}", f"keine {kw}", f"keinen {kw}",
                        f"nicht {kw}", f"{kw} vermeiden", f"ohne {kw}",
                    ]
                    if any(neg in text for neg in neg_patterns):
                        arch_issues.append({
                            "type": "architecture_conflict",
                            "title": f"Architektur-Konflikt: {rule.name}",
                            "description": (
                                f"Deine Task-Description verneint '{kw}', was im Konflikt mit unserer "
                                f"OpenBrain-Standardvorgabe steht. Regel: {rule.description}"
                            ),
                            "rule_id": rule.id,
                            "severity": rule.severity,
                            "suggestions": [
                                f"Pruefe, ob die Verneinung wirklich noetig ist",
                                "Im Zweifel: halte dich an die Standardvorgabe",
                            ],
                            "recommendation": f"Pruefe explizit, ob die Verneinung von '{kw}' noetig ist.",
                        })
                        break
            if arch_issues:
                issues.extend(arch_issues)
                return {"ok": False, "issues_count": len(issues), "arch_issues": len(arch_issues)}
            return {"ok": True, "issues_count": len(issues)}

        # === check_consistency ===
        if action == "check_consistency":
            desc = (task.description or "").lower()
            title = (task.title or "").lower()
            text = f"{title} {desc}"
            contradiction_pairs = [
                (["oauth", "openid"], ["lokal", "passwort"], "Auth-Konflikt: OAuth/OpenID vs. lokale Passwort-Auth"),
                (["sql", "postgres"], ["nosql", "mongodb", "redis"], "DB-Konflikt: SQL vs. NoSQL"),
                (["synchron", "sync"], ["async", "asynchron"], "Concurrency-Konflikt: synchron vs. asynchron"),
                (["monolith"], ["microservice"], "Architektur-Konflikt: Monolith vs. Microservices"),
                (["websocket"], ["polling"], "Realtime-Pattern: WebSocket vs. Polling"),
                (["serverless"], ["long-running", "langer prozess"], "Serverless nicht fuer long-running"),
            ]
            found_contradictions = []
            for group_a, group_b, desc_text in contradiction_pairs:
                has_a = any(kw in text for kw in group_a)
                has_b = any(kw in text for kw in group_b)
                if has_a and has_b:
                    found_contradictions.append(desc_text)
            if found_contradictions:
                for c in found_contradictions:
                    issues.append({
                        "type": "requirement_contradiction",
                        "title": f"Anforderungs-Widerspruch: {c}",
                        "description": (
                            f"Deine Task-Description enthaelt Widersprueche. Konkrete Konflikte: {c}."
                        ),
                        "suggestions": [
                            "Loese den Widerspruch, indem du eine Option explizit ausschliesst",
                            "Beispiel: 'NICHT lokal, sondern OAuth2'",
                        ],
                        "recommendation": "Vereinfache die Anforderung in eine klare, nicht-widersprüchliche Form.",
                    })
                return {"ok": False, "issues_count": len(issues), "contradictions": found_contradictions}
            return {"ok": True, "issues_count": len(issues)}

        # === decide_triage: finale Entscheidung ===
        if action == "decide_triage":
            n_issues = len(issues)
            from .task_service import TaskService
            if n_issues == 0:
                # OK → todo
                new_status = "todo"
                reason = "cio_triage_approved"
            else:
                # Issues → rueckfrage
                new_status = "rueckfrage"
                reason = "cio_auto_question"
                # Issues in t.meta speichern
                meta = task.meta if isinstance(task.meta, dict) else (_json.loads(task.meta) if task.meta else {})
                meta["cio_question"] = " | ".join(i.get("title", "") for i in issues)
                meta["cio_question_at"] = datetime.utcnow().isoformat()
                meta["cio_question_issues"] = issues
                meta["cio_question_questions"] = []
                # RACI dokumentieren
                raci = self._build_raci_for_task(task)
                meta["triage_raci"] = raci
                from sqlalchemy.orm.attributes import flag_modified
                flag_modified(task, "meta")
                task.meta = meta
            # Status wechseln
            return TaskService.change_status_with_delay(
                self.db, t=task, new_status=new_status,
                agent=step.agent, reason=reason,
                details={"sop_instance_id": instance.id, "sop_step_id": step.id,
                         "issues_count": n_issues, "issues": issues[:5]},
            )
        return {"ok": False, "error": f"unknown triage action: {action}"}

    def _build_raci_for_task(self, task: Task) -> Dict[str, Any]:
        """Baut die RACI-Matrix fuer einen Task (themenabhaengiger C-Agent)."""
        text = f"{(task.title or '').lower()} {(task.description or '').lower()}"
        if any(kw in text for kw in ["security", "auth", "password", "verschlüsselung", "encryption", "oauth", "jwt", "token", "xss", "csrf", "sql-injection", "berechtigung"]):
            c = "pi_security"
        elif any(kw in text for kw in ["architektur", "architecture", "microservice", "soa", "design", "konzept"]):
            c = "pi_coder"
        elif any(kw in text for kw in ["test", "coverage", "pytest", "jest"]):
            c = "pi_tester"
        elif any(kw in text for kw in ["review", "refactor", "code-quality", "clean-code"]):
            c = "pi_reviewer"
        elif any(kw in text for kw in ["bug", "fix", "defect", "fehler", "regression"]):
            c = "pi_fixer"
        else:
            c = None
        return {
            "R": "CIO", "A": "CIO", "C": c or "(keiner)", "I": "CEOdigital",
            "criteria_checked": [
                "1. Description ausfuehrlich genug",
                "2. Keine Verschlechterung des Prozess-Ergebnisses",
                "3. Konsistent mit OpenBrain-Architekturvorgaben",
                "4. Keine Widersprueche in der Anforderung",
            ],
            "auto_approved": True,
        }

    def _execute_rule_action(
        self, instance: SOPInstance, step: SOPStep,
        rule: SOPStepRule, step_result: Dict[str, Any]
    ) -> Optional[str]:
        """Fuehrt die Action einer feuernden Rule aus.

        Liefert die next_step_id (oder None fuer End-State).
        """
        action_type = rule.action_type
        target = rule.action_target
        params = rule.action_params or {}

        if action_type in ("move_status", "approve_triage", "submit_review",
                           "tester_approve", "tester_reject",
                           "cio_final_approve", "cio_final_reject", "start_work"):
            # Sync-Status-Wechsel (ohne weiteren Delay, der ist schon in run_step)
            if not instance.task_id:
                return step.next_step_id
            task = self.db.get(Task, instance.task_id)
            if not task:
                return step.next_step_id
            # Status-Mapping
            status_map = {
                "move_status": target,
                "approve_triage": "todo",
                "start_work": "in_progress",
                "submit_review": "review",
                "tester_approve": "block",
                "tester_reject": "in_progress",
                "cio_final_approve": "done",
            }
            new_status = status_map.get(action_type)
            if new_status:
                TaskService.set_status_sync(
                    self.db, instance.task_id, new_status,
                    agent=step.agent, reason=f"sop_rule:{rule.id}",
                )
            return step.next_step_id

        if action_type == "create_subtask":
            # Sub-Task anlegen
            if instance.task_id:
                sub = TaskService.create_task(
                    self.db, title=params.get("title", "Subtask"),
                    project_id=instance.project_id,
                    description=params.get("description"),
                    status=params.get("status", "todo"),
                    priority=params.get("priority", 50),
                    parent_id=instance.task_id,
                )
                self._log_execution(
                    instance, step_id=step.id, event="subtask_created",
                    agent=step.agent,
                    details={"subtask_id": sub.id, "title": sub.title},
                )
            return step.next_step_id

        if action_type == "spawn_sop":
            sub_sop_id = target or params.get("sop_id")
            if sub_sop_id:
                sub_inst = self.spawn_sub_sop(instance, sub_sop_id, params)
                # Parent wartet auf Sub-SOP
                instance.status = "waiting_sub_sop"
                self._log_execution(
                    instance, step_id=step.id, event="sub_sop_spawned",
                    agent=step.agent,
                    details={"sub_instance_id": sub_inst.id if sub_inst else None,
                             "sop_id": sub_sop_id},
                )
                return step.on_sub_sop_step_id or step.next_step_id
            return step.next_step_id

        if action_type == "escalate":
            self._log_execution(
                instance, step_id=step.id, event="escalated",
                agent=step.agent,
                details={"reason": params.get("reason", "rule escalation"),
                         "target": target},
            )
            if instance.task_id:
                TaskService.set_priority(self.db, instance.task_id, 100)
            return step.fail_step_id or step.next_step_id

        if action_type == "block":
            instance.status = "blocked"
            if instance.task_id:
                TaskService.set_status_sync(
                    self.db, instance.task_id, "block",
                    agent=step.agent, reason=f"sop_rule:block",
                )
            return None  # End-State

        if action_type == "complete":
            return None  # End-State

        if action_type == "goto_step":
            # Direkter Sprung zu einer bestimmten step_id (fuer Quality-Gate Loop-Back)
            target_step = self.db.get(SOPStep, target) if target else None
            if target_step:
                self._log_execution(
                    instance, step_id=step.id, event="goto_step",
                    agent=step.agent,
                    details={"target_step_id": target, "target_name": target_step.name},
                )
                return target
            # Fallback: default next_step_id wenn target nicht existiert
            return step.next_step_id

        # Default: naechster Step
        return step.next_step_id

    # === Navigation ===

    def advance(
        self, instance: SOPInstance, next_step_id: Optional[str],
        step_result: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Geht zum naechsten Step."""
        if not next_step_id:
            return self._complete_instance(instance, None, step_result)
        instance.current_step_id = next_step_id
        self._log_execution(
            instance, step_id=next_step_id, event="step_advanced",
            agent="system",
            details={"from_step": instance.current_step_id,
                     "to_step": next_step_id},
        )
        self.db.commit()
        return {"ok": True, "action": "advanced", "next_step_id": next_step_id}

    def spawn_sub_sop(
        self, parent_instance: SOPInstance, sop_id: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Optional[SOPInstance]:
        """Startet eine Sub-SOP als Kind der parent_instance."""
        sub_inst = self.create_instance(
            sop_id=sop_id,
            project_id=parent_instance.project_id,
            task_id=parent_instance.task_id,
            parent_instance_id=parent_instance.id,
            context=context or {},
        )
        return sub_inst

    def _complete_instance(
        self, instance: SOPInstance, step: Optional[SOPStep],
        step_result: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Markiert die Instance als completed.

        Defense-in-Depth (Task 7ce2066d5bd5, 25.06.2026):
            Prueft vor dem Task-Status 'done', ob die Instance auch tatsaechlich
            alle Steps der SOP durchlaufen hat. Verhindert den Bug, dass Tasks
            nach dem ersten Step als 'done' markiert werden, weil next_step_id
            in der DB nicht verkettet war.

            Pruefungen:
              1. Aktueller Step muss der letzte Step der SOP sein (step_order == max)
              2. ODER: Wenn der Step selbst next_step_id=None hat, ist es ein End-Step
                 (dann ist die SOP bewusst zu Ende)

            Bei Verletzung: Task wird auf 'block' gesetzt mit Reason 'sop_incomplete'.
        """
        instance.status = "completed"
        instance.completed_at = datetime.now(timezone.utc)
        self._log_execution(
            instance, step_id=step.id if step else None,
            event="instance_completed", agent="system",
            details={"step_result": step_result or {}},
        )
        # User-Direktive 23.06.2026: Task-Status auf done setzen, NICHT in triage lassen
        if instance.task_id:
            task = self.db.get(Task, instance.task_id)
            if task and task.status != "done":
                # Defense-in-Depth: Pruefe ob alle Steps der SOP durchlaufen wurden
                sop_incomplete_reason = self._check_sop_completion(instance, step)
                if sop_incomplete_reason:
                    logger.warning(
                        f"[sop-incomplete] Instance {instance.id[:8]} Task {task.id[:8]}: "
                        f"{sop_incomplete_reason} - Task wird auf 'block' gesetzt"
                    )
                    self._log_execution(
                        instance, step_id=step.id if step else None,
                        event="sop_incomplete_guard", agent="system",
                        details={"reason": sop_incomplete_reason},
                    )
                    from .task_service import TaskService
                    TaskService.set_status_sync(
                        self.db, task.id, "block",
                        agent="system",
                        reason=f"sop_incomplete:{instance.id}:{sop_incomplete_reason}",
                        delay_s=0.0,
                    )
                    self.db.commit()
                    return {
                        "ok": True,
                        "action": "blocked_incomplete",
                        "instance_id": instance.id,
                        "reason": sop_incomplete_reason,
                    }
                # Normal-Flow: alle Steps durchlaufen, Task auf done
                from .task_service import TaskService
                TaskService.set_status_sync(
                    self.db, task.id, "done",
                    agent="system", reason=f"sop_completed:{instance.id}", delay_s=0.0,
                )
                # Konsolidierten Swarm-Output in task.meta ablegen
                self._persist_swarm_outputs_to_task(task)
                # User-Direktive 23.06.2026 (Task 4bf7146b0780): Port-Bloecke freigeben
                try:
                    from ..services.port_manager import release_block, find_block_for_task
                    block = find_block_for_task(task.id)
                    if block and block.status == "active":
                        released = release_block(block.id)
                        if released:
                            logger.info(f"Port-Block {block.id} fuer Task {task.id[:8]} freigegeben")
                except Exception as port_rel_err:
                    logger.warning(f"Port-Release fehlgeschlagen: {port_rel_err}")
        # Parent-Instance (falls Sub-SOP) reaktivieren
        if instance.parent_instance_id:
            parent = self.db.get(SOPInstance, instance.parent_instance_id)
            if parent and parent.status == "waiting_sub_sop":
                parent.status = "running"
                self._log_execution(
                    parent, step_id=parent.current_step_id,
                    event="sub_sop_completed", agent="system",
                    details={"sub_instance_id": instance.id, "sub_status": instance.status},
                )
        self.db.commit()
        return {"ok": True, "action": "completed", "instance_id": instance.id}

    def _check_sop_completion(
        self, instance: SOPInstance, step: Optional[SOPStep],
    ) -> Optional[str]:
        """Defense-in-Depth (Task 7ce2066d5bd5, 25.06.2026).

        Prueft ob die SOP-Instance alle Steps der SOP durchlaufen hat.
        Wenn nicht, wird ein Reason-String zurueckgegeben (Task wird dann auf
        'block' gesetzt), sonst None (Task wird auf 'done' gesetzt).

        Logik:
          - Hole alle Steps der SOP (sortiert nach step_order)
          - Hole alle completed-step_ids aus sop_executions (event=step_completed)
          - Wenn es mehr als 1 Step in der SOP gibt UND der aktuelle Step nicht
            der letzte ist ODER nicht alle vorherigen Steps completed sind,
            dann ist die SOP unvollstaendig.

        Returns:
            None wenn OK (alle Steps durchlaufen ODER SOP hat nur 1 Step)
            str mit Reason wenn SOP unvollstaendig
        """
        if step is None:
            # Kein konkreter Step uebergeben (sollte nicht passieren, aber
            # falls doch: SOP als unvollstaendig markieren)
            return "no_step_provided"

        # Alle Steps der SOP laden
        all_steps = (
            self.db.query(SOPStep)
            .filter(SOPStep.sop_id == instance.sop_id)
            .order_by(SOPStep.step_order)
            .all()
        )
        if len(all_steps) <= 1:
            # SOP mit nur 1 Step: per Definition complete
            return None

        # Aktueller Step muss der letzte Step sein (step_order == max)
        max_step_order = max(s.step_order for s in all_steps)
        if step.step_order < max_step_order:
            return (
                f"current_step_order={step.step_order} < max_step_order={max_step_order} "
                f"(last_step={next((s.name for s in all_steps if s.step_order == max_step_order), '?')})"
            )

        # Auch pruefen: alle Schritte mit step_order < current wurden completed?
        completed_step_ids = set(
            row[0] for row in self.db.query(SOPExecution.step_id)
            .filter(
                SOPExecution.instance_id == instance.id,
                SOPExecution.event == "step_completed",
                SOPExecution.success == True,  # noqa: E712
            )
            .distinct()
            .all()
        )
        expected_prev_step_ids = {s.id for s in all_steps if s.step_order < step.step_order}
        missing = expected_prev_step_ids - completed_step_ids
        if missing:
            return (
                f"missing_completed_steps={[m[:8] for m in missing]} "
                f"(expected {len(expected_prev_step_ids)} prev steps, got {len(completed_step_ids & expected_prev_step_ids)})"
            )

        return None

    def _persist_swarm_outputs_to_task(self, task) -> None:
        """Konsolidiert alle Swarm-Outputs einer Task-Instance in task.meta.

        User-Direktive 23.06.2026: Subagent-Ergebnisse muessen am Haupttask
        konsolidiert werden. Wir laden alle swarm_workers der Task, gruppieren
        nach Swarm-Typ und schreiben einen konsolidierten Output in task.meta.
        """
        try:
            from ..models.swarm import SwarmRun as SwarmRunModel, SwarmWorker as SwarmWorkerModel
            runs = self.db.query(SwarmRunModel).filter_by(task_id=task.id).all()
            if not runs:
                return
            consolidated = {
                "total_swarms": len(runs),
                "total_cost_usd": sum(float(r.total_cost_usd or 0) for r in runs),
                "stages": {},
                "all_worker_outputs": [],
            }
            for run in runs:
                stage_key = (run.result or {}).get("stage_key") if isinstance(run.result, dict) else None
                stage_key = stage_key or f"swarm_{run.swarm_type}"
                consolidated["stages"][stage_key] = {
                    "swarm_run_id": run.id,
                    "swarm_type": run.swarm_type,
                    "merge_strategy": run.merge_strategy,
                    "consensus_score": (run.result or {}).get("merged_output", {}).get("avg_score")
                        if isinstance(run.result, dict) else None,
                    "auto_approved": (run.result or {}).get("merged_output", {}).get("auto_approve")
                        if isinstance(run.result, dict) else None,
                    "cost_usd": float(run.total_cost_usd or 0),
                }
                # Worker-Outputs sammeln
                for worker in self.db.query(SwarmWorkerModel).filter_by(swarm_run_id=run.id).all():
                    consolidated["all_worker_outputs"].append({
                        "swarm_run_id": run.id,
                        "stage_key": stage_key,
                        "role": worker.subagent_role,
                        "variant": worker.variant,
                        "status": worker.status,
                        "output": worker.output,
                        "cost_usd": float(worker.cost_usd or 0),
                    })
            # In task.meta schreiben
            if not isinstance(task.meta, dict):
                task.meta = {}
            task.meta["swarm_consolidated"] = consolidated
            # Konsens-Score als Top-Level-Feld fuer schnellen Zugriff
            last_score = None
            for stage_data in consolidated["stages"].values():
                if stage_data.get("consensus_score") is not None:
                    last_score = stage_data["consensus_score"]
            if last_score is not None:
                task.meta["consensus_score"] = last_score
                task.meta["swarm_iteration_count"] = task.meta.get("swarm_iteration_count", 0) + 1
            self.db.commit()
        except Exception as e:
            logger.warning(f"Swarm-Output-Konsolidierung fehlgeschlagen: {e}")

    def fail_instance(
        self, instance: SOPInstance, reason: str
    ) -> Dict[str, Any]:
        """Markiert die Instance als failed."""
        instance.status = "failed"
        instance.completed_at = datetime.now(timezone.utc)
        self._log_execution(
            instance, step_id=instance.current_step_id,
            event="instance_failed", agent="system", success=False,
            details={"reason": reason},
        )
        self.db.commit()
        return {"ok": True, "action": "failed", "reason": reason}

    # === Helper ===

    async def _execute_spawn_swarm(
        self, instance: SOPInstance, step: SOPStep,
        task: Optional[Task], params: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Multi-Agent-Swarm starten und orchestrieren.

        User-Direktive 22.06.2026: Staged Hybrid Swarm.
        Konfigurations-Prioritaet (User-Direktive 24.06.2026):
          1. step.action_params.workers[] (SOP-Definition, primaere Quelle)
          2. SWARM_CONFIGS[stage_key] (Legacy-Fallback fuer Migration)
          3. SwarmConfig.from_dict(params) (generischer Fallback)
        Worker-Prompts werden IMMER aus WorkerConfig.system_prompt gelesen.
        Beschreibung (user_prompt + ai_instructions_md) wird per LLM validiert.

        Returns:
            Dict mit ok=True/False, swarm_run_id, merged_output, cost_usd
        """
        from ..services.swarm_spawner import (
            SwarmConfig, SwarmType, MergeStrategy, WorkerConfig,
            SWARM_CONFIGS, create_swarm_run, execute_swarm,
        )

        # === Konfigurations-Resolution (SOP-zuerst) ===
        sop_workers = params.get("workers")  # Aus SOP-Step action_params
        if sop_workers and isinstance(sop_workers, list):
            # Primaere Quelle: SOP-Definition
            try:
                config = SwarmConfig(
                    swarm_type=SwarmType(params.get("swarm_type", "parallel")),
                    workers=[WorkerConfig(**w) for w in sop_workers],
                    merge_strategy=MergeStrategy(params.get("merge_strategy", "reviewer_picks_best")),
                    consensus_threshold=float(params.get("consensus_threshold", 75.0)),
                    auto_approve_threshold=float(params.get("auto_approve_threshold", 90.0)),
                    max_cost_usd=float(params.get("max_cost_usd", 0.50)),
                    timeout_sec=int(params.get("timeout_sec", 600)),
                    use_real_workers=bool(params.get("use_real_workers", False)),
                )
                logger.info(f"spawn_swarm: Config aus SOP-Step geladen ({len(sop_workers)} Worker)")
            except Exception as e:
                return {"ok": False, "error": f"spawn_swarm: invalid workers config: {e}"}
        else:
            # Fallback: SWARM_CONFIGS[stage_key] oder generic
            stage_key = params.get("stage_key")
            if stage_key and stage_key in SWARM_CONFIGS:
                config = SWARM_CONFIGS[stage_key]
                logger.info(f"spawn_swarm: Fallback auf SWARM_CONFIGS['{stage_key}']")
            else:
                try:
                    config = SwarmConfig.from_dict(params)
                except Exception as e:
                    return {"ok": False, "error": f"spawn_swarm: invalid config: {e}"}

        # === LLM-Validierung der Beschreibung (User-Direktive 24.06.2026) ===
        # Die SOP-Beschreibung (user_prompt + ai_instructions_md + Worker-Prompts)
        # wird vor dem Spawn von einem LLM auf Konsistenz geprueft. Bausteine
        # (Swarm-Spawner-Logik) bleiben unveraendert - nur die BESCHREIBUNG wird
        # validiert, weil sie sich je nach SOP aendert.
        if params.get("user_prompt") or params.get("ai_instructions_md"):
            validation_result = await self._validate_swarm_description(
                instance, step, task, params, config
            )
            if not validation_result.get("ok"):
                logger.warning(
                    f"spawn_swarm: LLM-Validierung der Beschreibung fehlgeschlagen: "
                    f"{validation_result.get('reasoning', '?')}"
                )
                # Trotzdem weitermachen, aber warnen (User kann es erzwingen)
                if params.get("strict_validation", False):
                    return {
                        "ok": False,
                        "error": "LLM-Validierung der SOP-Beschreibung fehlgeschlagen",
                        "validation": validation_result,
                    }

        # Swarm-Run in DB anlegen
        swarm_id = create_swarm_run(
            task_id=instance.task_id or "",
            sop_instance_id=instance.id,
            step_id=step.id,
            config=config,
        )

        # Task-Kontext fuer die Worker (inkl. Worker-Prompts aus SOP)
        worker_prompts = {}
        for w in config.workers:
            key = f"{w.role}:{w.variant}"
            if w.system_prompt:
                worker_prompts[key] = w.system_prompt
            worker_prompts[w.role] = w.system_prompt or worker_prompts.get(w.role, "")
        task_context = {
            "task_id": task.id if task else None,
            "title": task.title if task else None,
            "description": task.description if task else None,
            "sop_step_name": step.name,
            "sop_user_prompt": params.get("user_prompt", ""),
            "sop_workflow": params.get("ai_instructions_md", ""),
            "worker_prompts": worker_prompts,
        }

        # Swarm ausfuehren
        try:
            result = await execute_swarm(swarm_id, task_context=task_context)
        except Exception as e:
            logger.exception(f"spawn_swarm fehlgeschlagen: {e}")
            return {"ok": False, "error": f"spawn_swarm: {e}",
                    "swarm_run_id": swarm_id}

        # Konsens-Score extrahieren (falls vorhanden)
        consensus_score = None
        auto_approved = False
        merged = result.get("merged_output", {})
        if isinstance(merged, dict):
            consensus_score = merged.get("avg_score")
            auto_approved = merged.get("auto_approve", False)

        # === User-Direktive 23.06.2026 (Task 4bf7146b0780): Port-Reservation ===
        # Bei jedem Swarm-Spawn automatisch einen Port-Block reservieren.
        # Bei Task-Completion wird der Block wieder freigegeben.
        if task is not None:
            try:
                from ..services.port_manager import (
                    reserve_block, release_block, find_block_for_task,
                )
                # Nur einmal pro Task reservieren (re-uses existierenden Block)
                existing = find_block_for_task(task.id)
                if existing and existing.status == "active":
                    block_info = {
                        "block_id": existing.id,
                        "port_start": existing.port_start,
                        "port_end": existing.port_end,
                        "status": "reused",
                    }
                else:
                    block = reserve_block(
                        app_name="pi-dashboard-2",
                        task_id=task.id,
                        count=10,
                        notes=f"Swarm {swarm_id} (auto-reserved)",
                    )
                    block_info = {
                        "block_id": block.id,
                        "port_start": block.port_start,
                        "port_end": block.port_end,
                        "status": "new",
                    }
                # Port-Info in task.meta ablegen
                if not isinstance(task.meta, dict):
                    task.meta = {}
                if "port_allocations" not in task.meta:
                    task.meta["port_allocations"] = []
                task.meta["port_allocations"].append({
                    "swarm_id": swarm_id,
                    "block_id": block_info["block_id"],
                    "port_start": block_info["port_start"],
                    "port_end": block_info["port_end"],
                    "status": block_info["status"],
                })
                self.db.commit()
                logger.info(
                    f"Port-Block fuer Task {task.id[:8]} Swarm {swarm_id[:8]}: "
                    f"{block_info['port_start']}-{block_info['port_end']} ({block_info['status']})"
                )
            except Exception as port_err:
                logger.warning(f"Port-Reservation fehlgeschlagen: {port_err}")

        # Kosten-Check
        if result["total_cost_usd"] > config.max_cost_usd:
            logger.warning(
                f"Swarm {swarm_id} hat Cost-Limit ueberschritten: "
                f"${result['total_cost_usd']:.2f} > ${config.max_cost_usd:.2f}"
            )

        # === User-Direktive 22.06.2026 Phase 12: Score in task.meta persistieren ===
        # Wenn Competitive-Review-Swarm, Score + Iteration-Counter speichern
        # fuer Auto-Fix-Loop-Entscheidung in nachfolgenden Steps.
        if config.swarm_type == SwarmType.COMPETITIVE and task is not None and consensus_score is not None:
            try:
                if not isinstance(task.meta, dict):
                    task.meta = {}
                task.meta["consensus_score"] = consensus_score
                task.meta["last_swarm_run_id"] = swarm_id
                task.meta["swarm_iteration_count"] = int(task.meta.get("swarm_iteration_count", 0)) + 1
                # Auto-Fix-Loop-Entscheidung
                from ..services.task_metrics import (
                    should_auto_fix, get_next_iteration_action
                )
                iteration_count = task.meta["swarm_iteration_count"]
                if should_auto_fix(consensus_score, iteration_count - 1):
                    decision = get_next_iteration_action(consensus_score, iteration_count - 1)
                    task.meta["next_action"] = decision["action"]
                    task.meta["next_action_reason"] = decision["reason"]
                    logger.info(
                        f"Auto-Fix-Loop-Entscheidung: {decision['action']} "
                        f"(Score {consensus_score}, Iter {iteration_count})"
                    )
                self.db.commit()
            except Exception as e:
                logger.warning(f"Score-Persistierung fehlgeschlagen: {e}")

        return {
            "ok": True,
            "action": "spawn_swarm",
            "swarm_run_id": swarm_id,
            "swarm_type": config.swarm_type.value,
            "worker_count": result["worker_count"],
            "merge_strategy": config.merge_strategy.value,
            "total_cost_usd": result["total_cost_usd"],
            "consensus_score": consensus_score,
            "auto_approved": auto_approved,
            "merged_output": merged,
        }

    def _log_execution(
        self, instance: SOPInstance, step_id: Optional[str], event: str,
        agent: Optional[str] = None, details: Optional[Dict[str, Any]] = None,
        duration_ms: Optional[int] = None, success: bool = True,
    ) -> SOPExecution:
        ex = SOPExecution(
            instance_id=instance.id,
            step_id=step_id,
            event=event,
            agent=agent,
            details=details or {},
            duration_ms=duration_ms,
            success=success,
        )
        self.db.add(ex)
        self.db.flush()
        return ex


# === Default-SOP-Definitionen ===

DEFAULT_TASK_SOP = {
    "sop_key": "task_workflow",  # User-Direktive 24.06.2026: stabiler Key fuer seed_default_sops
    "name": "Standard-Workflow Task (User-Direktive 15.06.2026)",
    "description": (
        "Generischer Standard-Workflow fuer einen Task:\n"
        "TRIAGE (CIO Review) -> GO (Worker assigned) -> IN_PROGRESS "
        "(Worker arbeitet) -> REVIEW (Tester Code-Review) -> BLOCK (CIO Final) -> DONE.\n\n"
        "Implementiert die in der Kanban-Operator-Skill beschriebenen Regeln.\n"
        "Mit 5-Sekunden-Verzoegerung pro Step (User-Transparenz)."
    ),
    "category": "task",
    "default_delay_s": 5.0,
    "steps": [
        # Step 1: CIO Triage Review
        {
            "name": "CIO Triage Review",
            "phase": "Task",
            "trigger": "task_created",
            "action": "review_task",
            "agent": "CIO",
            "expected_result": "Task ist vollstaendig, verstaendlich, konfliktfrei",
            "success_criteria": [
                "Title >= 10 Zeichen",
                "Description >= 50 Zeichen",
                "Keine Konflikt-Keywords (TODO, TBD, ??)",
                "Priority 0-100",
            ],
            "delay_s": 5.0,
            "description": (
                "CIO prueft den Task auf Vollstaendigkeit, Verstaendlichkeit, "
                "Konflikte mit bestehender App/Funktion, Konformitaet mit OpenBrain-Entwicklungsvorgaben."
            ),
            "next_step": 1,  # -> Worker Assignment
            "fail_step": 5,  # -> Done (bei block-Abbruch)
            "rules": [
                {
                    "description": (
                        "Task ist vollstaendig: wird in GO verschoben. "
                        "Beispiel-User-Direktive: 'Wird verschoben in GO wenn CIO den Task fuer "
                        "umsetzbar einstuft und keine Widersprueche zu Architektur oder den "
                        "uebergeordneten Entwicklungsregeln gefunden hat.'"
                    ),
                    "condition_field": "step_ok",
                    "condition_operator": "is_true",
                    "condition_value": True,
                    "action_type": "approve_triage",
                    "action_target": "todo",
                    "action_params": {},
                },
                {
                    "description": "Konflikte gefunden: block + Frage an CEOdigital/CEO",
                    "condition_field": "step_ok",
                    "condition_operator": "is_false",
                    "condition_value": True,
                    "action_type": "block",
                    "action_target": "block",
                    "action_params": {"reason": "cio_question"},
                },
            ],
        },
        # Step 2: Worker Assignment
        {
            "name": "Worker Assignment",
            "phase": "Task",
            "trigger": "status_changed:todo",
            "action": "assign_worker",
            "agent": "CIO",
            "expected_result": "Task hat einen Worker (pi-coder, pi-tester, ...)",
            "delay_s": 5.0,
            "description": "CIO weist Task einem relevanten Worker zu.",
            "next_step": 2,  # -> Worker Implementation
            "rules": [
                {
                    "description": "Worker zugewiesen: Task bereit fuer Start",
                    "condition_field": "step_ok",
                    "condition_operator": "is_true",
                    "condition_value": True,
                    "action_type": "start_work",
                    "action_target": "in_progress",
                    "action_params": {},
                },
            ],
        },
        # Step 3: Worker Implementation
        {
            "name": "Worker Implementation",
            "phase": "Task",
            "trigger": "status_changed:in_progress",
            "action": "start_work",
            "agent": "pi-coder",
            "expected_result": "Worker hat Code geschrieben, Tests laufen",
            "delay_s": 5.0,
            "description": "Worker implementiert den Task.",
            "next_step": 3,  # -> Tester Code-Review
            "rules": [
                {
                    "description": "Worker fertig: Submit for Review",
                    "condition_field": "step_ok",
                    "condition_operator": "is_true",
                    "condition_value": True,
                    "action_type": "submit_review",
                    "action_target": "review",
                    "action_params": {},
                },
            ],
        },
        # Step 4: Tester Code-Review
        {
            "name": "Tester Code-Review",
            "phase": "Task",
            "trigger": "status_changed:review",
            "action": "review_task",
            "agent": "pi-tester",
            "expected_result": "Code ist sauber, keine Bugs gefunden",
            "delay_s": 5.0,
            "description": "Tester sucht Schwachstellen, schlecht programmierte Stellen, Bugs.",
            "next_step": 4,  # -> CIO Final-Review
            "fail_step": 2,  # -> Worker Assignment (bei tester_reject -> in_progress)
            "rules": [
                {
                    "description": "Tester OK: Task in BLOCK, Freigabe-Task wird erstellt",
                    "condition_field": "step_ok",
                    "condition_operator": "is_true",
                    "condition_value": True,
                    "action_type": "tester_approve",
                    "action_target": "block",
                    "action_params": {},
                },
                {
                    "description": "Tester findet Bugs: zurueck in IN_PROGRESS",
                    "condition_field": "step_ok",
                    "condition_operator": "is_false",
                    "condition_value": True,
                    "action_type": "tester_reject",
                    "action_target": "in_progress",
                    "action_params": {},
                },
            ],
        },
        # Step 5: CIO Final-Review
        {
            "name": "CIO Final-Review (Freigabe)",
            "phase": "Task",
            "trigger": "status_changed:block",
            "action": "review_task",
            "agent": "CIO",
            "expected_result": "Aufgabe erledigt, Ziele erreicht, Code-Qualitaet OK",
            "delay_s": 5.0,
            "description": "CIO prueft im BLOCK ob Aufgabe erledigt, Ziele erreicht, Code-Qualitaet stimmt.",
            "next_step": 5,  # -> Done
            "fail_step": 2,  # -> Worker Assignment (bei Reject)
            "rules": [
                {
                    "description": "CIO Approve: Task in DONE",
                    "condition_field": "step_ok",
                    "condition_operator": "is_true",
                    "condition_value": True,
                    "action_type": "cio_final_approve",
                    "action_target": "done",
                    "action_params": {},
                },
                {
                    "description": "CIO Reject: zurueck in IN_PROGRESS (Fix-Loop)",
                    "condition_field": "step_ok",
                    "condition_operator": "is_false",
                    "condition_value": True,
                    "action_type": "cio_final_reject",
                    "action_target": "in_progress",
                    "action_params": {"target_status": "in_progress"},
                },
            ],
        },
        # Step 6: Done (End-State)
        {
            "name": "Done",
            "phase": "End",
            "trigger": "status_changed:done",
            "action": "noop",
            "agent": "system",
            "expected_result": "Task abgeschlossen",
            "delay_s": 0.0,
            "description": "End-State. Task ist vollstaendig auditiert.",
            "next_step": None,
            "rules": [
                {
                    "description": "End-State erreicht",
                    "condition_field": "step_ok",
                    "condition_operator": "is_true",
                    "condition_value": True,
                    "action_type": "complete",
                    "action_target": None,
                    "action_params": {},
                },
            ],
        },
    ],
}



# === Default-SOP: CIO Triage Review (User-Direktive 16.06.2026) ===
# Generischer 4-Kriterien-Check, deklarativ in der DB gespeichert.
# Aktionen 'check_*' werden in SOPEngine._execute_action registriert.
DEFAULT_CIO_TRIAGE_SOP = {
    "sop_key": "cio_triage",  # User-Direktive 24.06.2026: stabiler Key fuer seed_default_sops
    "name": "CIO Triage Review (4 Kriterien)",
    "description": (
        "Generischer Triage-Prozess fuer neu erstellte Tasks. Prueft 4 Kriterien:\n"
        "  1. Description ausfuehrlich genug (Aufgabe + Ergebnis klar)\n"
        "  2. Keine Verschlechterung des Prozess-Ergebnisses\n"
        "  3. Konsistent mit OpenBrain-Architekturvorgaben\n"
        "  4. Keine Widersprueche in der Anforderung\n\n"
        "RACI: R+A = CIO, C = themenabhaengig, I = CEOdigital.\n"
        "Bei allen Kriterien OK → Status 'todo'. Bei Issues → Status 'rueckfrage' mit Frage."
    ),
    "category": "triage",
    "default_delay_s": 5.0,
    "steps": [
        {
            "name": "Title-Check",
            "phase": "Check",
            "trigger": "task_created",
            "action": "check_title",
            "agent": "CIO",
            "expected_result": "Titel >= 10 Zeichen, klar formuliert",
            "success_criteria": ["Titel enthaelt konkrete Aufgabe", "Titel hat >= 10 Zeichen"],
            "delay_s": 0.5,
            "description": "Prueft, ob der Titel aussagekraeftig genug ist.",
            "next_step": 1,
            "rules": [
                {
                    "description": "Title OK (>= 10 Zeichen)",
                    "condition_field": "step_ok",
                    "condition_operator": "is_true",
                    "condition_value": True,
                    "action_type": "complete",
                    "action_target": None,
                    "action_params": {},
                },
                {
                    "description": "Title zu kurz — Issue sammeln",
                    "condition_field": "step_ok",
                    "condition_operator": "is_false",
                    "condition_value": True,
                    "action_type": "collect_issue",
                    "action_target": None,
                    "action_params": {"issue_type": "title_too_short"},
                },
            ],
        },
        {
            "name": "Description-Check",
            "phase": "Check",
            "trigger": "task_created",
            "action": "check_description",
            "agent": "CIO",
            "expected_result": "Description >= 50 Zeichen mit Ziel + Akzeptanzkriterien",
            "success_criteria": ["Description >= 50 Zeichen", "Struktur: Ziel / Akzeptanz / Edge-Cases"],
            "delay_s": 0.5,
            "description": "Prueft, ob die Description ausfuehrlich genug ist.",
            "next_step": 2,
            "rules": [
                {
                    "description": "Description OK",
                    "condition_field": "step_ok",
                    "condition_operator": "is_true",
                    "condition_value": True,
                    "action_type": "complete",
                    "action_target": None,
                    "action_params": {},
                },
                {
                    "description": "Description fehlt / zu kurz",
                    "condition_field": "step_ok",
                    "condition_operator": "is_false",
                    "condition_value": True,
                    "action_type": "collect_issue",
                    "action_target": None,
                    "action_params": {"issue_type": "description_too_short"},
                },
            ],
        },
        {
            "name": "Success-Criteria-Check",
            "phase": "Check",
            "trigger": "task_created",
            "action": "check_success_criteria",
            "agent": "CIO",
            "expected_result": "Mindestens 1 Success-Criterion definiert",
            "success_criteria": ["success_criteria.length >= 1"],
            "delay_s": 0.5,
            "description": "Prueft, ob Akzeptanzkriterien definiert sind.",
            "next_step": 3,
            "rules": [
                {
                    "description": "Success-Criteria OK",
                    "condition_field": "step_ok",
                    "condition_operator": "is_true",
                    "condition_value": True,
                    "action_type": "complete",
                    "action_target": None,
                    "action_params": {},
                },
                {
                    "description": "Keine Success-Criteria definiert",
                    "condition_field": "step_ok",
                    "condition_operator": "is_false",
                    "condition_value": True,
                    "action_type": "collect_issue",
                    "action_target": None,
                    "action_params": {"issue_type": "no_success_criteria"},
                },
            ],
        },
        {
            "name": "Architektur-Alignment",
            "phase": "Check",
            "trigger": "task_created",
            "action": "check_architecture",
            "agent": "CIO",
            "expected_result": "Keine Konflikte mit OpenBrain-Standardvorgaben",
            "success_criteria": ["Keine explizite Verneinung von Architektur-Keywords"],
            "delay_s": 0.5,
            "description": "Prueft, ob die Description gegen OpenBrain-Architekturvorgaben verstoesst.",
            "next_step": 4,
            "rules": [
                {
                    "description": "Architektur OK",
                    "condition_field": "step_ok",
                    "condition_operator": "is_true",
                    "condition_value": True,
                    "action_type": "complete",
                    "action_target": None,
                    "action_params": {},
                },
                {
                    "description": "Architektur-Konflikt gefunden",
                    "condition_field": "step_ok",
                    "condition_operator": "is_false",
                    "condition_value": True,
                    "action_type": "collect_issue",
                    "action_target": None,
                    "action_params": {"issue_type": "architecture_conflict"},
                },
            ],
        },
        {
            "name": "Requirement-Consistency",
            "phase": "Check",
            "trigger": "task_created",
            "action": "check_consistency",
            "agent": "CIO",
            "expected_result": "Keine internen Widersprueche in der Anforderung",
            "success_criteria": ["Keine Konflikt-Paare (OAuth+lokal, SQL+NoSQL, etc.)"],
            "delay_s": 0.5,
            "description": "Prueft auf logische Widersprueche in der Anforderung.",
            "next_step": 5,
            "rules": [
                {
                    "description": "Konsistenz OK",
                    "condition_field": "step_ok",
                    "condition_operator": "is_true",
                    "condition_value": True,
                    "action_type": "complete",
                    "action_target": None,
                    "action_params": {},
                },
                {
                    "description": "Widerspruch gefunden",
                    "condition_field": "step_ok",
                    "condition_operator": "is_false",
                    "condition_value": True,
                    "action_type": "collect_issue",
                    "action_target": None,
                    "action_params": {"issue_type": "requirement_contradiction"},
                },
            ],
        },
        {
            "name": "Entscheidung: OK oder Rueckfrage",
            "phase": "Decision",
            "trigger": "task_created",
            "action": "decide_triage",
            "agent": "CIO",
            "expected_result": "Task → 'todo' (OK) oder 'rueckfrage' (Issues)",
            "success_criteria": ["Status-Wechsel dokumentiert", "Issues im t.meta gespeichert"],
            "delay_s": 0.5,
            "description": (
                "Entscheidung: wenn keine Issues gesammelt → move_status 'todo'. "
                "Wenn Issues vorhanden → move_status 'rueckfrage' + Frage."
            ),
            "next_step": None,
            "rules": [
                {
                    "description": "Keine Issues → Status 'todo'",
                    "condition_field": "issues_count",
                    "condition_operator": "is_zero",
                    "condition_value": 0,
                    "action_type": "move_status",
                    "action_target": "todo",
                    "action_params": {"reason": "cio_triage_approved", "next_agent": "Worker"},
                },
                {
                    "description": "Issues gefunden → Status 'rueckfrage' + Frage an CEOdigital",
                    "condition_field": "issues_count",
                    "condition_operator": "gt",
                    "condition_value": 0,
                    "action_type": "move_status",
                    "action_target": "rueckfrage",
                    "action_params": {"reason": "cio_auto_question", "next_agent": "CEOdigital"},
                },
            ],
        },
    ],
}


def seed_default_sops(db: Session) -> int:
    """Seeded die Standard-SOPs, falls noch nicht vorhanden.

    User-Direktive 24.06.2026: Override-Schutz + stabiler Match ueber sop_key.
      - Match ueber sop_key (Prioritaet 1), Fallback auf name (Prioritaet 2)
      - User-modifizierte SOPs (user_modified=True) werden NICHT ueberschrieben
      - Wenn eine SOP existiert aber keine der Default-Definitionen matcht:
        bleibt unveraendert (Custom-SOP)
      - Nur komplett fehlende SOPs werden neu angelegt
    """
    added = 0
    skipped_user_modified = 0
    for sop_def in (DEFAULT_TASK_SOP, DEFAULT_CIO_TRIAGE_SOP):
        sop_key = sop_def.get("sop_key")
        sop_name = sop_def.get("name")
        # Match ueber sop_key (stabil, rename-resistant)
        existing = None
        if sop_key:
            existing = db.execute(
                select(SOP).where(SOP.sop_key == sop_key)
            ).scalar_one_or_none()
        # Fallback: Match ueber Name (Legacy)
        if existing is None and sop_name:
            existing = db.execute(
                select(SOP).where(SOP.name == sop_name)
            ).scalar_one_or_none()
            # Wenn Legacy-Match: sop_key setzen fuer kuenftige Reloads
            if existing and sop_key and not existing.sop_key:
                existing.sop_key = sop_key
                logger.info(f"seed_default_sops: set sop_key={sop_key} for {existing.name[:40]}")
                db.commit()
        if existing:
            if getattr(existing, "user_modified", False):
                skipped_user_modified += 1
                logger.info(
                    f"seed_default_sops: skip {existing.name[:40]} "
                    f"(user_modified=True, Override-Schutz)"
                )
                continue
            else:
                # Existiert, ist NICHT user-modifiziert -> nichts tun (kein Update)
                # Updates nur ueber expliziten reset_to_default-Endpoint
                logger.debug(f"seed_default_sops: {existing.name[:40]} existiert, kein Update")
                continue
        # Neu anlegen
        engine = SOPEngine(db)
        sop = engine.create_sop(
            name=sop_def["name"],
            description=sop_def["description"],
            category=sop_def["category"],
            default_delay_s=sop_def["default_delay_s"],
            steps=sop_def["steps"],
            _trusted=True,
        )
        if sop:
            # sop_key an die neu angelegte SOP setzen
            sop.sop_key = sop_key
            sop.user_modified = False
            db.commit()
            added += 1
    if skipped_user_modified:
        logger.info(
            f"seed_default_sops: Skipped {skipped_user_modified} user-modified SOPs "
            f"(Override-Schutz aktiv)."
        )
    return added


def reset_sop_to_default(db: Session, sop_id: str) -> Optional[SOP]:
    """Setzt eine SOP auf die Default-Werte aus DEFAULT_TASK_SOP/DEFAULT_CIO_TRIAGE_SOP zurueck.

    ACHTUNG: Loescht ALLE Steps + Rules und legt sie neu an.
    Nur fuer SOPs mit matchendem sop_key.
    """
    sop = db.get(SOP, sop_id)
    if not sop:
        return None
    # Suche Default-Definition
    default_def = None
    for d in (DEFAULT_TASK_SOP, DEFAULT_CIO_TRIAGE_SOP):
        if d.get("sop_key") == sop.sop_key:
            default_def = d
            break
    if default_def is None:
        # Kein Default gefunden (custom SOP)
        sop.user_modified = False
        sop.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(sop)
        logger.info(f"reset_sop_to_default: {sop.name[:40]} (custom, nur Flag geloescht)")
        return sop
    # Alte Steps + Rules loeschen
    for step in list(sop.steps or []):
        for rule in list(step.rules or []):
            db.delete(rule)
        db.delete(step)
    db.flush()
    # Name, Description etc. aus Default
    sop.name = default_def["name"]
    sop.description = default_def["description"]
    sop.category = default_def["category"]
    sop.default_delay_s = default_def["default_delay_s"]
    # Neue Steps + Rules anlegen
    engine = SOPEngine(db)
    # create_sop geht von None aus, daher machen wir es manuell
    # Eigentlich: delete old SOP, create new? Nein, ID soll gleich bleiben.
    # Stattdessen: Steps manuell aus default_def["steps"] anlegen
    from ..models.sop import SOPStep, SOPStepRule
    import secrets as _secrets
    for idx, sd in enumerate(default_def["steps"]):
        step = SOPStep(
            id=_secrets.token_hex(6),
            sop_id=sop.id,
            step_order=idx,
            name=sd.get("name", f"Step {idx+1}"),
            phase=sd.get("phase", "Task"),
            trigger=sd.get("trigger", "step_completed"),
            action=sd.get("action", "noop"),
            action_params=sd.get("action_params") or {},
            agent=sd.get("agent", "system"),
            model=sd.get("model"),
            expected_result=sd.get("expected_result"),
            success_criteria=sd.get("success_criteria", []),
            delay_s=sd.get("delay_s", 5.0),
            description=sd.get("description"),
        )
        db.add(step)
        db.flush()
        for ridx, rd in enumerate(sd.get("rules", [])):
            rule = SOPStepRule(
                id=_secrets.token_hex(6),
                step_id=step.id,
                rule_order=ridx,
                description=rd.get("description"),
                condition_field=rd.get("condition_field", ""),
                condition_operator=rd.get("condition_operator", "eq"),
                condition_value=rd.get("condition_value"),
                action_type=rd.get("action_type", "noop"),
                action_target=rd.get("action_target"),
                action_params=rd.get("action_params", {}),
            )
            db.add(rule)
    sop.user_modified = False
    sop.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(sop)
    logger.info(f"reset_sop_to_default: {sop.name[:40]} komplett zurueckgesetzt")
    return sop
