"""SMproducer 3.0 Bridge (STUB).

CLEANUP-AUDIT 23.06.2026: Stub mit allen von main.py referenzierten Endpoints.
Funktionalitaet muss bei Bedarf in separatem Task wiederhergestellt werden.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List
from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel, Field

logger = logging.getLogger("pi-dashboard-2.smproducer_bridge")
router = APIRouter(prefix="/api/smproducer", tags=["smproducer"])


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str = "smproducer-bridge"
    mode: str = "stub"
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse()


@router.get("/manifest")
async def manifest() -> Dict[str, Any]:
    return {"version": "3.0.0", "mode": "stub", "services": [], "note": "STUB-Modus"}


@router.get("/status")
async def status() -> Dict[str, Any]:
    return {"running": False, "mode": "stub", "channels": [], "active_projects": 0}


@router.get("/channels")
async def channels() -> List[Dict[str, Any]]:
    return []


@router.get("/projects/{channel_prefix}")
async def list_projects(channel_prefix: str) -> List[Dict[str, Any]]:
    return []


@router.get("/projects/{channel_prefix}/{project_id}/thema")
async def get_thema(channel_prefix: str, project_id: str) -> Dict[str, Any]:
    return {"project_id": project_id, "thema": None, "mode": "stub"}


@router.patch("/projects/{channel_prefix}/{project_id}/meta")
async def patch_meta(channel_prefix: str, project_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    return {"ok": False, "mode": "stub"}


@router.post("/projects/{channel_prefix}/{project_id}/sources")
async def add_source(channel_prefix: str, project_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    return {"ok": False, "mode": "stub"}


@router.patch("/projects/{channel_prefix}/{project_id}/results/{result_id}")
async def patch_result(channel_prefix: str, project_id: str, result_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    return {"ok": False, "mode": "stub"}


@router.post("/projects/{channel_prefix}/{project_id}/analysis")
async def analysis(channel_prefix: str, project_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    return {"ok": False, "mode": "stub"}


@router.post("")
async def create_project(channel_prefix: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    return {"ok": False, "mode": "stub"}
