"""Port-Management-Service.

User-Direktive 23.06.2026 (Task 4bf7146b0780):
- Jede App bekommt 10 Ports reserviert
- 2+ Bloecke pro App moeglich
- reserve_port, release_port, list_allocations

Workflow:
1. Vor jedem Subagent-Spawn: reserve_block() aufrufen
2. Nach Task-Completion: release_block() aufrufen
3. Bei Port-Konflikt: find_free_block() sucht naechsten freien Block
"""
from __future__ import annotations

import json
import logging
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional

logger = logging.getLogger("pi-dashboard-2.port_manager")

# === Konfiguration ===

DEFAULT_BLOCK_SIZE = 10
# Reservierte Bereiche pro App: niemals auswaehlen
RESERVED_RANGES = [
    (0, 1023),      # System-Ports
    (5555, 5560),   # MCP-over-ZMQ (TCP 5555-5560)
    (9300, 9310),   # OpenBrain-Container
    (9400, 9410),   # SMproducer
    (9500, 9510),   # YouTube
    (9220, 9229),   # PI-Dashboard Backend
    (9230, 9239),   # PI-Dashboard Erweiterung
    (10000, 10009), # Generic Reserve
]


@dataclass
class PortBlock:
    id: str
    app_name: str
    port_start: int
    port_end: int
    task_id: Optional[str]
    status: str  # active / released
    allocated_at: Optional[str]
    released_at: Optional[str]
    notes: Optional[str]


def _get_conn():
    import os
    db_path = os.environ.get("PI_DB_PATH", "database/pi_dashboard.db")
    return sqlite3.connect(db_path)


def _row_to_block(row) -> PortBlock:
    return PortBlock(
        id=row["id"],
        app_name=row["app_name"],
        port_start=row["port_start"],
        port_end=row["port_end"],
        task_id=row["task_id"],
        status=row["status"],
        allocated_at=row["allocated_at"],
        released_at=row["released_at"],
        notes=row["notes"],
    )


# === Public API ===

def find_free_block(app_name: str, count: int = DEFAULT_BLOCK_SIZE,
                     start_search: int = 8000) -> Optional[tuple]:
    """Findet einen freien Block von `count` aufeinanderfolgenden Ports.

    Strategie:
    1. Sammle alle belegten Port-Ranges (active)
    2. Suche ab `start_search` aufsteigend nach `count` freien aufeinanderfolgenden Ports
    3. Vermeide reservierte Bereiche
    4. Gib (start, end) zurueck oder None wenn nichts gefunden

    Returns:
        Tuple (port_start, port_end) oder None
    """
    import os
    db_path = os.environ.get("PI_DB_PATH", "database/pi_dashboard.db")
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT port_start, port_end FROM app_port_allocations WHERE status = 'active'")
    occupied = [(r[0], r[1]) for r in cur.fetchall()]
    occupied.extend(RESERVED_RANGES)
    conn.close()
    # Sortiere nach Start
    occupied.sort()

    candidate = start_search
    while candidate < 65535:
        block_end = candidate + count - 1
        # Pruefe Kollision mit allen belegten Bereichen
        collision = False
        for occ_start, occ_end in occupied:
            # Bereiche ueberlappen wenn: candidate <= occ_end AND block_end >= occ_start
            if candidate <= occ_end and block_end >= occ_start:
                # Springe hinter den belegten Bereich
                candidate = occ_end + 1
                collision = True
                break
        if not collision:
            return (candidate, block_end)
    return None


def reserve_block(app_name: str, task_id: Optional[str] = None,
                  count: int = DEFAULT_BLOCK_SIZE, notes: Optional[str] = None) -> PortBlock:
    """Reserviert einen freien Block von `count` Ports fuer `app_name`.

    Returns:
        PortBlock mit der reservierten Range

    Raises:
        RuntimeError: Wenn kein freier Block gefunden wird
    """
    block = find_free_block(app_name, count=count)
    if not block:
        # Versuche einen hoeheren Bereich
        block = find_free_block(app_name, count=count, start_search=11000)
    if not block:
        raise RuntimeError(f"Kein freier {count}-Port-Block fuer {app_name} gefunden")
    port_start, port_end = block

    conn = _get_conn()
    cur = conn.cursor()
    block_id = f"alloc-{secrets.token_hex(6)}"
    now = datetime.now(timezone.utc).isoformat()
    cur.execute("""INSERT INTO app_port_allocations
                   (id, app_name, port_start, port_end, task_id, allocated_at, status, notes)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (block_id, app_name, port_start, port_end, task_id, now, "active", notes))
    conn.commit()
    cur.execute("SELECT * FROM app_port_allocations WHERE id = ?", (block_id,))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM app_port_allocations WHERE id = ?", (block_id,))
    row = cur.fetchone()
    conn.close()
    logger.info(f"Port-Block reserviert: {app_name} {port_start}-{port_end} (id={block_id})")
    return _row_to_block(row)


def release_block(block_id: str) -> bool:
    """Gibt einen Port-Block frei.

    Returns:
        True wenn erfolgreich freigegeben, False wenn Block nicht gefunden
    """
    conn = _get_conn()
    cur = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()
    cur.execute("""UPDATE app_port_allocations
                   SET status = 'released', released_at = ?
                   WHERE id = ? AND status = 'active'""",
                (now, block_id))
    conn.commit()
    success = cur.rowcount > 0
    conn.close()
    if success:
        logger.info(f"Port-Block freigegeben: {block_id}")
    return success


def list_allocations(app_name: Optional[str] = None,
                     status: Optional[str] = None) -> List[PortBlock]:
    """Listet Port-Allokationen (gefiltert nach app_name/status)."""
    conn = _get_conn()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    where = []
    params = []
    if app_name:
        where.append("app_name = ?")
        params.append(app_name)
    if status:
        where.append("status = ?")
        params.append(status)
    sql = "SELECT * FROM app_port_allocations"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY app_name, port_start"
    cur.execute(sql, params)
    rows = cur.fetchall()
    conn.close()
    return [_row_to_block(row) for row in rows]


def get_next_port_for_task(app_name: str, task_id: str, count: int = 1) -> int:
    """Praktische Helper-Funktion: Reserviert einen Block und gibt den ersten Port zurueck.

    Wird vom Subagent-Spawner verwendet, um einen freien Port zu bekommen.
    """
    block = reserve_block(app_name, task_id=task_id, count=count)
    return block.port_start


def find_block_for_task(task_id: str) -> Optional[PortBlock]:
    """Findet einen aktiven Port-Block, der fuer den gegebenen Task reserviert wurde."""
    conn = _get_conn()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("""SELECT * FROM app_port_allocations
                   WHERE task_id = ? AND status = 'active'
                   ORDER BY allocated_at DESC LIMIT 1""", (task_id,))
    row = cur.fetchone()
    conn.close()
    return _row_to_block(row) if row else None