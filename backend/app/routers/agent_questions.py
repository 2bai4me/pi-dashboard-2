"""AgentQuestion-Router: User <-> Agent Interaktionstool.

Ermoeglicht Agenten jeder Ebene (C-Level, Worker, Subagent), Fragen an
den User zu stellen und Antworten, Dateien oder Bilder zu erhalten.

Endpoints:
  POST   /api/tools/agent-questions/                  (Agent: Frage erstellen)
  GET    /api/tools/agent-questions/                  (User: Liste, mit Filtern)
  GET    /api/tools/agent-questions/wait              (User: Long-Polling auf neue/aktualisierte Fragen)
  GET    /api/tools/agent-questions/{id}              (Detail)
  POST   /api/tools/agent-questions/{id}/answer       (User: Antworten)
  POST   /api/tools/agent-questions/{id}/cancel       (Agent/Admin: Stornieren)
  POST   /api/tools/agent-questions/{id}/seen         (User: als gesehen markieren)
  POST   /api/tools/agent-questions/{id}/attachments  (Agent oder User: Datei hochladen)
  GET    /api/tools/agent-questions/{id}/attachments/{att_id}  (Datei herunterladen)
  GET    /api/tools/agent-questions/pending/count     (Anzahl offener Fragen, fuer Badge)
  POST   /api/tools/agent-questions/{id}/attach-image (Komfort: Bild direkt aus Base64)

User-Direktive 17.06.2026.
"""
from __future__ import annotations

import base64
import json
import logging
import secrets
import time
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select, func as sqlfunc, or_, and_
from sqlalchemy.orm import Session

from ..auth import require_auth
from ..db.base import get_db
from ..models.agent_question import (
    AgentQuestion, AgentQuestionAttachment, _gen_id as _gen_qid,
)
from ..schemas.agent_question import (
    AgentQuestionCreate, AgentQuestionAnswer,
    AgentQuestionRead, AgentQuestionDetail, AgentQuestionList,
)

logger = logging.getLogger("pi-dashboard-2.tools")

router = APIRouter(prefix="/api/tools/agent-questions", tags=["tools"])


# === Upload-Verzeichnis ===
UPLOAD_DIR = Path(__file__).resolve().parent.parent.parent / "database" / "agent_question_attachments"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


# === Hilfsfunktionen ===

def _to_read(q: AgentQuestion) -> dict:
    """Konvertiert ein AgentQuestion-Model in ein Read-Dict."""
    return q.to_dict(include_attachments=False)


def _to_detail(q: AgentQuestion) -> dict:
    """Konvertiert ein AgentQuestion-Model in ein Detail-Dict (mit Attachments)."""
    return q.to_dict(include_attachments=True)


# === Endpoints ===

@router.post("/")
async def create_question(
    body: AgentQuestionCreate,
    db: Session = Depends(get_db),
    user: str = Depends(require_auth),
) -> dict:
    """Agent erstellt eine neue Frage an den User.

    Blockierend (default) oder non-blocking (Frage erscheint, Agent laeuft
    separat weiter, Antwort wird spaeter per Long-Polling abgeholt).
    """
    q = AgentQuestion(
        id=_gen_qid(),
        agent_id=body.agent_id,
        agent_level=body.agent_level,
        agent_label=body.agent_label,
        question_type=body.question_type,
        title=body.title,
        question=body.question,
        description=body.description,
        recommendation=body.recommendation,
        options=body.options or [],
        options_config=json.dumps(body.options_config or {}, ensure_ascii=False) if body.options_config else None,
        context=body.context or {},
        priority=body.priority,
        expires_at=body.expires_at,
        status="pending",
    )
    db.add(q)
    db.commit()
    db.refresh(q)

    # Wenn die Frage an einen Task gebunden ist, setze den Task-Status auf "rueckfrage"
    # und speichere die Question-ID in der Task-Meta (fuer spaeteres Tracking).
    ctx = body.context or {}
    task_id_ctx = ctx.get("task_id")
    if task_id_ctx:
        try:
            from ..models.task import Task
            t = db.get(Task, task_id_ctx)
            if t and t.status not in ("done", "cancelled"):
                old_status = t.status
                if t.status != "rueckfrage":
                    t.status = "rueckfrage"
                # Meta erweitern (z.B. {"input_required": true, "input_question_id": "..."})
                try:
                    meta = t.meta if isinstance(t.meta, dict) else {}
                except Exception:
                    meta = {}
                meta = dict(meta or {})
                meta["input_required"] = True
                meta["input_question_id"] = q.id
                meta["input_from_agent"] = body.agent_id
                meta["input_from_label"] = body.agent_label or body.agent_id
                meta["input_created_at"] = datetime.utcnow().isoformat()
                t.meta = meta
                db.commit()
                # Audit-Eintrag in TaskHistory
                try:
                    from ..models.history import TaskHistory
                    th = TaskHistory(
                        task_id=t.id,
                        event="input_required",
                        agent=body.agent_id,
                        details={"question_id": q.id, "title": body.title, "old_status": old_status, "new_status": "rueckfrage"},
                    )
                    db.add(th)
                    db.commit()
                except Exception as e:
                    logger.warning(f"TaskHistory konnte nicht erstellt werden: {e}")
        except Exception as e:
            logger.warning(f"Task-Status-Update fehlgeschlagen: {e}")

    # SSE-Event veroeffentlichen (Multi-Process-safe)
    try:
        from .. import events
        await events.publish_event(
            project_id="__tools__",  # globaler Channel fuer Tools-Tab
            event_type="agent_question_created",
            data={
                "question_id": q.id,
                "agent_id": q.agent_id,
                "agent_level": q.agent_level,
                "title": q.title,
                "priority": q.priority,
                "question_type": q.question_type,
            },
        )
    except Exception as e:
        logger.warning(f"publish_event fehlgeschlagen (nicht kritisch): {e}")

    logger.info(
        f"Frage erstellt: id={q.id} agent={q.agent_id} level={q.agent_level} "
        f"type={q.question_type} priority={q.priority}"
    )
    return _to_read(q)


@router.get("/")
async def list_questions(
    status: Optional[str] = Query(None, description="Filter: pending|answered|cancelled|expired"),
    agent_id: Optional[str] = Query(None),
    agent_level: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
    unseen_only: bool = Query(False, description="Nur ungesehene"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    user: str = Depends(require_auth),
) -> dict:
    """Liste Fragen (mit Filtern). Standard: neueste zuerst."""
    stmt = select(AgentQuestion).order_by(AgentQuestion.created_at.desc())

    if status:
        if status == "open":
            stmt = stmt.where(AgentQuestion.status == "pending")
        else:
            stmt = stmt.where(AgentQuestion.status == status)
    if agent_id:
        stmt = stmt.where(AgentQuestion.agent_id == agent_id)
    if agent_level:
        stmt = stmt.where(AgentQuestion.agent_level == agent_level)
    if priority:
        stmt = stmt.where(AgentQuestion.priority == priority)
    if unseen_only:
        stmt = stmt.where(AgentQuestion.seen_at.is_(None), AgentQuestion.status == "pending")

    # Total-Count (gleiche Filter, ohne limit/offset)
    count_stmt = select(sqlfunc.count(AgentQuestion.id))
    if status:
        if status == "open":
            count_stmt = count_stmt.where(AgentQuestion.status == "pending")
        else:
            count_stmt = count_stmt.where(AgentQuestion.status == status)
    if agent_id:
        count_stmt = count_stmt.where(AgentQuestion.agent_id == agent_id)
    if agent_level:
        count_stmt = count_stmt.where(AgentQuestion.agent_level == agent_level)
    if priority:
        count_stmt = count_stmt.where(AgentQuestion.priority == priority)
    if unseen_only:
        count_stmt = count_stmt.where(AgentQuestion.seen_at.is_(None), AgentQuestion.status == "pending")
    total = db.execute(count_stmt).scalar() or 0

    # Pending + Unseen Counts (global, fuer Badge)
    pending_count = db.execute(
        select(sqlfunc.count(AgentQuestion.id)).where(AgentQuestion.status == "pending")
    ).scalar() or 0
    unseen_count = db.execute(
        select(sqlfunc.count(AgentQuestion.id)).where(
            AgentQuestion.seen_at.is_(None),
            AgentQuestion.status == "pending",
        )
    ).scalar() or 0

    stmt = stmt.limit(limit).offset(offset)
    items = list(db.execute(stmt).scalars())
    return {
        "items": [_to_read(q) for q in items],
        "total": int(total),
        "pending_count": int(pending_count),
        "unseen_count": int(unseen_count),
    }


@router.get("/pending/count")
async def pending_count(
    db: Session = Depends(get_db),
    user: str = Depends(require_auth),
) -> dict:
    """Schneller Endpoint fuer Notification-Badge: Anzahl offener + ungesehener Fragen."""
    pending = db.execute(
        select(sqlfunc.count(AgentQuestion.id)).where(AgentQuestion.status == "pending")
    ).scalar() or 0
    unseen = db.execute(
        select(sqlfunc.count(AgentQuestion.id)).where(
            AgentQuestion.seen_at.is_(None),
            AgentQuestion.status == "pending",
        )
    ).scalar() or 0
    return {"pending": int(pending), "unseen": int(unseen)}


@router.get("/wait")
async def wait_for_updates(
    since_id: int = Query(0, ge=0, description="Letzte gesehene updated_at-Order-ID (vereinfacht: created_at order)"),
    timeout: float = Query(30.0, ge=1.0, le=120.0, description="Long-Polling-Timeout in Sekunden"),
    status: Optional[str] = Query(None, description="Nur Updates mit bestimmtem Status"),
    db: Session = Depends(get_db),
    user: str = Depends(require_auth),
) -> dict:
    """Long-Polling-Endpoint: wartet bis neue oder aktualisierte Fragen verfuegbar sind.

    Prueft alle 0.5s, ob eine Frage mit created_at nach since_id (vereinfacht:
    Order-by-id) existiert. Wenn ja, returnt sie sofort. Sonst wartet bis timeout.

    Sinnvoll fuer: Subagent wartet auf User-Antwort, ohne aktiv zu pollen.
    """
    # Vereinfachung: since_id entspricht der Anzahl bereits abgerufener Fragen
    # (id-Werte sind nicht-sequenziell, aber wir koennen ueber COUNT approximieren)
    # Bessere Loesung: eigene Watermark in DB. Hier pragmatisch:
    # Wir liefern alles, was created_at > jetzt - X sek. ist.
    start = time.time()
    deadline = start + timeout

    while time.time() < deadline:
        # Hole alle pending Fragen (vereinfacht: nach created_at desc, count > since_id)
        stmt = select(AgentQuestion)
        if status:
            stmt = stmt.where(AgentQuestion.status == status)
        elif status is None:
            # Default: nur nicht-cancelled
            stmt = stmt.where(AgentQuestion.status.in_(["pending", "answered"]))
        stmt = stmt.order_by(AgentQuestion.created_at.desc())
        all_items = list(db.execute(stmt).scalars())
        # Skip die ersten since_id (die hat der Caller schon gesehen)
        if len(all_items) > since_id:
            new_items = all_items[since_id:]
            return {
                "items": [_to_read(q) for q in new_items],
                "checked_at": datetime.utcnow().isoformat(),
                "elapsed_ms": int((time.time() - start) * 1000),
                "has_more": False,
            }
        # Schlafe 0.5s und versuche es erneut
        await asyncio.sleep(0.5)

    # Timeout: leere Liste, Client pollt erneut
    return {
        "items": [],
        "checked_at": datetime.utcnow().isoformat(),
        "elapsed_ms": int((time.time() - start) * 1000),
        "has_more": False,
        "timeout": True,
    }


@router.get("/{question_id}")
async def get_question(
    question_id: str,
    db: Session = Depends(get_db),
    user: str = Depends(require_auth),
) -> dict:
    """Detail einer Frage inkl. Attachments."""
    q = db.get(AgentQuestion, question_id)
    if not q:
        raise HTTPException(404, f"Frage {question_id} nicht gefunden")
    return _to_detail(q)


@router.post("/{question_id}/answer")
async def answer_question(
    question_id: str,
    body: AgentQuestionAnswer,
    db: Session = Depends(get_db),
    user: str = Depends(require_auth),
) -> dict:
    """User beantwortet eine offene Frage."""
    q = db.get(AgentQuestion, question_id)
    if not q:
        raise HTTPException(404, f"Frage {question_id} nicht gefunden")
    if q.status != "pending":
        raise HTTPException(409, f"Frage hat bereits Status '{q.status}', kann nicht beantwortet werden")

    if not body.answer_text and not body.answer_choice:
        raise HTTPException(400, "Entweder answer_text oder answer_choice erforderlich")

    # Bei confirmation: nur answer_text mit "ja"/"nein" ok
    if q.question_type == "confirmation" and body.answer_text:
        ans = body.answer_text.strip().lower()
        if ans not in ("ja", "nein", "yes", "no", "j", "n", "y"):
            raise HTTPException(400, "Bei confirmation-Fragen ist nur 'ja' oder 'nein' erlaubt")

    # Bei choice: answer_choice muss in options sein
    if q.question_type == "choice":
        if not body.answer_choice:
            raise HTTPException(400, "answer_choice erforderlich (question_type=choice)")
        if body.answer_choice not in (q.options or []):
            raise HTTPException(400, f"answer_choice muss eine der Optionen sein: {q.options}")

    q.answer_text = body.answer_text
    q.answer_choice = body.answer_choice
    if body.answer_attachments is not None:
        q.answer_attachments = json.dumps(body.answer_attachments, ensure_ascii=False)
    q.answered_at = datetime.utcnow()
    q.answered_by = body.answered_by
    q.status = "answered"
    q.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(q)

    # === Auto-Workflow: Wenn User eine C-Level-Frage (CIO/CEO) beantwortet hat,
    #     den Task automatisch im Standard-Workflow weiterverarbeiten.
    #     Logik: rueckfrage -> User hat geantwortet -> automatisch triage-approve -> todo
    #     Begruendung: User-Antwort = implizite Genehmigung durch den User.
    auto_workflow_result = None
    try:
        ctx = q.context or {}
        task_id_ctx = ctx.get("task_id")
        if task_id_ctx and q.agent_level == "C-Level":
            from ..models.task import Task
            from ..models.history import TaskHistory
            t = db.get(Task, task_id_ctx)
            # Fix (User-Direktive 18.06.2026): Auch "block" akzeptieren, weil
            # die Engine oft "block" setzt (sop_rule:block) statt "rueckfrage".
            if t and t.status in ("rueckfrage", "block"):
                # Meta bereinigen (input_required weg)
                try:
                    meta = dict(t.meta or {})
                except Exception:
                    meta = {}
                meta["input_required"] = False
                meta["input_answered_at"] = datetime.utcnow().isoformat()
                meta["auto_workflow"] = "user_input_answered"
                t.meta = meta
                # Audit
                th = TaskHistory(
                    task_id=t.id,
                    event="input_answered",
                    agent=q.agent_id,
                    details={
                        "question_id": q.id,
                        "old_status": old_status,
                        "new_status": "triage",
                        "answered_by": q.answered_by,
                    },
                )
                db.add(th)
                db.commit()
                # Auto-Approve: setzt status auf todo
                th2 = TaskHistory(
                    task_id=t.id,
                    event="triage_approved_auto",
                    agent=q.agent_id,
                    details={"reason": "user_answered_cio_question", "question_id": q.id, "from": "auto_workflow"},
                )
                db.add(th2)
                t.status = "todo"
                db.commit()
                auto_workflow_result = {
                    "auto_approved": True,
                    "old_status": old_status,
                    "new_status": "todo",
                    "task_id": t.id,
                }
                logger.info(
                    f"[auto-workflow] Task {t.id[:8]} nach User-Antwort: "
                    f"{old_status} -> triage -> todo (auto-approved via user input)"
                )
    except Exception as e:
        logger.warning(f"Auto-Workflow fehlgeschlagen: {e}")

    # SSE-Event veroeffentlichen
    try:
        from .. import events
        await events.publish_event(
            project_id="__tools__",
            event_type="agent_question_answered",
            data={
                "question_id": q.id,
                "agent_id": q.agent_id,
                "answered_by": q.answered_by,
                "auto_workflow": auto_workflow_result,
            },
        )
    except Exception as e:
        logger.warning(f"publish_event fehlgeschlagen: {e}")

    logger.info(f"Frage beantwortet: id={q.id} by={q.answered_by}")
    return _to_detail(q)


@router.post("/{question_id}/cancel")
async def cancel_question(
    question_id: str,
    db: Session = Depends(get_db),
    user: str = Depends(require_auth),
) -> dict:
    """Agent oder Admin storniert eine offene Frage."""
    q = db.get(AgentQuestion, question_id)
    if not q:
        raise HTTPException(404, f"Frage {question_id} nicht gefunden")
    if q.status != "pending":
        raise HTTPException(409, f"Frage hat Status '{q.status}', kann nicht storniert werden")

    q.status = "cancelled"
    q.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(q)
    logger.info(f"Frage storniert: id={q.id}")
    return _to_read(q)


@router.post("/{question_id}/seen")
async def mark_seen(
    question_id: str,
    db: Session = Depends(get_db),
    user: str = Depends(require_auth),
) -> dict:
    """Markiert eine Frage als vom User gesehen (Badge-Update)."""
    q = db.get(AgentQuestion, question_id)
    if not q:
        raise HTTPException(404, f"Frage {question_id} nicht gefunden")
    if q.seen_at is None:
        q.seen_at = datetime.utcnow()
        db.commit()
    return _to_read(q)


# === Attachments ===

@router.post("/{question_id}/attachments")
async def upload_attachment(
    question_id: str,
    file: UploadFile = File(...),
    source: str = Form("agent", description="agent | user"),
    kind: str = Form("file", description="file | image"),
    db: Session = Depends(get_db),
    user: str = Depends(require_auth),
) -> dict:
    """Laedt eine Datei oder ein Bild zu einer Frage hoch."""
    q = db.get(AgentQuestion, question_id)
    if not q:
        raise HTTPException(404, f"Frage {question_id} nicht gefunden")

    if source not in ("agent", "user"):
        raise HTTPException(400, "source muss 'agent' oder 'user' sein")
    if kind not in ("file", "image"):
        raise HTTPException(400, "kind muss 'file' oder 'image' sein")

    # Auto-detect kind anhand MIME-Type
    mime = file.content_type or "application/octet-stream"
    if kind == "file" and mime.startswith("image/"):
        kind = "image"

    # Eindeutiger Dateiname: q-{id}/{att_id}-{filename}
    att_id = f"att-{secrets.token_hex(6)}"
    safe_name = Path(file.filename or "upload").name
    qdir = UPLOAD_DIR / q.id
    qdir.mkdir(parents=True, exist_ok=True)
    target = qdir / f"{att_id}-{safe_name}"

    # Stream to disk (max 25 MB)
    MAX_BYTES = 25 * 1024 * 1024
    written = 0
    with target.open("wb") as f:
        while chunk := await file.read(64 * 1024):
            written += len(chunk)
            if written > MAX_BYTES:
                f.close()
                target.unlink(missing_ok=True)
                raise HTTPException(413, f"Datei zu gross (max {MAX_BYTES // (1024*1024)} MB)")
            f.write(chunk)

    att = AgentQuestionAttachment(
        id=att_id,
        question_id=q.id,
        kind=kind,
        file_name=safe_name,
        file_path=str(target.relative_to(UPLOAD_DIR)),
        mime_type=mime,
        size_bytes=written,
        source=source,
    )
    db.add(att)
    q.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(att)
    return att.to_dict()


class ImageAttachRequest(BaseModel):
    """Komfort-Endpoint: Bild direkt aus Base64-String."""
    base64_data: str
    file_name: str
    mime_type: str = "image/png"
    source: str = "agent"


@router.post("/{question_id}/attach-image")
async def attach_image(
    question_id: str,
    body: ImageAttachRequest,
    db: Session = Depends(get_db),
    user: str = Depends(require_auth),
) -> dict:
    """Komfort-Endpoint: Bild direkt aus Base64-String (fuer CLI/Curl-Submit)."""
    q = db.get(AgentQuestion, question_id)
    if not q:
        raise HTTPException(404, f"Frage {question_id} nicht gefunden")

    try:
        # data:image/png;base64,... Prefix entfernen
        b64 = body.base64_data
        if "," in b64[:64]:
            b64 = b64.split(",", 1)[1]
        raw = base64.b64decode(b64)
    except Exception as e:
        raise HTTPException(400, f"Base64-Parse-Fehler: {e}")

    if len(raw) > 25 * 1024 * 1024:
        raise HTTPException(413, "Bild zu gross (max 25 MB)")

    att_id = f"att-{secrets.token_hex(6)}"
    safe_name = Path(body.file_name).name
    qdir = UPLOAD_DIR / q.id
    qdir.mkdir(parents=True, exist_ok=True)
    target = qdir / f"{att_id}-{safe_name}"
    target.write_bytes(raw)

    att = AgentQuestionAttachment(
        id=att_id,
        question_id=q.id,
        kind="image",
        file_name=safe_name,
        file_path=str(target.relative_to(UPLOAD_DIR)),
        mime_type=body.mime_type,
        size_bytes=len(raw),
        source=body.source if body.source in ("agent", "user") else "agent",
    )
    db.add(att)
    q.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(att)
    return att.to_dict()


@router.get("/{question_id}/attachments/{att_id}")
async def download_attachment(
    question_id: str,
    att_id: str,
    db: Session = Depends(get_db),
    user: str = Depends(require_auth),
):
    """Laedt eine Anhang-Datei herunter."""
    att = db.get(AgentQuestionAttachment, att_id)
    if not att or att.question_id != question_id:
        raise HTTPException(404, "Anhang nicht gefunden")

    full_path = UPLOAD_DIR / att.file_path
    if not full_path.exists():
        raise HTTPException(404, "Datei nicht auf Disk gefunden")

    return FileResponse(
        path=str(full_path),
        media_type=att.mime_type or "application/octet-stream",
        filename=att.file_name,
    )
