"""Status-API (User-Direktive 24.06.2026).

Liefert erweiterte Status-Informationen fuer die Status-Seite (PG-071-STATUS):
  - Projekte mit GitHub-URL, lokaler Pfad, Verfuegbarkeit
  - System-Metriken (operative DB, Archiv, Backend)
  - SOP-Live-Aktivitaet
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select, func, text
from fastapi import Query
from sqlalchemy.orm import Session

from ..db.base import get_db, SessionLocal
from ..models.project import Project
from ..models.sop import SOPInstance, SOPExecution
from ..models.task import Task
from ..auth import require_auth

logger = logging.getLogger("pi-dashboard-2.status")

router = APIRouter(prefix="/api/status", tags=["status-extended"])


class ProjectStatusItem(BaseModel):
    id: str
    name: str
    project_number: Optional[str]
    github_url: Optional[str]
    local_path: Optional[str]
    local_available: bool
    container_name: Optional[str]
    status: Optional[str] = "active"
    component_count: Optional[int] = 0
    task_count: int
    tasks_done: int
    tasks_open: int
    tasks_cancelled: int


class SystemStatusItem(BaseModel):
    total_projects: int
    projects_with_local_path: int
    total_tasks_operational: int
    total_tasks_archived: int
    archive_size_mb: float
    active_sop_instances: int
    server_uptime_sec: float
    backend_status: str
    frontend_status: str
    timestamp: str


@router.get("/projects", response_model=List[ProjectStatusItem])
async def list_projects_with_status(
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    """Liefert alle Projekte mit Status (lokal verfuegbar?, Pfad, GitHub-URL).
    Filter: nur aktive Projekte (keine archived/closed) — User-Direktive 24.06.2026."""
    projects = db.execute(
        select(Project)
        .where(Project.status.notin_(["archived", "closed"]))
        .order_by(Project.name)
    ).scalars().all()
    result = []
    for p in projects:
        # Stats aus operativer DB (nicht Archiv)
        total = db.execute(
            select(func.count(Task.id)).where(Task.project_id == p.id)
        ).scalar() or 0
        done = db.execute(
            select(func.count(Task.id))
            .where(Task.project_id == p.id, Task.status == "done")
        ).scalar() or 0
        cancelled = db.execute(
            select(func.count(Task.id))
            .where(Task.project_id == p.id, Task.status == "cancelled")
        ).scalar() or 0
        # Active = total - done - cancelled
        active = total - done - cancelled
        cc = db.execute(
            text("SELECT COUNT(*) FROM project_components WHERE project_id = :pid"),
            {"pid": p.id}
        ).scalar() or 0
        item = ProjectStatusItem(
            id=p.id, name=p.name, project_number=p.project_number,
            github_url=p.github_url, local_path=p.local_path,
            local_available=bool(p.local_available), container_name=p.container_name,
            status=p.status, component_count=cc,
            task_count=total, tasks_done=done, tasks_open=active,
            tasks_cancelled=cancelled,
        )
        # Container-Info als zusaetzliches Feld (nicht in ProjectStatusItem)
        item_dict = item.dict()
        if p.container_image:
            item_dict["container_image"] = p.container_image
            item_dict["container_port"] = p.container_port
        if p.github_url:
            item_dict["github_stars"] = p.github_stars
            item_dict["github_forks"] = p.github_forks
            item_dict["github_fetched_at"] = p.github_fetched_at.isoformat() if p.github_fetched_at else None
        result.append(item_dict)
    return result


@router.get("/projects/{project_id}/details")
async def get_project_details(
    project_id: str,
    force_refresh: bool = Query(False, description="GitHub-API-Cache umgehen"),
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    """Liefert alle Details zu einem Projekt (fuer Modal)."""
    from app.services.github_service import fetch_repo_info
    from app.models.project import Project
    from sqlalchemy.orm.attributes import flag_modified

    p = db.get(Project, project_id)
    if not p:
        from fastapi import HTTPException
        raise HTTPException(404, "Project not found")

    # Tasks
    tasks = db.execute(
        select(Task).where(Task.project_id == project_id)
        .order_by(Task.created_at.desc())
        .limit(50)
    ).scalars().all()

    # GitHub-Daten (live oder gecached)
    github_data = None
    if p.github_url:
        github_data = fetch_repo_info(p.github_url, use_cache=not force_refresh)

    # Critical Findings parsen
    critical_findings = None
    if p.critical_findings:
        try:
            import json as _json
            critical_findings = _json.loads(p.critical_findings)
        except (ValueError, TypeError):
            critical_findings = None

    # Topics parsen
    topics = []
    if p.github_topics:
        try:
            import json as _json
            topics = _json.loads(p.github_topics)
        except (ValueError, TypeError):
            pass

    return {
        "id": p.id,
        "name": p.name,
        "project_number": p.project_number,
        "description": p.description,
        "category": p.category,
        "mode": p.mode,
        "status": p.status,
        "github_url": p.github_url,
        "github_data": github_data,
        "github_stars": p.github_stars,
        "github_forks": p.github_forks,
        "github_default_branch": p.github_default_branch,
        "github_size_kb": p.github_size_kb,
        "github_license": p.github_license,
        "github_topics": topics,
        "github_language": p.github_language,
        "github_fetched_at": p.github_fetched_at.isoformat() if p.github_fetched_at else None,
        "local_path": p.local_path,
        "local_available": bool(p.local_available),
        "container_image": p.container_image,
        "container_port": p.container_port,
        "container_status": p.container_status,
        "critical_findings": critical_findings,
        "task_count": len(tasks),
        "tasks": [
            {
                "id": t.id,
                "title": t.title,
                "status": t.status,
                "priority": t.priority,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in tasks[:20]
        ],
        "components": _get_components_for_project(db, project_id),
    }


def _get_components_for_project(db, project_id: str) -> list[dict]:
    """Liefert alle Sub-Components eines Projekts (Pipeline/Frontend/NotebookLM etc.)."""
    from sqlalchemy import text
    rows = db.execute(text("""
        SELECT c.id, c.slug, c.name, c.component_type, c.description,
               c.container_image, c.container_port, c.container_status,
               c.container_name, c.local_path, c.github_url,
               (SELECT COUNT(*) FROM containers cn WHERE cn.component_id = c.id) as container_count
        FROM project_components c
        WHERE c.project_id = :pid
        ORDER BY c.sort_order ASC, c.id ASC
    """), {"pid": project_id}).fetchall()
    return [
        {
            "id": r[0],
            "slug": r[1],
            "name": r[2],
            "type": r[3],
            "description": r[4],
            "container_image": r[5],
            "container_port": r[6],
            "container_status": r[7],
            "container_name": r[8],
            "local_path": r[9],
            "github_url": r[10],
            "container_count": r[11],
        }
        for r in rows
    ]


@router.get("/components/{component_id}")
async def get_component_details(
    component_id: int,
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    """Liefert Details einer Component + zugehoerige Container."""
    from sqlalchemy import text
    row = db.execute(text("""
        SELECT c.id, c.project_id, c.slug, c.name, c.component_type, c.description,
               c.container_image, c.container_port, c.container_status,
               c.container_name, c.local_path, c.github_url, c.sort_order
        FROM project_components c WHERE c.id = :id
    """), {"id": component_id}).fetchone()
    if not row:
        from fastapi import HTTPException
        raise HTTPException(404, "Component not found")
    containers = db.execute(text("""
        SELECT name, image, external_ports, internal_port, network, ip, status
        FROM containers WHERE component_id = :cid ORDER BY sort_order
    """), {"cid": component_id}).fetchall()
    return {
        "id": row[0], "project_id": row[1], "slug": row[2], "name": row[3],
        "type": row[4], "description": row[5],
        "container_image": row[6], "container_port": row[7], "container_status": row[8],
        "container_name": row[9], "local_path": row[10], "github_url": row[11],
        "sort_order": row[12],
        "containers": [
            {"name": c[0], "image": c[1], "external_ports": c[2], "internal_port": c[3],
             "network": c[4], "ip": c[5], "status": c[6]}
            for c in containers
        ],
    }


@router.post("/projects/{project_id}/github-update")
async def update_github_data(
    project_id: str,
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    """Aktualisiert die GitHub-Daten eines Projekts (Stars, Forks, ...)."""
    from app.services.github_service import update_project_from_github
    result = update_project_from_github(db, project_id)
    if not result.get("success"):
        from fastapi import HTTPException
        raise HTTPException(400, result.get("error", "Update failed"))
    return result


@router.get("/github-cache/stats")
async def get_github_cache_stats(
    _user: str = Depends(require_auth),
):
    """GitHub-Cache-Statistiken."""
    from app.services.github_service import get_cache_stats
    return get_cache_stats()


@router.get("/system", response_model=SystemStatusItem)
async def get_system_status(
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    """Liefert System-Metriken."""
    import time
    # Archiv-Stats
    archive_path = Path(__file__).parent.parent.parent.parent / "database" / "pi_dashboard_archive.db"
    archive_size = 0.0
    archive_tasks = 0
    if archive_path.exists():
        archive_size = round(archive_path.stat().st_size / 1024 / 1024, 2)
        try:
            import sqlite3
            conn = sqlite3.connect(str(archive_path), timeout=10)
            archive_tasks = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] or 0
            conn.close()
        except Exception:
            pass

    # Projekte mit lokalem Pfad
    projects_total = db.execute(select(func.count(Project.id))).scalar() or 0
    projects_with_local = db.execute(
        select(func.count(Project.id)).where(Project.local_available == True)
    ).scalar() or 0

    # Aktive SOP-Instances
    active_instances = db.execute(
        select(func.count(SOPInstance.id)).where(
            SOPInstance.status.in_(["running", "paused"])
        )
    ).scalar() or 0

    # Operative DB-Tasks
    total_tasks = db.execute(select(func.count(Task.id))).scalar() or 0

    return SystemStatusItem(
        total_projects=projects_total,
        projects_with_local_path=projects_with_local,
        total_tasks_operational=total_tasks,
        total_tasks_archived=archive_tasks,
        archive_size_mb=archive_size,
        active_sop_instances=active_instances,
        server_uptime_sec=time.time(),  # approximativ
        backend_status="ok",
        frontend_status="ok",
        timestamp=datetime.utcnow().isoformat(),
    )


@router.get("/sop-logs/recent")
async def get_recent_sop_logs(
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    """Liefert die letzten SOP-Execution-Logs (fuer die Live-Log-Spalte)."""
    from ..models.sop import SOPStep
    rows = db.execute(
        select(SOPExecution, SOPStep.name, SOPStep.step_order, Task.title)
        .join(SOPStep, SOPExecution.step_id == SOPStep.id)
        .join(SOPInstance, SOPExecution.instance_id == SOPInstance.id)
        .join(Task, SOPInstance.task_id == Task.id)
        .order_by(SOPExecution.ts.desc())
        .limit(limit)
    ).all()
    return [
        {
            "ts": exec.ts.isoformat() if exec.ts else None,
            "event": exec.event,
            "agent": exec.agent,
            # model/provider sind in details (nicht als Spalten in SOPExecution)
            "model": (exec.details or {}).get("model") if exec.details else None,
            "provider": (exec.details or {}).get("provider") if exec.details else None,
            "duration_ms": exec.duration_ms,
            "step_name": step_name,
            "step_order": step_order,
            "task_title": task_title,
            "details": str(exec.details)[:300] if exec.details else None,
        }
        for exec, step_name, step_order, task_title in rows
    ]


@router.get("/service-repos")
async def list_service_repos(
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    """Liefert alle verwandten Service-Repos (User-Direktive 24.06.2026)."""
    from ..models.service_repo import ExternalServiceRepo
    repos = db.execute(
        select(ExternalServiceRepo).order_by(ExternalServiceRepo.sort_order)
    ).scalars().all()
    return [
        {
            "id": r.id,
            "name": r.name,
            "local_path": r.local_path,
            "github_url": r.github_url,
            "local_available": bool(r.local_available),
            "category": r.category,
            "description": r.description,
        }
        for r in repos
    ]


@router.get("/containers")
async def list_active_containers(
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
    grouped: bool = Query(True, description="Container nach App/Project gruppieren"),
):
    """Liefert alle aktiven Container aus der containers-Tabelle.

    grouped=true (Default): gruppiert nach Projekt (App), mit Component-Info.
    grouped=false: flache Liste (Legacy).
    """
    from sqlalchemy import text
    rows = db.execute(text("""
        SELECT c.id, c.name, c.image, c.external_ports, c.internal_port,
               c.network, c.ip, c.status, c.category, c.component_id,
               c.sort_order,
               pc.slug AS component_slug, pc.name AS component_name,
               pc.project_id, p.name AS project_name, p.project_number
        FROM containers c
        LEFT JOIN project_components pc ON c.component_id = pc.id
        LEFT JOIN projects p ON pc.project_id = p.id
        ORDER BY COALESCE(p.name, '~ungrouped') ASC, c.sort_order ASC, c.name ASC
    """)).fetchall()

    flat = [
        {
            "id": r[0],
            "name": r[1],
            "image": r[2],
            "port_external": r[3],
            "port_internal": r[4],
            "network": r[5],
            "ip": r[6],
            "status": r[7],
            "category": r[8],
            "component_id": r[9],
            "component_slug": r[11],
            "component_name": r[12],
            "project_id": r[13],
            "project_name": r[14],
            "project_number": r[15],
        }
        for r in rows
    ]

    if not grouped:
        return flat

    # Gruppierung nach Projekt (App)
    from collections import OrderedDict
    groups: "OrderedDict[str, dict]" = OrderedDict()
    ungrouped = []
    for c in flat:
        if c["project_id"]:
            key = c["project_id"]
            if key not in groups:
                groups[key] = {
                    "project_id": c["project_id"],
                    "project_name": c["project_name"],
                    "project_number": c["project_number"],
                    "container_count": 0,
                    "healthy_count": 0,
                    "running_count": 0,
                    "containers": [],
                    "components": OrderedDict(),
                }
            g = groups[key]
            g["container_count"] += 1
            if c["status"] in ("healthy", "running"):
                g["healthy_count"] += 1
            if c["status"] == "running":
                g["running_count"] += 1
            g["containers"].append(c)
            # Components-Sub-Group
            comp_key = c["component_slug"] or "_unassigned"
            if comp_key not in g["components"]:
                g["components"][comp_key] = {
                    "slug": c["component_slug"],
                    "name": c["component_name"],
                    "container_count": 0,
                    "containers": [],
                }
            g["components"][comp_key]["container_count"] += 1
            g["components"][comp_key]["containers"].append(c)
        else:
            ungrouped.append(c)

    # "Ungrouped"-Bucket (Infrastruktur ohne Component-Zuordnung)
    if ungrouped:
        groups["_infra"] = {
            "project_id": None,
            "project_name": "Infrastruktur (kein Projekt)",
            "project_number": None,
            "container_count": len(ungrouped),
            "healthy_count": sum(1 for c in ungrouped if c["status"] in ("healthy", "running")),
            "running_count": sum(1 for c in ungrouped if c["status"] == "running"),
            "containers": ungrouped,
            "components": {"_unassigned": {"slug": None, "name": "Allgemein", "container_count": len(ungrouped), "containers": ungrouped}},
        }

    return {
        "groups": list(groups.values()),
        "total_containers": len(flat),
        "group_count": len(groups),
    }
