"""Sub-Agent-Spawner — Hook fuer echte Worker-Integration (User-Direktive 19.06.2026).

Vorher: Tasks mit status=in_progress + assigned_subagent blieben haengen,
        weil das Backend keinen Hook fuer spawn.sh hatte.
Nachher: Bei Auto-Claim auf in_progress wird der Sub-Agent via spawn.sh gestartet,
         PID getrackt, Log-Datei erstellt, Crash-Detection implementiert.

Architektur:
  Status-Wechsel → Auto-Claim → in_progress
    └─→ _spawn_sub_agent(t, db)
         └─→ subprocess.Popen(spawn.sh role task_id title)
              └─→ PID in sub_agent_meta gespeichert
              └─→ Log-Datei: ~/.pi/agent/operator/logs/spawn-<task_id>.log
"""
from __future__ import annotations

import asyncio
import logging
import os
import platform
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from ..models.task import Task
from ..models.history import TaskHistory
from ..models.transition import TaskTransition
from ..config import settings

logger = logging.getLogger("pi-dashboard-2.sub-agent")


# === In-Memory Tracking (fuer schnelle Lookups) ===
# Format: task_id -> {"pid": int, "spawned_at": float, "log_path": str, "role": str}
_AGENT_REGISTRY: Dict[str, Dict[str, Any]] = {}


def _get_spawn_script_path() -> Optional[Path]:
    """Findet den spawn.sh-Pfad auf dem System."""
    # 1) Settings (wenn konfiguriert)
    if hasattr(settings, "SPAWN_SH_PATH") and settings.SPAWN_SH_PATH:
        p = Path(settings.SPAWN_SH_PATH)
        if p.exists():
            return p

    # 2) Standard-Pfade
    candidates = [
        Path("C:/Users/uwean/.pi/agent/extensions/swarm-spawner/spawn.sh"),
        Path(os.path.expanduser("~/.pi/agent/extensions/swarm-spawner/spawn.sh")),
        Path("/home/uwean/.pi/agent/extensions/swarm-spawner/spawn.sh"),
        Path("extensions/swarm-spawner/spawn.sh"),
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


def _get_bash_executable() -> Optional[str]:
    """Findet bash auf dem System (Windows braucht Git-Bash oder WSL)."""
    if platform.system() != "Windows":
        return "bash"  # Unix hat bash

    # Windows: Git-Bash oder WSL-Bash
    candidates = [
        r"C:\Program Files\Git\usr\bin\bash.EXE",
        r"C:\Program Files\Git\bin\bash.exe",
        r"C:\Windows\System32\bash.exe",  # WSL
        shutil.which("bash"),
        shutil.which("bash.exe"),
    ]
    for c in candidates:
        if c and os.path.exists(c):
            return c
    return None


async def _spawn_sub_agent(t: Task, db: Session) -> Optional[Dict[str, Any]]:
    """Startet den Sub-Agent fuer den Task via spawn.sh.

    Wird aufgerufen wenn:
      - Task wechselt zu in_progress (Auto-Claim)
      - Task hat assigned_subagent gesetzt
      - Task hat noch keinen Sub-Agent-Prozess laufen

    Returns: Dict mit pid, spawned_at, log_path, role — oder None bei Fehler.
    """
    # 1) Pre-Check: bereits ein Agent fuer diesen Task?
    if t.id in _AGENT_REGISTRY:
        existing = _AGENT_REGISTRY[t.id]
        if _is_process_alive(existing.get("pid")):
            logger.debug(f"Sub-Agent fuer Task {t.id[:8]} laeuft bereits (PID {existing['pid']})")
            return existing
        else:
            logger.warning(f"Sub-Agent fuer Task {t.id[:8]} ist abgestuerzt (PID {existing.get('pid')}). Cleanup.")
            _AGENT_REGISTRY.pop(t.id, None)

    # 2) Welcher Sub-Agent soll starten?
    role = t.assigned_subagent or t.assigned_role
    if not role:
        logger.warning(f"Task {t.id[:8]} hat keinen assigned_subagent, kann nicht spawnen")
        return None

    # 3) Spawn-Skript finden
    spawn_script = _get_spawn_script_path()
    if not spawn_script:
        logger.error("spawn.sh nicht gefunden! Sub-Agent kann nicht gestartet werden.")
        return None

    # 4) Bash finden
    bash = _get_bash_executable()
    if not bash:
        logger.error("bash nicht gefunden (Windows braucht Git-Bash oder WSL)")
        return None

    # 5) Log-Verzeichnis vorbereiten
    log_dir = Path(os.path.expanduser("~/.pi/agent/operator/logs"))
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"spawn-{t.id}.log"
    log_file = open(log_path, "a", encoding="utf-8")

    # 6) Context aus Task zusammenbauen
    context_parts = [
        f"task_id={t.id}",
        f"title={t.title}",
        f"description={t.description or ''}",
        f"priority={t.priority}",
        f"status={t.status}",
        f"branch=task/{t.id}",
    ]
    context = "; ".join(context_parts)

    # 7) Sub-Agent starten (asynchron via subprocess.Popen)
    cmd = [str(bash), str(spawn_script), role, t.id, context]
    logger.info(f"Spawning Sub-Agent: {' '.join(cmd)}")

    try:
        # Popen startet den Prozess und kehrt sofort zurueck
        proc = subprocess.Popen(
            cmd,
            stdout=log_file,
            stderr=subprocess.STDOUT,  # stderr nach stdout (Log-Datei)
            stdin=subprocess.DEVNULL,  # kein stdin
            cwd=str(spawn_script.parent),
            env={**os.environ, "PI_DASHBOARD_API": "http://127.0.0.1:9220"},
            creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0,
        )

        spawned_at = time.time()

        # 8) In Registry speichern
        agent_info = {
            "pid": proc.pid,
            "spawned_at": spawned_at,
            "log_path": str(log_path),
            "role": role,
            "task_id": t.id,
            "process": proc,
        }
        _AGENT_REGISTRY[t.id] = agent_info

        # 9) In DB tracken (sub_agent_meta)
        if t.meta is None:
            t.meta = {}
        t.meta["sub_agent"] = {
            "pid": proc.pid,
            "role": role,
            "spawned_at": spawned_at,
            "log_path": str(log_path),
            "status": "running",
        }
        db.commit()

        # 10) History-Eintrag
        TaskService_add_history_safe(
            db, t, "sub_agent_spawned", agent="system",
            details={
                "pid": proc.pid,
                "role": role,
                "log_path": str(log_path),
                "spawn_script": str(spawn_script),
            },
        )
        db.commit()

        logger.info(f"Sub-Agent fuer Task {t.id[:8]} gestartet: PID {proc.pid}, Rolle {role}")
        return agent_info

    except Exception as e:
        logger.error(f"Fehler beim Starten des Sub-Agents fuer Task {t.id[:8]}: {e}")
        log_file.write(f"\n[ERROR] {e}\n")
        log_file.close()
        return None


def _is_process_alive(pid: Optional[int]) -> bool:
    """Prueft ob ein Prozess mit der PID noch laeuft."""
    if pid is None:
        return False
    try:
        if platform.system() == "Windows":
            import ctypes
            kernel32 = ctypes.windll.kernel32
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            STILL_ACTIVE = 259
            h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if h == 0:
                return False
            try:
                exit_code = ctypes.c_ulong()
                kernel32.GetExitCodeProcess(h, ctypes.byref(exit_code))
                return exit_code.value == STILL_ACTIVE
            finally:
                kernel32.CloseHandle(h)
        else:
            os.kill(pid, 0)  # Signal 0 = nur pruefen
            return True
    except (OSError, ProcessLookupError):
        return False


def get_agent_for_task(task_id: str) -> Optional[Dict[str, Any]]:
    """Gibt die Agent-Info fuer einen Task zurueck (oder None)."""
    info = _AGENT_REGISTRY.get(task_id)
    if info and _is_process_alive(info.get("pid")):
        return info
    return None


def list_active_agents() -> list:
    """Listet alle aktiven Sub-Agent-Prozesse."""
    active = []
    for task_id, info in list(_AGENT_REGISTRY.items()):
        if _is_process_alive(info.get("pid")):
            active.append({
                "task_id": task_id,
                "pid": info["pid"],
                "role": info["role"],
                "spawned_at": info["spawned_at"],
                "log_path": info["log_path"],
                "uptime_s": time.time() - info["spawned_at"],
            })
    return active


def cleanup_dead_agents() -> int:
    """Entfernt abgestuerzte Agenten aus der Registry. Gibt Anzahl zurueck."""
    cleaned = 0
    for task_id in list(_AGENT_REGISTRY.keys()):
        if not _is_process_alive(_AGENT_REGISTRY[task_id].get("pid")):
            _AGENT_REGISTRY.pop(task_id, None)
            cleaned += 1
    return cleaned


# Helper, weil TaskService statisch ist
def TaskService_add_history_safe(db: Session, t: Task, event: str, agent: str, details: Dict[str, Any]):
    """Wrapper fuer TaskService._add_history (vermeidet zirkulaere Imports)."""
    from .task_service import TaskService
    return TaskService._add_history(db, t, event, agent=agent, details=details)
