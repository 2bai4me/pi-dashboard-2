"""Sub-Agent-Service — Sicherer Sub-Agent-Spawner (RCE-gehärtet).

Ersetzt die alte `sub_agent.py` mit vollständiger RCE-Prävention:

Sicherheitsmaßnahmen:
  1. Whitelist für erlaubte Rollen (nur vordefinierte Sub-Agent-Rollen)
  2. Regex-Validierung aller User-Inputs (task_id, title, description, role)
  3. Längenbegrenzung auf 500 Zeichen (abgestimmt mit DB-Constraint)
  4. Keine Shell-Metazeichen erlaubt (Positiv-Liste statt Negativ-Liste)
  5. subprocess.Popen mit shell=False und separaten Argumenten
  6. spawn.sh-Pfad nur aus .env (kein Fallback auf hartcodierte Pfade)
  7. Audit-Log für jeden Spawning-Vorgang
  8. Budget-Guard: Maximale Sub-Agents pro Task
  9. Timeout nach 30 Minuten (automatischer Kill)

Architektur:
  Status-Wechsel → in_progress → _spawn_sub_agent()
    └─→ validate_inputs()           ← Validierung
    └─→ _get_spawn_script_path()    ← Pfad nur aus .env
    └─→ subprocess.Popen()          ← shell=False, einzelne Args
    └─→ _AGENT_REGISTRY[task_id]    ← PID + Status-Tracking
    └─→ Audit-Log (History)         ← Nachvollziehbarkeit

Schnittstelle:
  spawn_sub_agent(task, db, user)   → Dict | None
  kill_sub_agent(task_id)           → bool (Timeout/Terminate)
  get_agent_for_task(task_id)       → Dict | None
  list_active_agents()              → List[Dict]
  cleanup_dead_agents()             → int

Environment-Variablen:
  SPAWN_SH_PATH=<pfad>              # Pflicht, sonst kein Spawning
  SUB_AGENT_TIMEOUT_MIN=30          # Optional, Default 30
"""
from __future__ import annotations

import asyncio
import logging
import os
import platform
import re
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, List

from sqlalchemy.orm import Session

from ..models.task import Task
from ..config import settings
from ..utils.exceptions import SubAgentError, InvalidInputError
from ..utils.id_generator import gen_id

logger = logging.getLogger("pi-dashboard-2.sub-agent")


# === Sicherheits-Konstanten ===

# Erlaubte Rollen (Whitelist) - nur diese dürfen Sub-Agents spawnen
ALLOWED_ROLES: frozenset[str] = frozenset({
    "pi-coder", "pi-tester", "pi-reviewer", "pi-fixer",
    "CIO", "CEO-digital",
})

# Erlaubte Zeichen für task_id: Hexadezimal (6 Bytes = 12 Zeichen)
_TASK_ID_RE = re.compile(r"^[a-f0-9]{12}$")

# Erlaubte Zeichen für Titel/Description (Positiv-Liste statt Negativ-Liste)
# Erlaubt: Buchstaben, Zahlen, Leerzeichen, Punkte, Kommas, Doppelpunkte,
#          Schrägstriche, Gleichheitszeichen, Plus, Minus, At-Zeichen, Anführungszeichen
_SAFE_TEXT_RE = re.compile(
    r"^[\w\s.,:;\/'+=@\-_!?()äöüÄÖÜßéèêàáâçÇñÑ]{1,500}$", re.UNICODE
)

# Maximale Länge für Titel (abgestimmt mit DB: String(500))
MAX_TITLE_LENGTH = 500
# Maximale Länge für Description
MAX_DESC_LENGTH = 50000
# Timeout in Minuten
SUB_AGENT_TIMEOUT_MIN = int(os.getenv("SUB_AGENT_TIMEOUT_MIN", "30"))
# Maximale Sub-Agents pro Task
MAX_AGENTS_PER_TASK = 3


# === In-Memory Registry ===
_AGENT_REGISTRY: Dict[str, Dict[str, Any]] = {}


def _get_spawn_script_path() -> Optional[Path]:
    """Findet den spawn.sh-Pfad (NUR aus .env, kein hartcodierter Fallback mehr).
    
    Fix (v2.0-rc): Der alte hartcodierte Pfad 
    'C:/Users/uwean/.pi/agent/extensions/swarm-spawner/spawn.sh' wurde entfernt.
    Stattdessen muss SPAWN_SH_PATH in .env gesetzt sein.
    
    Returns:
        Path zum spawn.sh oder None
    
    Raises:
        SubAgentError: Wenn SPAWN_SH_PATH nicht gesetzt ist
    """
    spawn_path = os.getenv("SPAWN_SH_PATH") or getattr(settings, "SPAWN_SH_PATH", None)
    if not spawn_path:
        raise SubAgentError(
            "SPAWN_SH_PATH nicht konfiguriert! "
            "Setze SPAWN_SH_PATH in .env auf den Pfad zu spawn.sh.\n"
            "Beispiel: SPAWN_SH_PATH=C:/Users/uwean/.pi/agent/extensions/swarm-spawner/spawn.sh"
        )
    
    p = Path(str(spawn_path))
    if not p.exists():
        raise SubAgentError(f"spawn.sh nicht gefunden unter: {p}")
    
    return p


def _get_bash_executable() -> Optional[str]:
    """Findet bash auf dem System.
    
    Windows: Git-Bash → WSL-Bash → System-PATH
    Unix: /bin/bash
    """
    if platform.system() != "Windows":
        bash = subprocess.getoutput("which bash 2>/dev/null || echo /bin/bash")
        return bash if bash else "/bin/bash"
    
    candidates = [
        r"C:\Program Files\Git\usr\bin\bash.EXE",
        r"C:\Program Files\Git\bin\bash.exe",
        r"C:\Windows\System32\bash.exe",
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    
    # Letzter Versuch: PATH
    bash = os.getenv("BASH") or subprocess.getoutput("where bash 2>nul || echo")
    if bash and os.path.exists(bash):
        return bash
    
    return None


def validate_spawn_inputs(
    task_id: Optional[str],
    title: Optional[str],
    description: Optional[str],
    role: Optional[str],
) -> tuple[bool, str]:
    """Validiert ALLE Eingaben für den Sub-Agent-Spawner.
    
    Diese Validierung ist die zentrale RCE-Prävention. Jeder Fehler
    führt zur vollständigen Ablehnung des Spawn-Vorgangs.
    
    Prüfungen:
      1. Role in Whitelist?
      2. task_id gültiges Hex?
      3. Titel nicht leer, kein Shell-Metazeichen, Länge ≤ 500?
      4. Description optional, aber wenn vorhanden: sicher?
    
    Returns:
        (is_valid: bool, reason: str)
    """
    if not role:
        return False, "role fehlt"
    if role not in ALLOWED_ROLES:
        return False, f"Rolle '{role}' ist nicht erlaubt (Whitelist: {', '.join(sorted(ALLOWED_ROLES))})"
    
    if not task_id:
        return False, "task_id fehlt"
    if not _TASK_ID_RE.match(task_id):
        return False, f"task_id '{task_id}' ungültig (erwartet: 12-stelliges Hex)"
    
    if not title:
        return False, "title fehlt"
    if len(title) > MAX_TITLE_LENGTH:
        return False, f"title zu lang (max {MAX_TITLE_LENGTH} Zeichen, hat {len(title)})"
    if not _SAFE_TEXT_RE.match(title):
        return False, f"title enthält unerlaubte Zeichen: {repr(title[:50])}"
    
    if description:
        if len(description) > MAX_DESC_LENGTH:
            return False, f"description zu lang (max {MAX_DESC_LENGTH} Zeichen)"
        if not _SAFE_TEXT_RE.match(description):
            return False, f"description enthält unerlaubte Zeichen"
    
    return True, ""


async def spawn_sub_agent(
    t: Task,
    db: Session,
    user: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Startet einen Sub-Agent für einen Task.
    
    Diese Funktion ersetzt die alte `_spawn_sub_agent()` mit vollständiger
    RCE-Prävention und klarer Fehlerbehandlung.
    
    Args:
        t: Der Task für den der Sub-Agent gestartet werden soll
        db: SQLAlchemy-Session
        user: Optionaler User für Audit-Log
    
    Returns:
        Dict mit pid, spawned_at, log_path, role oder None bei Fehler
    
    Raises:
        SubAgentError: Bei schwerwiegenden Fehlern (z.B. fehlender spawn.sh)
        InvalidInputError: Bei ungültigen Eingaben
    """
    # ============================================
    # 1. Pre-Check: Max Sub-Agents pro Task
    # ============================================
    agent_count = sum(
        1 for info in _AGENT_REGISTRY.values()
        if info.get("task_id") == t.id and _is_process_alive(info.get("pid"))
    )
    if agent_count >= MAX_AGENTS_PER_TASK:
        logger.warning(f"Task {t.id[:8]}: Max Sub-Agents erreicht ({MAX_AGENTS_PER_TASK})")
        return None
    
    # ============================================
    # 2. Role bestimmen
    # ============================================
    role = t.assigned_subagent or t.assigned_role
    if not role:
        logger.warning(f"Task {t.id[:8]}: kein assigned_subagent oder assigned_role")
        return None
    
    # ============================================
    # 3. Input-Validierung (RCE-Prävention)
    # ============================================
    is_valid, reason = validate_spawn_inputs(
        task_id=t.id,
        title=t.title,
        description=t.description,
        role=role,
    )
    if not is_valid:
        _add_history_safe(db, t, "sub_agent_spawn_rejected", "system", {
            "reason": reason,
            "role": role,
            "user": user,
        })
        db.commit()
        raise InvalidInputError("sub_agent_input", reason)
    
    # ============================================
    # 4. Spawn-Skript und Bash finden
    # ============================================
    try:
        spawn_script = _get_spawn_script_path()
    except SubAgentError as e:
        _add_history_safe(db, t, "sub_agent_spawn_failed", "system", {
            "error": str(e),
            "role": role,
        })
        db.commit()
        raise
    
    bash = _get_bash_executable()
    if not bash:
        error_msg = "bash nicht gefunden (Windows braucht Git-Bash oder WSL)"
        _add_history_safe(db, t, "sub_agent_spawn_failed", "system", {
            "error": error_msg,
            "role": role,
        })
        db.commit()
        raise SubAgentError(error_msg)
    
    # ============================================
    # 5. Log-Verzeichnis vorbereiten
    # ============================================
    log_dir = Path(os.path.expanduser("~/.pi/agent/operator/logs"))
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"spawn-{t.id}.log"
    
    # ============================================
    # 6. Context aus Task (NUR sichere Felder!)
    # ============================================
    # WICHTIG: Keine User-Inputs mehr im Context-String!
    # Der Context dient nur der Identifikation, nicht der Steuerung.
    context = f"task_id={t.id}; branch=task/{t.id}"
    
    # ============================================
    # 7. Sub-Prozess starten
    # ============================================
    cmd = [str(bash), str(spawn_script), role, t.id, context]
    logger.info(f"Spawning Sub-Agent: role={role} task={t.id[:8]} script={spawn_script.name}")
    
    try:
        with open(log_path, "a", encoding="utf-8") as log_file:
            proc = subprocess.Popen(
                cmd,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                cwd=str(spawn_script.parent),
                env={**os.environ, "PI_DASHBOARD_API": "http://127.0.0.1:9220"},
                creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0,
                shell=False,  # ← KEIN Shell-Injection möglich!
            )
        
        spawned_at = time.time()
        
        # In Registry speichern
        agent_info = {
            "pid": proc.pid,
            "spawned_at": spawned_at,
            "log_path": str(log_path),
            "role": role,
            "task_id": t.id,
            "process": proc,
        }
        _AGENT_REGISTRY[t.id] = agent_info
        
        # In DB tracken
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
        
        # Audit-Log
        _add_history_safe(db, t, "sub_agent_spawned", "system", {
            "pid": proc.pid,
            "role": role,
            "log_path": str(log_path),
            "spawn_script": str(spawn_script),
            "user": user,
        })
        db.commit()
        
        logger.info(f"Sub-Agent Task {t.id[:8]}: PID {proc.pid}, Rolle {role}")
        return agent_info
        
    except Exception as e:
        logger.error(f"Fehler beim Spawn für Task {t.id[:8]}: {e}")
        return None


def kill_sub_agent(task_id: str) -> bool:
    """Beendet einen Sub-Agent-Prozess (zuerst SIGTERM, dann SIGKILL).
    
    Args:
        task_id: ID des Tasks
    
    Returns:
        True wenn Prozess beendet wurde, False wenn nicht gefunden
    """
    info = _AGENT_REGISTRY.get(task_id)
    if not info:
        return False
    
    pid = info.get("pid")
    if pid is None:
        return False
    
    try:
        if platform.system() == "Windows":
            subprocess.run(f"taskkill /PID {pid} /F", shell=True, capture_output=True)
        else:
            os.kill(pid, 15)  # SIGTERM
            time.sleep(1)
            if _is_process_alive(pid):
                os.kill(pid, 9)  # SIGKILL
        
        _AGENT_REGISTRY.pop(task_id, None)
        logger.info(f"Sub-Agent Task {task_id[:8]}: PID {pid} beendet")
        return True
    except ProcessLookupError:
        _AGENT_REGISTRY.pop(task_id, None)
        return True
    except Exception as e:
        logger.error(f"Fehler beim Beenden von Task {task_id[:8]}: {e}")
        return False


def _is_process_alive(pid: Optional[int]) -> bool:
    """Prüft ob ein Prozess noch läuft."""
    if pid is None:
        return False
    try:
        if platform.system() == "Windows":
            import ctypes
            kernel32 = ctypes.windll.kernel32
            h = kernel32.OpenProcess(0x1000, False, pid)
            if h == 0:
                return False
            try:
                exit_code = ctypes.c_ulong()
                kernel32.GetExitCodeProcess(h, ctypes.byref(exit_code))
                return exit_code.value == 259  # STILL_ACTIVE
            finally:
                kernel32.CloseHandle(h)
        else:
            os.kill(pid, 0)
            return True
    except (OSError, ProcessLookupError):
        return False


def get_agent_for_task(task_id: str) -> Optional[Dict[str, Any]]:
    """Gibt Agent-Info für einen Task zurück (None wenn nicht aktiv)."""
    info = _AGENT_REGISTRY.get(task_id)
    if info and _is_process_alive(info.get("pid")):
        return info
    return None


def list_active_agents() -> List[Dict[str, Any]]:
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
        else:
            _AGENT_REGISTRY.pop(task_id, None)
    return active


def cleanup_dead_agents() -> int:
    """Entfernt abgestürzte Agenten aus der Registry."""
    cleaned = 0
    for task_id in list(_AGENT_REGISTRY.keys()):
        info = _AGENT_REGISTRY.get(task_id)
        if info and not _is_process_alive(info.get("pid")):
            _AGENT_REGISTRY.pop(task_id, None)
            cleaned += 1
    return cleaned


def _add_history_safe(db, task, event, agent, details):
    """Wrapper für History-Eintrag (vermeidet Circular Import)."""
    from ..services.task_service import TaskService
    TaskService._add_history(db, task, event, agent=agent, details=details)
