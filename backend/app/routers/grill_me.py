"""Grill-Me Router (User-Direktive 24.06.2026, Grill-Me-Skill).

Endpoints:
  GET    /api/projects/{project_id}/info              - Alle Info-Eintraege
  POST   /api/projects/{project_id}/info              - Eintrag hinzufuegen
  PATCH  /api/projects/{project_id}/info/{entry_id}   - Eintrag aendern
  DELETE /api/projects/{project_id}/info/{entry_id}   - Eintrag loeschen
  POST   /api/agents/grill-me/start                  - Grill-Session starten
  POST   /api/agents/grill-me/{session_id}/answer    - Antwort in Session
  POST   /api/agents/grill-me/{session_id}/create-task - Bulletproof -> Task
"""
from __future__ import annotations

import json
import uuid
import asyncio
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Body
from pydantic import BaseModel, Field
from sqlalchemy import select, func, text
from sqlalchemy.orm import Session

from ..auth import require_auth
from ..db.base import get_db
from ..models import ProjectInfoEntry, Project, Task

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["grill-me-info"])

# === Grill-Me Analyst System Prompt (User-Direktive 24.06.2026) ===
GRILL_ME_SYSTEM_PROMPT = """Du bist der **Grill-Me Analyst**: Ein System-Analyst, der User-Anforderungen durch gezieltes Fragen stellen in eine bulletproof Spezifikation verwandelt.

**Deine Aufgabe (vor jeder Implementierung):**
1. **Identifiziere Luecken:** Suche nach unklaren Anforderungen, fehlenden Randbedingungen (Edge Cases) oder widerspruechlichen Statements in der urspruenglichen Anfrage.
2. **Frage "Warum" und "Was passiert wenn...":** Fordere den Nutzer auf, Szenarien zu klaeren (z.B. "Was soll passieren, wenn die API keine Daten liefert?", "Welche spezifischen Fehlermeldungen sollen dem User angezeigt werden?").
3. **Stress-Test der Logik:** Erstelle gezielte Fragen, um die logische Konsistenz des Features zu pruefen. Wenn eine Anforderung drei verschiedene Wege zur Loesung haben koennte, fordere den Nutzer auf, den Weg explizit festzulegen.
4. **Finalisiere das PRD:** Erst wenn du alle Luecken geschlossen hast und die Anforderungen "bulletproof" sind (d.h., ein Agent sie ohne Rueckfragen umsetzen koennte), darfst du in die Implementierungsphase uebergehen.

**Ziel:** Du wechselst vom Modus "Code-Interpreter" in den Modus "System-Analyst". Dein Ziel ist es, eine Spezifikation so praezise zu machen, dass keinerlei Interpretationsspielraum mehr fuer dich oder andere Agenten bleibt.

**Wichtige Regeln:**
- Du bist KEIN Code-Writer. Du schreibst NUR Spezifikationen.
- Du stellst immer hoechstens 5 Fragen pro Runde (sonst wird der User ueberfordert).
- Du priorisierst die kritischsten Luecken zuerst (Sicherheit > Datenintegritaet > UX > Optimierung).
- Du nutzt das vorhandene Informationspaket, um keine redundanten Fragen zu stellen.
- Wenn das PRD bulletproof ist, signalisierst du `"status": "ready"` mit `"title"`, `"description"`, `"acceptance_criteria"`.

**Output-Format (JSON):**
{
  "status": "grilling" | "ready",
  "questions": [
    {"id": "q1", "category": "edge-case|logic|ux|security|integration", "question": "...", "context": "...", "priority": "high|medium|low"}
  ],
  "gaps_identified": ["..."],
  "progress": 0-100,
  "title": "...",  // nur wenn status=ready
  "description": "...",  // nur wenn status=ready
  "acceptance_criteria": ["..."],  // nur wenn status=ready
  "recommended_component": "...",  // Pipeline|Frontend|NotebookLM|null
  "info_to_record": [
    {"info_type": "architecture|conventions|...", "key": "...", "value": "...", "source": "grill-me"}
  ]
}
"""


# === Pydantic Schemas ===
class ProjectInfoEntryIn(BaseModel):
    info_type: str = Field(..., max_length=32)
    info_key: str = Field(..., max_length=100)
    info_value: str
    source: str = "manual"
    confidence: int = 100
    updated_by: Optional[str] = None


class ProjectInfoEntryPatch(BaseModel):
    info_type: Optional[str] = None
    info_key: Optional[str] = None
    info_value: Optional[str] = None
    source: Optional[str] = None
    confidence: Optional[int] = None


class GrillStartIn(BaseModel):
    project_id: str
    raw_request: str
    context: Optional[Dict[str, Any]] = None


class GrillAnswerIn(BaseModel):
    answers: Dict[str, str]  # {"q1": "Antwort", ...}


class GrillCreateTaskIn(BaseModel):
    title: str
    description: str
    acceptance_criteria: List[str] = []
    recommended_component: Optional[str] = None
    priority: int = 50


# === In-Memory Sessions (fuer MVP) ===
_grill_sessions: Dict[str, Dict[str, Any]] = {}


# === Info-Endpoints ===
@router.get("/project-info/{project_id}")
async def list_project_info(
    project_id: str,
    info_type: Optional[str] = Query(None, description="Filter by info_type"),
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    """Liefert alle Info-Eintraege fuer ein Projekt."""
    q = select(ProjectInfoEntry).where(ProjectInfoEntry.project_id == project_id)
    if info_type:
        q = q.where(ProjectInfoEntry.info_type == info_type)
    q = q.order_by(ProjectInfoEntry.info_type, ProjectInfoEntry.info_key)
    rows = db.execute(q).scalars().all()
    return [
        {
            "id": r.id,
            "project_id": r.project_id,
            "info_type": r.info_type,
            "info_key": r.info_key,
            "info_value": r.info_value,
            "source": r.source,
            "confidence": r.confidence,
            "updated_by": r.updated_by,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        }
        for r in rows
    ]


@router.post("/project-info/{project_id}")
async def add_project_info(
    project_id: str,
    entry: ProjectInfoEntryIn,
    db: Session = Depends(get_db),
    user: str = Depends(require_auth),
):
    """Neuen Info-Eintrag hinzufuegen (idempotent: gleicher key -> update)."""
    # Pruefe Projekt existiert
    p = db.get(Project, project_id)
    if not p:
        raise HTTPException(404, "Project not found")

    existing = db.execute(
        select(ProjectInfoEntry).where(
            ProjectInfoEntry.project_id == project_id,
            ProjectInfoEntry.info_type == entry.info_type,
            ProjectInfoEntry.info_key == entry.info_key,
        )
    ).scalar_one_or_none()

    if existing:
        existing.info_value = entry.info_value
        existing.source = entry.source
        existing.confidence = entry.confidence
        existing.updated_by = entry.updated_by or user
        existing.updated_at = datetime.now()
        db.commit()
        return {"updated": True, "id": existing.id}

    e = ProjectInfoEntry(
        project_id=project_id,
        info_type=entry.info_type,
        info_key=entry.info_key,
        info_value=entry.info_value,
        source=entry.source,
        confidence=entry.confidence,
        updated_by=entry.updated_by or user,
    )
    db.add(e)
    db.commit()
    db.refresh(e)
    return {"created": True, "id": e.id}


@router.patch("/project-info/{project_id}/{entry_id}")
async def patch_project_info(
    project_id: str,
    entry_id: int,
    patch: ProjectInfoEntryPatch,
    db: Session = Depends(get_db),
    user: str = Depends(require_auth),
):
    """Info-Eintrag aendern."""
    e = db.get(ProjectInfoEntry, entry_id)
    if not e or e.project_id != project_id:
        raise HTTPException(404, "Entry not found")
    for k, v in patch.dict(exclude_none=True).items():
        setattr(e, k, v)
    e.updated_by = user
    e.updated_at = datetime.now()
    db.commit()
    return {"ok": True}


@router.delete("/project-info/{project_id}/{entry_id}")
async def delete_project_info(
    project_id: str,
    entry_id: int,
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    """Info-Eintrag loeschen."""
    e = db.get(ProjectInfoEntry, entry_id)
    if not e or e.project_id != project_id:
        raise HTTPException(404, "Entry not found")
    db.delete(e)
    db.commit()
    return {"ok": True}


# === Grill-Me Session Endpoints ===
async def _call_grill_analyst(
    project_name: str,
    project_info: List[dict],
    raw_request: str,
    history: List[dict],
    user_answers: Optional[Dict[str, str]] = None,
) -> dict:
    """Ruft den Grill-Me Analyst (LLM) auf."""
    from ..services.llm_service import chat_completion

    info_summary = "\n".join(
        f"- [{e['info_type']}] {e['info_key']}: {e['info_value']} (source={e['source']})"
        for e in project_info[:50]
    ) or "(noch keine Infos vorhanden)"

    history_summary = "\n".join(
        f"Q: {h.get('question','?')}\nA: {h.get('answer','(keine)')}"
        for h in history[-5:]
    )

    user_prompt = f"""**Projekt:** {project_name}

**Informationspaket (was wir bereits wissen):**
{info_summary}

**Vorherige Fragen/Antworten:**
{history_summary or '(noch keine)'}

**Neue Antworten vom User:**
{json.dumps(user_answers or {}, ensure_ascii=False, indent=2)}

**User-Anfrage:**
{raw_request}

Analysiere die Anfrage und stelle die naechsten kritischen Fragen. Wenn das PRD bulletproof ist, setze status='ready' mit title/description/acceptance_criteria.
"""

    try:
        result = await chat_completion(
            messages=[
                {"role": "system", "content": GRILL_ME_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            model="minimax-m3",
            provider="minimax-direct",
            temperature=0.3,
            max_tokens=2000,
            response_format={"type": "json_object"},
        )
        content = result.get("content", "{}")
        # JSON-Parse robust
        from ..utils.json_repair import safe_json_loads
        parsed = safe_json_loads(content)
        return parsed
    except Exception as e:
        log.exception("Grill-Me LLM call failed: %s", e)
        return {
            "status": "grilling",
            "questions": [{
                "id": "q_fallback",
                "category": "logic",
                "question": f"Fehler beim Aufruf des Grill-Analyst: {e}. Bitte ueberpruefe die Verbindung.",
                "priority": "high",
            }],
            "gaps_identified": ["LLM-Fehler"],
            "progress": 0,
        }


@router.post("/agents/grill-me/start")
async def grill_me_start(
    payload: GrillStartIn,
    db: Session = Depends(get_db),
    user: str = Depends(require_auth),
):
    """Startet eine Grill-Session fuer ein Projekt."""
    p = db.get(Project, payload.project_id)
    if not p:
        raise HTTPException(404, "Project not found")

    # Lade Info-Paket
    info_rows = db.execute(
        select(ProjectInfoEntry).where(ProjectInfoEntry.project_id == payload.project_id)
    ).scalars().all()
    project_info = [
        {"info_type": r.info_type, "info_key": r.info_key, "info_value": r.info_value,
         "source": r.source, "confidence": r.confidence}
        for r in info_rows
    ]

    # Lade Components
    comp_rows = db.execute(text("""
        SELECT slug, name, component_type, description, container_port
        FROM project_components WHERE project_id = :pid
        ORDER BY sort_order
    """), {"pid": payload.project_id}).fetchall()
    components = [
        {"slug": r[0], "name": r[1], "type": r[2], "description": r[3], "port": r[4]}
        for r in comp_rows
    ]

    # LLM Call
    result = await _call_grill_analyst(
        project_name=p.name,
        project_info=project_info,
        raw_request=payload.raw_request,
        history=[],
        user_answers=None,
    )

    # Speichere Session
    sid = str(uuid.uuid4())[:12]
    _grill_sessions[sid] = {
        "session_id": sid,
        "project_id": payload.project_id,
        "user": user,
        "raw_request": payload.raw_request,
        "history": [],
        "result": result,
        "created_at": datetime.now().isoformat(),
    }
    return {
        "session_id": sid,
        "project_id": payload.project_id,
        "project_name": p.name,
        "components": components,
        "info_package_size": len(project_info),
        "result": result,
    }


@router.post("/agents/grill-me/{session_id}/answer")
async def grill_me_answer(
    session_id: str,
    payload: GrillAnswerIn,
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    """Antwort in eine Grill-Session einspeisen, naechste Runde."""
    sess = _grill_sessions.get(session_id)
    if not sess:
        raise HTTPException(404, "Session not found")

    # History updaten
    existing_qs = {q["id"]: q["question"] for q in sess["result"].get("questions", [])}
    for qid, answer in payload.answers.items():
        sess["history"].append({
            "question": existing_qs.get(qid, qid),
            "answer": answer,
        })

    # Projekt + Info neu laden
    p = db.get(Project, sess["project_id"])
    info_rows = db.execute(
        select(ProjectInfoEntry).where(ProjectInfoEntry.project_id == sess["project_id"])
    ).scalars().all()
    project_info = [
        {"info_type": r.info_type, "info_key": r.info_key, "info_value": r.info_value}
        for r in info_rows
    ]

    # Naechste LLM-Runde
    new_result = await _call_grill_analyst(
        project_name=p.name if p else "Unknown",
        project_info=project_info,
        raw_request=sess["raw_request"],
        history=sess["history"],
        user_answers=payload.answers,
    )
    sess["result"] = new_result

    # Auto-Record neue Insights ins Info-Paket
    for info in new_result.get("info_to_record", []):
        try:
            existing = db.execute(
                select(ProjectInfoEntry).where(
                    ProjectInfoEntry.project_id == sess["project_id"],
                    ProjectInfoEntry.info_type == info.get("info_type", "context"),
                    ProjectInfoEntry.info_key == info["key"],
                )
            ).scalar_one_or_none()
            if existing:
                existing.info_value = info["value"]
                existing.source = "grill-me"
            else:
                db.add(ProjectInfoEntry(
                    project_id=sess["project_id"],
                    info_type=info.get("info_type", "context"),
                    info_key=info["key"],
                    info_value=info["value"],
                    source="grill-me",
                    confidence=80,
                ))
        except Exception as e:
            log.warning("Could not record info entry: %s", e)
    db.commit()

    return {
        "session_id": session_id,
        "result": new_result,
        "history_count": len(sess["history"]),
    }


@router.post("/agents/grill-me/{session_id}/create-task")
async def grill_me_create_task(
    session_id: str,
    payload: GrillCreateTaskIn,
    db: Session = Depends(get_db),
    user: str = Depends(require_auth),
):
    """Erstellt einen Task aus einem bulletproof PRD."""
    sess = _grill_sessions.get(session_id)
    if not sess:
        raise HTTPException(404, "Session not found")
    res = sess["result"]
    if res.get("status") != "ready":
        raise HTTPException(400, "PRD not bulletproof yet (status != 'ready')")

    p = db.get(Project, sess["project_id"])
    if not p:
        raise HTTPException(404, "Project not found")

    # Erstelle Task (analog POST /api/kanban/tasks)
    new_id = "task_" + uuid.uuid4().hex[:12]
    description_body = payload.description
    if payload.acceptance_criteria:
        description_body += "\n\n**Acceptance Criteria:**\n" + "\n".join(
            f"- {ac}" for ac in payload.acceptance_criteria
        )
    if payload.recommended_component:
        description_body += f"\n\n**Empfohlene Component:** {payload.recommended_component}"

    db.add(Task(
        id=new_id,
        project_id=sess["project_id"],
        title=payload.title,
        description=description_body,
        status="todo",
        priority=payload.priority,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    ))
    db.commit()

    # Session clean up
    del _grill_sessions[session_id]

    return {
        "created": True,
        "task_id": new_id,
        "project_id": sess["project_id"],
        "title": payload.title,
    }


@router.get("/agents/grill-me/{session_id}")
async def grill_me_get_session(
    session_id: str,
    _user: str = Depends(require_auth),
):
    """Liefert aktuellen Session-Zustand."""
    sess = _grill_sessions.get(session_id)
    if not sess:
        raise HTTPException(404, "Session not found")
    return sess


# === VoiceComunicatior Integration (User-Direktive 25.06.2026) ===
import os
import httpx

VOICE_COMMUNICATOR_URL = os.getenv("VOICE_COMMUNICATOR_URL", "http://127.0.0.1:8005")
VOICE_COMMUNICATOR_API_KEY = os.getenv("VOICE_COMMUNICATOR_API_KEY", "voice-communicator-dev-key-2026")


@router.get("/agents/grill-me/voice-status")
async def grill_me_voice_status(_user: str = Depends(require_auth)):
    """Prueft ob der VoiceComunicatior-Service erreichbar ist.

    Wird vom Grill-Me Analyst und vom Frontend genutzt, um zu wissen,
    ob fluechtige Sprach-Konversation moeglich ist.
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(
                f"{VOICE_COMMUNICATOR_URL}/health",
                headers={"X-API-Key": VOICE_COMMUNICATOR_API_KEY},
            )
            r.raise_for_status()
            data = r.json()
            return {
                "voice_communicator_available": True,
                "voice_communicator_url": VOICE_COMMUNICATOR_URL,
                "service_status": data.get("status"),
                "engines": data.get("components", {}),
                "voice_session_recommended": True,
            }
    except Exception as e:
        log.info("VoiceComunicatior nicht erreichbar: %s", e)
        return {
            "voice_communicator_available": False,
            "voice_communicator_url": VOICE_COMMUNICATOR_URL,
            "error": str(e),
            "voice_session_recommended": False,
        }


@router.post("/agents/grill-me/{session_id}/voice-talk")
async def grill_me_voice_talk_proxy(
    session_id: str,
    audio: "UploadFile",  # type: ignore[name-defined]
    _user: str = Depends(require_auth),
):
    """Proxy: Leitet User-Audio an VoiceComunicatior weiter.

    Convenience-Endpoint, damit das Frontend nicht zwei API-Keys verwalten muss.
    """
    try:
        from fastapi import UploadFile  # noqa: F401
    except ImportError:
        pass

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            files = {"audio": (audio.filename or "audio.wav", await audio.read(), audio.content_type or "audio/wav")}
            r = await client.post(
                f"{VOICE_COMMUNICATOR_URL}/v1/grill-me/{session_id}/talk",
                headers={"X-API-Key": VOICE_COMMUNICATOR_API_KEY},
                files=files,
            )
            r.raise_for_status()
            return r.json()
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"VoiceComunicatior-Fehler: {e.response.text[:300]}",
        ) from e
    except Exception as e:
        log.exception("Voice-Talk-Proxy fehlgeschlagen")
        raise HTTPException(502, f"Voice-Talk fehlgeschlagen: {e}") from e
