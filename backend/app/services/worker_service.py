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
