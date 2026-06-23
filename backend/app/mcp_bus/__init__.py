"""MCP-over-ZMQ Bus (STUB).

Siehe CLEANUP-AUDIT 23.06.2026 + Port_Migration_PI_Dashboard_2.md.
HTTP-Fallback in pi_code_agent_wrapper.py ist aktiv; MCP-Bus optional.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger("pi-dashboard-2.mcp_bus")


class MCPServer:
    """Stub fuer externen Sub-Agent-Bus (HTTP-Fallback aktiv)."""

    def __init__(self, *args, **kwargs) -> None:
        self.session_factory = kwargs.get("session_factory")
        self.running: bool = False
        logger.warning("MCPServer STUB-Modus aktiv (HTTP-Fallback)")

    def start(self) -> None:
        self.running = True

    def stop(self) -> None:
        self.running = False

    def is_running(self) -> bool:
        return self.running


__all__ = ["MCPServer"]
