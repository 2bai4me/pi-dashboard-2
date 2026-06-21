"""SOP-Router — CRUD, Engine-Steuerung, BPMN-Export, UML-Visualisierung.

User-Direktive 15.06.2026: Generisches SOP-System fuer wiederverwendbare
Regelprozesse im Bereich 'SOP Prozesse'.

Endpoints:
  GET    /api/sops                          — Liste aller SOPs
  POST   /api/sops                          — Neue SOP erstellen
  GET    /api/sops/{id}                     — SOP-Details inkl. Steps + Rules
  PUT    /api/sops/{id}                     — SOP-Metadaten aktualisieren
  DELETE /api/sops/{id}                     — SOP loeschen (CASCADE)
  GET    /api/sops/{id}/bpmn                — BPMN 2.0 XML
  GET    /api/sops/{id}/uml                 — UML Sequenzdiagramm
  POST   /api/sops/{id}/start               — Instance starten (an Projekt/Task)
  GET    /api/sops/instances                — Liste aller Instances
  GET    /api/sops/instances/{id}           — Instance-Details + Execution-Log
  POST   /api/sops/instances/{id}/run       — Engine: aktuellen Step ausfuehren
  POST   /api/sops/instances/{id}/fail      — Instance als failed markieren
  POST   /api/sops/seed-defaults            — Default-SOPs seeden
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, ValidationError, field_validator
from sqlalchemy.orm import Session
from sqlalchemy import select

from ..db.base import get_db
from ..auth import require_auth
from ..models.sop import SOP, SOPStep, SOPStepRule, SOPInstance, SOPExecution
from ..services.sop_engine import SOPEngine, seed_default_sops, DEFAULT_TASK_SOP, ALLOWED_SOP_ACTIONS
from ..schemas.sop_action import ALLOWED_ACTIONS, ACTION_PARAM_SCHEMAS

router = APIRouter(prefix="/api/sops", tags=["sops"])


def _validate_step_action_params(action: Optional[str], action_params: Optional[dict]) -> None:
    """Prueft action gegen die Whitelist und action_params gegen das Pydantic-Schema.

    Wirft HTTPException(400) bei Verstossen, damit der Client ein klares
    Fehler-Response bekommt.
    """
    if action is not None and action not in ALLOWED_SOP_ACTIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown or disallowed SOP action: {action!r}. Allowed: {sorted(ALLOWED_SOP_ACTIONS)}",
        )
    schema_cls = ACTION_PARAM_SCHEMAS.get(action) if action else None
    if schema_cls and action_params is not None:
        try:
            schema_cls.model_validate(action_params)
        except ValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
logger = logging.getLogger("pi-dashboard-2.sops")


# === Pydantic-Schemas (Request/Response) ===

class SOPStepInput(BaseModel):
    name: str
    phase: str = "Task"
    trigger: str
    action: str
    action_params: Optional[Dict[str, Any]] = None
    agent: str
    expected_result: Optional[str] = None
    success_criteria: Optional[List[str]] = None
    delay_s: float = 5.0
    description: Optional[str] = None
    rules: Optional[List[Dict[str, Any]]] = None
    # Verzweigungen werden spaeter per step_index aufgeloest
    next_step: Optional[int] = None
    fail_step: Optional[int] = None
    on_sub_sop_step: Optional[int] = None

    @field_validator("action", "action_params")
    @classmethod
    def _validate_action_and_params(cls, v, info):
        if info.field_name == "action":
            if v not in ALLOWED_SOP_ACTIONS:
                raise ValueError(
                    f"Action {v!r} not allowed. Allowed: {sorted(ALLOWED_SOP_ACTIONS)}"
                )
            return v
        # action_params
        action = info.data.get("action")
        schema_cls = ACTION_PARAM_SCHEMAS.get(action) if action else None
        if schema_cls and v is not None:
            schema_cls.model_validate(v)
        return v


class SOPCreate(BaseModel):
    name: str
    description: str
    category: str = "task"
    version: int = 1
    parent_sop_id: Optional[str] = None
    is_template: bool = False
    default_delay_s: float = 5.0
    steps: List[SOPStepInput] = Field(default_factory=list)


class SOPUpdate(BaseModel):
    name: Optional[str] = None  # User-Direktive 17.06.2026: SOP-Titel editierbar
    description: Optional[str] = None
    category: Optional[str] = None
    is_template: Optional[bool] = None
    default_delay_s: Optional[float] = None
    version: Optional[int] = None  # Optional: bei Rename kann version inkrementiert werden


class SOPInstanceCreate(BaseModel):
    sop_id: str
    project_id: Optional[str] = None
    task_id: Optional[str] = None
    context: Optional[Dict[str, Any]] = None


class AiEvaluateBody(BaseModel):
    """POST /api/sops/{sop_id}/steps/{step_id}/ai-evaluate

    User-Direktive 16.06.2026: KI-Support-Designer fuer SOP-Steps.
    Iterativ: jeder Aufruf nimmt die User-Nachricht + bisherigen MD-Text,
    gibt verbesserten MD-Text zurueck. Frontend fuehrt die Chat-History.
    """
    user_input: str = Field(..., min_length=10, description="Freitext-Beschreibung des Steps")
    model: Optional[str] = Field(None, description="LLM-Modell (default: minimax-direct/minimax-m3)")
    auto_save: bool = Field(False, description="Bei True wird das Ergebnis sofort in action_params.ai_instructions_md gespeichert")
    current_md: Optional[str] = Field(None, description="Bisheriger MD-Text (bei iterativem Chat-Modus)")
    conversation: Optional[List[Dict[str, str]]] = Field(
        None,
        description="Chat-History im OpenAI-Format (role/content). Wenn gesetzt, wird der iterative Modus benutzt."
    )


# === SOP-Endpoints ===

@router.get("")
async def list_sops(
    category: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    engine = SOPEngine(db)
    sops = engine.list_sops(category=category)
    return {"items": [s.to_dict(include_steps=False) for s in sops], "total": len(sops)}


@router.post("", status_code=201)
async def create_sop(
    req: SOPCreate,
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    engine = SOPEngine(db)
    # Sicherheitspruefung: jeder Step muss eine erlaubte Action haben und
    # action_params muessen zum jeweiligen Schema passen.
    for step in req.steps:
        _validate_step_action_params(step.action, step.action_params)

    steps_payload = [s.model_dump(exclude_none=True) for s in req.steps]
    try:
        sop = engine.create_sop(
            name=req.name, description=req.description, category=req.category,
            version=req.version, parent_sop_id=req.parent_sop_id,
            is_template=req.is_template, default_delay_s=req.default_delay_s,
            steps=steps_payload,
        )
    except (ValidationError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not sop:
        raise HTTPException(400, "SOP konnte nicht erstellt werden")
    return sop.to_dict(include_steps=True)


@router.get("/{sop_id}")
async def get_sop(
    sop_id: str,
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    engine = SOPEngine(db)
    sop = engine.get_sop(sop_id)
    if not sop:
        raise HTTPException(404, f"SOP {sop_id} not found")
    return sop.to_dict(include_steps=True)


@router.put("/{sop_id}")
async def update_sop(
    sop_id: str,
    req: SOPUpdate,
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    engine = SOPEngine(db)
    sop = engine.update_sop(sop_id, **req.model_dump(exclude_none=True))
    if not sop:
        raise HTTPException(404, f"SOP {sop_id} not found")
    return sop.to_dict(include_steps=False)


# === PATCH Step-Description (User-Direktive 16.06.2026: "Was passiert hier?" editierbar) ===
class StepDescriptionUpdate(BaseModel):
    description: Optional[str] = None
    expected_result: Optional[str] = None
    ai_instructions_md: Optional[str] = None
    # User-Input-Tool (User-Direktive 17.06.2026) — erweitert
    input_tool_required: Optional[bool] = None
    input_tool_type: Optional[str] = None
    input_tool_prompt: Optional[str] = None
    input_tool_description: Optional[str] = None
    input_tool_recommendation: Optional[str] = None
    input_tool_options: Optional[str] = None  # JSON-String
    input_tool_options_config: Optional[str] = None  # JSON-String
    input_tool_context_key: Optional[str] = None
    # Stufe 1: Action-Handler-Wechsel + acceptance_criteria (User-Direktive 18.06.2026)
    action: Optional[str] = None  # z.B. "tester_code_review", "cio_final_review", "review_task"
    action_params: Optional[dict] = None  # z.B. {"acceptance_criteria": ["coverage >= 80", "lint == 0"]}
    trigger: Optional[str] = None
    agent: Optional[str] = None

    @field_validator("action", "action_params")
    @classmethod
    def _validate_action_and_params(cls, v, info):
        if info.field_name == "action":
            if v is not None and v not in ALLOWED_SOP_ACTIONS:
                raise ValueError(
                    f"Action {v!r} not allowed. Allowed: {sorted(ALLOWED_SOP_ACTIONS)}"
                )
            return v
        # action_params
        action = info.data.get("action")
        schema_cls = ACTION_PARAM_SCHEMAS.get(action) if action else None
        if schema_cls and v is not None:
            schema_cls.model_validate(v)
        return v


# === POST neuer Step (User-Direktive 17.06.2026: "+ Step hinzufügen"-Button) ===
class StepCreate(BaseModel):
    """Schema zum Anlegen eines neuen SOP-Steps ueber die UI.

    Erforderlich: name
    Optional: alle weiteren Felder (phase, agent, trigger, action, etc.)
    """
    name: str = Field(..., min_length=1, max_length=255)
    phase: Optional[str] = Field("Task", description="z.B. Task | Sub-SOP | End")
    trigger: Optional[str] = Field("manual", description="z.B. manual | sop_start | step_completed")
    action: Optional[str] = Field("noop", description="z.B. noop | set_status | spawn_sop | ask_user | llm_call")
    action_params: Optional[dict] = Field(default_factory=dict)
    agent: Optional[str] = Field("pi-coder", description="Worker-Rolle (pi-coder, cio, ceo-digital, etc.)")
    expected_result: Optional[str] = None
    success_criteria: Optional[list] = Field(default_factory=list)
    description: Optional[str] = None
    delay_s: Optional[float] = Field(5.0, ge=0.0, le=600.0)
    # RACI (optional, mit sinnvollen Defaults)
    raci_r: Optional[str] = None
    raci_a: Optional[str] = None
    raci_c: Optional[str] = None
    raci_i: Optional[str] = None
    # User-Input-Tool (optional)
    input_tool_required: Optional[bool] = False
    input_tool_type: Optional[str] = None
    input_tool_prompt: Optional[str] = None
    input_tool_description: Optional[str] = None
    input_tool_recommendation: Optional[str] = None
    input_tool_options: Optional[list] = None
    input_tool_options_config: Optional[dict] = None
    input_tool_context_key: Optional[str] = None
    # Optional: explizit eine step_order setzen (sonst: max+1)
    step_order: Optional[int] = None
    # Optional: vorheriger Step (fuer nahtlosen Anschluss via next_step_id)
    insert_after_step_id: Optional[str] = None

    @field_validator("action", "action_params")
    @classmethod
    def _validate_action_and_params(cls, v, info):
        if info.field_name == "action":
            if v is not None and v not in ALLOWED_SOP_ACTIONS:
                raise ValueError(
                    f"Action {v!r} not allowed. Allowed: {sorted(ALLOWED_SOP_ACTIONS)}"
                )
            return v
        # action_params
        action = info.data.get("action")
        schema_cls = ACTION_PARAM_SCHEMAS.get(action) if action else None
        if schema_cls and v is not None:
            schema_cls.model_validate(v)
        return v


def _generate_step_id() -> str:
    """Erzeugt eine neue 12-stellige hexadezimale Step-ID (konsistent mit _gen_qid-Stil)."""
    import uuid as _uuid
    return _uuid.uuid4().hex[:12]


@router.post("/{sop_id}/steps", status_code=201)
async def create_step(
    sop_id: str,
    req: StepCreate,
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    """Erstellt einen neuen Step in einer SOP.

    Verhalten:
    - step_order: wenn nicht angegeben, wird (max+1) verwendet
    - insert_after_step_id: wenn gesetzt, wird der neue Step direkt nach diesem eingefuegt
      und die nachfolgenden Steps werden um +1 verschoben
    - next_step_id: previous.next_step_id -> neuer Step (falls insert_after)
    - input_tool_options/options_config werden als JSON-String persistiert
    """
    sop = db.get(SOP, sop_id)
    if not sop:
        raise HTTPException(404, f"SOP {sop_id} not found")

    # Action + action_params gegen Whitelist/Schema pruefen (klares 400)
    _validate_step_action_params(req.action, req.action_params)

    # === 1) step_order bestimmen ===
    existing_steps = db.execute(
        select(SOPStep).where(SOPStep.sop_id == sop_id).order_by(SOPStep.step_order)
    ).scalars().all()

    target_order: int
    insert_after: Optional[SOPStep] = None
    if req.insert_after_step_id:
        insert_after = db.get(SOPStep, req.insert_after_step_id)
        if not insert_after or insert_after.sop_id != sop_id:
            raise HTTPException(400, f"insert_after_step_id {req.insert_after_step_id} not found in SOP")
        target_order = insert_after.step_order + 1
    elif req.step_order is not None:
        target_order = req.step_order
    else:
        target_order = (max((s.step_order for s in existing_steps), default=-1)) + 1

    # === 2) Konflikte behandeln: wenn target_order bereits belegt, nachfolgende verschieben ===
    if any(s.step_order == target_order for s in existing_steps):
        for s in existing_steps:
            if s.step_order >= target_order:
                s.step_order += 1
        db.flush()

    # === 3) Neuen Step erstellen ===
    new_step = SOPStep(
        id=_generate_step_id(),
        sop_id=sop_id,
        step_order=target_order,
        name=req.name,
        phase=req.phase or "Task",
        trigger=req.trigger or "manual",
        action=req.action or "noop",
        action_params=req.action_params or {},
        agent=req.agent or "pi-coder",
        expected_result=req.expected_result,
        success_criteria=req.success_criteria or [],
        raci_r=req.raci_r or req.agent or "pi-coder",
        raci_a=req.raci_a or req.agent or "pi-coder",
        raci_c=req.raci_c,
        raci_i=req.raci_i,
        description=req.description,
        delay_s=req.delay_s if req.delay_s is not None else 5.0,
        # User-Input-Tool
        input_tool_required=bool(req.input_tool_required),
        input_tool_type=req.input_tool_type,
        input_tool_prompt=req.input_tool_prompt,
        input_tool_description=req.input_tool_description,
        input_tool_recommendation=req.input_tool_recommendation,
        input_tool_options=json.dumps(req.input_tool_options) if req.input_tool_options else None,
        input_tool_options_config=json.dumps(req.input_tool_options_config) if req.input_tool_options_config else None,
        input_tool_context_key=req.input_tool_context_key,
    )
    db.add(new_step)
    db.flush()

    # === 4) insert_after: previous.next_step_id auf neuen Step setzen ===
    if insert_after:
        if not insert_after.next_step_id:
            insert_after.next_step_id = new_step.id
    db.commit()
    db.refresh(new_step)

    return {
        "ok": True,
        "step": new_step.to_dict() if hasattr(new_step, "to_dict") else {"id": new_step.id, "step_order": new_step.step_order, "name": new_step.name},
        "sop_id": sop_id,
    }



@router.patch("/{sop_id}/steps/{step_id}")
async def update_step(
    sop_id: str,
    step_id: str,
    req: StepDescriptionUpdate,
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    """Aktualisiert die Description (oder expected_result) eines SOP-Steps.


    User-Direktive 16.06.2026: Im BPMN/UML-Tab soll der Text "Was passiert hier?"
    editierbar sein, damit User Anpassungen ohne API-Aufruf machen koennen.

    Optional kann auch ai_instructions_md (KI-Support-Designer Output)
    persistiert werden — wird in action_params gespeichert.
    """
    from ..models.sop import SOPStep
    sop = db.get(SOP, sop_id)
    if not sop:
        raise HTTPException(404, f"SOP {sop_id} not found")
    step = db.get(SOPStep, step_id)
    if not step or step.sop_id != sop_id:
        raise HTTPException(404, f"Step {step_id} not found in SOP {sop_id}")

    # Action + action_params gegen Whitelist/Schema pruefen (klares 400)
    _validate_step_action_params(req.action, req.action_params)

    changes = []
    if req.description is not None:
        old = step.description
        step.description = req.description
        changes.append(f"description: '{old[:40] if old else ''}' -> '{req.description[:40]}'")
    if req.expected_result is not None:
        old = step.expected_result
        step.expected_result = req.expected_result
        changes.append(f"expected_result: '{old[:40] if old else ''}' -> '{req.expected_result[:40]}'")
    if req.ai_instructions_md is not None:
        params = dict(step.action_params or {})
        params["ai_instructions_md"] = req.ai_instructions_md
        step.action_params = params
        old_len = len(params.get("ai_instructions_md") or "")
        changes.append(f"ai_instructions_md: {old_len} -> {len(req.ai_instructions_md)} chars")
    # Stufe 1: Action-Handler-Wechsel + acceptance_criteria (User-Direktive 18.06.2026)
    if req.action is not None:
        old = step.action
        step.action = req.action
        changes.append(f"action: {old!r} -> {req.action!r}")
    if req.action_params is not None:
        old = dict(step.action_params or {})
        step.action_params = req.action_params
        changes.append(f"action_params: {len(old)} -> {len(req.action_params)} keys")
    if req.trigger is not None:
        old = step.trigger
        step.trigger = req.trigger
        changes.append(f"trigger: {old!r} -> {req.trigger!r}")
    if req.agent is not None:
        old = step.agent
        step.agent = req.agent
        changes.append(f"agent: {old!r} -> {req.agent!r}")
    # User-Input-Tool Felder (User-Direktive 17.06.2026)
    if req.input_tool_required is not None:
        old = step.input_tool_required
        step.input_tool_required = req.input_tool_required
        changes.append(f"input_tool_required: {old} -> {req.input_tool_required}")
    if req.input_tool_type is not None:
        old = step.input_tool_type
        step.input_tool_type = req.input_tool_type
        changes.append(f"input_tool_type: {old} -> {req.input_tool_type}")
    if req.input_tool_prompt is not None:
        old = step.input_tool_prompt
        step.input_tool_prompt = req.input_tool_prompt
        changes.append(f"input_tool_prompt: {len(old or '')} -> {len(req.input_tool_prompt)} chars")
    if req.input_tool_description is not None:
        old = step.input_tool_description
        step.input_tool_description = req.input_tool_description
        changes.append(f"input_tool_description: {len(old or '')} -> {len(req.input_tool_description)} chars")
    if req.input_tool_recommendation is not None:
        old = step.input_tool_recommendation
        step.input_tool_recommendation = req.input_tool_recommendation
        changes.append(f"input_tool_recommendation: {len(old or '')} -> {len(req.input_tool_recommendation)} chars")
    if req.input_tool_options is not None:
        old = step.input_tool_options
        step.input_tool_options = req.input_tool_options
        changes.append(f"input_tool_options: updated")
    if req.input_tool_options_config is not None:
        old = step.input_tool_options_config
        step.input_tool_options_config = req.input_tool_options_config
        changes.append(f"input_tool_options_config: updated")
    if req.input_tool_context_key is not None:
        old = step.input_tool_context_key
        step.input_tool_context_key = req.input_tool_context_key
        changes.append(f"input_tool_context_key: {old} -> {req.input_tool_context_key}")
    if not changes:
        raise HTTPException(400, "Keine Aenderungen angegeben")
    from datetime import datetime as _dt
    step.updated_at = _dt.utcnow()
    db.commit()
    db.refresh(step)
    return {
        "ok": True,
        "sop_id": sop_id,
        "step_id": step_id,
        "changes": changes,
        "step": {
            "id": step.id,
            "name": step.name,
            "description": step.description,
            "expected_result": step.expected_result,
            "action_params": step.action_params or {},
            "input_tool_required": step.input_tool_required,
            "input_tool_type": step.input_tool_type,
            "input_tool_prompt": step.input_tool_prompt,
            "input_tool_description": step.input_tool_description,
            "input_tool_recommendation": step.input_tool_recommendation,
            "input_tool_options": step.input_tool_options,
            "input_tool_options_config": step.input_tool_options_config,
            "input_tool_context_key": step.input_tool_context_key,
        },
    }


# === AI-Helper: User-Notiz -> optimierte Description + Expected Result ===
# User-Direktive 16.06.2026: User klickt "Bearbeiten", beschreibt in einfacher Sprache,
# was gemacht werden soll. KI ergaenzt zu optimalem Prompt.
class AiHelperBody(BaseModel):
    user_input: str = Field(..., min_length=5, description="User-Notiz in einfachem Deutsch")
    model: Optional[str] = Field(None, description="LLM-Modell (default: minimax-m3)")


@router.post("/{sop_id}/steps/{step_id}/ai-helper")
async def ai_step_helper(
    sop_id: str,
    step_id: str,
    body: AiHelperBody,
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    """AI-gestuetzter Prompt-Helfer fuer SOP-Step-Description.

    Nimmt eine kurze User-Notiz + Step-Kontext, ruft minimax-M3 auf,
    und liefert eine praezise Description + Expected Result zurueck.

    Returns: { ok, description, expected_result, questions, suggestions, usage }
    """
    import json as _json
    from ..models.sop import SOPStep, SOP as _SOP
    from ..services.llm_service import chat_completion, build_sop_step_prompt
    from ..services.pricing_service import take_pricing_snapshot
    from ..models.token_usage import TokenUsage

    sop = db.get(_SOP, sop_id)
    if not sop:
        raise HTTPException(404, f"SOP {sop_id} not found")
    step = db.get(SOPStep, step_id)
    if not step or step.sop_id != sop_id:
        raise HTTPException(404, f"Step {step_id} not found in SOP {sop_id}")

    # LLM-Prompt bauen
    step_dict = {
        "name": step.name, "phase": step.phase, "agent": step.agent,
        "action": step.action, "trigger": step.trigger,
        "description": step.description, "expected_result": step.expected_result,
    }
    messages, _ = build_sop_step_prompt(step_dict, body.user_input, sop.name)
    model = body.model or "minimax-m3"

    try:
        raw_response = await chat_completion(
            messages=messages, model=model, temperature=0.3, max_tokens=2000,
            role=step.agent,
        )
    except Exception as e:
        logger.error(f"AI-Helper Fehler: {e}")
        raise HTTPException(503, f"LLM-Aufruf fehlgeschlagen: {e}")

    # JSON parsen (LLM gibt manchmal Markdown-Codeblock drumherum)
    text = raw_response.strip()
    if text.startswith("```"):
        # Entferne Markdown-Codeblock
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)

    try:
        parsed = _json.loads(text)
    except Exception:
        # Fallback: versuche JSON im Text zu finden
        import re
        m = re.search(r"\{[\s\S]*\}", text)
        if m:
            try:
                parsed = _json.loads(m.group(0))
            except Exception:
                parsed = {
                    "description": text[:500],
                    "expected_result": "",
                    "questions": ["LLM-Antwort war kein gueltiges JSON. Bitte manuell ergaenzen."],
                    "suggestions": [],
                }
        else:
            parsed = {
                "description": text[:500],
                "expected_result": "",
                "questions": ["LLM-Antwort war kein gueltiges JSON. Bitte manuell ergaenzen."],
                "suggestions": [],
            }

    # Token-Usage dokumentieren (optional)
    try:
        from ..models.token_usage import TokenUsage as _TU
        from ..models.history import TaskHistory as _TH
        from decimal import Decimal
        in_tokens = sum(len(m["content"]) // 4 for m in messages)
        out_tokens = len(raw_response) // 4
        tu = _TU(
            task_id=None, history_id=None,
            model=model, provider="minimax-direct",
            role=step.agent or "ai_helper",
            tokens_in=in_tokens, tokens_out=out_tokens,
            cost_usd=Decimal("0"),
            input_per_1m=Decimal("0.30"), output_per_1m=Decimal("1.20"),
            pricing_source="static_fallback",
            snapshot_at=datetime.utcnow(),
        )
        db.add(tu)
    except Exception as e:
        logger.warning(f"TokenUsage konnte nicht erstellt werden: {e}")

    return {
        "ok": True,
        "sop_id": sop_id,
        "step_id": step_id,
        "description": parsed.get("description", "").strip(),
        "expected_result": parsed.get("expected_result", "").strip(),
        "questions": parsed.get("questions", []) or [],
        "suggestions": parsed.get("suggestions", []) or [],
        "model": model,
        "raw_length": len(raw_response),
    }


# === KI-Support-Designer: erzeugt Markdown-Anweisung fuer den PI-Agent ===
@router.post("/{sop_id}/steps/{step_id}/ai-evaluate")
async def ai_step_evaluate(
    sop_id: str,
    step_id: str,
    body: AiEvaluateBody,
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    """KI-Support-Designer (User-Direktive 16.06.2026): Aus User-Freitext wird
    eine vollstaendige Markdown-Anweisung fuer den PI-Agent erzeugt.

    Workflow:
      1. User klickt 'KI-Support Designer' (links neben XML-Button) in BPMN-View
      2. Popup oeffnet sich mit Chat-UI (Textarea links)
      3. User schreibt frei, was der Step tun soll / welche Infos relevant sind
      4. 'Evaluieren' ruft diesen Endpoint auf
      5. KI (default ollama/qwen3:4b) generiert MD-Text
      6. User kann uebernehmen -> wird in step.action_params.ai_instructions_md
         persistiert und in der StepDetailSidebar (rechts) als Editor angezeigt.

    Returns: { ok, ai_instructions_md, model, raw_length, auto_saved }
    """
    from ..models.sop import SOPStep, SOP as _SOP

    sop = db.get(_SOP, sop_id)
    if not sop:
        raise HTTPException(404, f"SOP {sop_id} not found")
    step = db.get(SOPStep, step_id)
    if not step or step.sop_id != sop_id:
        raise HTTPException(404, f"Step {step_id} not found in SOP {sop_id}")

    # LLM-Aufruf (Provider aus settings, default minimax-direct/minimax-m3 — User-Direktive 16.06.2026)
    from ..services.llm_service import chat_completion
    from ..models.token_usage import TokenUsage
    from decimal import Decimal

    model = body.model or "minimax-direct/minimax-m3"

    # System-Prompt: SOP-Designer mit PI-Agent-Kontext
    system_prompt = (
        "Du bist ein SOP-Designer fuer das Pi Dashboard 2.0. Deine Aufgabe: "
        "Aus dem Freitext des Users generierst du eine praezise, ausfuehrbare "
        "Markdown-Anweisung, die ein PI-Agent (Coding-Agent) direkt lesen und "
        "befolgen kann, wenn dieser Schritt bei einem Task ausgefuehrt wird.\n\n"
        "REGELN:\n"
        "1. Antworte AUSSCHLIESSLICH mit Markdown (kein JSON, kein Code-Block drumherum).\n"
        "2. Struktur (genau diese Reihenfolge und Anzahl der Sektionen):\n"
        "   - '# <Step-Name>' (Titel, ein H1)\n"
        "   - '## Verantwortlich' (wer fuehrt diesen Schritt aus — Agent-Rolle, z.B. 'CIO', 'pi-coder', 'pi-tester', 'CEO-digital')\n"
        "   - '## Ziel' (was soll erreicht werden, 1-2 Saetze)\n"
        "   - '## Vorgehen' (nummerierte Liste, konkrete Schritte)\n"
        "   - '## Ergebnisse' (was liegt am Ende konkret vor — Datei, Commit, Status, Output, ...)\n"
        "   - '## Erfolgskriterien' (Bullet-Liste mit 'Erfolg wenn: ...' Saetzen)\n"
        "   - '## KPIs' (messbare Kennzahlen, z.B. Antwortzeit, Fehlerrate, Coverage, etc.)\n"
        "   - '## Nächste Schritte' (was passiert nach diesem Step, wer uebernimmt, welcher Status folgt)\n"
        "3. Konkret und handlungsorientiert schreiben — der PI-Agent soll ohne Rueckfragen wissen, was zu tun ist.\n"
        "4. Edge-Cases und Eskalation in 'Vorgehen' oder 'Erfolgskriterien' beschreiben.\n"
        "5. KEINE generischen Floskeln ('sorgfaeltig pruefen', 'gewissenhaft arbeiten').\n"
        "6. Umlaute (ä, ö, ü, ß) sind erlaubt und erwünscht — schreibe 'Nächste Schritte', nicht 'Naechste Schritte'.\n"
        "7. Im ITERATIVEN MODUS: Du bekommst den bisherigen MD-Text und eine neue User-Nachricht. "
        "Verbessere den Text gemaess der neuen Nachricht, behalte aber alle bestehenden korrekten Inhalte. "
        "Gib den GESAMTEN aktualisierten MD-Text zurueck, nicht nur die Aenderung.\n"
        "8. Wenn der User-Text unklar ist: '## Klärungsbedarf' am Ende mit konkreten Fragen.\n"
    )

    # Iterativer Chat-Modus vs. Einmal-Modus
    if body.conversation and len(body.conversation) > 0:
        # === ITERATIV: Conversation-History vom Frontend nutzen ===
        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": (
                    f"## Step-Definition (aus SOP '{sop.name}')\n"
                    f"- **Name:** {step.name}\n"
                    f"- **Phase:** {step.phase}\n"
                    f"- **Agent (Standard, falls User nichts anderes sagt):** {step.agent}\n"
                    f"- **Trigger:** {step.trigger}\n"
                    f"- **Action:** {step.action}\n\n"
                    f"## Bisheriger MD-Text (falls vorhanden)\n"
                    f"{(body.current_md or '(noch keiner)').strip() or '(noch keiner)'}\n\n"
                    f"---\n"
                    f"Fuehre die letzte User-Nachricht aus und gib den GESAMTEN aktualisierten MD-Text zurueck."
                )
            },
        ]
        # Chat-History (außer der letzten User-Nachricht, die separat behandelt wird)
        for msg in body.conversation[:-1]:
            messages.append({"role": msg.get("role", "user"), "content": msg.get("content", "")})
        # Letzte User-Nachricht
        if body.conversation and body.conversation[-1].get("role") == "user":
            messages.append({"role": "user", "content": body.conversation[-1]["content"]})
    else:
        # === Einmal-Modus (alter Code, kompatibel) ===
        user_prompt = (
            f"## Step-Definition (aus SOP '{sop.name}')\n"
            f"- **Name:** {step.name}\n"
            f"- **Phase:** {step.phase}\n"
            f"- **Agent (Standard):** {step.agent}\n"
            f"- **Trigger:** {step.trigger}\n"
            f"- **Action:** {step.action}\n"
            f"- **Description (bisher):** {step.description or '(leer)'}\n"
            f"- **Expected Result (bisher):** {step.expected_result or '(leer)'}\n\n"
            f"## User-Beschreibung (Freitext)\n"
            f"{body.user_input}\n\n"
            f"---\n"
            f"Generiere die Markdown-Anweisung fuer den PI-Agent."
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    try:
        ai_md = await chat_completion(
            messages=messages, model=model, temperature=0.3, max_tokens=4000,
            timeout_sec=300.0,  # 5 Min — lokale Ollama-Modelle (gemma4:12b) brauchen oft 60-180s
            role=step.agent,
        )
    except Exception as e:
        logger.error(f"AI-Evaluate Fehler: {e}")
        raise HTTPException(503, f"LLM-Aufruf fehlgeschlagen: {e}")

    ai_md = (ai_md or "").strip()
    # 1) Markdown-Codeblock auspacken falls vorhanden
    if ai_md.startswith("```"):
        lines_ = ai_md.split("\n")
        if lines_[0].startswith("```"):
            lines_ = lines_[1:]
        if lines_ and lines_[-1].strip() == "```":
            lines_ = lines_[:-1]
        ai_md = "\n".join(lines_).strip()
    # 2) MiniMax M3 gibt oft <think>...</think> Bloecke mit aus — rausfiltern
    #    Nur entfernen wenn BEIDE Marker vorhanden sind (sonst bleibt der Text)
    import re as _re
    if "<think>" in ai_md and "</think>" in ai_md:
        ai_md = _re.sub(r"<think>.*?</think>\s*", "", ai_md, flags=_re.DOTALL).strip()
    # 3) Doppelte Leerzeilen reduzieren
    ai_md = _re.sub(r"\n{3,}", "\n\n", ai_md).strip()

    # Token-Usage dokumentieren
    try:
        in_tokens = sum(len(m["content"]) // 4 for m in messages)
        out_tokens = len(ai_md) // 4
        tu = TokenUsage(
            task_id=None, history_id=None,
            model=model, provider=model.split("/")[0] if "/" in model else "ollama",
            role=step.agent or "ai_designer",
            tokens_in=in_tokens, tokens_out=out_tokens,
            cost_usd=Decimal("0"),
            input_per_1m=Decimal("0"), output_per_1m=Decimal("0"),
            pricing_source="local_ollama" if model.startswith("ollama/") else "static_fallback",
            snapshot_at=datetime.utcnow(),
        )
        db.add(tu)
    except Exception as e:
        logger.warning(f"TokenUsage konnte nicht erstellt werden: {e}")

    # Optional: direkt persistieren
    auto_saved = False
    if body.auto_save:
        params = dict(step.action_params or {})
        params["ai_instructions_md"] = ai_md
        step.action_params = params
        db.commit()
        db.refresh(step)
        auto_saved = True

    return {
        "ok": True,
        "sop_id": sop_id,
        "step_id": step_id,
        "ai_instructions_md": ai_md,
        "model": model,
        "raw_length": len(ai_md),
        "auto_saved": auto_saved,
    }


@router.delete("/{sop_id}", status_code=204)
async def delete_sop(
    sop_id: str,
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    engine = SOPEngine(db)
    if not engine.delete_sop(sop_id):
        raise HTTPException(404, f"SOP {sop_id} not found")


@router.get("/{sop_id}/bpmn")
async def get_bpmn(
    sop_id: str,
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    """Liefert die SOP als BPMN 2.0 XML (zur Anzeige in bpmn.io)."""
    engine = SOPEngine(db)
    sop = engine.get_sop(sop_id)
    if not sop:
        raise HTTPException(404, f"SOP {sop_id} not found")
    if sop.bpmn_xml:
        return {"sop_id": sop_id, "format": "bpmn20-xml", "xml": sop.bpmn_xml}
    # BPMN automatisch generieren
    bpmn_xml = _generate_bpmn(sop)
    return {"sop_id": sop_id, "format": "bpmn20-xml", "xml": bpmn_xml, "auto_generated": True}


@router.get("/{sop_id}/uml")
async def get_uml(
    sop_id: str,
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    """Liefert die SOP als UML-Sequenzdiagramm (PlantUML-Format)."""
    engine = SOPEngine(db)
    sop = engine.get_sop(sop_id)
    if not sop:
        raise HTTPException(404, f"SOP {sop_id} not found")
    if sop.uml_sequence_diagram:
        return {"sop_id": sop_id, "format": "plantuml", "source": sop.uml_sequence_diagram}
    puml = _generate_uml(sop)
    return {"sop_id": sop_id, "format": "plantuml", "source": puml, "auto_generated": True}


@router.post("/{sop_id}/start", status_code=201)
async def start_instance(
    sop_id: str,
    req: SOPInstanceCreate,
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    engine = SOPEngine(db)
    inst = engine.create_instance(
        sop_id=sop_id,
        project_id=req.project_id,
        task_id=req.task_id,
        context=req.context,
    )
    if not inst:
        raise HTTPException(400, f"Konnte Instance nicht starten (SOP {sop_id} ungueltig oder leer)")
    return inst.to_dict(include_executions=True)


# === Instance-Endpoints ===

@router.get("/instances/all")
async def list_instances(
    project_id: Optional[str] = Query(None),
    task_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    engine = SOPEngine(db)
    insts = engine.list_instances(project_id=project_id, task_id=task_id, status=status)
    return {"items": [i.to_dict(include_executions=False) for i in insts], "total": len(insts)}


@router.get("/instances/{instance_id}")
async def get_instance(
    instance_id: str,
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    engine = SOPEngine(db)
    inst = engine.get_instance(instance_id)
    if not inst:
        raise HTTPException(404, f"Instance {instance_id} not found")
    return inst.to_dict(include_executions=True)


@router.post("/instances/{instance_id}/run")
async def run_instance(
    instance_id: str,
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    """Engine: aktuellen Step ausfuehren (inkl. 5s-Verzoegerung)."""
    engine = SOPEngine(db)
    inst = engine.get_instance(instance_id)
    if not inst:
        raise HTTPException(404, f"Instance {instance_id} not found")
    result = await engine.run_step(inst)
    inst = engine.get_instance(instance_id)  # Refresh
    return {"result": result, "instance": inst.to_dict(include_executions=True) if inst else None}


@router.post("/instances/{instance_id}/fail")
async def fail_instance(
    instance_id: str,
    reason: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    engine = SOPEngine(db)
    inst = engine.get_instance(instance_id)
    if not inst:
        raise HTTPException(404, f"Instance {instance_id} not found")
    result = engine.fail_instance(inst, reason)
    return result


class ContextUpdateBody(BaseModel):
    context: Dict[str, Any] = Field(..., description="Kontext-Variablen, die in Rules ausgewertet werden (z.B. step_ok=True)")


@router.post("/instances/{instance_id}/context")
async def set_instance_context(
    instance_id: str,
    body: ContextUpdateBody,
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    """Setzt Kontext-Variablen einer Instance (fuer Rule-Evaluation)."""
    inst = db.get(SOPInstance, instance_id)
    if not inst:
        raise HTTPException(404, f"Instance {instance_id} not found")
    inst.context = body.context
    db.commit()
    db.refresh(inst)
    return inst.to_dict(include_executions=False)


@router.post("/seed-defaults", status_code=201)
async def seed_defaults(
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    """Seeded die Standard-Task-SOP, falls noch nicht vorhanden."""
    count = seed_default_sops(db)
    return {"ok": True, "seeded": count, "sop_name": DEFAULT_TASK_SOP["name"]}


# === Generators: BPMN 2.0 + UML Sequenzdiagramm ===

def _generate_bpmn(sop: SOP) -> str:
    """Generiert valides BPMN 2.0 XML aus einer SOP-Definition (bpmn-js-kompatibel).

    Architektur (User-Direktive 17.06.2026):
    - Top-Level: 4 SubProcesses (kollabierbar) + Start/End in horizontalem Layout
        1. Ziel-Erfassung (User-Input-Schritte)
        2. Spec-Generierung (Orchestrator + Subagenten)
        3. CIO Review-Zirkel (Reviews + Gateways + Loop-Back)
        4. Spec-Finalizer
    - SubProcesses sind collapsed: isExpanded=false (bpmn-js zeigt + zum Aufklappen)
    - Innerhalb jedes SubProcess: alle Steps + Gateways + Edges
    - Loop-Back-Edge: vom Review-SubProcess zurueck zum Spec-Generierung-SubProcess
      (sichtbar als horizontaler Bogen unter den SubProcesses)
    - Beim Klick auf einen SubProcess expandiert bpmn-js ihn automatisch
    - Grosszuegige Abstaende zwischen den Elementen
    """
    ns = "http://www.omg.org/spec/BPMN/20100524/MODEL"
    bpmndi_ns = "http://www.omg.org/spec/BPMN/20100524/DI"
    dc_ns = "http://www.omg.org/spec/DD/20100524/DC"
    di_ns = "http://www.omg.org/spec/DD/20100524/DI"
    bpmnjs_ns = "http://bpmn.io/schema/bpmn-js"

    defs_id = f"Definitions_{sop.id}"
    proc_id = f"Process_{sop.id}"
    start_id = f"start_{sop.id}"
    end_id = f"end_{sop.id}"

    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<bpmn:definitions xmlns:bpmn="{ns}" '
        f'xmlns:bpmndi="{bpmndi_ns}" '
        f'xmlns:dc="{dc_ns}" '
        f'xmlns:di="{di_ns}" '
        f'xmlns:bpmnjs="{bpmnjs_ns}" '
        f'id="{defs_id}" targetNamespace="http://bpmn.io/schema/bpmn">',
        f'  <bpmn:process id="{proc_id}" name="{_xml_escape(sop.name)}" isExecutable="false">',
        f'    <bpmn:documentation>{_xml_escape(sop.description or "")}</bpmn:documentation>',
    ]

    sorted_steps = sorted(sop.steps, key=lambda s: s.step_order)
    if not sorted_steps:
        parts.append(f'    <bpmn:startEvent id="{start_id}" name="SOP Start" />')
        parts.append(f'    <bpmn:endEvent id="{end_id}" name="SOP End" />')
        parts.append(f'    <bpmn:sequenceFlow id="flow_empty" sourceRef="{start_id}" targetRef="{end_id}" />')
        parts.append('  </bpmn:process>')
        parts.append('</bpmn:definitions>')
        return "\n".join(parts)

    # === Schritte in SubProcess-Gruppen klassifizieren ===
    def _classify(step) -> str:
        if step.phase == "End":
            return "finalizer"
        if step.rules:
            return "review"
        if step.input_tool_required or (step.agent and "ceo" in step.agent.lower()):
            return "input"
        if step.agent and step.agent.startswith("pi-coder-spec"):
            return "subagent"
        if step.agent and step.agent.startswith("pi-coder"):
            return "orchestrator"
        return "other"

    groups: dict = {"input": [], "orchestrator": [], "subagent": [], "review": [], "finalizer": [], "other": []}
    for s in sorted_steps:
        groups[_classify(s)].append(s)

    sp_defs = []
    if groups["input"]:
        sp_defs.append({"id": "sp1_input", "name": "1. Ziel-Erfassung", "steps": groups["input"]})
    if groups["orchestrator"] or groups["subagent"]:
        all_gen = groups["orchestrator"] + groups["subagent"]
        sp_defs.append({"id": "sp2_gen", "name": "2. Spec-Generierung (Schwarm)", "steps": all_gen})
    if groups["review"]:
        sp_defs.append({"id": "sp3_review", "name": "3. CIO Review-Zirkel", "steps": groups["review"]})
    if groups["finalizer"]:
        sp_defs.append({"id": "sp4_final", "name": "4. Spec-Finalizer", "steps": groups["finalizer"]})

    # === Top-Level: StartEvent + SubProcesses + EndEvent ===
    parts.append(f'    <bpmn:startEvent id="{start_id}" name="SOP Start" />')

    for sp in sp_defs:
        parts.append(f'    <bpmn:subProcess id="{sp["id"]}" name="{_xml_escape(sp["name"])}">')
        sp_steps = sp["steps"]
        step_gw: dict = {}

        # Tasks + Gateways
        for step in sp_steps:
            if step.agent and step.agent.startswith("pi-coder-spec"):
                task_tag = "bpmn:scriptTask"
            elif step.agent and step.agent.startswith("pi-coder"):
                task_tag = "bpmn:scriptTask"
            elif step.agent in ("user", "CEO", "CEO-digital"):
                task_tag = "bpmn:userTask"
            elif step.phase == "End":
                task_tag = "bpmn:serviceTask"
            else:
                task_tag = "bpmn:serviceTask"
            doc_text = (
                f"Phase: {step.phase} | Agent: {step.agent} | "
                f"Trigger: {step.trigger} | Action: {step.action} | "
                f"Expected: {(step.expected_result or '')[:80]} | Delay: {step.delay_s}s"
            )
            parts.append(
                f'      <{task_tag} id="step_{step.id}" name="{_xml_escape(step.name)}">'
                f'<bpmn:documentation>{_xml_escape(doc_text)}</bpmn:documentation>'
                f'</{task_tag}>'
            )
            if step.rules:
                gw_id = f"gw_{step.id}"
                step_gw[step.id] = gw_id
                parts.append(f'      <bpmn:exclusiveGateway id="{gw_id}" name="?" />')

        # Inner-SubProcess-Edges
        for i, step in enumerate(sp_steps):
            if step.id in step_gw:
                gw = step_gw[step.id]
                # Step -> Gateway
                parts.append(
                    f'      <bpmn:sequenceFlow id="inner_step_{step.id}_to_gw" '
                    f'sourceRef="step_{step.id}" targetRef="{gw}" />'
                )
                # Rule-Conditional-Flows
                for ridx, rule in enumerate(sorted(step.rules, key=lambda r: r.rule_order)):
                    tgt = rule.action_target
                    if tgt in [s.id for s in sp_steps]:
                        target_ref = f"step_{tgt}"
                    elif tgt and tgt in [s.id for s in sorted_steps]:
                        # Loop-Back: zeigt auf Step in einem anderen (collapsed) SubProcess
                        target_ref = f"step_{tgt}"
                    else:
                        target_ref = end_id
                    cond_text = f"{rule.condition_field} {rule.condition_operator} {rule.condition_value}"
                    parts.append(
                        f'      <bpmn:sequenceFlow id="inner_gw_{step.id}_r{ridx}" '
                        f'sourceRef="{gw}" targetRef="{target_ref}">'
                        f'<bpmn:conditionExpression>{_xml_escape(cond_text)}</bpmn:conditionExpression>'
                        f'</bpmn:sequenceFlow>'
                    )
                # Default-Flow
                default_target = step.next_step_id
                if default_target and default_target in [s.id for s in sp_steps]:
                    default_ref = f"step_{default_target}"
                else:
                    default_ref = end_id
                parts.append(
                    f'      <bpmn:sequenceFlow id="inner_gw_{step.id}_default" '
                    f'sourceRef="{gw}" targetRef="{default_ref}" name="default" />'
                )
            else:
                if i + 1 < len(sp_steps):
                    next_s = sp_steps[i + 1]
                    parts.append(
                        f'      <bpmn:sequenceFlow id="inner_step_{step.id}" '
                        f'sourceRef="step_{step.id}" targetRef="step_{next_s.id}" '
                        f'name="{_xml_escape(_flow_label(step))}" />'
                    )
        parts.append('    </bpmn:subProcess>')

    parts.append(f'    <bpmn:endEvent id="{end_id}" name="SOP End" />')

    # === Top-Level-Edges ===
    if sp_defs:
        parts.append(
            f'    <bpmn:sequenceFlow id="flow_start_to_sp1" '
            f'sourceRef="{start_id}" targetRef="{sp_defs[0]["id"]}" name="start" />'
        )
        for i in range(len(sp_defs) - 1):
            parts.append(
                f'    <bpmn:sequenceFlow id="flow_sp{i+1}_to_sp{i+2}" '
                f'sourceRef="{sp_defs[i]["id"]}" targetRef="{sp_defs[i + 1]["id"]}" />'
            )
        parts.append(
            f'    <bpmn:sequenceFlow id="flow_sp_last_to_end" '
            f'sourceRef="{sp_defs[-1]["id"]}" targetRef="{end_id}" />'
        )

    parts.append('  </bpmn:process>')

    # === BPMN-DI (Diagram Interchange) ===
    # Layout: horizontal, zentriert, grosszuegige Abstaende
    # SubProcess-Hoehe wird dynamisch pro SubProcess berechnet (passt zum Inhalt)
    # Vertikale Zentrierung: alle SubProcesses haben ihre MITTE auf der gleichen Y-Linie
    SP_W = 320  # SubProcess-Breite
    X_START = 80
    Y_CENTER_REF = 500  # Y-Koordinate, an der die Mittelpunkte aller SubProcesses ausgerichtet sind
    SP_GAP_X = 220  # horizontaler Abstand zwischen SubProcesses
    SP_GAP_Y = 180  # vertikaler Abstand zwischen SubProcess-Reihen (bei mehrzeiligem Layout)

    # Berechne Hoehe pro SubProcess basierend auf Inhalt
    INNER_STEP_H = 50
    INNER_GW_H = 36
    INNER_GAP = 30  # vertikaler Abstand zwischen Elementen
    SP_HEADER_H = 60  # Platz oben fuer SubProcess-Header
    SP_FOOTER_PAD = 25

    sp_dims: dict = {}  # sp_id -> (x, y, w, h)
    for sp in sp_defs:
        n_steps = len(sp["steps"])
        n_gw = sum(1 for s in sp["steps"] if s.rules)
        # Inhalt-Hoehe = steps * (STEP_H + GAP) + gateways * (GW_H + GAP) - letztes GAP
        content_h = n_steps * (INNER_STEP_H + INNER_GAP) + n_gw * (INNER_GW_H + INNER_GAP)
        if content_h > 0:
            content_h -= INNER_GAP  # letztes GAP abziehen
        sp_h = SP_HEADER_H + content_h + SP_FOOTER_PAD
        # Mindesthoehe fuer Konsistenz
        sp_h = max(sp_h, 200)
        sp_dims[sp["id"]] = (SP_W, sp_h)

    parts.append(f'  <bpmndi:BPMNDiagram id="BPMNDiagram_{sop.id}">')
    parts.append(f'    <bpmndi:BPMNPlane id="BPMNPlane_{sop.id}" bpmnElement="{proc_id}">')

    def _shape_bounds(elem_id: str, x: int, y: int, w: int, h: int) -> str:
        return (
            f'      <bpmndi:BPMNShape id="{elem_id}_di" bpmnElement="{elem_id}">\n'
            f'        <dc:Bounds x="{x}" y="{y}" width="{w}" height="{h}" />\n'
            f'      </bpmndi:BPMNShape>'
        )

    def _shape_subprocess(elem_id: str, x: int, y: int, w: int, h: int) -> str:
        # isExpanded=true: zeigt alle inneren Elemente (Steps, Gateways, Edges) in der Box
        return (
            f'      <bpmndi:BPMNShape id="{elem_id}_di" bpmnElement="{elem_id}">\n'
            f'        <dc:Bounds x="{x}" y="{y}" width="{w}" height="{h}" />\n'
            f'        <bpmndi:BPMNLabel/>\n'
            f'        <bpmnjs:isExpanded>true</bpmnjs:isExpanded>\n'
            f'      </bpmndi:BPMNShape>'
        )

    # StartEvent (vertikal zentriert auf Y_CENTER_REF)
    Y_CENTER = Y_CENTER_REF
    parts.append(_shape_bounds(start_id, X_START, Y_CENTER - 25, 50, 50))
    # SubProcesses (alle vertikal zentriert auf Y_CENTER_REF)
    x_cursor = X_START + 50 + SP_GAP_X
    sp_x: dict = {}
    sp_y: dict = {}
    for sp in sp_defs:
        w, h = sp_dims[sp["id"]]
        sp_x[sp["id"]] = x_cursor
        # Vertikale Zentrierung: SubProcess-Mitte = Y_CENTER_REF
        sp_y[sp["id"]] = Y_CENTER - h // 2
        parts.append(_shape_subprocess(sp["id"], x_cursor, sp_y[sp["id"]], w, h))
        x_cursor += w + SP_GAP_X
    # EndEvent (vertikal zentriert)
    x_end = x_cursor
    parts.append(_shape_bounds(end_id, x_end, Y_CENTER - 25, 50, 50))

    # === DI-Shapes fuer die INNEREN Elemente der SubProcesses ===
    # Layout: grosszuegige vertikale Liste innerhalb jeder SubProcess-Box
    # Steps sind 260px breit (innerhalb 320px Box), Gateways zentriert daneben
    INNER_STEP_W = 260
    INNER_STEP_H = 50
    INNER_GW = 40
    INNER_GAP = 60  # grosszuegiger vertikaler Abstand zwischen Elementen
    SP_HEADER_H_INNER = 70  # Platz oben fuer SubProcess-Header

    for sp in sp_defs:
        sp_left = sp_x[sp["id"]]
        sp_top = sp_y[sp["id"]]
        sp_w = sp_dims[sp["id"]][0]
        sp_steps = sp["steps"]
        # Steps horizontal zentriert
        step_left = sp_left + (sp_w - INNER_STEP_W) // 2
        # Gateway-Position: rechts neben dem Step (nicht darunter, damit es nicht ueberlappt)
        gw_left = step_left + INNER_STEP_W + 30  # rechts neben dem Step, mit Gap

        inner_y_cursor = sp_top + SP_HEADER_H_INNER
        # Map step_id -> y_center
        y_inner: dict = {}

        for i, step in enumerate(sp_steps):
            # Step-DI-Shape
            parts.append(_shape_bounds(
                f"step_{step.id}", step_left, inner_y_cursor, INNER_STEP_W, INNER_STEP_H
            ))
            y_inner[step.id] = inner_y_cursor + INNER_STEP_H // 2
            inner_y_cursor += INNER_STEP_H + INNER_GAP

            # Gateway-DI-Shape (falls Rules) - rechts neben dem Step
            if step.rules:
                gw_id = f"gw_{step.id}"
                gw_y = inner_y_cursor - INNER_GAP + (INNER_STEP_H - INNER_GW) // 2  # auf Step-Hoehe zentriert
                parts.append(_shape_bounds(
                    gw_id, gw_left, gw_y, INNER_GW, INNER_GW
                ))
                y_inner[gw_id] = gw_y + INNER_GW // 2

        # Inner-Edges (waypoints) - saubere Linien ohne Ueberschneidung
        for i, step in enumerate(sp_steps):
            if step.rules:
                gw = f"gw_{step.id}"
                # Step -> Gateway: horizontal nach rechts
                y_step_mid = y_inner[step.id]
                y_gw_mid = y_inner[gw]
                x_step_right = step_left + INNER_STEP_W
                x_gw_left = gw_left
                parts.append(
                    f'      <bpmndi:BPMNEdge id="inner_step_{step.id}_to_gw_di" bpmnElement="inner_step_{step.id}_to_gw">\n'
                    f'        <di:waypoint x="{x_step_right}" y="{y_step_mid}" />\n'
                    f'        <di:waypoint x="{x_gw_left}" y="{y_gw_mid}" />\n'
                    f'      </bpmndi:BPMNEdge>'
                )
                # Gateway -> Default-Target: vom Gateway nach unten-links zum naechsten Step
                default_target = step.next_step_id
                if default_target and default_target in [s.id for s in sp_steps]:
                    next_s = next(s for s in sp_steps if s.id == default_target)
                    x_gw_right = gw_left + INNER_GW
                    y_next_top = y_inner[next_s.id] - INNER_STEP_H // 2
                    parts.append(
                        f'      <bpmndi:BPMNEdge id="inner_gw_{step.id}_default_di" bpmnElement="inner_gw_{step.id}_default">\n'
                        f'        <di:waypoint x="{x_gw_right}" y="{y_gw_mid}" />\n'
                        f'        <di:waypoint x="{step_left + INNER_STEP_W // 2}" y="{y_next_top}" />\n'
                        f'      </bpmndi:BPMNEdge>'
                    )
            elif i + 1 < len(sp_steps):
                # Linearer Inner-Edge zum naechsten Step
                next_s = sp_steps[i + 1]
                y_step_bottom = y_inner[step.id] + INNER_STEP_H // 2
                y_next_top = y_inner[next_s.id] - INNER_STEP_H // 2
                parts.append(
                    f'      <bpmndi:BPMNEdge id="inner_step_{step.id}_di" bpmnElement="inner_step_{step.id}">\n'
                    f'        <di:waypoint x="{step_left + INNER_STEP_W // 2}" y="{y_step_bottom}" />\n'
                    f'        <di:waypoint x="{step_left + INNER_STEP_W // 2}" y="{y_next_top}" />\n'
                    f'      </bpmndi:BPMNEdge>'
                )

    # === Top-Level-Edges (waypoints) ===
    def _edge_h(eid: str, src: str, tgt: str, src_x: int, tgt_x: int, y: int) -> str:
        return (
            f'      <bpmndi:BPMNEdge id="{eid}_di" bpmnElement="{eid}">\n'
            f'        <di:waypoint x="{src_x}" y="{y}" />\n'
            f'        <di:waypoint x="{tgt_x}" y="{y}" />\n'
            f'      </bpmndi:BPMNEdge>'
        )

    if sp_defs:
        sp0 = sp_defs[0]
        # Start -> sp1: alle SubProcesses sind zentriert auf Y_CENTER, also geht der Edge auf Y_CENTER
        sp0_h = sp_dims[sp0["id"]][1]
        sp0_mid_y = Y_CENTER
        # Wenn sp0 klein ist, geht der Edge in einer Stufe zur SubProcess-Mitte (auch Y_CENTER)
        # (jetzt sind alle zentriert, also keine Stufen mehr noetig - einheitliche Linie)
        parts.append(_edge_h("flow_start_to_sp1", start_id, sp0["id"],
                              X_START + 50, sp_x[sp0["id"]], Y_CENTER))
        # sp -> sp (alle auf Y_CENTER, horizontal)
        for i in range(len(sp_defs) - 1):
            src_sp = sp_defs[i]
            tgt_sp = sp_defs[i + 1]
            src_x_right = sp_x[src_sp["id"]] + SP_W
            tgt_x_left = sp_x[tgt_sp["id"]]
            parts.append(_edge_h(
                f"flow_sp{i+1}_to_sp{i+2}", src_sp["id"], tgt_sp["id"],
                src_x_right, tgt_x_left, Y_CENTER
            ))
        # last sp -> end
        last_sp = sp_defs[-1]
        parts.append(_edge_h(
            "flow_sp_last_to_end", last_sp["id"], end_id,
            sp_x[last_sp["id"]] + SP_W, x_end, Y_CENTER
        ))

    parts.append('    </bpmndi:BPMNPlane>')
    parts.append('  </bpmndi:BPMNDiagram>')
    parts.append('</bpmn:definitions>')
    return "\n".join(parts)


def _flow_label(step) -> str:
    """Erzeugt ein kurzes Label fuer den SequenceFlow (z.B. 'agent=CIO, action=move_status')."""
    return f"→ {step.agent}: {step.action}"[:60]


def _generate_uml(sop: SOP) -> str:
    """Generiert ein UML-Sequenzdiagramm (PlantUML) aus einer SOP-Definition.

    Participants: Board-Phasen (Triage, GO, In Progress, Review, Block, Done)
    Messages: Status-Wechsel zwischen Phasen (mit Agent + Delay)
    alt/else: zeigt alternative Pfade (z.B. tester_reject -> Fix-Loop)

    Mapping action_type -> Ziel-Phase:
      - approve_triage          -> "GO"
      - assign_worker / start_work / move_status(in_progress) -> "In Progress"
      - submit_review            -> "Review"
      - tester_approve           -> "Block"
      - tester_reject            -> "In Progress" (Fix-Loop, sichtbar als alt-Pfad)
      - cio_final_approve        -> "Done"
      - cio_final_reject         -> "In Progress"
      - block (in Triage)        -> "Rueckfragen" (CIO-Frage an User/CEO)
      - block (sonst)            -> "Block"
      - complete                 -> "Done"

    User-Initial-Trigger: User -> Triage (Task wird angelegt)
    """
    # Mapping: action_type -> Phase-Key (default)
    ACTION_TO_PHASE = {
        "approve_triage": "todo",
        "start_work": "in_progress",
        "submit_review": "review",
        "tester_approve": "block",
        "tester_reject": "in_progress",
        "cio_final_approve": "done",
        "cio_final_reject": "in_progress",
        "block": "block",  # wird in Triage ueberschrieben -> rueckfragen
        "complete": "done",
    }

    # Mapping: Phase-Key -> Display-Name (fuer Participant-Namen)
    PHASE_DISPLAY = {
        "triage": "Triage",
        "todo": "GO",
        "in_progress": "In Progress",
        "review": "Review",
        "block": "Block",
        "rueckfragen": "Rueckfragen",
        "done": "Done",
    }

    # Mapping: Phase-Key -> PlantUML-Alias (kurz, ohne Sonderzeichen)
    PHASE_ALIAS = {
        "triage": "Triage",
        "todo": "GO",
        "in_progress": "InProgress",
        "review": "Review",
        "block": "Block",
        "rueckfragen": "Rueckfragen",
        "done": "Done",
    }

    def _action_to_phase(action_type: str, step) -> str:
        """Mapping Action -> Phase, mit Sonderfall 'block' in Triage."""
        if action_type == "block" and step.phase == "Triage":
            return "rueckfragen"
        return ACTION_TO_PHASE.get(action_type, "todo")

    sorted_steps = sorted(sop.steps, key=lambda s: s.step_order)
    transitions = []  # (from_phase, to_phase, agent, action, delay_s, step_name, expected_result)

    for i, step in enumerate(sorted_steps):
        # Skip Steps ohne Action (z.B. End-State "Done" mit noop)
        if step.action in ("noop", None, ""):
            continue

        # Sammle alle alternativen Ziele aus Rules (fuer alt/else-Pfade)
        # Prioritaet: 1. erste Rule, 2. action_params, 3. action_type
        primary_target = None
        alt_targets = []  # (target_phase, condition_text, action_type)

        # 1) Aus Rules: Erste matchende Rule = primary, weitere = alternativen
        if step.rules:
            for ridx, rule in enumerate(step.rules):
                if rule.action_type in ("move_status", "approve_triage", "start_work",
                                          "submit_review", "tester_approve", "tester_reject",
                                          "cio_final_approve", "cio_final_reject", "block", "complete"):
                    target = _action_to_phase(rule.action_type, step)
                    cond = f"{rule.condition_field} {rule.condition_operator} {rule.condition_value}"
                    if ridx == 0 and primary_target is None:
                        primary_target = target
                    else:
                        alt_targets.append((target, cond, rule.action_type))

        # 2) Aus action_params.status (move_status)
        if not primary_target and step.action == "move_status":
            primary_target = step.action_params.get("status") if isinstance(step.action_params, dict) else None

        # 3) Aus action_type (Standard-Mapping)
        if not primary_target and step.action in ACTION_TO_PHASE:
            primary_target = _action_to_phase(step.action, step)

        # Quell-Phase: vorheriger Step-Ziel (oder erster Step = "triage")
        if i == 0:
            from_phase = "triage"
        else:
            from_phase = transitions[-1][1] if transitions else "triage"

        if primary_target:
            transitions.append((
                from_phase, primary_target,
                step.agent, step.action, step.delay_s,
                step.name, step.expected_result or "",
                alt_targets,  # Liste alternativer Ziele fuer alt/else
            ))

    # Generiere PlantUML
    lines = [
        "@startuml",
        f"title SOP Sequenzdiagramm: {sop.name}",
        "",
        "skinparam maxMessageSize 200",
        "skinparam BoxPadding 6",
        "skinparam NoteBackgroundColor #FFFACD",
        "",
        "actor \"User\" as User",
    ]

    # Participants: nur die Phasen, die in der SOP vorkommen (in kanonischer Reihenfolge)
    phase_order = ["triage", "todo", "in_progress", "review", "block", "rueckfragen", "done"]
    used_phases = set()
    for entry in transitions:
        f, t, *_ = entry
        used_phases.add(f)
        used_phases.add(t)
        for (alt_target, *_) in entry[6]:  # alt_targets
            used_phases.add(alt_target)

    for pkey in phase_order:
        if pkey in used_phases:
            display = PHASE_DISPLAY[pkey]
            alias = PHASE_ALIAS[pkey]
            lines.append(f'participant "{display}" as {alias}')

    lines.append("")

    # Initial-Trigger: User erstellt Task
    lines.append("User -> Triage : neuer Task")
    lines.append("note right of Triage: CIO prueft\\n(Vollstaendigkeit, Konflikte)")

    # Messages: Phase-Übergänge
    for i, (f, t, agent, action, delay_s, step_name, expected, alt_targets) in enumerate(transitions, 1):
        from_alias = PHASE_ALIAS[f]
        to_alias = PHASE_ALIAS[t]

        # Wenn gleiche Phase (kein Wechsel): Skip
        if from_alias == to_alias:
            continue

        # Message-Label (Hauptpfad)
        label = f"{action}"
        if agent and agent != "system":
            label = f"{action} ({agent})"
        if delay_s and delay_s > 0:
            label += f"\\n⏱ {delay_s}s"

        lines.append(f"{from_alias} -> {to_alias} : {label}")

        # Note mit Step-Details (rechts vom Ziel)
        note_lines = []
        if step_name:
            note_lines.append(f"Step {i}: {step_name}")
        if expected:
            note_lines.append(f"Erwartet: {expected[:80]}")
        if note_lines:
            lines.append(f"note right of {to_alias}: {' | '.join(note_lines)}")

        # alt/else-Bloecke fuer alternative Pfade (z.B. tester_reject)
        if alt_targets:
            lines.append("")
            for alt_idx, (alt_target, cond, alt_action) in enumerate(alt_targets):
                alt_alias = PHASE_ALIAS.get(alt_target, alt_target)
                alt_label = f"{alt_action}"
                if agent and agent != "system":
                    alt_label = f"{alt_action} ({agent})"
                if delay_s and delay_s > 0:
                    alt_label += f"\\n⏱ {delay_s}s"
                alt_keyword = "alt" if alt_idx == 0 else "else"
                lines.append(f"{alt_keyword} {cond}")
                # Gestrichelter Rueck-Pfeil fuer Reject-Loop
                lines.append(f"  {from_alias} --> {alt_alias} : {alt_label}")
                # Note zum Fix-Loop
                if alt_action == "tester_reject":
                    lines.append(f"  note right of {alt_alias}: Fix-Loop: Worker muss nachbessern")
                elif alt_action == "cio_final_reject":
                    lines.append(f"  note right of {alt_alias}: Fix-Loop: Worker muss nachbessern")
                elif alt_action == "block" and step.phase == "Triage":
                    lines.append(f"  note right of {alt_alias}: CIO hat Frage an User/CEO")
            lines.append("end")
            lines.append("")

    # End-Marker
    if "done" in used_phases:
        lines.append("")
        lines.append("note over Done: ✅ Task abgeschlossen")

    lines.append("@enduml")
    return "\n".join(lines)


def _xml_escape(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
              .replace('"', "&quot;").replace("'", "&apos;"))


def _truncate(s: str, n: int) -> str:
    if len(s) > n:
        return s[:n-3] + "..."
    return s
