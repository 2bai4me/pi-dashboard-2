"""SOP-Engine — generischer Regelprozess-Interpreter.

User-Direktive 15.06.2026:
  Ersetzt den hartcodierten Workflow (TRIAGE -> GO -> IN_PROGRESS -> REVIEW ->
  BLOCK -> DONE) durch eine generische Engine, die beliebige SOPs
  (Standard Operating Procedures) ausfuehren kann.

Engine-Aufgaben:
  1. Trigger pruefen: feuert der aktuelle Step?
  2. Step ausfuehren: Action an Agent delegieren
  3. Rule auswerten: Wenn-Dann-Logik anwenden
  4. Transition: zum naechsten Step gehen (success/fail/sub-sop)
  5. Sub-SOP spawnen: action_type="spawn_sop"
  6. Audit: jede Aktion in sop_executions dokumentieren

Verwendung:
  engine = SOPEngine(db)
  instance = engine.create_instance(sop_id=..., project_id=..., task_id=...)
  engine.run_step(instance)  # fuehrt aktuellen Step aus
  engine.evaluate_rules(instance, step_result)
  engine.advance(instance)
"""
from __future__ import annotations

import asyncio
import json
import logging
import secrets
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.sop import (
    SOP, SOPStep, SOPStepRule, SOPInstance, SOPExecution,
)
from ..models.task import Task
from ..models.project import Project
from .task_service import TaskService

logger = logging.getLogger("pi-dashboard-2.sop")


def _gen_id() -> str:
    return secrets.token_hex(6)


# === Engine-Hauptklasse ===

class SOPEngine:
    """Engine zum Ausfuehren von SOPs.

    Methoden:
      - list_sops(category=None)
      - get_sop(sop_id)
      - create_sop(name, description, steps, ...)
      - update_sop(sop_id, ...)
      - delete_sop(sop_id)
      - create_instance(sop_id, project_id, task_id, parent_instance_id)
      - run_step(instance) -> fuehrt aktuellen Step aus
      - evaluate_rules(instance, step_result) -> wertet Wenn-Dann aus
      - advance(instance, next_step_id) -> geht zum naechsten Step
      - spawn_sub_sop(parent_instance, sub_sop_id) -> startet Sub-SOP
      - complete(instance) -> markiert Instance als completed
      - fail(instance, reason) -> markiert Instance als failed
    """

    def __init__(self, db: Session):
        self.db = db

    # === CRUD: SOPs ===

    def list_sops(self, category: Optional[str] = None) -> List[SOP]:
        stmt = select(SOP).order_by(SOP.name, SOP.version.desc())
        if category:
            stmt = stmt.where(SOP.category == category)
        return list(self.db.execute(stmt).scalars())

    def get_sop(self, sop_id: str) -> Optional[SOP]:
        return self.db.get(SOP, sop_id)

    def create_sop(
        self, name: str, description: str, category: str = "task",
        version: int = 1, parent_sop_id: Optional[str] = None,
        is_template: bool = False, default_delay_s: float = 5.0,
        steps: Optional[List[Dict[str, Any]]] = None,
    ) -> SOP:
        """Erstellt eine neue SOP inkl. Steps + Rules.

        steps: Liste von Dicts mit:
          {
            "name": "...", "phase": "Task", "trigger": "...",
            "action": "...", "action_params": {...}, "agent": "...",
            "expected_result": "...", "success_criteria": [...],
            "delay_s": 5.0, "description": "...",
            "rules": [
              {
                "condition_field": "...", "condition_operator": "eq",
                "condition_value": True,
                "action_type": "move_status", "action_target": "todo",
                "action_params": {...}, "description": "..."
              },
              ...
            ]
          }
        """
        sop = SOP(
            id=_gen_id(),
            name=name,
            description=description,
            category=category,
            version=version,
            parent_sop_id=parent_sop_id,
            is_template=is_template,
            default_delay_s=default_delay_s,
        )
        self.db.add(sop)
        self.db.flush()

        step_id_map: Dict[int, str] = {}  # index -> step_id
        if steps:
            for idx, sd in enumerate(steps):
                step = SOPStep(
                    id=_gen_id(),
                    sop_id=sop.id,
                    step_order=idx,
                    name=sd.get("name", f"Step {idx+1}"),
                    phase=sd.get("phase", "Task"),
                    trigger=sd.get("trigger", "manual"),
                    action=sd.get("action", "noop"),
                    action_params=sd.get("action_params", {}),
                    agent=sd.get("agent", "system"),
                    expected_result=sd.get("expected_result"),
                    success_criteria=sd.get("success_criteria", []),
                    delay_s=sd.get("delay_s", default_delay_s),
                    description=sd.get("description"),
                )
                self.db.add(step)
                self.db.flush()
                step_id_map[idx] = step.id

                # Rules
                for ridx, rd in enumerate(sd.get("rules", [])):
                    rule = SOPStepRule(
                        id=_gen_id(),
                        step_id=step.id,
                        rule_order=ridx,
                        description=rd.get("description"),
                        condition_field=rd.get("condition_field", ""),
                        condition_operator=rd.get("condition_operator", "eq"),
                        condition_value=rd.get("condition_value"),
                        action_type=rd.get("action_type", "noop"),
                        action_target=rd.get("action_target"),
                        action_params=rd.get("action_params", {}),
                    )
                    self.db.add(rule)

            # Verzweigungen setzen
            self.db.flush()
            for idx, sd in enumerate(steps):
                if idx in step_id_map:
                    step = self.db.get(SOPStep, step_id_map[idx])
                    if "next_step" in sd and sd["next_step"] is not None:
                        step.next_step_id = step_id_map.get(sd["next_step"])
                    if "fail_step" in sd and sd["fail_step"] is not None:
                        step.fail_step_id = step_id_map.get(sd["fail_step"])
                    if "on_sub_sop_step" in sd and sd["on_sub_sop_step"] is not None:
                        step.on_sub_sop_step_id = step_id_map.get(sd["on_sub_sop_step"])

        self.db.commit()
        self.db.refresh(sop)
        return sop

    def update_sop(self, sop_id: str, **fields) -> Optional[SOP]:
        sop = self.db.get(SOP, sop_id)
        if not sop:
            return None
        for k, v in fields.items():
            if v is not None and hasattr(sop, k):
                setattr(sop, k, v)
        sop.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(sop)
        return sop

    def delete_sop(self, sop_id: str) -> bool:
        sop = self.db.get(SOP, sop_id)
        if not sop:
            return False
        self.db.delete(sop)
        self.db.commit()
        return True

    # === Instances ===

    def list_instances(
        self, project_id: Optional[str] = None,
        task_id: Optional[str] = None, status: Optional[str] = None,
    ) -> List[SOPInstance]:
        stmt = select(SOPInstance).order_by(SOPInstance.started_at.desc())
        if project_id:
            stmt = stmt.where(SOPInstance.project_id == project_id)
        if task_id:
            stmt = stmt.where(SOPInstance.task_id == task_id)
        if status:
            stmt = stmt.where(SOPInstance.status == status)
        return list(self.db.execute(stmt).scalars())

    def get_instance(self, instance_id: str) -> Optional[SOPInstance]:
        return self.db.get(SOPInstance, instance_id)

    def create_instance(
        self, sop_id: str,
        project_id: Optional[str] = None,
        task_id: Optional[str] = None,
        parent_instance_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Optional[SOPInstance]:
        """Startet eine neue SOP-Instance. Setzt current_step_id auf den ersten Step."""
        sop = self.db.get(SOP, sop_id)
        if not sop:
            return None
        if not sop.steps:
            logger.warning(f"SOP {sop_id} hat keine Steps")
            return None
        first_step = sorted(sop.steps, key=lambda s: s.step_order)[0]
        inst = SOPInstance(
            id=_gen_id(),
            sop_id=sop_id,
            project_id=project_id,
            task_id=task_id,
            current_step_id=first_step.id,
            status="running",
            parent_instance_id=parent_instance_id,
            context=context or {},
        )
        self.db.add(inst)
        self.db.flush()
        # Audit: instance_started
        self._log_execution(
            inst, step_id=first_step.id, event="instance_started",
            agent="system",
            details={"sop_id": sop_id, "first_step": first_step.id,
                     "first_step_name": first_step.name,
                     "project_id": project_id, "task_id": task_id},
        )
        self.db.commit()
        self.db.refresh(inst)
        return inst

    # === Engine: Step ausfuehren ===

    async def run_step(self, instance: SOPInstance) -> Dict[str, Any]:
        """Fuehrt den aktuellen Step aus.

        Reihenfolge:
          1) Step laden
          2) User-Input-Tool pruefen (blockierend wenn required und Context leer)
          3) Trigger pruefen
          4) Audit: step_started
          5) asyncio.sleep(step.delay_s) (sichtbarer Delay)
          6) Action an Agent delegieren (delegate-Action)
          7) Audit: step_completed mit Ergebnis
          8) Rules auswerten -> naechster Step
        """
        if instance.status != "running":
            return {"ok": False, "error": f"Instance is {instance.status}, not running"}

        step = self.db.get(SOPStep, instance.current_step_id)
        if not step:
            return {"ok": False, "error": "Step not found"}

        # === User-Input-Tool (User-Direktive 17.06.2026) ===
        # Wenn der Step ein Input-Tool erfordert UND der Context-Wert fehlt,
        # wird BLOCKIEREND auf die User-Antwort gewartet.
        if step.input_tool_required:
            ctx_key = step.input_tool_context_key or f"step_{step.step_order}_input"
            existing = (instance.context or {}).get(ctx_key)
            if not existing:
                # User-Input holen (blockierend)
                input_result = await self._await_user_input(instance, step, ctx_key)
                if not input_result:
                    return {
                        "ok": False,
                        "error": "User-Input-Tool hat keine Antwort erhalten (abgebrochen oder Timeout)",
                        "blocked": True,
                    }
                # Context-Variable setzen
                ctx = dict(instance.context or {})
                ctx[ctx_key] = input_result
                instance.context = ctx
                self.db.commit()
                # Audit
                self._log_execution(
                    instance, step_id=step.id, event="input_received",
                    agent="user", success=True,
                    details={"context_key": ctx_key, "input": input_result},
                )
                self.db.commit()

        start_ts = datetime.utcnow()
        # Audit: step_started
        self._log_execution(
            instance, step_id=step.id, event="step_started",
            agent=step.agent,
            details={"step_name": step.name, "phase": step.phase,
                     "trigger": step.trigger, "action": step.action,
                     "action_params": step.action_params or {},
                     "delay_s": step.delay_s},
        )
        self.db.commit()

        # Sichtbarer Delay (User-Direktive: 5s Verzoegerung)
        if step.delay_s > 0:
            logger.info(
                f"[sop-step-delay] Instance {instance.id[:8]} step {step.name!r} "
                f"agent={step.agent!r}: waiting {step.delay_s}s"
            )
            await asyncio.sleep(step.delay_s)

        # Action ausfuehren (delegiert an Task-Service)
        step_result = await self._execute_action(instance, step)
        duration_ms = int((datetime.utcnow() - start_ts).total_seconds() * 1000)

        # Audit: step_completed
        self._log_execution(
            instance, step_id=step.id, event="step_completed",
            agent=step.agent, duration_ms=duration_ms, success=step_result.get("ok", True),
            details=step_result,
        )
        self.db.commit()

        # Rules auswerten
        next_step_id, action = self.evaluate_rules(instance, step, step_result)
        if next_step_id is None:
            # End-State: Instance abschliessen
            return self._complete_instance(instance, step, step_result)

        # Zum naechsten Step
        return self.advance(instance, next_step_id, step_result)

    async def _await_user_input(
        self, instance: SOPInstance, step: SOPStep, ctx_key: str,
        timeout_s: float = 3600.0,
    ) -> Optional[Dict[str, Any]]:
        """Erstellt eine AgentQuestion und wartet BLOCKIEREND auf die User-Antwort.

        Long-Polling: prueft alle 2s den Status der AgentQuestion.
        Timeout: default 1h (User hat genug Zeit fuer komplexe Antworten).
        Returns: dict {text, choice, question_id, answered_at, answered_by} oder None.
        """
        from ..models.agent_question import AgentQuestion
        from ..db.base import SessionLocal as _SessionLocal

        # 1) AgentQuestion erstellen
        q = AgentQuestion(
            agent_id=f"sop-{instance.id[:8]}",
            agent_level="Worker",
            agent_label=f"SOP '{instance.sop.name}' (Step {step.step_order}: {step.name})",
            question_type=step.input_tool_type or "text",
            title=step.name,
            question=step.input_tool_prompt or "Bitte um Input fuer diesen SOP-Step.",
            description=step.input_tool_description,
            recommendation=step.input_tool_recommendation,
            options=json.loads(step.input_tool_options) if step.input_tool_options else [],
            options_config=step.input_tool_options_config,  # JSON-String (show_description, show_tts, etc.)
            context={
                "sop_instance_id": instance.id,
                "sop_id": instance.sop_id,
                "step_id": step.id,
                "step_order": step.step_order,
                "context_key": ctx_key,
                "project_id": instance.project_id,
                "task_id": instance.task_id,
            },
            priority="medium",
            status="pending",
        )
        # Eigene Session fuer AgentQuestion-Insert (Hauptsession blockt)
        with _SessionLocal() as qdb:
            qdb.add(q)
            qdb.commit()
            qdb.refresh(q)
            qid = q.id

        # === Auto-Status-Update: Wenn Question an Task gebunden ist,
        #     Task-Status auf 'rueckfrage' setzen (via Helper).
        #     Wichtig: Helper nutzt eigene Session, weil die Engine-Hauptsession blockt.
        if instance.task_id:
            try:
                from .agent_question_helpers import update_task_on_question
                with _SessionLocal() as helper_db:
                    update_task_on_question(
                        db=helper_db,
                        task_id=instance.task_id,
                        question_id=qid,
                        agent_id=q.agent_id,
                        agent_label=q.agent_label,
                    )
            except Exception as e:
                logger.warning(f"Helper update_task_on_question fehlgeschlagen: {e}")

        # Audit: input_requested
        self._log_execution(
            instance, step_id=step.id, event="input_requested",
            agent="user", success=True,
            details={"context_key": ctx_key, "question_id": qid,
                     "question_type": step.input_tool_type, "timeout_s": timeout_s},
        )
        self.db.commit()

        logger.info(
            f"[user-input] SOP-Instance {instance.id[:8]} Step {step.name!r}: "
            f"BLOCKING on user input (question={qid}, timeout={timeout_s}s)"
        )

        # 2) BLOCKIEREND auf Antwort warten
        start = datetime.utcnow()
        deadline = start.timestamp() + timeout_s
        try:
            while datetime.utcnow().timestamp() < deadline:
                await asyncio.sleep(2.0)
                # In eigener Session pruefen (Hauptsession ist durch step in use)
                with _SessionLocal() as qdb:
                    current = qdb.get(AgentQuestion, qid)
                    if not current:
                        logger.warning(f"[user-input] Question {qid} disappeared")
                        return None
                    if current.status == "answered":
                        return {
                            "text": current.answer_text,
                            "choice": current.answer_choice,
                            "question_id": current.id,
                            "answered_at": current.answered_at.isoformat() if current.answered_at else None,
                            "answered_by": current.answered_by,
                        }
                    if current.status == "cancelled":
                        logger.info(f"[user-input] Question {qid} cancelled by user/agent")
                        return None
            # Timeout erreicht
            logger.warning(f"[user-input] Question {qid} timed out after {timeout_s}s")
            # Frage als expired markieren
            with _SessionLocal() as qdb:
                current = qdb.get(AgentQuestion, qid)
                if current and current.status == "pending":
                    current.status = "expired"
                    qdb.commit()
            return None
        except asyncio.CancelledError:
            logger.info(f"[user-input] Wait for {qid} cancelled")
            raise

    async def _execute_action(self, instance: SOPInstance, step: SOPStep) -> Dict[str, Any]:
        """Delegiert die Action des Steps an den zustaendigen Service.

        Unterstuetzte Actions:
          - noop: nichts tun
          - review_task: Task in step.agent Review geben (Phase 'review')
          - approve_triage: setzt Task in GO (CIO-Approve)
          - assign_worker: setzt assigned_role
          - start_work: setzt status in_progress
          - submit_review: setzt status review
          - tester_review: tester approve/reject
          - cio_final_approve: setzt done
          - spawn_sop: startet Sub-SOP
          - move_status: generischer Status-Wechsel
        """
        action = step.action
        task = self.db.get(Task, instance.task_id) if instance.task_id else None
        params = step.action_params or {}

        if action == "noop":
            return {"ok": True, "action": "noop", "note": "no action performed"}

        if action == "spawn_sop":
            sub_sop_id = params.get("sop_id")
            if not sub_sop_id:
                return {"ok": False, "error": "spawn_sop: sop_id missing in action_params"}
            sub_inst = self.spawn_sub_sop(instance, sub_sop_id, params.get("context", {}))
            if sub_inst:
                return {"ok": True, "action": "spawn_sop", "sub_instance_id": sub_inst.id,
                        "sop_id": sub_sop_id, "status": sub_inst.status}
            return {"ok": False, "error": "spawn_sop failed"}

        # === Custom-Actions fuer CIO-Triage-SOP ===
        # Diese Actions fuehren die 4 Kriterien-Pruefungen aus und sammeln Issues.
        # Sie arbeiten mit der Task-Description, den Architecture-Rules, etc.
        if action in ("check_title", "check_description", "check_success_criteria",
                       "check_architecture", "check_consistency", "decide_triage",
                       "collect_issue"):
            return self._execute_triage_action(instance, step, task, action, params)

        # Alle Task-Status-bezogenen Actions

        # Alle Task-Status-bezogenen Actions
        if not task:
            return {"ok": False, "error": f"action {action!r} requires task_id on instance"}

        if action == "review_task":
            # Step 'review': fuehrt die CIO-Heuristik aus, wenn ein Task vorhanden ist.
            # Fix (User-Direktive 18.06.2026): review_task muss die Heuristik aufrufen,
            # damit der step_ok korrekt aus den 4 Kriterien abgeleitet wird.
            # Vorher: gab immer ok=True zurueck, was dazu fuehrte, dass die
            # Rule "step_ok == true" IMMER feuerte, auch wenn der Task eigentlich
            # nicht OK war (z.B. "Komplexe Negation in der Description").
            if task:
                try:
                    from ..routers.workflow import _check_cio_heuristic
                    result = _check_cio_heuristic(self.db, task)
                    return {
                        "ok": result["ok"],
                        "action": "review_task",
                        "task_id": task.id,
                        "current_status": task.status,
                        "agent": step.agent,
                        "message": (
                            f"Review durch {step.agent}: "
                            f"{'OK' if result['ok'] else 'Issues gefunden'}"
                        ),
                        "issues": result.get("issues", []),
                        "questions": result.get("questions", []),
                    }
                except Exception as e:
                    logger.warning(f"review_task: Heuristik fehlgeschlagen: {e}")
                    # Fallback: manueller Review-Mode
                    return {"ok": True, "action": "review_task",
                            "task_id": task.id, "current_status": task.status,
                            "agent": step.agent,
                            "message": f"Task wartet auf Review durch {step.agent} (Heuristik-Fallback)"}
            return {"ok": False, "error": "review_task benoetigt einen Task"}

        # === Stufe 1: Konkrete Step-Handler (User-Direktive 18.06.2026) ===
        # Vorher: review_task (generisch) wurde fuer ALLE Review-Steps genutzt.
        # Jetzt: tester_code_review und cio_final_review pruefen SPEZIFISCHE
        # Metriken und schreiben sie in instance.context. Die Rules lesen dann
        # diese Metriken (statt nur step_ok).

        if action == "tester_code_review":
            # Konkrete Metriken aus task.meta lesen
            meta = task.meta if isinstance(task.meta, dict) else {}
            test_coverage = float(meta.get("test_coverage", 0) or 0)
            lint_errors = int(meta.get("lint_errors", 0) or 0)
            test_files_count = int(meta.get("test_files_count", 0) or 0)
            critical_issues = int(meta.get("critical_issues", 0) or 0)
            # Acceptance-Criteria aus action_params (z.B. ["coverage >= 80", "no_lint_errors"])
            acceptance = params.get("acceptance_criteria", [
                "test_coverage >= 80",
                "lint_errors == 0",
                "test_files > 0",
                "critical_issues == 0",
            ])
            # Checks auswerten
            checks = {
                "test_coverage": test_coverage,
                "lint_errors": lint_errors,
                "test_files": test_files_count,
                "critical_issues": critical_issues,
            }
            # Welche Kriterien sind erfuellt?
            issues = []
            for criterion in acceptance:
                if "coverage" in criterion and ">= 80" in criterion and test_coverage < 80:
                    issues.append(f"test_coverage={test_coverage}% < 80%")
                if "lint" in criterion and "== 0" in criterion and lint_errors > 0:
                    issues.append(f"lint_errors={lint_errors} > 0")
                if "test_files" in criterion and "> 0" in criterion and test_files_count == 0:
                    issues.append(f"test_files={test_files_count} = 0 (keine Tests gefunden)")
                if "critical_issues" in criterion and "== 0" in criterion and critical_issues > 0:
                    issues.append(f"critical_issues={critical_issues} > 0")
            ok = len(issues) == 0
            return {
                "ok": ok,
                "action": "tester_code_review",
                "task_id": task.id,
                "current_status": task.status,
                "agent": step.agent,
                "message": f"Tester-Code-Review: {'OK' if ok else 'Issues: ' + ', '.join(issues)}",
                "test_coverage": test_coverage,
                "lint_errors": lint_errors,
                "test_files": test_files_count,
                "critical_issues": critical_issues,
                "checks_performed": len(acceptance),
                "issues_found": issues,
            }

        if action == "cio_final_review":
            # Konkrete Metriken aus success_criteria + task.meta
            criteria_total = len(task.success_criteria or [])
            criteria_met = int((task.meta or {}).get("criteria_met", 0) if isinstance(task.meta, dict) else 0)
            all_tests_passing = bool((task.meta or {}).get("all_tests_passing", False) if isinstance(task.meta, dict) else False)
            no_open_todos = bool((task.meta or {}).get("no_open_todos", True) if isinstance(task.meta, dict) else True)
            code_quality_ok = bool((task.meta or {}).get("code_quality_ok", True) if isinstance(task.meta, dict) else True)
            # Acceptance-Criteria aus action_params
            acceptance = params.get("acceptance_criteria", [
                "criteria_met == criteria_total",
                "all_tests_passing == True",
                "no_open_todos == True",
                "code_quality_ok == True",
            ])
            issues = []
            for criterion in acceptance:
                if "criteria_met" in criterion and "== criteria_total" in criterion:
                    if criteria_met < criteria_total:
                        issues.append(f"criteria_met={criteria_met}/{criteria_total}")
                if "all_tests_passing" in criterion and "== True" in criterion and not all_tests_passing:
                    issues.append("all_tests_passing=False")
                if "no_open_todos" in criterion and "== True" in criterion and not no_open_todos:
                    issues.append("no_open_placeholders=False (es gibt noch offene Code-Marker wie TODO/FIXME)")
                if "code_quality_ok" in criterion and "== True" in criterion and not code_quality_ok:
                    issues.append("code_quality_ok=False")
            ok = len(issues) == 0
            return {
                "ok": ok,
                "action": "cio_final_review",
                "task_id": task.id,
                "current_status": task.status,
                "agent": step.agent,
                "message": f"CIO-Final-Review: {'OK' if ok else 'Issues: ' + ', '.join(issues)}",
                "criteria_met": criteria_met,
                "criteria_total": criteria_total,
                "all_tests_passing": all_tests_passing,
                "no_open_todos": no_open_todos,
                "code_quality_ok": code_quality_ok,
                "checks_performed": len(acceptance),
                "issues_found": issues,
            }


        if action == "move_status":
            new_status = params.get("status")
            if not new_status:
                return {"ok": False, "error": "move_status: status missing"}
            t = await TaskService.change_status_with_delay(
                self.db, t=task, new_status=new_status,
                agent=step.agent, reason=f"sop:{instance.sop_id}:{step.id}",
                details={"sop_instance_id": instance.id, "sop_step_id": step.id,
                         "sop_step_name": step.name},
                delay_s=0.0,  # Bereits in run_step gewartet
            )
            return {"ok": True, "action": "move_status",
                    "task_id": task.id, "new_status": t.status}

        # Standard-Workflow-Actions (koppeln an TaskService)
        if action == "approve_triage":
            t = await TaskService.change_status_with_delay(
                self.db, t=task, new_status="todo",
                agent=step.agent, reason="sop:approve_triage",
                delay_s=0.0,
            )
            return {"ok": True, "action": "approve_triage",
                    "task_id": task.id, "new_status": t.status}

        if action == "assign_worker":
            worker = params.get("worker", step.agent)
            old = task.assigned_role
            task.assigned_role = worker
            task.updated_at = datetime.utcnow()
            self.db.commit()
            return {"ok": True, "action": "assign_worker",
                    "task_id": task.id, "from": old, "to": worker}

        if action == "start_work":
            task.claimed_at = datetime.utcnow()
            # Stufe 2: assigned_role = step.agent (z.B. pi-coder in Step 2)
            old_role = task.assigned_role
            task.assigned_role = step.agent
            self.db.commit()
            t = await TaskService.change_status_with_delay(
                self.db, t=task, new_status="in_progress",
                agent=step.agent, reason="sop:start_work",
                delay_s=0.0,
            )
            return {"ok": True, "action": "start_work",
                    "task_id": task.id, "new_status": t.status, "worker": task.assigned_role,
                    "role_changed": {"from": old_role, "to": task.assigned_role}}

        if action == "submit_review":
            old_role = task.assigned_role
            task.assigned_role = step.agent  # pi-coder bleibt (Step 2 -> review, Worker dokumentiert)
            self.db.commit()
            t = await TaskService.change_status_with_delay(
                self.db, t=task, new_status="review",
                agent=step.agent, reason="sop:submit_review",
                delay_s=0.0,
            )
            return {"ok": True, "action": "submit_review",
                    "task_id": task.id, "new_status": t.status}

        if action == "tester_approve":
            old_role = task.assigned_role
            task.assigned_role = "pi-tester"  # Step 3 = pi-tester
            self.db.commit()
            t = await TaskService.change_status_with_delay(
                self.db, t=task, new_status="block",
                agent="pi-tester", reason="sop:tester_approve",
                delay_s=0.0,
            )
            return {"ok": True, "action": "tester_approve",
                    "task_id": task.id, "new_status": t.status}

        if action == "tester_reject":
            old_role = task.assigned_role
            task.assigned_role = "pi-tester"  # Step 3 = pi-tester
            self.db.commit()
            t = await TaskService.change_status_with_delay(
                self.db, t=task, new_status="in_progress",
                agent="pi-tester", reason="sop:tester_reject",
                delay_s=0.0,
            )
            task.iteration_count = (task.iteration_count or 0) + 1
            self.db.commit()
            return {"ok": True, "action": "tester_reject",
                    "task_id": task.id, "new_status": t.status,
                    "iteration": task.iteration_count}

        if action == "cio_final_approve":
            old_role = task.assigned_role
            task.assigned_role = step.agent  # Step 4 = CIO
            self.db.commit()
            t = await TaskService.change_status_with_delay(
                self.db, t=task, new_status="done",
                agent=step.agent, reason="sop:cio_final_approve",
                delay_s=0.0,
            )
            return {"ok": True, "action": "cio_final_approve",
                    "task_id": task.id, "new_status": t.status}

        if action == "cio_final_reject":
            old_role = task.assigned_role
            task.assigned_role = step.agent  # Step 4 = CIO
            self.db.commit()
            target = params.get("target_status", "in_progress")
            t = await TaskService.change_status_with_delay(
                self.db, t=task, new_status=target,
                agent=step.agent, reason="sop:cio_final_reject",
                delay_s=0.0,
            )
            return {"ok": True, "action": "cio_final_reject",
                    "task_id": task.id, "new_status": t.status}

        return {"ok": False, "error": f"unknown action: {action!r}"}

    # === Rules: Wenn-Dann-Logik ===

    def evaluate_rules(
        self, instance: SOPInstance, step: SOPStep, step_result: Dict[str, Any]
    ) -> Tuple[Optional[str], Optional[str]]:
        """Wertet die Rules des Steps aus. Liefert (next_step_id, action).

        Reihenfolge:
          1) Hole alle Rules des Steps (sortiert nach rule_order)
          2) Pruefe Condition (condition_field aus instance.context, condition_value)
          3) Wenn Condition erfuellt: action ausfuehren, naechsten Step bestimmen
          4) Audit: rule_evaluated pro Rule
        """
        rules = sorted(step.rules or [], key=lambda r: r.rule_order)
        ctx = instance.context or {}
        # Step-Result in Context mergen
        for k, v in step_result.items():
            ctx[f"step_{k}"] = v

        for rule in rules:
            field_value = ctx.get(rule.condition_field)
            target_value = rule.condition_value
            op = rule.condition_operator
            # Stufe 1 (User-Direktive 18.06.2026): target_value darf ein dynamischer
            # Field-Prefix sein ("step_xxx" / "ctx_xxx"). Dann den Wert aus ctx lesen.
            if isinstance(target_value, str) and (
                target_value.startswith("step_") or target_value.startswith("ctx_")
            ):
                target_value = ctx.get(target_value)

            if self._eval_condition(field_value, op, target_value):
                # Rule feuert
                self._log_execution(
                    instance, step_id=step.id, event="rule_evaluated",
                    agent=step.agent, success=True,
                    details={"rule_id": rule.id, "matched": True,
                             "field": rule.condition_field,
                             "value": field_value,
                             "action": rule.action_type,
                             "action_target": rule.action_target},
                )

                # Action ausfuehren
                next_step_id = self._execute_rule_action(instance, step, rule, step_result)

                instance.context = ctx
                self.db.commit()
                return next_step_id, rule.action_type

            else:
                self._log_execution(
                    instance, step_id=step.id, event="rule_evaluated",
                    agent=step.agent, success=False,
                    details={"rule_id": rule.id, "matched": False,
                             "field": rule.condition_field,
                             "value": field_value,
                             "expected_op": op,
                             "expected_value": target_value},
                )

        # Keine Rule hat gefeuert
        # Default: next_step_id des Steps, falls vorhanden
        instance.context = ctx
        self.db.commit()
        return step.next_step_id, None

    def _eval_condition(self, field_value: Any, op: str, target_value: Any) -> bool:
        """Wertet eine Condition aus."""
        try:
            if op == "eq":
                return field_value == target_value
            if op == "ne":
                return field_value != target_value
            if op == "gt":
                return field_value is not None and field_value > target_value
            if op == "lt":
                return field_value is not None and field_value < target_value
            if op == "ge":
                return field_value is not None and field_value >= target_value
            if op == "le":
                return field_value is not None and field_value <= target_value
            if op == "in":
                return field_value in (target_value or [])
            if op == "not_in":
                return field_value not in (target_value or [])
            if op == "contains":
                return target_value in (field_value or "")
            if op == "is_true":
                return bool(field_value)
            if op == "is_false":
                return not bool(field_value)
            if op == "is_none":
                return field_value is None
            if op == "is_zero":
                return int(field_value) == 0
            if op == "gt":
                try:
                    return float(field_value) > float(target_value)
                except (TypeError, ValueError):
                    return False
            if op == "lt":
                try:
                    return float(field_value) < float(target_value)
                except (TypeError, ValueError):
                    return False
            if op == "gte":
                try:
                    return float(field_value) >= float(target_value)
                except (TypeError, ValueError):
                    return False
            if op == "lte":
                try:
                    return float(field_value) <= float(target_value)
                except (TypeError, ValueError):
                    return False
            if op == "eq":
                try:
                    return field_value == target_value
                except Exception:
                    return False
            if op == "neq":
                try:
                    return field_value != target_value
                except Exception:
                    return False
            return False
        except Exception as e:
            logger.warning(f"Condition-Eval fehlgeschlagen: {e}")
            return False

    # === Triage-spezifische Check-Actions ===
    # Diese Funktionen implementieren die 4 CIO-Triage-Kriterien
    # als registrierbare Actions. Sie lesen die Task-Daten, pruefen
    # und schreiben Issues in instance.meta['triage_issues'].
    def _execute_triage_action(
        self, instance: SOPInstance, step: SOPStep, task: Task,
        action: str, params: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Fuehrt die Triage-Check-Actions aus.

        Unterstuetzte Actions:
          - check_title: prueft Titel-Laenge und Inhalt
          - check_description: prueft Description-Laenge und Konflikt-Keywords
          - check_success_criteria: prueft ob welche definiert sind
          - check_architecture: prueft gegen OpenBrain-Standardvorgaben
          - check_consistency: prueft auf Widersprueche
          - decide_triage: finale Entscheidung (move_status todo/rueckfrage)
        """
        import json as _json
        from ..models.architecture_rule import ArchitectureRule

        # Meta-Init
        if not isinstance(instance.meta, dict):
            try:
                instance.meta = _json.loads(instance.meta) if instance.meta else {}
            except Exception:
                instance.meta = {}

        issues: list = instance.meta.setdefault("triage_issues", [])
        warnings: list = instance.meta.setdefault("triage_warnings", [])

        # === check_title ===
        if action == "check_title":
            title = task.title or ""
            if len(title.strip()) < 10:
                issues.append({
                    "type": "title_too_short",
                    "title": "Titel zu kurz oder fehlt",
                    "description": (
                        f"Der Titel des Tasks hat nur {len(title)} Zeichen (Minimum: 10). "
                        "Ein guter Titel beschreibt die KERN-Aufgabe in 5-15 Worten."
                    ),
                    "suggestions": [
                        "Formuliere den Titel als Aufgabe: 'Implementiere X' / 'Fixe Bug Y'",
                        "Inkludiere den Scope: Backend, Frontend, API, DB wenn relevant",
                    ],
                    "recommendation": "Schreibe den Titel als konkrete Aufgabe mit Scope-Indikator.",
                })
                return {"ok": False, "issues_count": len(issues), "title": title}
            return {"ok": True, "issues_count": len(issues), "title": title}

        # === check_description ===
        if action == "check_description":
            desc = task.description or ""
            if len(desc.strip()) < 50:
                issues.append({
                    "type": "description_too_short",
                    "title": "Description fehlt oder zu kurz",
                    "description": (
                        f"Die Description hat nur {len(desc)} Zeichen (Minimum: 50, ideal: 200+). "
                        "Ohne ausreichende Description weiss der Worker nicht, WAS implementiert werden soll."
                    ),
                    "suggestions": [
                        "Strukturierte Description: Ziel, Akzeptanz, Edge-Cases",
                        "Konkrete Beispiele: Input/Output, Vorher/Nachher",
                    ],
                    "recommendation": "Mindestens 200 Zeichen. Struktur: Ziel, Umsetzung, Akzeptanz.",
                })
                return {"ok": False, "issues_count": len(issues)}
            # Konflikt-Keywords
            conflict_kws = ["todo:", "tbd", "fixme", "??", "klären", "kl\u00e4ren", "unbekannt"]
            found = [kw for kw in conflict_kws if kw in desc.lower()]
            if found:
                issues.append({
                    "type": "conflict_keyword",
                    "title": f"Konflikt-Keywords gefunden: {', '.join(found)}",
                    "description": (
                        f"Die Description enthaelt unklare Platzhalter: {', '.join(found)}. "
                        "Diese verstoßen gegen unsere OpenBrain-Vorgabe 'Tasks muessen selbsterklaerend sein'."
                    ),
                    "suggestions": [
                        f"Ersetze '{found[0]}' durch die konkrete Information",
                        "Entferne FIXME-Marker oder lege separate Tasks an",
                    ],
                    "recommendation": "Gehe durch den Task und ersetze JEDES Konflikt-Keyword durch konkrete Information.",
                })
                return {"ok": False, "issues_count": len(issues), "conflicts": found}
            return {"ok": True, "issues_count": len(issues)}

        # === check_success_criteria ===
        if action == "check_success_criteria":
            sc = task.success_criteria or []
            if not isinstance(sc, list) or len(sc) < 1:
                issues.append({
                    "type": "no_success_criteria",
                    "title": "Keine Erfolgskriterien definiert",
                    "description": (
                        "Ohne Erfolgskriterien kann der Worker nicht wissen, wann der Task 'fertig' ist, "
                        "und der Tester kann nicht objektiv pruefen, ob der Task korrekt umgesetzt wurde."
                    ),
                    "suggestions": [
                        "Mindestens 1-3 messbare Erfolgskriterien definieren",
                        "Beispiel: 'Login funktioniert mit gueltigen Credentials', 'Tests geschrieben'",
                    ],
                    "recommendation": "Definiere klare, messbare Erfolgskriterien (Definition of Done).",
                })
                return {"ok": False, "issues_count": len(issues)}
            return {"ok": True, "issues_count": len(issues), "count": len(sc)}

        # === check_architecture ===
        if action == "check_architecture":
            desc = (task.description or "").lower()
            title = (task.title or "").lower()
            text = f"{title} {desc}"
            arch_stop = {
                "regel", "vorgabe", "standard", "beispiel", "eigen", "eigenstaendig",
                "auch", "sowie", "kein", "keine", "keinen", "vermeiden",
                "sollte", "muss", "darf", "wird",
            }
            try:
                rules = self.db.execute(
                    select(ArchitectureRule).where(ArchitectureRule.is_active == True)
                ).scalars().all()
            except Exception:
                return {"ok": True, "issues_count": len(issues), "note": "rules not loadable"}
            arch_issues = []
            for rule in rules:
                if not rule.description:
                    continue
                keywords = [w for w in re.findall(r"\b[a-z]{5,}\b", rule.description.lower()) if w not in arch_stop][:5]
                for kw in keywords:
                    neg_patterns = [
                        f"kein {kw}", f"keine {kw}", f"keinen {kw}",
                        f"nicht {kw}", f"{kw} vermeiden", f"ohne {kw}",
                    ]
                    if any(neg in text for neg in neg_patterns):
                        arch_issues.append({
                            "type": "architecture_conflict",
                            "title": f"Architektur-Konflikt: {rule.name}",
                            "description": (
                                f"Deine Task-Description verneint '{kw}', was im Konflikt mit unserer "
                                f"OpenBrain-Standardvorgabe steht. Regel: {rule.description}"
                            ),
                            "rule_id": rule.id,
                            "severity": rule.severity,
                            "suggestions": [
                                f"Pruefe, ob die Verneinung wirklich noetig ist",
                                "Im Zweifel: halte dich an die Standardvorgabe",
                            ],
                            "recommendation": f"Pruefe explizit, ob die Verneinung von '{kw}' noetig ist.",
                        })
                        break
            if arch_issues:
                issues.extend(arch_issues)
                return {"ok": False, "issues_count": len(issues), "arch_issues": len(arch_issues)}
            return {"ok": True, "issues_count": len(issues)}

        # === check_consistency ===
        if action == "check_consistency":
            desc = (task.description or "").lower()
            title = (task.title or "").lower()
            text = f"{title} {desc}"
            contradiction_pairs = [
                (["oauth", "openid"], ["lokal", "passwort"], "Auth-Konflikt: OAuth/OpenID vs. lokale Passwort-Auth"),
                (["sql", "postgres"], ["nosql", "mongodb", "redis"], "DB-Konflikt: SQL vs. NoSQL"),
                (["synchron", "sync"], ["async", "asynchron"], "Concurrency-Konflikt: synchron vs. asynchron"),
                (["monolith"], ["microservice"], "Architektur-Konflikt: Monolith vs. Microservices"),
                (["websocket"], ["polling"], "Realtime-Pattern: WebSocket vs. Polling"),
                (["serverless"], ["long-running", "langer prozess"], "Serverless nicht fuer long-running"),
            ]
            found_contradictions = []
            for group_a, group_b, desc_text in contradiction_pairs:
                has_a = any(kw in text for kw in group_a)
                has_b = any(kw in text for kw in group_b)
                if has_a and has_b:
                    found_contradictions.append(desc_text)
            if found_contradictions:
                for c in found_contradictions:
                    issues.append({
                        "type": "requirement_contradiction",
                        "title": f"Anforderungs-Widerspruch: {c}",
                        "description": (
                            f"Deine Task-Description enthaelt Widersprueche. Konkrete Konflikte: {c}."
                        ),
                        "suggestions": [
                            "Loese den Widerspruch, indem du eine Option explizit ausschliesst",
                            "Beispiel: 'NICHT lokal, sondern OAuth2'",
                        ],
                        "recommendation": "Vereinfache die Anforderung in eine klare, nicht-widersprüchliche Form.",
                    })
                return {"ok": False, "issues_count": len(issues), "contradictions": found_contradictions}
            return {"ok": True, "issues_count": len(issues)}

        # === decide_triage: finale Entscheidung ===
        if action == "decide_triage":
            n_issues = len(issues)
            from .task_service import TaskService
            if n_issues == 0:
                # OK → todo
                new_status = "todo"
                reason = "cio_triage_approved"
            else:
                # Issues → rueckfrage
                new_status = "rueckfrage"
                reason = "cio_auto_question"
                # Issues in t.meta speichern
                meta = task.meta if isinstance(task.meta, dict) else (_json.loads(task.meta) if task.meta else {})
                meta["cio_question"] = " | ".join(i.get("title", "") for i in issues)
                meta["cio_question_at"] = datetime.utcnow().isoformat()
                meta["cio_question_issues"] = issues
                meta["cio_question_questions"] = []
                # RACI dokumentieren
                raci = self._build_raci_for_task(task)
                meta["triage_raci"] = raci
                from sqlalchemy.orm.attributes import flag_modified
                flag_modified(task, "meta")
                task.meta = meta
            # Status wechseln
            return TaskService.change_status_with_delay(
                self.db, t=task, new_status=new_status,
                agent=step.agent, reason=reason,
                details={"sop_instance_id": instance.id, "sop_step_id": step.id,
                         "issues_count": n_issues, "issues": issues[:5]},
            )
        return {"ok": False, "error": f"unknown triage action: {action}"}

    def _build_raci_for_task(self, task: Task) -> Dict[str, Any]:
        """Baut die RACI-Matrix fuer einen Task (themenabhaengiger C-Agent)."""
        text = f"{(task.title or '').lower()} {(task.description or '').lower()}"
        if any(kw in text for kw in ["security", "auth", "password", "verschlüsselung", "encryption", "oauth", "jwt", "token", "xss", "csrf", "sql-injection", "berechtigung"]):
            c = "pi_security"
        elif any(kw in text for kw in ["architektur", "architecture", "microservice", "soa", "design", "konzept"]):
            c = "pi_coder"
        elif any(kw in text for kw in ["test", "coverage", "pytest", "jest"]):
            c = "pi_tester"
        elif any(kw in text for kw in ["review", "refactor", "code-quality", "clean-code"]):
            c = "pi_reviewer"
        elif any(kw in text for kw in ["bug", "fix", "defect", "fehler", "regression"]):
            c = "pi_fixer"
        else:
            c = None
        return {
            "R": "CIO", "A": "CIO", "C": c or "(keiner)", "I": "CEOdigital",
            "criteria_checked": [
                "1. Description ausfuehrlich genug",
                "2. Keine Verschlechterung des Prozess-Ergebnisses",
                "3. Konsistent mit OpenBrain-Architekturvorgaben",
                "4. Keine Widersprueche in der Anforderung",
            ],
            "auto_approved": True,
        }

    def _execute_rule_action(
        self, instance: SOPInstance, step: SOPStep,
        rule: SOPStepRule, step_result: Dict[str, Any]
    ) -> Optional[str]:
        """Fuehrt die Action einer feuernden Rule aus.

        Liefert die next_step_id (oder None fuer End-State).
        """
        action_type = rule.action_type
        target = rule.action_target
        params = rule.action_params or {}

        if action_type in ("move_status", "approve_triage", "submit_review",
                           "tester_approve", "tester_reject",
                           "cio_final_approve", "cio_final_reject", "start_work"):
            # Sync-Status-Wechsel (ohne weiteren Delay, der ist schon in run_step)
            if not instance.task_id:
                return step.next_step_id
            task = self.db.get(Task, instance.task_id)
            if not task:
                return step.next_step_id
            # Status-Mapping
            status_map = {
                "move_status": target,
                "approve_triage": "todo",
                "start_work": "in_progress",
                "submit_review": "review",
                "tester_approve": "block",
                "tester_reject": "in_progress",
                "cio_final_approve": "done",
            }
            new_status = status_map.get(action_type)
            if new_status:
                TaskService.set_status_sync(
                    self.db, instance.task_id, new_status,
                    agent=step.agent, reason=f"sop_rule:{rule.id}",
                )
            return step.next_step_id

        if action_type == "create_subtask":
            # Sub-Task anlegen
            if instance.task_id:
                sub = TaskService.create_task(
                    self.db, title=params.get("title", "Subtask"),
                    project_id=instance.project_id,
                    description=params.get("description"),
                    status=params.get("status", "todo"),
                    priority=params.get("priority", 50),
                    parent_id=instance.task_id,
                )
                self._log_execution(
                    instance, step_id=step.id, event="subtask_created",
                    agent=step.agent,
                    details={"subtask_id": sub.id, "title": sub.title},
                )
            return step.next_step_id

        if action_type == "spawn_sop":
            sub_sop_id = target or params.get("sop_id")
            if sub_sop_id:
                sub_inst = self.spawn_sub_sop(instance, sub_sop_id, params)
                # Parent wartet auf Sub-SOP
                instance.status = "waiting_sub_sop"
                self._log_execution(
                    instance, step_id=step.id, event="sub_sop_spawned",
                    agent=step.agent,
                    details={"sub_instance_id": sub_inst.id if sub_inst else None,
                             "sop_id": sub_sop_id},
                )
                return step.on_sub_sop_step_id or step.next_step_id
            return step.next_step_id

        if action_type == "escalate":
            self._log_execution(
                instance, step_id=step.id, event="escalated",
                agent=step.agent,
                details={"reason": params.get("reason", "rule escalation"),
                         "target": target},
            )
            if instance.task_id:
                TaskService.set_priority(self.db, instance.task_id, 100)
            return step.fail_step_id or step.next_step_id

        if action_type == "block":
            instance.status = "blocked"
            if instance.task_id:
                TaskService.set_status_sync(
                    self.db, instance.task_id, "block",
                    agent=step.agent, reason=f"sop_rule:block",
                )
            return None  # End-State

        if action_type == "complete":
            return None  # End-State

        if action_type == "goto_step":
            # Direkter Sprung zu einer bestimmten step_id (fuer Quality-Gate Loop-Back)
            target_step = self.db.get(SOPStep, target) if target else None
            if target_step:
                self._log_execution(
                    instance, step_id=step.id, event="goto_step",
                    agent=step.agent,
                    details={"target_step_id": target, "target_name": target_step.name},
                )
                return target
            # Fallback: default next_step_id wenn target nicht existiert
            return step.next_step_id

        # Default: naechster Step
        return step.next_step_id

    # === Navigation ===

    def advance(
        self, instance: SOPInstance, next_step_id: Optional[str],
        step_result: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Geht zum naechsten Step."""
        if not next_step_id:
            return self._complete_instance(instance, None, step_result)
        instance.current_step_id = next_step_id
        self._log_execution(
            instance, step_id=next_step_id, event="step_advanced",
            agent="system",
            details={"from_step": instance.current_step_id,
                     "to_step": next_step_id},
        )
        self.db.commit()
        return {"ok": True, "action": "advanced", "next_step_id": next_step_id}

    def spawn_sub_sop(
        self, parent_instance: SOPInstance, sop_id: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Optional[SOPInstance]:
        """Startet eine Sub-SOP als Kind der parent_instance."""
        sub_inst = self.create_instance(
            sop_id=sop_id,
            project_id=parent_instance.project_id,
            task_id=parent_instance.task_id,
            parent_instance_id=parent_instance.id,
            context=context or {},
        )
        return sub_inst

    def _complete_instance(
        self, instance: SOPInstance, step: Optional[SOPStep],
        step_result: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Markiert die Instance als completed."""
        instance.status = "completed"
        instance.completed_at = datetime.utcnow()
        self._log_execution(
            instance, step_id=step.id if step else None,
            event="instance_completed", agent="system",
            details={"step_result": step_result or {}},
        )
        # Parent-Instance (falls Sub-SOP) reaktivieren
        if instance.parent_instance_id:
            parent = self.db.get(SOPInstance, instance.parent_instance_id)
            if parent and parent.status == "waiting_sub_sop":
                parent.status = "running"
                self._log_execution(
                    parent, step_id=parent.current_step_id,
                    event="sub_sop_completed", agent="system",
                    details={"sub_instance_id": instance.id, "sub_status": instance.status},
                )
        self.db.commit()
        return {"ok": True, "action": "completed", "instance_id": instance.id}

    def fail_instance(
        self, instance: SOPInstance, reason: str
    ) -> Dict[str, Any]:
        """Markiert die Instance als failed."""
        instance.status = "failed"
        instance.completed_at = datetime.utcnow()
        self._log_execution(
            instance, step_id=instance.current_step_id,
            event="instance_failed", agent="system", success=False,
            details={"reason": reason},
        )
        self.db.commit()
        return {"ok": True, "action": "failed", "reason": reason}

    # === Helper ===

    def _log_execution(
        self, instance: SOPInstance, step_id: Optional[str], event: str,
        agent: Optional[str] = None, details: Optional[Dict[str, Any]] = None,
        duration_ms: Optional[int] = None, success: bool = True,
    ) -> SOPExecution:
        ex = SOPExecution(
            instance_id=instance.id,
            step_id=step_id,
            event=event,
            agent=agent,
            details=details or {},
            duration_ms=duration_ms,
            success=success,
        )
        self.db.add(ex)
        self.db.flush()
        return ex


# === Default-SOP-Definitionen ===

DEFAULT_TASK_SOP = {
    "name": "Standard-Workflow Task (User-Direktive 15.06.2026)",
    "description": (
        "Generischer Standard-Workflow fuer einen Task:\n"
        "TRIAGE (CIO Review) -> GO (Worker assigned) -> IN_PROGRESS "
        "(Worker arbeitet) -> REVIEW (Tester Code-Review) -> BLOCK (CIO Final) -> DONE.\n\n"
        "Implementiert die in der Kanban-Operator-Skill beschriebenen Regeln.\n"
        "Mit 5-Sekunden-Verzoegerung pro Step (User-Transparenz)."
    ),
    "category": "task",
    "default_delay_s": 5.0,
    "steps": [
        # Step 1: CIO Triage Review
        {
            "name": "CIO Triage Review",
            "phase": "Task",
            "trigger": "task_created",
            "action": "review_task",
            "agent": "CIO",
            "expected_result": "Task ist vollstaendig, verstaendlich, konfliktfrei",
            "success_criteria": [
                "Title >= 10 Zeichen",
                "Description >= 50 Zeichen",
                "Keine Konflikt-Keywords (TODO, TBD, ??)",
                "Priority 0-100",
            ],
            "delay_s": 5.0,
            "description": (
                "CIO prueft den Task auf Vollstaendigkeit, Verstaendlichkeit, "
                "Konflikte mit bestehender App/Funktion, Konformitaet mit OpenBrain-Entwicklungsvorgaben."
            ),
            "next_step": 1,  # -> Worker Assignment
            "fail_step": 5,  # -> Done (bei block-Abbruch)
            "rules": [
                {
                    "description": (
                        "Task ist vollstaendig: wird in GO verschoben. "
                        "Beispiel-User-Direktive: 'Wird verschoben in GO wenn CIO den Task fuer "
                        "umsetzbar einstuft und keine Widersprueche zu Architektur oder den "
                        "uebergeordneten Entwicklungsregeln gefunden hat.'"
                    ),
                    "condition_field": "step_ok",
                    "condition_operator": "is_true",
                    "condition_value": True,
                    "action_type": "approve_triage",
                    "action_target": "todo",
                    "action_params": {},
                },
                {
                    "description": "Konflikte gefunden: block + Frage an CEOdigital/CEO",
                    "condition_field": "step_ok",
                    "condition_operator": "is_false",
                    "condition_value": True,
                    "action_type": "block",
                    "action_target": "block",
                    "action_params": {"reason": "cio_question"},
                },
            ],
        },
        # Step 2: Worker Assignment
        {
            "name": "Worker Assignment",
            "phase": "Task",
            "trigger": "status_changed:todo",
            "action": "assign_worker",
            "agent": "CIO",
            "expected_result": "Task hat einen Worker (pi-coder, pi-tester, ...)",
            "delay_s": 5.0,
            "description": "CIO weist Task einem relevanten Worker zu.",
            "next_step": 2,  # -> Worker Implementation
            "rules": [
                {
                    "description": "Worker zugewiesen: Task bereit fuer Start",
                    "condition_field": "step_ok",
                    "condition_operator": "is_true",
                    "condition_value": True,
                    "action_type": "start_work",
                    "action_target": "in_progress",
                    "action_params": {},
                },
            ],
        },
        # Step 3: Worker Implementation
        {
            "name": "Worker Implementation",
            "phase": "Task",
            "trigger": "status_changed:in_progress",
            "action": "start_work",
            "agent": "pi-coder",
            "expected_result": "Worker hat Code geschrieben, Tests laufen",
            "delay_s": 5.0,
            "description": "Worker implementiert den Task.",
            "next_step": 3,  # -> Tester Code-Review
            "rules": [
                {
                    "description": "Worker fertig: Submit for Review",
                    "condition_field": "step_ok",
                    "condition_operator": "is_true",
                    "condition_value": True,
                    "action_type": "submit_review",
                    "action_target": "review",
                    "action_params": {},
                },
            ],
        },
        # Step 4: Tester Code-Review
        {
            "name": "Tester Code-Review",
            "phase": "Task",
            "trigger": "status_changed:review",
            "action": "review_task",
            "agent": "pi-tester",
            "expected_result": "Code ist sauber, keine Bugs gefunden",
            "delay_s": 5.0,
            "description": "Tester sucht Schwachstellen, schlecht programmierte Stellen, Bugs.",
            "next_step": 4,  # -> CIO Final-Review
            "fail_step": 2,  # -> Worker Assignment (bei tester_reject -> in_progress)
            "rules": [
                {
                    "description": "Tester OK: Task in BLOCK, Freigabe-Task wird erstellt",
                    "condition_field": "step_ok",
                    "condition_operator": "is_true",
                    "condition_value": True,
                    "action_type": "tester_approve",
                    "action_target": "block",
                    "action_params": {},
                },
                {
                    "description": "Tester findet Bugs: zurueck in IN_PROGRESS",
                    "condition_field": "step_ok",
                    "condition_operator": "is_false",
                    "condition_value": True,
                    "action_type": "tester_reject",
                    "action_target": "in_progress",
                    "action_params": {},
                },
            ],
        },
        # Step 5: CIO Final-Review
        {
            "name": "CIO Final-Review (Freigabe)",
            "phase": "Task",
            "trigger": "status_changed:block",
            "action": "review_task",
            "agent": "CIO",
            "expected_result": "Aufgabe erledigt, Ziele erreicht, Code-Qualitaet OK",
            "delay_s": 5.0,
            "description": "CIO prueft im BLOCK ob Aufgabe erledigt, Ziele erreicht, Code-Qualitaet stimmt.",
            "next_step": 5,  # -> Done
            "fail_step": 2,  # -> Worker Assignment (bei Reject)
            "rules": [
                {
                    "description": "CIO Approve: Task in DONE",
                    "condition_field": "step_ok",
                    "condition_operator": "is_true",
                    "condition_value": True,
                    "action_type": "cio_final_approve",
                    "action_target": "done",
                    "action_params": {},
                },
                {
                    "description": "CIO Reject: zurueck in IN_PROGRESS (Fix-Loop)",
                    "condition_field": "step_ok",
                    "condition_operator": "is_false",
                    "condition_value": True,
                    "action_type": "cio_final_reject",
                    "action_target": "in_progress",
                    "action_params": {"target_status": "in_progress"},
                },
            ],
        },
        # Step 6: Done (End-State)
        {
            "name": "Done",
            "phase": "End",
            "trigger": "status_changed:done",
            "action": "noop",
            "agent": "system",
            "expected_result": "Task abgeschlossen",
            "delay_s": 0.0,
            "description": "End-State. Task ist vollstaendig auditiert.",
            "next_step": None,
            "rules": [
                {
                    "description": "End-State erreicht",
                    "condition_field": "step_ok",
                    "condition_operator": "is_true",
                    "condition_value": True,
                    "action_type": "complete",
                    "action_target": None,
                    "action_params": {},
                },
            ],
        },
    ],
}


# === Default-SOP: Task-Creation (Triage + Prio 1) ===
# User-Direktive 15.06.2026: Jeder neue Task wird mit status=triage + priority=1 angelegt.
DEFAULT_TASK_CREATION_SOP = {
    "name": "Task Creation Default (Triage + Prio 1)",
    "description": (
        "SOP, die festlegt, dass jeder neue Task IMMER in Triage mit Prio 1 "
        "angelegt wird. CIO bewertet im Triage-Prozess und hebt die Prio an. "
        "Verhindert, dass neue Tasks mit Default-Prio 50 die Watchdog-Logik "
        "oder die Sortierung dominieren.\n\n"
        "User-Direktive 15.06.2026. Teil der kanban-operator Skill."
    ),
    "category": "task-creation",
    "default_delay_s": 0.0,
    "steps": [
        {
            "name": "Task anlegen mit Standard-Defaults",
            "phase": "Task",
            "trigger": "task_created",
            "action": "apply_defaults",
            "agent": "system",
            "expected_result": (
                "Task existiert in DB mit status='triage' und priority=1. "
                "History-Eintrag 'task_created' enthaelt details.sop='task-creation-default'."
            ),
            "success_criteria": [
                "Task-Status ist 'triage' (nicht 'todo' oder 'in_progress')",
                "Task-Priority ist 1 (nicht 50 oder hoeher)",
                "History-Eintrag enthaelt SOP-Referenz",
            ],
            "delay_s": 0.0,
            "description": (
                "Beim Anlegen eines neuen Tasks werden folgende Defaults "
                "AUTOMATISCH gesetzt: status='triage', priority=1, "
                "category='new_request', assigned_role='pi-coder'. Diese "
                "Defaults sind Teil der SOP und duerfen nur durch explizite "
                "Argumente ueberschrieben werden (z.B. fuer Sub-Tasks oder "
                "System-Tasks).\n\n"
                "API-Endpoint: POST /api/kanban/tasks\n"
                "Backend-Funktion: TaskService.create_task()"
            ),
            "next_step": 1,  # -> Process Triage
            "rules": [
                {
                    "description": (
                        "Task wurde erfolgreich mit status=triage + priority=1 "
                        "angelegt. History-Eintrag dokumentiert die SOP-Anwendung."
                    ),
                    "condition_field": "step_ok",
                    "condition_operator": "is_true",
                    "condition_value": True,
                    "action_type": "complete",
                    "action_target": None,
                    "action_params": {},
                },
            ],
        },
        {
            "name": "Triage-Prozess durchfuehren",
            "phase": "Task",
            "trigger": "manual OR process_triage_endpoint",
            "action": "evaluate_and_move_to_todo",
            "agent": "CIO",
            "expected_result": (
                "Task-Status ist 'todo' (Auto-Claim triggert Worker-Start), "
                "Priority ist passend zur Komplexitaet (25/50/75/100), "
                "History-Eintrag 'status_changed' mit details.reason='process_triage'."
            ),
            "success_criteria": [
                "Status ist nicht mehr 'triage'",
                "Priority ist >= 25 (CIO hat bewertet)",
                "History-Eintrag dokumentiert die Triage-Entscheidung",
            ],
            "delay_s": 0.0,
            "description": (
                "Der CIO bewertet den Triage-Task: liest Description, prueft "
                "Klarheit, setzt passende Prio (25/50/75/100) und schiebt den "
                "Task auf 'todo'.\n\n"
                "Trigger: User klickt 'Process Triage' (Bulk fuer alle "
                "Triage-Tasks eines Projekts) oder manuell via Task-Detail-Sidebar.\n\n"
                "Logik: Basiert auf Description-Laenge: desc>500 -> Prio 75, "
                ">200 -> 50, sonst -> 25. Role: 'pi-tester' wenn 'test'/"
                "'pruefen' im Text, sonst 'pi-coder'."
            ),
            "next_step": None,  # End-State
            "rules": [
                {
                    "description": "Triage abgeschlossen: Task in todo",
                    "condition_field": "step_ok",
                    "condition_operator": "is_true",
                    "condition_value": True,
                    "action_type": "complete",
                    "action_target": None,
                    "action_params": {},
                },
            ],
        },
    ],
}


# === Default-SOP: CIO Triage Review (User-Direktive 16.06.2026) ===
# Generischer 4-Kriterien-Check, deklarativ in der DB gespeichert.
# Aktionen 'check_*' werden in SOPEngine._execute_action registriert.
DEFAULT_CIO_TRIAGE_SOP = {
    "name": "CIO Triage Review (4 Kriterien)",
    "description": (
        "Generischer Triage-Prozess fuer neu erstellte Tasks. Prueft 4 Kriterien:\n"
        "  1. Description ausfuehrlich genug (Aufgabe + Ergebnis klar)\n"
        "  2. Keine Verschlechterung des Prozess-Ergebnisses\n"
        "  3. Konsistent mit OpenBrain-Architekturvorgaben\n"
        "  4. Keine Widersprueche in der Anforderung\n\n"
        "RACI: R+A = CIO, C = themenabhaengig, I = CEOdigital.\n"
        "Bei allen Kriterien OK → Status 'todo'. Bei Issues → Status 'rueckfrage' mit Frage."
    ),
    "category": "triage",
    "default_delay_s": 5.0,
    "steps": [
        {
            "name": "Title-Check",
            "phase": "Check",
            "trigger": "task_created",
            "action": "check_title",
            "agent": "CIO",
            "expected_result": "Titel >= 10 Zeichen, klar formuliert",
            "success_criteria": ["Titel enthaelt konkrete Aufgabe", "Titel hat >= 10 Zeichen"],
            "delay_s": 0.5,
            "description": "Prueft, ob der Titel aussagekraeftig genug ist.",
            "next_step": 1,
            "rules": [
                {
                    "description": "Title OK (>= 10 Zeichen)",
                    "condition_field": "step_ok",
                    "condition_operator": "is_true",
                    "condition_value": True,
                    "action_type": "complete",
                    "action_target": None,
                    "action_params": {},
                },
                {
                    "description": "Title zu kurz — Issue sammeln",
                    "condition_field": "step_ok",
                    "condition_operator": "is_false",
                    "condition_value": True,
                    "action_type": "collect_issue",
                    "action_target": None,
                    "action_params": {"issue_type": "title_too_short"},
                },
            ],
        },
        {
            "name": "Description-Check",
            "phase": "Check",
            "trigger": "task_created",
            "action": "check_description",
            "agent": "CIO",
            "expected_result": "Description >= 50 Zeichen mit Ziel + Akzeptanzkriterien",
            "success_criteria": ["Description >= 50 Zeichen", "Struktur: Ziel / Akzeptanz / Edge-Cases"],
            "delay_s": 0.5,
            "description": "Prueft, ob die Description ausfuehrlich genug ist.",
            "next_step": 2,
            "rules": [
                {
                    "description": "Description OK",
                    "condition_field": "step_ok",
                    "condition_operator": "is_true",
                    "condition_value": True,
                    "action_type": "complete",
                    "action_target": None,
                    "action_params": {},
                },
                {
                    "description": "Description fehlt / zu kurz",
                    "condition_field": "step_ok",
                    "condition_operator": "is_false",
                    "condition_value": True,
                    "action_type": "collect_issue",
                    "action_target": None,
                    "action_params": {"issue_type": "description_too_short"},
                },
            ],
        },
        {
            "name": "Success-Criteria-Check",
            "phase": "Check",
            "trigger": "task_created",
            "action": "check_success_criteria",
            "agent": "CIO",
            "expected_result": "Mindestens 1 Success-Criterion definiert",
            "success_criteria": ["success_criteria.length >= 1"],
            "delay_s": 0.5,
            "description": "Prueft, ob Akzeptanzkriterien definiert sind.",
            "next_step": 3,
            "rules": [
                {
                    "description": "Success-Criteria OK",
                    "condition_field": "step_ok",
                    "condition_operator": "is_true",
                    "condition_value": True,
                    "action_type": "complete",
                    "action_target": None,
                    "action_params": {},
                },
                {
                    "description": "Keine Success-Criteria definiert",
                    "condition_field": "step_ok",
                    "condition_operator": "is_false",
                    "condition_value": True,
                    "action_type": "collect_issue",
                    "action_target": None,
                    "action_params": {"issue_type": "no_success_criteria"},
                },
            ],
        },
        {
            "name": "Architektur-Alignment",
            "phase": "Check",
            "trigger": "task_created",
            "action": "check_architecture",
            "agent": "CIO",
            "expected_result": "Keine Konflikte mit OpenBrain-Standardvorgaben",
            "success_criteria": ["Keine explizite Verneinung von Architektur-Keywords"],
            "delay_s": 0.5,
            "description": "Prueft, ob die Description gegen OpenBrain-Architekturvorgaben verstoesst.",
            "next_step": 4,
            "rules": [
                {
                    "description": "Architektur OK",
                    "condition_field": "step_ok",
                    "condition_operator": "is_true",
                    "condition_value": True,
                    "action_type": "complete",
                    "action_target": None,
                    "action_params": {},
                },
                {
                    "description": "Architektur-Konflikt gefunden",
                    "condition_field": "step_ok",
                    "condition_operator": "is_false",
                    "condition_value": True,
                    "action_type": "collect_issue",
                    "action_target": None,
                    "action_params": {"issue_type": "architecture_conflict"},
                },
            ],
        },
        {
            "name": "Requirement-Consistency",
            "phase": "Check",
            "trigger": "task_created",
            "action": "check_consistency",
            "agent": "CIO",
            "expected_result": "Keine internen Widersprueche in der Anforderung",
            "success_criteria": ["Keine Konflikt-Paare (OAuth+lokal, SQL+NoSQL, etc.)"],
            "delay_s": 0.5,
            "description": "Prueft auf logische Widersprueche in der Anforderung.",
            "next_step": 5,
            "rules": [
                {
                    "description": "Konsistenz OK",
                    "condition_field": "step_ok",
                    "condition_operator": "is_true",
                    "condition_value": True,
                    "action_type": "complete",
                    "action_target": None,
                    "action_params": {},
                },
                {
                    "description": "Widerspruch gefunden",
                    "condition_field": "step_ok",
                    "condition_operator": "is_false",
                    "condition_value": True,
                    "action_type": "collect_issue",
                    "action_target": None,
                    "action_params": {"issue_type": "requirement_contradiction"},
                },
            ],
        },
        {
            "name": "Entscheidung: OK oder Rueckfrage",
            "phase": "Decision",
            "trigger": "task_created",
            "action": "decide_triage",
            "agent": "CIO",
            "expected_result": "Task → 'todo' (OK) oder 'rueckfrage' (Issues)",
            "success_criteria": ["Status-Wechsel dokumentiert", "Issues im t.meta gespeichert"],
            "delay_s": 0.5,
            "description": (
                "Entscheidung: wenn keine Issues gesammelt → move_status 'todo'. "
                "Wenn Issues vorhanden → move_status 'rueckfrage' + Frage."
            ),
            "next_step": None,
            "rules": [
                {
                    "description": "Keine Issues → Status 'todo'",
                    "condition_field": "issues_count",
                    "condition_operator": "is_zero",
                    "condition_value": 0,
                    "action_type": "move_status",
                    "action_target": "todo",
                    "action_params": {"reason": "cio_triage_approved", "next_agent": "Worker"},
                },
                {
                    "description": "Issues gefunden → Status 'rueckfrage' + Frage an CEOdigital",
                    "condition_field": "issues_count",
                    "condition_operator": "gt",
                    "condition_value": 0,
                    "action_type": "move_status",
                    "action_target": "rueckfrage",
                    "action_params": {"reason": "cio_auto_question", "next_agent": "CEOdigital"},
                },
            ],
        },
    ],
}


def seed_default_sops(db: Session) -> int:
    """Seeded die Standard-SOPs, falls noch nicht vorhanden."""
    added = 0
    for sop_def in (DEFAULT_TASK_SOP, DEFAULT_TASK_CREATION_SOP, DEFAULT_CIO_TRIAGE_SOP):
        existing = db.execute(
            select(SOP).where(SOP.name == sop_def["name"])
        ).scalar_one_or_none()
        if existing:
            continue
        engine = SOPEngine(db)
        sop = engine.create_sop(
            name=sop_def["name"],
            description=sop_def["description"],
            category=sop_def["category"],
            default_delay_s=sop_def["default_delay_s"],
            steps=sop_def["steps"],
        )
        if sop:
            added += 1
    return added
