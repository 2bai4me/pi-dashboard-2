"""Ports API: OpenBrain-konformes Port-Management.

User-Direktive 23.06.2026 (Task 4bf7146b0780):
- Pro App 10 Ports reserviert (kann 2+ Bloecke haben)
- Jede Entwicklung MUSS erst nachfragen, welche Ports frei sind
- MUSS zurueckmelden wenn Port belegt
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..auth import require_auth
from ..services.port_manager import (
    PortBlock, find_free_block, reserve_block, release_block,
    list_allocations, find_block_for_task,
)

logger = logging.getLogger("pi-dashboard-2.ports_api")
router = APIRouter(prefix="/api/ports", tags=["ports"])


# === Pydantic-Schemas ===

class CheckPortsIn(BaseModel):
    app_name: str = Field(..., min_length=1, max_length=64)
    count: int = Field(10, ge=1, le=100)
    start_search: int = Field(8000, ge=1024, le=60000)


class CheckPortsOut(BaseModel):
    app_name: str
    requested_count: int
    available: bool
    block: Optional[dict] = None  # {port_start, port_end}


class ReservePortsIn(BaseModel):
    app_name: str = Field(..., min_length=1, max_length=64)
    task_id: Optional[str] = None
    count: int = Field(10, ge=1, le=100)
    notes: Optional[str] = None


class PortBlockOut(BaseModel):
    id: str
    app_name: str
    port_start: int
    port_end: int
    task_id: Optional[str]
    status: str
    allocated_at: Optional[str]
    released_at: Optional[str]
    notes: Optional[str]


def _block_to_out(b: PortBlock) -> PortBlockOut:
    return PortBlockOut(
        id=b.id, app_name=b.app_name, port_start=b.port_start, port_end=b.port_end,
        task_id=b.task_id, status=b.status, allocated_at=b.allocated_at,
        released_at=b.released_at, notes=b.notes,
    )


# === Endpoints ===

@router.post("/check", response_model=CheckPortsOut)
def check_ports(
    req: CheckPortsIn,
    _user: str = Depends(require_auth),
):
    """Prueft ob ein freier Block verfuegbar ist (ohne Reservierung).

    Wird vor jedem Subagent-Spawn aufgerufen, um freie Ports zu finden.
    """
    block = find_free_block(req.app_name, count=req.count, start_search=req.start_search)
    if block:
        return CheckPortsOut(
            app_name=req.app_name,
            requested_count=req.count,
            available=True,
            block={"port_start": block[0], "port_end": block[1]},
        )
    # Versuche hoeheren Bereich
    block = find_free_block(req.app_name, count=req.count, start_search=11000)
    if block:
        return CheckPortsOut(
            app_name=req.app_name,
            requested_count=req.count,
            available=True,
            block={"port_start": block[0], "port_end": block[1]},
        )
    return CheckPortsOut(app_name=req.app_name, requested_count=req.count, available=False)


@router.post("/reserve", response_model=PortBlockOut, status_code=201)
def reserve_ports(
    req: ReservePortsIn,
    _user: str = Depends(require_auth),
):
    """Reserviert einen neuen Block von `count` Ports fuer `app_name`.

    User-Direktive: MUSS bei jeder Entwicklung aufgerufen werden,
    BEVOR ein Port belegt wird. Pro App koennen mehrere Bloecke existieren.
    """
    try:
        block = reserve_block(req.app_name, task_id=req.task_id,
                              count=req.count, notes=req.notes)
    except RuntimeError as e:
        raise HTTPException(503, str(e))
    return _block_to_out(block)


@router.post("/{block_id}/release", response_model=PortBlockOut)
def release_ports(
    block_id: str,
    _user: str = Depends(require_auth),
):
    """Gibt einen Port-Block frei (z.B. bei Task-Completion).

    User-Direktive: MUSS aufgerufen werden, wenn ein Port nicht mehr
    gebraucht wird.
    """
    success = release_block(block_id)
    if not success:
        raise HTTPException(404, f"Block {block_id} nicht gefunden oder bereits released")
    # Aktualisierten Block zurueckgeben
    from ..services.port_manager import list_allocations
    all_blocks = list_allocations()
    block = next((b for b in all_blocks if b.id == block_id), None)
    if not block:
        raise HTTPException(404, f"Block {block_id} nicht gefunden")
    return _block_to_out(block)


@router.get("", response_model=List[PortBlockOut])
def list_port_allocations(
    app_name: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    _user: str = Depends(require_auth),
):
    """Listet alle Port-Allokationen."""
    blocks = list_allocations(app_name=app_name, status=status)
    return [_block_to_out(b) for b in blocks]


@router.get("/by-task/{task_id}", response_model=List[PortBlockOut])
def list_ports_by_task(
    task_id: str,
    _user: str = Depends(require_auth),
):
    """Listet alle Port-Bloecke, die fuer einen Task reserviert wurden."""
    blocks = list_allocations()
    task_blocks = [b for b in blocks if b.task_id == task_id]
    return [_block_to_out(b) for b in task_blocks]