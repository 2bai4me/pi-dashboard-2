"""Process-Template Router — BPMN Process Designer Endpoints.

Endpoints:
  GET    /api/process-templates?project_id=...       Liste
  POST   /api/process-templates                          Erstellen
  GET    /api/process-templates/{id}                    Detail
  PUT    /api/process-templates/{id}                    Update (nodes/edges/name)
  DELETE /api/process-templates/{id}                    Loeschen
  POST   /api/process-templates/{id}/apply-to-task/{task_id}   Erstellt Sub-Tasks im Board
"""
from __future__ import annotations

from typing import Optional, List, Dict, Any
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from ..db.base import get_db
from ..auth import require_auth
from ..models.process_template import ProcessTemplate
from ..models.task import Task
from ..models.history import TaskHistory
from ..services.task_service import TaskService, _gen_id

router = APIRouter(prefix="/api/process-templates", tags=["process-templates"])


# ─────────────── Schemas ───────────────

class NodeModel(BaseModel):
    id: str
    type: str = Field(..., description="start | end | task | decision | parallel | merge")
    label: str = Field("", description="Anzeige-Name des Schritts")
    x: float = 100
    y: float = 100
    properties: Dict[str, Any] = Field(default_factory=dict, description="assigned_role, priority, success_criteria, ...")

class EdgeModel(BaseModel):
    id: str
    from_node: str = Field(..., alias="from")
    to_node: str = Field(..., alias="to")
    label: str = ""
    condition: str = ""

class CreateTemplateBody(BaseModel):
    project_id: str
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    category: str = "workflow"
    nodes: List[NodeModel] = Field(default_factory=list)
    edges: List[EdgeModel] = Field(default_factory=list)
    created_by: Optional[str] = None

class UpdateTemplateBody(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    nodes: Optional[List[NodeModel]] = None
    edges: Optional[List[EdgeModel]] = None


# ─────────────── Endpoints ───────────────

@router.get("")
def list_templates(project_id: Optional[str] = None, db: Session = Depends(get_db), _user: str = Depends(require_auth)):
    """Liste aller Process-Templates (optional gefiltert nach project_id)."""
    from sqlalchemy import select
    q = select(ProcessTemplate).order_by(ProcessTemplate.updated_at.desc())
    if project_id:
        q = q.where(ProcessTemplate.project_id == project_id)
    return [t.to_dict() for t in db.execute(q).scalars()]


@router.post("", status_code=201)
def create_template(body: CreateTemplateBody, db: Session = Depends(get_db), _user: str = Depends(require_auth)):
    """Erstellt ein neues Process-Template (leeres oder mit nodes/edges)."""
    t = ProcessTemplate(
        project_id=body.project_id,
        name=body.name,
        description=body.description,
        category=body.category,
        nodes=[n.model_dump() for n in body.nodes],
        edges=[e.model_dump(by_alias=True) for e in body.edges],
        node_count=len(body.nodes),
        edge_count=len(body.edges),
        created_by=body.created_by,
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return t.to_dict()


@router.get("/{template_id}")
def get_template(template_id: str, db: Session = Depends(get_db), _user: str = Depends(require_auth)):
    """Detail eines Templates."""
    t = db.get(ProcessTemplate, template_id)
    if not t:
        raise HTTPException(404, "Process-Template not found")
    return t.to_dict()


@router.put("/{template_id}")
def update_template(template_id: str, body: UpdateTemplateBody, db: Session = Depends(get_db), _user: str = Depends(require_auth)):
    """Update name/description/nodes/edges."""
    t = db.get(ProcessTemplate, template_id)
    if not t:
        raise HTTPException(404, "Process-Template not found")
    if body.name is not None: t.name = body.name
    if body.description is not None: t.description = body.description
    if body.category is not None: t.category = body.category
    if body.nodes is not None:
        t.nodes = [n.model_dump() for n in body.nodes]
        t.node_count = len(body.nodes)
    if body.edges is not None:
        t.edges = [e.model_dump(by_alias=True) for e in body.edges]
        t.edge_count = len(body.edges)
    t.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(t)
    return t.to_dict()


@router.delete("/{template_id}", status_code=204)
def delete_template(template_id: str, db: Session = Depends(get_db), _user: str = Depends(require_auth)):
    """Loescht ein Process-Template (nicht die damit erstellten Sub-Tasks)."""
    t = db.get(ProcessTemplate, template_id)
    if not t:
        raise HTTPException(404, "Process-Template not found")
    db.delete(t)
    db.commit()


# ─────────────── ACTIVATION: Template fuer Projekt freischalten ───────────────

class ActivateBody(BaseModel):
    project_id: str = Field(..., description="Projekt, fuer das das Template aktiviert wird")
    agent: str = "CEO"
    note: Optional[str] = None

@router.post("/{template_id}/activate")
def activate_template(template_id: str, body: ActivateBody, db: Session = Depends(get_db), _user: str = Depends(require_auth)):
    """Template 'freischalten' — ab sofort steuert dieses Template den Workflow fuer das Projekt.

    - Setzt is_active=True und activated_at
    - Deaktiviert andere aktive Templates desselben Projekts (nur 1 aktiv pro Projekt)
    - Operator folgt ab sofort den Edges als Transition-Map
    """
    t = db.get(ProcessTemplate, template_id)
    if not t:
        raise HTTPException(404, "Process-Template not found")

    # Andere Templates im selben Projekt deaktivieren
    from sqlalchemy import update
    db.execute(
        update(ProcessTemplate)
        .where(ProcessTemplate.activated_for_project_id == body.project_id)
        .where(ProcessTemplate.id != template_id)
        .values(is_active=False, activated_at=None)
    )

    t.is_active = True
    t.activated_at = datetime.utcnow()
    t.activated_by = body.agent
    t.activated_for_project_id = body.project_id
    t.activation_note = body.note
    db.commit()
    db.refresh(t)

    return {
        "ok": True,
        "template_id": template_id,
        "project_id": body.project_id,
        "is_active": True,
        "activated_at": t.activated_at.isoformat(),
        "message": f"Template '{t.name}' ist jetzt aktiv fuer Projekt {body.project_id}. "
                   f"Der Operator folgt ab sofort den Edges als Transition-Map.",
    }


@router.post("/{template_id}/deactivate")
def deactivate_template(template_id: str, db: Session = Depends(get_db), _user: str = Depends(require_auth)):
    """Template wieder deaktivieren — Operator faellt auf Standard-Workflow zurueck."""
    t = db.get(ProcessTemplate, template_id)
    if not t:
        raise HTTPException(404, "Process-Template not found")

    t.is_active = False
    t.activated_at = None
    t.activated_by = None
    t.activation_note = None
    db.commit()
    db.refresh(t)

    return {"ok": True, "template_id": template_id, "is_active": False}


@router.get("/active/{project_id}")
def get_active_template(project_id: str, db: Session = Depends(get_db), _user: str = Depends(require_auth)):
    """Gibt das aktuell aktive Process-Template fuer ein Projekt zurueck (oder null)."""
    from sqlalchemy import select
    t = db.execute(
        select(ProcessTemplate)
        .where(ProcessTemplate.activated_for_project_id == project_id)
        .where(ProcessTemplate.is_active == True)
    ).scalar_one_or_none()
    if not t:
        return {"active": False, "template": None}
    return {"active": True, "template": t.to_dict()}


@router.post("/{template_id}/apply-to-task/{task_id}")
def apply_to_task(template_id: str, task_id: str, db: Session = Depends(get_db), _user: str = Depends(require_auth)):
    """Wendet das Process-Template als Sub-Tasks auf einen Board-Task an.

    Erstellt fuer jeden 'task'-Node einen Sub-Task mit:
    - title = Node-Label
    - assigned_role = Node-Property
    - priority = Node-Property (oder 50 default)
    - parent_id = task_id
    - status = 'triage'
    """
    template = db.get(ProcessTemplate, template_id)
    if not template:
        raise HTTPException(404, "Process-Template not found")
    parent = db.get(Task, task_id)
    if not parent:
        raise HTTPException(404, "Parent task not found")

    # Finde Topological-Order (folgt den Edges) — einfache Variante: nodes in Reihenfolge
    nodes: List[Dict[str, Any]] = list(template.nodes or [])
    edges: List[Dict[str, Any]] = list(template.edges or [])

    # Build Adj-List
    from collections import defaultdict, deque
    adj = defaultdict(list)
    in_degree = defaultdict(int)
    node_ids = {n["id"] for n in nodes}
    for n in nodes:
        in_degree[n["id"]] = 0
    for e in edges:
        adj[e["from"]].append(e["to"])
        in_degree[e["to"]] += 1

    # Topological Sort (Kahn)
    queue = deque([nid for nid in node_ids if in_degree[nid] == 0])
    ordered_ids = []
    while queue:
        nid = queue.popleft()
        ordered_ids.append(nid)
        for nb in adj[nid]:
            in_degree[nb] -= 1
            if in_degree[nb] == 0:
                queue.append(nb)
    # Falls nicht alle erreicht: fuege Rest hinten an
    for n in nodes:
        if n["id"] not in ordered_ids:
            ordered_ids.append(n["id"])

    # Mapping: node.id -> erstellter sub-task.id
    node_to_task = {}
    created_subtasks = []
    for order_idx, nid in enumerate(ordered_ids):
        node = next((n for n in nodes if n["id"] == nid), None)
        if not node:
            continue
        ntype = node.get("type", "task")
        if ntype in ("start", "end", "parallel", "merge"):
            # Kein Sub-Task fuer reine Marker
            continue
        props = node.get("properties", {}) or {}
        title = node.get("label") or f"{ntype.capitalize()}-{order_idx+1}"
        sub = Task(
            id=_gen_id(),
            project_id=parent.project_id,
            parent_id=parent.id,
            title=title,
            description=f"Schritt aus Process-Template: {template.name}\n\n{props.get('description', '')}",
            status="triage",
            priority=int(props.get("priority", 50)),
            category=props.get("category", "new_request"),
            assigned_role=props.get("assigned_role", "pi-coder"),
            success_criteria=props.get("success_criteria", []),
            order=order_idx,
        )
        db.add(sub)
        db.flush()
        node_to_task[nid] = sub.id
        TaskService._add_history(db, sub, "task_created", agent="system",
                                 details={"reason": "process_template_applied", "template_id": template.id})
        created_subtasks.append({"id": sub.id, "title": sub.title, "type": ntype, "order": order_idx})

    db.commit()

    # Mappe Edges zu Sub-Task-Parent-IDs (optional, fuer spaetere Verlinkung)
    for e in edges:
        if e["from"] in node_to_task and e["to"] in node_to_task:
            # Optional: predecessor in description speichern
            pass

    return {
        "ok": True,
        "template_id": template_id,
        "parent_task_id": task_id,
        "created_subtasks": created_subtasks,
        "total": len(created_subtasks),
    }
