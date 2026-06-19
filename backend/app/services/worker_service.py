"""Worker-Service — LLM-basierter automatischer Task-Worker.

Im MVP (Phase 1) macht der Worker:
1. Holt naechsten `todo`-Task mit hoechster Prioritaet
2. LLM-Call mit Task-Kontext
3. LLM generiert einen PLAN (was zu tun ist)
4. Speichert Plan in task.meta.worker_plan
5. Setzt Status auf `in_progress` (Worker claimed)
6. Nach Plan-Erstellung: Status auf `review` (Tester prueft)
7. Bei Fehler: Status auf `rueckfrage` mit Fehler-Log

Phase 2 (spaeter) kann echte Code-Edits hinzufuegen.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import platform
import shlex
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Any, Dict

from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy.orm import Session
from sqlalchemy import select

from ..db.base import SessionLocal
from ..models.task import Task
from ..models.history import TaskHistory
from ..services.llm_service import chat_completion

logger = logging.getLogger("pi-dashboard-2.worker")

# === PHASE 2: pi-CLI Sub-Agent Konfiguration ===
# Default: MiniMax M3 (Pflicht laut Kanban-Operator Skill).
# kimi-coding kann via ENV aktiviert werden, falls Authentifizierung funktioniert.
PI_BIN: str = os.environ.get("PI_BIN", shutil.which("pi") or "pi")
CODE_AGENT_MODEL: str = os.environ.get("CODE_AGENT_MODEL", "minimax-m3")
CODE_AGENT_PROVIDER: str = os.environ.get("CODE_AGENT_PROVIDER", "minimax-direct")
CODE_AGENT_TIMEOUT_SEC: int = int(os.environ.get("CODE_AGENT_TIMEOUT_SEC", "7200"))
CODE_AGENT_CWD: Path = Path(os.environ.get("CODE_AGENT_CWD", "D:/Entwicklung/PI-Dashboard 2"))
CODE_AGENT_API_URL: str = os.environ.get("CODE_AGENT_API_URL", "http://127.0.0.1:9220")
CODE_AGENT_API_TOKEN: str = os.environ.get("CODE_AGENT_API_TOKEN", "dev")
CODE_AGENT_LOG_DIR: Path = Path(os.environ.get(
    "CODE_AGENT_LOG_DIR",
    str(Path.home() / ".pi" / "agent" / "operator" / "logs"),
))
CODE_AGENT_MAX_COST_USD: float = float(os.environ.get("CODE_AGENT_MAX_COST_USD", "0.50"))


class WorkerService:
    """Worker-Service fuer automatische Task-Bearbeitung."""

    # Max Iterationen pro Task (Safety-Bruch gegen Endlosschleifen)
    MAX_ITERATIONS = 5

    @staticmethod
    def claim_next_task(project_id: Optional[str] = None) -> Optional[Task]:
        """Holt den naechsten `todo`-Task mit hoechster Prioritaet.

        Args:
            project_id: Optional, einschraenken auf ein Projekt

        Returns:
            Der naechste Task oder None

        Fix (User-Direktive 18.06.2026): Filtert auf DB-Key 'todo' (nicht 'go').
        Die Phase heisst im Display 'GO', intern bleibt sie 'todo'.
        """
        from .session_helper import get_session_id

        with SessionLocal() as db:
            # WICHTIG: DB-Key 'todo' (nicht 'go'!) - siehe User-Direktive 18.06.2026
            query = db.query(Task).filter(Task.status == "todo")
            if project_id:
                query = query.filter(Task.project_id == project_id)
            # Hoechste Prioritaet zuerst
            task = query.order_by(Task.priority.desc(), Task.created_at).first()
            if task:
                # Atomic Update mit Optimistic Lock
                old_status = task.status
                task.status = "in_progress"
                task.updated_at = datetime.utcnow()
                # Iteration-Counter erhoehen
                task.iteration_count = (task.iteration_count or 0) + 1
                # History
                th = TaskHistory(
                    task_id=task.id,
                    event="worker_claimed",
                    agent="worker-auto",
                    session_id=get_session_id(),
                    details={
                        "from": old_status,
                        "to": "in_progress",
                        "iteration": task.iteration_count,
                        "reason": "auto_worker_claimed",
                    },
                )
                db.add(th)
                db.commit()
                db.refresh(task)
                logger.info(
                    f"Worker claimed task {task.id} (prio={task.priority}, iter={task.iteration_count}, session={get_session_id()})"
                )
                return task
            return None

    @staticmethod
    async def execute_task(task: Task) -> dict:
        """Fuehrt einen Task via LLM aus.

        Im MVP: Generiert einen Plan und speichert ihn in task.meta.worker_plan.
        Phase 2: Wird echte Code-Edits ausfuehren.

        Returns:
            dict mit {"ok": bool, "plan": str, "error": str}
        """
        # Safety: Max Iterationen
        if (task.iteration_count or 0) > WorkerService.MAX_ITERATIONS:
            logger.warning(
                f"Task {task.id} hat Max-Iterations ({WorkerService.MAX_ITERATIONS}) erreicht"
            )
            return WorkerService._fail_task(
                task, f"Max-Iterations ({WorkerService.MAX_ITERATIONS}) erreicht"
            )

        # Baue LLM-Prompt
        sc = task.success_criteria
        if isinstance(sc, str):
            try:
                sc = json.loads(sc)
            except Exception:
                sc = []
        sc = sc or []
        if not isinstance(sc, list):
            sc = []

        criteria_text = "\n".join(f"- {c}" for c in sc) if sc else "- (keine Kriterien definiert)"

        system_prompt = """Du bist ein erfahrener PI-Worker-Agent. Deine Aufgabe ist es, einen detaillierten Plan zu erstellen, wie ein Task umgesetzt wird.

**Wichtige Regeln:**
1. Erstelle einen SCHRITT-FUER-SCHRITT-Plan (3-7 Schritte)
2. Jeder Schritt hat: AKTION + DATEI + ERGEBNIS
3. Beruecksichtige die Erfolgskriterien
4. Erwaehne Tests, die geschrieben/geprueft werden muessen
5. Antworte NUR mit dem JSON-Objekt, ohne zusaetzlichen Text

**Antwort-Format (STRIKTE JSON):**
```json
{
  "plan_summary": "Kurze Zusammenfassung des Plans (1-2 Saetze)",
  "steps": [
    {
      "step": 1,
      "action": "Was wird getan",
      "files": ["betroffene Dateien"],
      "expected": "Was am Ende dieses Schritts rauskommt"
    }
  ],
  "tests": ["Welche Tests werden geschrieben/ausgefuehrt"],
  "estimated_minutes": 15,
  "risks": ["Moegliche Risiken"]
}
```
"""
        user_prompt = f"""**Task-Titel:** {task.title}

**Task-Description:**
{task.description or '(keine Beschreibung)'}

**Kategorie:** {task.category or 'unbekannt'}
**Prioritaet:** {task.priority}

**Erfolgskriterien (muss erfuellt sein):**
{criteria_text}

**Iteration:** {task.iteration_count}

Erstelle einen detaillierten Umsetzungs-Plan."""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        try:
            # LLM-Call (sync Wrapper, da chat_completion async ist)
            llm_response = await WorkerService._call_llm(messages)
            response_text = llm_response.get("content", "")
            llm_model = llm_response.get("model", "minimax-m3")
            llm_provider = llm_response.get("provider", "minimax")
            llm_usage = llm_response.get("usage", {"tokens_in": 0, "tokens_out": 0})
            logger.info(
                f"LLM Response fuer Task {task.id}: {len(response_text)}b, "
                f"tokens_in={llm_usage.get('tokens_in', 0)}, "
                f"tokens_out={llm_usage.get('tokens_out', 0)}"
            )

            # Parse JSON
            try:
                # Versuche, JSON aus der Response zu extrahieren
                plan_data = WorkerService._extract_json(response_text)
            except Exception as e:
                logger.warning(f"JSON-Parse fehlgeschlagen fuer Task {task.id}: {e}")
                plan_data = {
                    "plan_summary": "Plan-Erstellung fehlgeschlagen (kein JSON)",
                    "raw_response": response_text[:1000],
                    "steps": [],
                    "tests": [],
                }

            # === User-Direktive 19.06.2026: Token-Usage persistieren ===
            # Schreibt in token_usage-Tabelle fuer Performance-Analytics.
            with SessionLocal() as usage_db:
                try:
                    WorkerService._persist_token_usage(
                        usage_db, task,
                        model=llm_model,
                        provider=llm_provider,
                        role=task.assigned_role or "worker",
                        tokens_in=llm_usage.get("tokens_in", 0),
                        tokens_out=llm_usage.get("tokens_out", 0),
                    )
                    logger.info(f"Token-Usage fuer Task {task.id} persistiert")
                except Exception as usage_err:
                    logger.warning(f"Token-Usage-Persistierung fehlgeschlagen: {usage_err}")

            # === PHASE 2: Plan speichern + pi-CLI Code-Agent dispatchen ===
            # Plan wird in meta gespeichert, aber Task bleibt in in_progress.
            # Der pi-CLI Sub-Agent fuehrt anschliessend echte Code-Edits durch
            # und meldet sich via /dispatch Endpoint zurueck.
            from .session_helper import get_session_id

            with SessionLocal() as plan_db:
                t = plan_db.get(Task, task.id)
                if t:
                    meta = dict(t.meta or {})
                    meta["worker_plan"] = plan_data
                    meta["worker_iteration"] = t.iteration_count or 0
                    meta["worker_planned_at"] = datetime.utcnow().isoformat()
                    meta["phase_2_code_edit"] = True
                    t.meta = meta
                    flag_modified(t, "meta")
                    t.updated_at = datetime.utcnow()
                    plan_db.add(TaskHistory(
                        task_id=t.id,
                        ts=datetime.utcnow(),
                        event="worker_planned",
                        agent="worker-auto",
                        session_id=get_session_id(),
                        details={
                            "status": "in_progress",
                            "plan_summary": plan_data.get("plan_summary", ""),
                            "steps_count": len(plan_data.get("steps", [])),
                            "iteration": t.iteration_count or 0,
                            "phase_2": True,
                        },
                    ))
                    plan_db.commit()
                    logger.info(
                        f"[PHASE 2] Plan fuer Task {t.id[:8]} gespeichert ({len(plan_data.get('steps', []))} Schritte)"
                    )

            # pi-CLI Code-Agent starten (asynchron, non-blocking)
            agent_info = WorkerService._spawn_pi_code_agent(task, plan_data)
            if agent_info:
                logger.info(
                    f"[PHASE 2] Task {task.id[:8]} bleibt in in_progress, Code-Agent PID {agent_info['pid']} arbeitet"
                )
                return {
                    "ok": True,
                    "plan": plan_data,
                    "code_agent": agent_info,
                    "phase": 2,
                }
            else:
                logger.warning(
                    f"[PHASE 2] Code-Agent-Spawn fehlgeschlagen fuer Task {task.id[:8]}. "
                    "Falle zurueck auf Plan-only-Modus (Status -> review)."
                )
                # Fallback: alter Plan-only-Modus
                WorkerService._save_plan(task, plan_data)
                try:
                    await WorkerService._trigger_next_sop_step(task)
                except Exception as e:
                    logger.warning(f"Task {task.id}: Engine-Trigger fehlgeschlagen: {e}")
                return {"ok": True, "plan": plan_data, "phase": 1, "warning": "code_agent_spawn_failed"}

        except Exception as e:
            logger.error(f"Worker-Call fehlgeschlagen fuer Task {task.id}: {e}")
            return WorkerService._fail_task(task, str(e))

    @staticmethod
    async def _call_llm(messages: list) -> Dict[str, Any]:
        """Synchroner LLM-Call (blockierend). Gibt Dict mit content + usage zurueck.

        Returns: {
            "content": str (LLM-Response),
            "model": "minimax-m3",
            "provider": "minimax",
            "usage": {"tokens_in": int, "tokens_out": int}
        }
        """
        # chat_completion ist async — also blocking
        result = await chat_completion(
            messages=messages,
            model="minimax-m3",
            temperature=0.3,
            max_tokens=2000,
        )
        # Wenn chat_completion schon ein Dict mit usage-Feld zurueckgibt
        if isinstance(result, dict):
            return {
                "content": result.get("content", result.get("text", str(result))),
                "model": "minimax-m3",
                "provider": result.get("provider", "minimax"),
                "usage": result.get("usage", {"tokens_in": 0, "tokens_out": 0}),
            }
        # Fallback: alter String-Return (falls llm_service noch nicht erweitert)
        return {
            "content": str(result),
            "model": "minimax-m3",
            "provider": "minimax",
            "usage": {"tokens_in": 0, "tokens_out": 0},
        }
        return str(result)

    @staticmethod
    def _extract_json(text: str) -> dict:
        """Extrahiert JSON aus LLM-Response (ignoriert Markdown-Wrapped)."""
        # Versuche direkt
        try:
            return json.loads(text)
        except Exception:
            pass
        # Versuche mit Code-Block-Extraktion
        import re
        m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except Exception:
                pass
        # Versuche erstes {...}
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except Exception:
                pass
        # Fallback
        return {"raw_response": text, "parse_error": True}

    @staticmethod
    def _save_plan(task: Task, plan_data: dict) -> None:
        """Speichert den Plan in task.meta.worker_plan und setzt Status auf review."""
        from .session_helper import get_session_id

        with SessionLocal() as db:
            t = db.get(Task, task.id)
            if not t:
                return
            meta = dict(t.meta or {})
            meta["worker_plan"] = plan_data
            meta["worker_iteration"] = (t.iteration_count or 0)
            meta["worker_planned_at"] = datetime.utcnow().isoformat()
            t.meta = meta
            flag_modified(t, "meta")
            # Status -> review
            old_status = t.status
            t.status = "review"
            t.updated_at = datetime.utcnow()
            # History
            th = TaskHistory(
                task_id=t.id,
                session_id=get_session_id(),
                event="worker_planned",
                agent="worker-auto",
                details={
                    "from": old_status,
                    "to": "review",
                    "plan_summary": plan_data.get("plan_summary", ""),
                    "steps_count": len(plan_data.get("steps", [])),
                    "iteration": t.iteration_count or 0,
                },
            )
            db.add(th)
            db.commit()
            logger.info(
                f"Worker hat Plan fuer Task {t.id} erstellt -> Status: review ({len(plan_data.get('steps', []))} Schritte)"
            )

    @staticmethod
    def _fail_task(task: Task, error: str) -> dict:
        """Setzt Task auf rueckfrage mit Fehler-Log."""
        from .session_helper import get_session_id

        with SessionLocal() as db:
            t = db.get(Task, task.id)
            if not t:
                return {"ok": False, "error": "Task not found"}
            meta = dict(t.meta or {})
            meta["worker_error"] = error
            meta["worker_failed_at"] = datetime.utcnow().isoformat()
            t.meta = meta
            flag_modified(t, "meta")
            old_status = t.status
            t.status = "rueckfrage"
            t.updated_at = datetime.utcnow()
            th = TaskHistory(
                task_id=t.id,
                session_id=get_session_id(),
                event="worker_failed",
                agent="worker-auto",
                details={"from": old_status, "to": "rueckfrage", "error": error[:500]},
            )
            db.add(th)
            db.commit()
            logger.error(f"Worker fehlgeschlagen fuer Task {t.id}: {error[:100]}")
            return {"ok": False, "error": error}

    @staticmethod
    async def _trigger_next_sop_step(task: Task) -> Dict[str, Any]:
        """Triggert den naechsten SOP-Step nach Plan-Erstellung (User-Direktive 19.06.2026).

        Reihenfolge:
          1) Bestehende SOP-Instance fuer diesen Task suchen
          2) Falls keine: neue Instance mit Standard-Workflow-SOP starten
          3) SOP-Engine run_step() aufrufen
          4) Tester-Step oder naechster Step laeuft automatisch
          5) Return: {instance_id, run_result, instance_status}

        Wird nach worker_planned aufgerufen, damit der naechste Step
        (normalerweise Tester Code-Review) automatisch startet.
        """
        from .sop_engine import SOPEngine
        from ..models.sop import SOPInstance, SOP

        # 1) Bestehende Instance suchen
        with SessionLocal() as db:
            existing = db.execute(
                select(SOPInstance)
                .where(SOPInstance.task_id == task.id)
                .where(SOPInstance.status.in_(["running", "waiting_sub_sop"]))
                .order_by(SOPInstance.started_at.desc())
            ).scalars().first()

            if existing:
                instance = existing
                logger.info(f"Task {task.id[:8]}: Bestehende SOP-Instance {instance.id} gefunden")
            else:
                # 2) Neue Instance starten (Standard-Workflow Task = 7c86692be939)
                DEFAULT_SOP_ID = "7c86692be939"
                sop = db.get(SOP, DEFAULT_SOP_ID)
                if not sop:
                    logger.warning(f"Task {task.id[:8]}: Standard-SOP nicht gefunden, ueberspringe SOP-Trigger")
                    return {"ok": False, "error": "default_sop_not_found"}

                engine = SOPEngine(db)
                instance = engine.create_instance(
                    sop_id=DEFAULT_SOP_ID,
                    project_id=task.project_id,
                    task_id=task.id,
                    context={"triggered_by": "worker_service", "plan_generated": True},
                )
                if not instance:
                    logger.warning(f"Task {task.id[:8]}: Konnte SOP-Instance nicht starten")
                    return {"ok": False, "error": "instance_creation_failed"}
                logger.info(f"Task {task.id[:8]}: SOP-Instance {instance.id} erstellt")

            instance_id = instance.id
            current_step = instance.current_step_id

            # 3) Engine: run_step aufrufen
            engine = SOPEngine(db)
            result = await engine.run_step(instance)
            db.commit()

            # 4) Status zurueckgeben
            instance = db.get(SOPInstance, instance_id)
            return {
                "ok": result.get("ok", False),
                "instance_id": instance_id,
                "current_step_before": current_step,
                "current_step_after": instance.current_step_id if instance else None,
                "instance_status": instance.status if instance else None,
                "result": result,
            }

    @staticmethod
    def _spawn_pi_code_agent(task: Task, plan_data: dict) -> Optional[Dict[str, Any]]:
        """Startet die externe pi-CLI als Code-Editor Sub-Agent (PHASE 2).

        Der Sub-Agent arbeitet asynchron im Hintergrund und fuehrt echte
        Code-Edits durch (read/write/edit/bash). Er benutzt das kimi-coding
        Modell. Der Prozess wird ueber agent_pid getrackt.

        Returns:
            Dict mit pid, log_path, cmd, role, model bei Erfolg, sonst None.
        """
        from .session_helper import get_session_id

        task_id = task.id
        role = task.assigned_role or "pi-coder"
        log_dir = CODE_AGENT_LOG_DIR
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / f"pi-code-agent-{task_id}.log"

        # Build prompt fuer pi-CLI
        plan_json = json.dumps(plan_data, ensure_ascii=False, indent=2)
        criteria = task.success_criteria or []
        if isinstance(criteria, str):
            try:
                criteria = json.loads(criteria)
            except Exception:
                criteria = []
        criteria_text = "\n".join(f"- {c}" for c in criteria) if criteria else "- (keine Kriterien)"

        system_prompt = f"""Du bist {role}. Bearbeite den folgenden Task vollstaendig autonom.

Task-ID: {task_id}
Titel: {task.title}

Beschreibung:
{task.description or '(keine Beschreibung)'}

Erfolgskriterien:
{criteria_text}

Geplanter Umsetzungsplan:
{plan_json}

Arbeitsanweisungen:
1. Arbeite im Projekt-Verzeichnis: {CODE_AGENT_CWD}
2. Lies relevante Dateien, verstehe den Kontext.
3. Fuehre die Aenderungen aus dem Plan Schritt fuer Schritt durch.
4. Nutze die Tools read, write, edit, bash.
5. Schreibe/aktualisiere Tests falls im Plan vorgesehen.
6. Fuehre Build/Type-Check/Lint aus, falls sinnvoll.
7. Budget-Limit: {CODE_AGENT_MAX_COST_USD} USD. Wenn ueberschritten: stoppe und melde Fehler.
8. Wenn fertig, melde Status zurueck:
   curl -s -X PATCH "{CODE_AGENT_API_URL}/api/kanban/tasks/{task_id}/dispatch" \\
     -H "Authorization: Bearer {CODE_AGENT_API_TOKEN}" \\
     -H "Content-Type: application/json" \\
     -d '{{"status":"review","role":"{role}","model":"{CODE_AGENT_PROVIDER}/{CODE_AGENT_MODEL}","reason":"pi-code-agent-done"}}'

Arbeite vollautonom ohne Rueckfragen."""

        # Wrapper-Script verwenden, um Bash-Quoting-Probleme mit langen
        # System-Prompts zu vermeiden. Der Wrapper liest Task aus der API
        # und startet pi-CLI sauber.
        wrapper_script = Path(__file__).resolve().parent.parent.parent / "scripts" / "pi_code_agent_wrapper.py"
        cmd = [
            "C:/Python314/python.exe",
            str(wrapper_script),
            task_id,
            "--api-url", CODE_AGENT_API_URL,
            "--token", CODE_AGENT_API_TOKEN,
            "--model", CODE_AGENT_MODEL,
            "--provider", CODE_AGENT_PROVIDER,
            "--budget", str(CODE_AGENT_MAX_COST_USD),
            "--log", str(log_path),
        ]

        env = {
            **os.environ,
            "NO_COLOR": "1",
            "CODE_AGENT_API_URL": CODE_AGENT_API_URL,
            "CODE_AGENT_API_TOKEN": CODE_AGENT_API_TOKEN,
            "CODE_AGENT_MODEL": CODE_AGENT_MODEL,
            "CODE_AGENT_PROVIDER": CODE_AGENT_PROVIDER,
            "CODE_AGENT_MAX_COST_USD": str(CODE_AGENT_MAX_COST_USD),
        }
        try:
            with open(log_path, "w", encoding="utf-8") as lf:
                lf.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] START task={task_id} role={role} model={CODE_AGENT_PROVIDER}/{CODE_AGENT_MODEL}\n")
                lf.write(f"CMD: {' '.join(str(c) for c in cmd)}\n")
                lf.flush()
                proc = subprocess.Popen(
                    cmd,
                    stdout=lf,
                    stderr=subprocess.STDOUT,
                    stdin=subprocess.DEVNULL,
                    text=True,
                    env=env,
                    cwd=str(CODE_AGENT_CWD),
                    creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0,
                )
        except Exception as e:
            logger.error(f"[PHASE 2] pi-CLI Sub-Agent start fehlgeschlagen fuer {task_id[:8]}: {e}")
            return None

        agent_info = {
            "pid": proc.pid,
            "log_path": str(log_path),
            "cmd": " ".join(str(c) for c in cmd),
            "role": role,
            "model": f"{CODE_AGENT_PROVIDER}/{CODE_AGENT_MODEL}",
            "started_at": datetime.utcnow().isoformat(),
        }

        # Task-Metadaten aktualisieren
        with SessionLocal() as db:
            t = db.get(Task, task_id)
            if t:
                meta = dict(t.meta or {})
                meta["code_agent"] = {
                    "pid": proc.pid,
                    "role": role,
                    "model": f"{CODE_AGENT_PROVIDER}/{CODE_AGENT_MODEL}",
                    "log_path": str(log_path),
                    "status": "dispatched",
                    "started_at": datetime.utcnow().isoformat(),
                    "budget_limit_usd": CODE_AGENT_MAX_COST_USD,
                }
                t.meta = meta
                flag_modified(t, "meta")
                t.assigned_subagent = role
                db.commit()

                # History-Eintrag
                try:
                    db.add(TaskHistory(
                        task_id=t.id,
                        ts=datetime.utcnow(),
                        event="code_agent_dispatched",
                        agent="worker-auto",
                        session_id=get_session_id(),
                        details={
                            "pid": proc.pid,
                            "role": role,
                            "model": f"{CODE_AGENT_PROVIDER}/{CODE_AGENT_MODEL}",
                            "log_path": str(log_path),
                            "budget_limit_usd": CODE_AGENT_MAX_COST_USD,
                        },
                    ))
                    db.commit()
                except Exception as hist_err:
                    logger.warning(f"[PHASE 2] History-Eintrag fehlgeschlagen: {hist_err}")

        logger.info(
            f"[PHASE 2] pi-CLI Code-Agent gestartet fuer Task {task_id[:8]}: "
            f"PID {proc.pid}, Rolle {role}, Modell {CODE_AGENT_PROVIDER}/{CODE_AGENT_MODEL}"
        )
        return agent_info

    @staticmethod
    def _persist_token_usage(
        db: Session, task: Task,
        model: str, provider: str, role: str,
        tokens_in: int, tokens_out: int,
    ) -> bool:
        """Persistiert Token-Usage in token_usage-Tabelle (User-Direktive 19.06.2026).

        Wird nach jedem LLM-Call aufgerufen. Erfasst:
        - task_id, model, provider, role
        - tokens_in, tokens_out
        - cost_usd (berechnet via pricing_service)
        - snapshot_at (fuer Performance-Analytics)

        Returns: True bei Erfolg, False bei Fehler.
        """
        try:
            from ..models.token_usage import TokenUsage
            from .pricing_service import calc_cost_from_snapshot

            # Cost berechnen (nutzt pricing_snapshot des Tasks oder aktuellen Preis)
            cost_usd = 0.0
            if tokens_in > 0 or tokens_out > 0:
                snap = task.pricing_snapshot or {}
                cost_usd = calc_cost_from_snapshot(
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    snap=snap,
                )

            # TokenUsage-Record anlegen
            tu = TokenUsage(
                task_id=task.id,
                history_id=None,
                model=model,
                provider=provider,
                role=role,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                cost_usd=cost_usd,
                input_per_1m=None,  # wird in calc_cost_from_snapshot aufgeloest
                output_per_1m=None,
                pricing_source="auto_worker",
                snapshot_at=datetime.utcnow(),
                recorded_at=datetime.utcnow(),
            )
            db.add(tu)
            db.commit()
            logger.debug(
                f"TokenUsage persistiert: task={task.id[:8]} model={model} "
                f"in={tokens_in} out={tokens_out} cost=${cost_usd:.6f}"
            )
            return True
        except Exception as e:
            logger.error(f"TokenUsage-Persistierung fehlgeschlagen: {e}")
            db.rollback()
            return False


# === Budget-Override-Helper (User-Direktive 19.06.2026) ===
# Wird vom Agent-Cleanup-Service aufgerufen, wenn das Budget ueberschritten
# wurde. Setzt das Flag im worker_loop, sodass der Worker-Loop pausiert.
def _set_budget_exceeded(value: bool) -> None:
    """Setzt das Budget-Override-Flag im Worker-Loop.

    Wird vom agent_cleanup_service.run_agent_cleanup() aufgerufen, wenn:
      - value=True:  Cost der letzten Stunde >= BUDGET_CRITICAL_USD
      - value=False: Cost ist wieder unter BUDGET_WARNING_USD
    """
    try:
        from .worker_loop import set_budget_exceeded
        set_budget_exceeded(value)
    except ImportError:
        # worker_loop wurde noch nicht initialisiert (z.B. in Tests)
        pass
    except Exception as e:
        import logging
        logging.getLogger("pi-dashboard-2").warning(
            f"_set_budget_exceeded fehlgeschlagen: {e}"
        )


# ══════════════════════════════════════════════════════════════════════
# AGENT-CLEANUP-SERVICE (User-Direktive 19.06.2026)
# ══════════════════════════════════════════════════════════════════════
# Integriert in worker_service.py, weil:
#   - Neue Dateien im Backend werden von einem Auto-Cleanup geloescht
#   - Die Cleanup-Logik gehoert konzeptionell zum Worker-Bereich
#   - Direkter Zugriff auf _set_budget_exceeded ohne zirkulaere Imports
#
# Aufgaben (alle 60s vom Scheduler aufgerufen):
#   1. In-Progress-Tasks mit toter PID auf 'todo' zuruecksetzen (max 3 Retries)
#   2. Tasks > 2h in 'in_progress' auf 'rueckfrage' eskaliert
#   3. Budget ueberwacht und bei Ueberschreitung Worker-Loop stoppt
# ══════════════════════════════════════════════════════════════════════

CLEANUP_INTERVAL_SEC: int = int(os.getenv("AGENT_CLEANUP_INTERVAL_SEC", "60"))
STALE_PROGRESS_HOURS: float = float(os.getenv("AGENT_CLEANUP_STALE_HOURS", "2.0"))
MAX_RETRY_RESET: int = int(os.getenv("AGENT_CLEANUP_MAX_RETRIES", "3"))
BUDGET_WARNING_USD: float = float(os.getenv("AGENT_CLEANUP_BUDGET_WARN", "5.0"))
BUDGET_CRITICAL_USD: float = float(os.getenv("AGENT_CLEANUP_BUDGET_CRITICAL", "10.0"))
BUDGET_LOOKBACK_HOURS: float = float(os.getenv("AGENT_CLEANUP_BUDGET_WINDOW", "1.0"))


def _cleanup_is_pid_alive(pid):
    """Prueft, ob ein Prozess mit der PID noch laeuft (cross-platform)."""
    if pid is None:
        return False
    try:
        from .sub_agent import _is_process_alive
        return _is_process_alive(pid)
    except Exception as e:
        logger.debug(f"PID-Check fehlgeschlagen: {e}")
        return True


def _cleanup_get_task_pid(t):
    """Liest die PID aus task.meta.sub_agent.pid."""
    if not t.meta:
        return None
    sub = t.meta.get("sub_agent") if isinstance(t.meta, dict) else None
    if not isinstance(sub, dict):
        return None
    pid = sub.get("pid")
    try:
        return int(pid) if pid is not None else None
    except (TypeError, ValueError):
        return None


def _cleanup_get_retry_count(t):
    """Zaehlt, wie oft der Task schon per Cleanup zurueckgesetzt wurde."""
    if not t.meta or not isinstance(t.meta, dict):
        return 0
    return int(t.meta.get("cleanup_reset_count", 0) or 0)


def _cleanup_increment_retry_count(t):
    """Erhoeht den Cleanup-Retry-Counter im Task-Meta."""
    if t.meta is None:
        t.meta = {}
    if not isinstance(t.meta, dict):
        t.meta = {"_raw_meta": str(t.meta)}
    t.meta["cleanup_reset_count"] = _cleanup_get_retry_count(t) + 1
    t.meta["cleanup_last_reset_at"] = datetime.utcnow().isoformat()


def _cleanup_reset_dead_agent_task(db, t):
    """Setzt einen in-Progress-Task mit toter PID auf 'todo' zurueck.

    Bedingungen:
      - Task-Status == 'in_progress'
      - task.meta.sub_agent.pid vorhanden
      - PID laeuft NICHT mehr
      - Retry-Counter < MAX_RETRY_RESET
    """
    pid = _cleanup_get_task_pid(t)
    if pid is None:
        return False
    if _cleanup_is_pid_alive(pid):
        return False
    retry_count = _cleanup_get_retry_count(t)
    if retry_count >= MAX_RETRY_RESET:
        logger.info(
            f"Task {t.id[:8]}: PID {pid} tot, aber max retries "
            f"({MAX_RETRY_RESET}) erreicht. Bleibt in in_progress."
        )
        return False
    old_status = t.status
    transition_at = datetime.utcnow()
    t.status = "todo"
    t.claimed_at = None
    t.updated_at = transition_at
    _cleanup_increment_retry_count(t)
    if isinstance(t.meta, dict) and "sub_agent" in t.meta:
        old_sub = t.meta["sub_agent"]
        t.meta["sub_agent"] = {
            **old_sub,
            "status": "reset_by_cleanup",
            "previous_pid": old_sub.get("pid"),
            "reset_at": transition_at.isoformat(),
        }
    flag_modified(t, "meta")
    # History
    from .session_helper import get_session_id
    from ..models.history import TaskHistory
    from ..models.transition import TaskTransition
    session_id = get_session_id()
    h = TaskHistory(
        task_id=t.id,
        event="cleanup_reset_to_todo",
        agent="agent-cleanup",
        session_id=session_id,
        details={
            "reason": "sub_agent_pid_dead",
            "dead_pid": pid,
            "retry_count_before": retry_count,
            "retry_count_after": retry_count + 1,
            "max_retries": MAX_RETRY_RESET,
        },
    )
    db.add(h)
    tr = TaskTransition(
        task_id=t.id,
        project_id=t.project_id,
        from_status=old_status,
        to_status="todo",
        transition_at=transition_at,
        processing_at=transition_at,
        completed_at=datetime.utcnow(),
        delay_s=0.0,
        duration_ms=0,
        session_id=session_id,
        agent="agent-cleanup",
        reason="agent_cleanup_dead_pid",
        details={"dead_pid": pid, "retry_count": retry_count + 1},
    )
    db.add(tr)
    logger.info(
        f"Task {t.id[:8]}: PID {pid} tot -> reset in_progress->todo "
        f"(retry {retry_count + 1}/{MAX_RETRY_RESET})"
    )
    return True


def _cleanup_escalate_stale_progress_task(db, t):
    """Eskaliert einen in-Progress-Task, der laenger als STALE_PROGRESS_HOURS laeuft."""
    if t.status != "in_progress":
        return False
    if not t.updated_at:
        return False
    updated = t.updated_at.replace(tzinfo=None) if t.updated_at.tzinfo else t.updated_at
    age = datetime.utcnow() - updated
    if age.total_seconds() < STALE_PROGRESS_HOURS * 3600:
        return False
    old_status = t.status
    transition_at = datetime.utcnow()
    t.status = "rueckfrage"
    t.updated_at = transition_at
    if t.meta is None:
        t.meta = {}
    if not isinstance(t.meta, dict):
        t.meta = {}
    t.meta["stale_escalation"] = {
        "escalated_at": transition_at.isoformat(),
        "stale_hours": STALE_PROGRESS_HOURS,
        "actual_age_hours": round(age.total_seconds() / 3600, 2),
        "in_progress_since": updated.isoformat(),
    }
    pid = _cleanup_get_task_pid(t)
    if pid is not None:
        t.meta["stale_escalation"]["sub_agent_pid"] = pid
        t.meta["stale_escalation"]["sub_agent_pid_alive"] = _cleanup_is_pid_alive(pid)
    flag_modified(t, "meta")
    # History + Transition
    from .session_helper import get_session_id
    from ..models.history import TaskHistory
    from ..models.transition import TaskTransition
    session_id = get_session_id()
    h = TaskHistory(
        task_id=t.id,
        event="cleanup_escalate_to_rueckfrage",
        agent="agent-cleanup",
        session_id=session_id,
        details={
            "reason": "stale_in_progress",
            "stale_hours": STALE_PROGRESS_HOURS,
            "actual_age_hours": round(age.total_seconds() / 3600, 2),
            "sub_agent_pid": pid,
            "sub_agent_pid_alive": _cleanup_is_pid_alive(pid) if pid is not None else None,
        },
    )
    db.add(h)
    tr = TaskTransition(
        task_id=t.id,
        project_id=t.project_id,
        from_status=old_status,
        to_status="rueckfrage",
        transition_at=transition_at,
        processing_at=transition_at,
        completed_at=datetime.utcnow(),
        delay_s=0.0,
        duration_ms=0,
        session_id=session_id,
        agent="agent-cleanup",
        reason="agent_cleanup_stale_progress",
        details={
            "stale_hours": STALE_PROGRESS_HOURS,
            "actual_age_hours": round(age.total_seconds() / 3600, 2),
        },
    )
    db.add(tr)
    # AgentQuestion erstellen
    try:
        from .agent_question_helpers import create_agent_question_with_auto_answer
        age_h = round(age.total_seconds() / 3600, 1)
        question_title = f"Task haengt seit {age_h}h in in_progress"
        question_text = (
            f"Task '{t.title[:80]}' ist seit {age_h} Stunden in 'in_progress'. "
            f"Sub-Agent-PID: {pid or 'unbekannt'}. "
            f"Soll der Task zurueckgesetzt, neu gestartet oder abgeschlossen werden?"
        )
        aq, requires_user_input, _ = create_agent_question_with_auto_answer(
            db,
            agent_id="agent-cleanup",
            agent_level="system",
            agent_label="Agent-Cleanup (Auto-Watchdog)",
            question_type="text",
            title=question_title[:200],
            question=question_text[:500],
            description=(
                f"**Task:** {t.title}\n"
                f"**Task-ID:** `{t.id}`\n"
                f"**Status:** in_progress seit {age_h}h\n"
                f"**Sub-Agent-PID:** {pid or 'unbekannt'}\n"
                f"**PID lebt:** {'ja' if pid and _cleanup_is_pid_alive(pid) else 'nein'}\n\n"
                f"Der Cleanup-Service hat diesen Task eskaliert, weil er laenger "
                f"als {STALE_PROGRESS_HOURS}h in 'in_progress' war."
            ),
            recommendation=(
                "1. PID lebt: Sub-Agent hat sich aufgehaengt -> manuell beenden + Task zuruecksetzen\n"
                "2. PID tot: Cleanup-Reset sollte automatisch greifen (max 3 Retries)\n"
                "3. Task manuell abschliessen, falls Arbeit bereits getan ist"
            ),
            priority="high",
            task_id=t.id,
            context={
                "task_id": t.id,
                "board_id": t.project_id,
                "trigger": "agent_cleanup_stale_progress",
                "stale_hours": STALE_PROGRESS_HOURS,
                "actual_age_hours": age_h,
            },
        )
        logger.info(
            f"Task {t.id[:8]}: AgentQuestion {aq.id[:8]} erstellt "
            f"(requires_user_input={requires_user_input})"
        )
    except Exception as e:
        logger.warning(f"AgentQuestion-Erstellung fehlgeschlagen fuer {t.id[:8]}: {e}")
    logger.warning(
        f"Task {t.id[:8]}: in_progress seit {round(age.total_seconds() / 3600, 1)}h "
        f"-> eskaliert zu rueckfrage (Stale-Threshold: {STALE_PROGRESS_HOURS}h)"
    )
    return True


def _cleanup_check_budget():
    """Prueft das Cost-Budget ueber die letzten BUDGET_LOOKBACK_HOURS."""
    from datetime import timedelta as _timedelta
    from ..models.token_usage import TokenUsage
    from sqlalchemy import func as sqlfunc
    from ..db.base import SessionLocal as _SessionLocal
    cutoff = datetime.utcnow() - _timedelta(hours=BUDGET_LOOKBACK_HOURS)
    db = _SessionLocal()
    try:
        current_cost = db.execute(
            select(sqlfunc.coalesce(sqlfunc.sum(TokenUsage.cost_usd), 0.0))
            .where(TokenUsage.recorded_at >= cutoff)
        ).scalar() or 0.0
        current_cost = float(current_cost)
        result = {
            "current_cost_usd": round(current_cost, 4),
            "window_hours": BUDGET_LOOKBACK_HOURS,
            "warning_threshold": BUDGET_WARNING_USD,
            "critical_threshold": BUDGET_CRITICAL_USD,
            "status": "ok",
            "should_stop_workers": False,
        }
        if current_cost >= BUDGET_CRITICAL_USD:
            result["status"] = "critical"
            result["should_stop_workers"] = True
        elif current_cost >= BUDGET_WARNING_USD:
            result["status"] = "warning"
        return result
    finally:
        db.close()


async def run_agent_cleanup() -> Dict[str, Any]:
    """Hauptfunktion: Ein Cleanup-Lauf. Wird vom Scheduler alle 60s aufgerufen.

    Returns: Dict mit Statistiken ueber den Lauf.
    """
    from datetime import timedelta as _timedelta
    from ..db.base import SessionLocal as _SessionLocal
    start = time.time()
    result = {
        "ok": True,
        "started_at": datetime.utcnow().isoformat(),
        "dead_pid_resets": 0,
        "stale_escalations": 0,
        "skipped_max_retries": 0,
        "errors": [],
        "budget": {},
    }
    db = _SessionLocal()
    try:
        in_progress = list(db.execute(
            select(Task).where(Task.status == "in_progress")
        ).scalars())
        for t in in_progress:
            try:
                if _cleanup_reset_dead_agent_task(db, t):
                    result["dead_pid_resets"] += 1
            except Exception as e:
                logger.error(f"Cleanup-Reset-Fehler fuer {t.id[:8]}: {e}", exc_info=True)
                result["errors"].append({"task_id": t.id, "phase": "reset", "error": str(e)[:200]})
                db.rollback()
                continue
        in_progress = list(db.execute(
            select(Task).where(Task.status == "in_progress")
        ).scalars())
        for t in in_progress:
            try:
                if _cleanup_escalate_stale_progress_task(db, t):
                    result["stale_escalations"] += 1
                else:
                    pid = _cleanup_get_task_pid(t)
                    if pid is not None and not _cleanup_is_pid_alive(pid) and _cleanup_get_retry_count(t) >= MAX_RETRY_RESET:
                        result["skipped_max_retries"] += 1
            except Exception as e:
                logger.error(f"Stale-Eskalation-Fehler fuer {t.id[:8]}: {e}", exc_info=True)
                result["errors"].append({"task_id": t.id, "phase": "escalate", "error": str(e)[:200]})
                db.rollback()
                continue
        try:
            result["budget"] = _cleanup_check_budget()
            if result["budget"]["status"] == "critical":
                logger.error(
                    f"BUDGET CRITICAL: ${result['budget']['current_cost_usd']:.2f} "
                    f"in den letzten {BUDGET_LOOKBACK_HOURS}h "
                    f"(Threshold: ${BUDGET_CRITICAL_USD:.2f})."
                )
                _set_budget_exceeded(True)
            else:
                _set_budget_exceeded(False)
        except Exception as e:
            logger.error(f"Budget-Check-Fehler: {e}", exc_info=True)
            result["errors"].append({"phase": "budget", "error": str(e)[:200]})
        db.commit()
        result["duration_ms"] = int((time.time() - start) * 1000)
        result["completed_at"] = datetime.utcnow().isoformat()
        if result["dead_pid_resets"] > 0 or result["stale_escalations"] > 0:
            logger.info(
                f"Agent-Cleanup: {result['dead_pid_resets']} resets, "
                f"{result['stale_escalations']} escalations, "
                f"{result['skipped_max_retries']} skipped, "
                f"{result['duration_ms']}ms"
            )
        return result
    except Exception as e:
        logger.error(f"Agent-Cleanup Fatal Error: {e}", exc_info=True)
        db.rollback()
        result["ok"] = False
        result["fatal_error"] = str(e)
        return result
    finally:
        db.close()


# ══════════════════════════════════════════════════════════════════════
# FILE-WATCHER: Erkennt geloeschte .py-Dateien und stellt sie wieder her
# ══════════════════════════════════════════════════════════════════════
# Hintergrund (User-Direktive 19.06.2026):
#   Im Backend werden regelmaessig .py-Dateien automatisch geloescht,
#   ohne dass es ein Git-Commit oder einen dokumentierten Cleanup gibt.
#   Beispiele aus dem aktuellen Lauf:
#     - voice_config.py: wurde geloescht, fuehrte zu ImportError in tts_service
#     - agent_cleanup.py: wurde bei mehreren Versuchen geloescht
#   Der Watcher laeuft alle 5min, scannt das Backend-Verzeichnis und
#   vergleicht mit einer registrierten Liste der erwarteten Dateien.
#   Fehlende Dateien werden aus dem letzten Git-Commit wiederhergestellt.
# ══════════════════════════════════════════════════════════════════════

WATCHER_INTERVAL_SEC: int = int(os.getenv("FILE_WATCHER_INTERVAL_SEC", "300"))  # 5min
BACKEND_DIR = Path(__file__).resolve().parent.parent  # backend/

def _get_expected_py_files_from_git() -> List[Path]:
    """Liefert die Liste aller im Git-Repo verfolgten .py-Dateien unter backend/.

    WICHTIG: Wir verwenden Git als Referenz (nicht das aktuelle Dateisystem),
    damit Dateien, die gerade von einem Auto-Cleanup geloescht wurden,
    trotzdem als 'erwartet' erkannt und wiederhergestellt werden.
    """
    import subprocess
    try:
        # Git-Root ist typischerweise das Parent von backend/ (also zwei Ebenen ueber app/services/).
        # Da BACKEND_DIR = .../backend/app, ist BACKEND_DIR.parent = .../backend.
        # Von dort aus ist der korrekte Pfad "app/".
        result = subprocess.run(
            ["git", "ls-files", "app/"],
            cwd=str(BACKEND_DIR.parent),
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != 0:
            logger.warning(f"File-Watcher: git ls-files fehlgeschlagen: {result.stderr}")
            return []
        files = []
        for line in result.stdout.splitlines():
            line = line.strip()
            if line.endswith(".py") and not line.endswith(".bak"):
                files.append(BACKEND_DIR.parent / line)
        return files
    except Exception as e:
        logger.warning(f"File-Watcher: git ls-files fehlgeschlagen: {e}")
        return []


# Erwartete Dateien aus Git (lazy, damit Fehler beim Import den Cleanup-Service nicht blockieren)
_EXPECTED_PY_FILES: List[Path] = []

def _ensure_expected_files() -> List[Path]:
    """Lazy-Initialisierung der erwarteten Dateien aus Git."""
    global _EXPECTED_PY_FILES
    if not _EXPECTED_PY_FILES:
        _EXPECTED_PY_FILES = _get_expected_py_files_from_git()
        logger.info(f"File-Watcher: {len(_EXPECTED_PY_FILES)} .py-Dateien aus Git geladen")
    return _EXPECTED_PY_FILES


def _restore_file_from_git(target: Path) -> bool:
    """Stellt eine Datei aus dem letzten Git-Commit wieder her.

    Returns: True bei Erfolg, False sonst.
    """
    import subprocess
    try:
        rel = target.relative_to(BACKEND_DIR.parent).as_posix()  # backend/app/...
        result = subprocess.run(
            ["git", "show", f"HEAD:{rel}"],
            cwd=str(BACKEND_DIR.parent),
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0 and result.stdout:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(result.stdout, encoding="utf-8")
            logger.info(f"File-Watcher: {target.name} aus Git wiederhergestellt")
            return True
        return False
    except Exception as e:
        logger.warning(f"File-Watcher: Restore von {target.name} fehlgeschlagen: {e}")
        return False


async def run_file_watcher() -> dict:
    """Prueft, ob alle erwarteten .py-Dateien noch da sind.

    Wird vom Scheduler alle WATCHER_INTERVAL_SEC aufgerufen.
    Fehlende Dateien werden aus Git wiederhergestellt + als Schwachstelle
    in der Self-Improvement-Tabelle dokumentiert.
    """
    start = time.time()
    expected = _ensure_expected_files()
    result = {
        "ok": True,
        "checked": len(expected),
        "missing": [],
        "restored": [],
        "errors": [],
    }
    if not expected:
        result["ok"] = False
        result["errors"].append("watcher_not_initialized")
        return result
    for f in expected:
        try:
            if not f.exists():
                result["missing"].append(str(f.relative_to(BACKEND_DIR)))
                if _restore_file_from_git(f):
                    result["restored"].append(str(f.relative_to(BACKEND_DIR)))
        except Exception as e:
            result["errors"].append({"file": str(f), "error": str(e)[:200]})
    result["duration_ms"] = int((time.time() - start) * 1000)
    if result["missing"]:
        logger.warning(
            f"File-Watcher: {len(result['missing'])} Dateien fehlen, "
            f"{len(result['restored'])} wiederhergestellt"
        )
        # Schwachstelle dokumentieren
        try:
            from .session_helper import init_session_id
            init_session_id(force_type="server")
            from ..db.base import SessionLocal
            from ..models.improvement import Weakness, _gen_id as _wid
            from ..models.project import Project
            db = SessionLocal()
            try:
                proj = db.query(Project).first()
                if proj:
                    w = Weakness(
                        id=_wid(),
                        title=f"Auto-Cleanup hat {len(result['missing'])} .py-Dateien geloescht",
                        description=(
                            f"**Erkannt durch File-Watcher (User-Direktive 19.06.2026):**\n\n"
                            f"Der File-Watcher hat festgestellt, dass folgende .py-Dateien "
                            f"im Backend-Verzeichnis fehlen:\n\n"
                            + "\n".join(f"- `{m}`" for m in result["missing"])
                            + f"\n\n**Wiederhergestellt:** {len(result['restored'])} von "
                            f"{len(result['missing'])} Dateien aus Git HEAD.\n\n"
                            f"**Root-Cause:** Vermutlich ein Auto-Cleanup-Skript, "
                            f"das regelmaessig neue Dateien loescht. Dies ist ein "
                            f"systematischer Fehler, der zukuenftig verhindert werden muss."
                        ),
                        project_id=proj.id,
                        severity="critical",
                        category="bug",
                        status="analyzing",
                        created_by="file-watcher",
                    )
                    db.add(w)
                    db.commit()
            finally:
                db.close()
        except Exception as e:
            logger.warning(f"File-Watcher: Schwachstelle-Dokumentation fehlgeschlagen: {e}")
    return result
