"""MCP Sub-Agent Client (STUB).

CLEANUP-AUDIT 23.06.2026: HTTP-Fallback wird vom pi_code_agent_wrapper.py genutzt.
"""
from __future__ import annotations

import logging
from typing import Optional, Dict, Any

logger = logging.getLogger("pi-dashboard-2.mcp_bus.sub_agent_client")


async def get_task(task_id: str, endpoint: str, api_key: str) -> Optional[Dict[str, Any]]:
    raise RuntimeError("MCP-Bus STUB: HTTP-Fallback nutzen (kein --endpoint flag).")


async def report_status(
    task_id: str, status: str, agent: str = "", reason: str = "",
    endpoint: str = "", api_key: str = "",
) -> Optional[Dict[str, Any]]:
    raise RuntimeError("MCP-Bus STUB: HTTP-Fallback nutzen.")


async def report_dispatch(
    task_id: str, role: str = "pi-coder", status: str = "done", model: str = "",
    reason: str = "", endpoint: str = "", api_key: str = "",
) -> Optional[Dict[str, Any]]:
    raise RuntimeError("MCP-Bus STUB: HTTP-Fallback nutzen.")


__all__ = ["get_task", "report_status", "report_dispatch"]
