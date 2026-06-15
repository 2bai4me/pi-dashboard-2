"""TaskService — Business-Logic fuer Tasks + Pricing-Snapshot-Mechanik."""
from __future__ import annotations

import logging
import secrets
from datetime import datetime
from decimal import Decimal
from typing import Optional, List, Dict, Any

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from ..models.project import Project
from ..models.task import Task
from ..models.history import TaskHistory
from ..models.token_usage import TokenUsage
from .pricing_service import (
    take_pricing_snapshot, calc_cost_from_snapshot, get_current_pricing,
)

logger = logging.getLogger("pi-dashboard-2")


def _gen_id() -> str:
    return secrets.token_hex(6)


class TaskService:
    """Service-Klasse fuer Task-Operationen."""

    @staticmethod
    def list_tasks(db: Session, project_id: Optional[str] = None,
                   status: Optional[str] = None) -> List[Task]:
        stmt = select(Task).order_by(Task.priority.desc(), Task.created_at.asc())
        if project_id:
            stmt = stmt.where(Task.project_id == project_id)
        if status:
            stmt = stmt.where(Task.status == status)
        return list(db.execute(stmt).scalars())

    @staticmethod
    def get_task(db: Session, task_id: str) -> Optional[Task]:
        return db.get(Task, task_id)

    @staticmethod
    def create_task(db: Session, title: str, project_id: Optional[str] = None,
                   description: Optional[str] = None, status: str = "triage",
                   priority: int = 50, category: str = "new_request",
                   parent_id: Optional[str] = None,
                   assigned_role: Optional[str] = None) -> Task:
        t = Task(
            id=_gen_id(),
            project_id=project_id,
            parent_id=parent_id,
            title=title,
            description=description,
            status=status,
            priority=priority,
            category=category,
            assigned_role=assigned_role or "pi-coder",
            tags=[],
            success_criteria=[],
            meta={},
        )
        db.add(t)
        db.flush()
        # History: task_created
        TaskService._add_history(db, t, "task_created", agent="system",
                                 details={"reason": "manual creation"})
        db.commit()
        db.refresh(t)
        return t

    @staticmethod
    def update_task(db: Session, task_id: str, **fields) -> Optional[Task]:
        t = db.get(Task, task_id)
        if not t:
            return None
        for k, v in fields.items():
            if v is not None and hasattr(t, k):
                setattr(t, k, v)
        t.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(t)
        return t

    @staticmethod
    def set_status(db: Session, task_id: str, new_status: str) -> Optional[Task]:
        """Setzt Status + auto_claim bei todo + emergency_watchdog bei Prio>=90."""
        t = db.get(Task, task_id)
        if not t:
            return None
        old_status = t.status
        t.status = new_status
        t.updated_at = datetime.utcnow()

        if new_status == "todo" and old_status != "in_progress":
            # Auto-Claim
            t.status = "in_progress"
            t.claimed_at = datetime.utcnow()
            if not t.assigned_role:
                t.assigned_role = "pi-coder"
            # Snapshot anlegen
            take_pricing_snapshot(t, db=db)
            TaskService._add_history(db, t, "auto_claim", agent="system",
                                     details={"reason": "status_changed_to_todo",
                                              "assigned_role": t.assigned_role})

        if t.priority >= 90 and t.status != "done" and not t.emergency:
            # Emergency-Watchdog
            t.emergency = True
            from datetime import datetime as _dt
            t.emergency_at = _dt.utcnow()
            take_pricing_snapshot(t, db=db)
            TaskService._add_history(db, t, "watchdog_triggered", agent="system",
                                     details={"reason": "priority>=90"})
        elif t.priority < 90 and t.emergency:
            t.emergency = False

        TaskService._add_history(db, t, "status_changed", agent="system",
                                 details={"from": old_status, "to": new_status})
        db.commit()
        db.refresh(t)
        return t

    @staticmethod
    def set_priority(db: Session, task_id: str, priority: int) -> Optional[Task]:
        """Setzt Prio (Notfall-Watchdog bei >= 90)."""
        t = db.get(Task, task_id)
        if not t:
            return None
        old = t.priority
        t.priority = priority
        t.updated_at = datetime.utcnow()
        if priority >= 90 and t.status != "done":
            t.emergency = True
            t.emergency_at = datetime.utcnow()
            take_pricing_snapshot(t, db=db)
            TaskService._add_history(db, t, "emergency_watchdog", agent="system",
                                     details={"old_prio": old, "new_prio": priority})
        elif priority < 90 and t.emergency:
            t.emergency = False
            t.emergency_cleared_at = datetime.utcnow()
        TaskService._add_history(db, t, "priority_changed", agent="system",
                                 details={"from": old, "to": priority})
        db.commit()
        db.refresh(t)
        return t

    @staticmethod
    def report_dispatch(db: Session, task_id: str, role: str, status: str,
                        model: str, agent_pid: Optional[int] = None,
                        reason: Optional[str] = None,
                        tokens_in: int = 0, tokens_out: int = 0) -> Optional[Dict[str, Any]]:
        """Sub-Agent meldet Dispatch-Status zurueck."""
        t = db.get(Task, task_id)
        if not t:
            return None
        t.assigned_subagent = role
        t.updated_at = datetime.utcnow()
        if not t.pricing_snapshot or t.pricing_snapshot.get("model") != model:
            take_pricing_snapshot(t, model_id=model, db=db)
        snap = t.pricing_snapshot
        cost = calc_cost_from_snapshot(tokens_in, tokens_out, snap)
        TaskService._add_history(db, t, "subagent_dispatched", agent=role,
                                 model=model, tokens_in=tokens_in, tokens_out=tokens_out,
                                 cost_usd=cost,
                                 details={"status": status, "agent_pid": agent_pid,
                                          "reason": reason, "pricing_snapshot_used": snap})
        db.commit()
        db.refresh(t)
        return {"ok": True, "task_id": task_id, "model": model, "cost_usd": float(cost),
                "pricing_snapshot": snap}

    @staticmethod
    def report_usage(db: Session, task_id: str, tokens_in: int, tokens_out: int,
                     model: Optional[str] = None, role: Optional[str] = None,
                     note: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Sub-Agent meldet kumulierte Token-Counts."""
        t = db.get(Task, task_id)
        if not t:
            return None
        model = model or t.assigned_subagent_model or "minimax/minimax-m3"
        if not t.pricing_snapshot or t.pricing_snapshot.get("model") != model:
            take_pricing_snapshot(t, model_id=model, db=db)
        snap = t.pricing_snapshot
        cost = calc_cost_from_snapshot(tokens_in, tokens_out, snap)
        # History
        h = TaskService._add_history(db, t, "token_usage_report", agent=role or t.assigned_subagent or "subagent",
                                     model=model, tokens_in=tokens_in, tokens_out=tokens_out,
                                     cost_usd=cost,
                                     details={"note": note or "", "pricing_snapshot_used": snap},
                                     return_entry=True)
        # TokenUsage-Record (fuer Analytics)
        in_per_m  = Decimal(str(snap.get("input_per_1m", "0")))
        out_per_m = Decimal(str(snap.get("output_per_1m", "0")))
        tu = TokenUsage(
            task_id=t.id,
            history_id=h.id,
            model=model,
            provider=snap.get("provider", "unknown"),
            role=role,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=cost,
            input_per_1m=in_per_m,
            output_per_1m=out_per_m,
            pricing_source=snap.get("source"),
            snapshot_at=datetime.fromisoformat(snap["snapshot_at"]) if snap.get("snapshot_at") else None,
        )
        db.add(tu)
        db.commit()
        db.refresh(t)
        return {"ok": True, "task_id": task_id, "tokens_in": tokens_in, "tokens_out": tokens_out,
                "cost_usd": float(cost), "pricing_snapshot": snap}

    @staticmethod
    def delete_task(db: Session, task_id: str) -> bool:
        t = db.get(Task, task_id)
        if not t:
            return False
        db.delete(t)
        db.commit()
        return True

    @staticmethod
    def _add_history(db: Session, t: Task, event: str, agent: str = "system",
                     model: Optional[str] = None,
                     tokens_in: int = 0, tokens_out: int = 0,
                     cost_usd: Optional[Decimal] = None,
                     details: Optional[Dict[str, Any]] = None,
                     return_entry: bool = False):
        h = TaskHistory(
            task_id=t.id, event=event, agent=agent, model=model,
            tokens_in=tokens_in, tokens_out=tokens_out,
            cost_usd=cost_usd or Decimal("0"),
            details=details or {},
        )
        db.add(h)
        db.flush()
        return h if return_entry else None

    @staticmethod
    def task_stats(db: Session, task_id: str) -> Dict[str, Any]:
        """Aggregierte Stats: tokens, cost, model, duration, history_count, snapshot."""
        t = db.get(Task, task_id)
        if not t:
            return {}
        history = list(db.execute(
            select(TaskHistory).where(TaskHistory.task_id == task_id).order_by(TaskHistory.ts)
        ).scalars())
        tokens_in  = sum(h.tokens_in for h in history)
        tokens_out = sum(h.tokens_out for h in history)
        snap = t.pricing_snapshot
        if snap:
            cost = float(calc_cost_from_snapshot(tokens_in, tokens_out, snap))
        else:
            cost = float(sum(h.cost_usd for h in history))
        model_usage: Dict[str, int] = {}
        for h in history:
            m = h.model or "unknown"
            model_usage[m] = model_usage.get(m, 0) + 1
        main_model = max(model_usage, key=model_usage.get) if model_usage else "unknown"
        # Duration
        duration_s = 0
        if len(history) >= 1:
            try:
                duration_s = int((history[-1].ts - history[0].ts).total_seconds())
            except (AttributeError, TypeError):
                pass
        return {
            "task_id":          task_id,
            "model":            main_model,
            "model_usage":      model_usage,
            "tokens":           {"in": tokens_in, "out": tokens_out, "total": tokens_in + tokens_out},
            "cost_usd":         cost,
            "duration_s":       duration_s,
            "history_count":    len(history),
            "pricing_snapshot": snap,
        }

    @staticmethod
    def generate_completion_report(db: Session, project: Project) -> str:
        """Generiert ausfuehrlichen Abschlussbericht im Markdown-Format."""
        from ..models.history import TaskHistory
        from ..models.token_usage import TokenUsage
        from sqlalchemy import func as sqlfunc

        tasks = list(db.execute(select(Task).where(Task.project_id == project.id)).scalars())
        # Status-Distribution
        status_dist: Dict[str, int] = {}
        for t in tasks:
            status_dist[t.status] = status_dist.get(t.status, 0) + 1
        # Token-Aggregation
        tokens = db.execute(
            select(
                sqlfunc.coalesce(sqlfunc.sum(TokenUsage.tokens_in), 0),
                sqlfunc.coalesce(sqlfunc.sum(TokenUsage.tokens_out), 0),
                sqlfunc.coalesce(sqlfunc.sum(TokenUsage.cost_usd), 0),
            )
            .join(Task, Task.id == TokenUsage.task_id)
            .where(Task.project_id == project.id)
        ).one()
        total_in, total_out, total_cost = tokens
        # Cost by Provider
        cost_by_prov: Dict[str, float] = {}
        cost_by_role: Dict[str, float] = {}
        cost_by_model: Dict[str, float] = {}
        rows = db.execute(
            select(TokenUsage.provider, TokenUsage.role, TokenUsage.model, TokenUsage.cost_usd)
            .join(Task, Task.id == TokenUsage.task_id)
            .where(Task.project_id == project.id)
        ).all()
        for prov, role, model, cost in rows:
            if prov:
                cost_by_prov[prov] = cost_by_prov.get(prov, 0) + float(cost)
            if role:
                cost_by_role[role] = cost_by_role.get(role, 0) + float(cost)
            if model:
                cost_by_model[model] = cost_by_model.get(model, 0) + float(cost)
        # Top 5 teuerste Tasks (sortiert nach Summe-Cost DESC)
        cost_col = sqlfunc.coalesce(sqlfunc.sum(TokenUsage.cost_usd), 0).label("c")
        top5 = db.execute(
            select(Task.id, Task.title, cost_col)
            .join(TokenUsage, TokenUsage.task_id == Task.id, isouter=True)
            .where(Task.project_id == project.id)
            .group_by(Task.id, Task.title)
            .order_by(cost_col.desc())
            .limit(5)
        ).all()
        top5_list = [{"id": t[0], "title": t[1], "cost_usd": float(t[2])} for t in top5]
        # Duration
        dur_days = 0
        if project.created_at:
            dur = datetime.utcnow() - project.created_at
            dur_days = dur.days

        # Markdown-Report
        lines = [
            f"# Abschlussbericht: {project.name}",
            "",
            f"**Projekt-ID:** {project.id}",
            f"**Abgeschlossen am:** {datetime.utcnow().isoformat()}",
            f"**Dauer:** {dur_days} Tage",
            f"**Modus:** {project.mode}",
            f"**Kategorie (ITIL):** {project.category}",
            "",
            "## Kennzahlen-Uebersicht",
            "",
            f"- **Tasks gesamt:** {len(tasks)}",
        ]
        for status, cnt in sorted(status_dist.items(), key=lambda x: -x[1]):
            lines.append(f"  - {status}: {cnt}")
        lines += [
            f"- **Tokens (Input):** {total_in:,}".replace(",", "."),
            f"- **Tokens (Output):** {total_out:,}".replace(",", "."),
            f"- **Gesamtkosten:** ${float(total_cost):.4f}",
            "",
            "## Kosten pro Provider",
            "",
        ]
        for prov, c in sorted(cost_by_prov.items(), key=lambda x: -x[1]):
            lines.append(f"- **{prov}:** ${c:.4f}")
        if not cost_by_prov:
            lines.append("- (keine Provider-Kosten erfasst)")
        lines += ["", "## Kosten pro Rolle", ""]
        for role, c in sorted(cost_by_role.items(), key=lambda x: -x[1]):
            lines.append(f"- **{role}:** ${c:.4f}")
        if not cost_by_role:
            lines.append("- (keine Rollen-Kosten erfasst)")
        lines += ["", "## Kosten pro Modell", ""]
        for m, c in sorted(cost_by_model.items(), key=lambda x: -x[1]):
            lines.append(f"- **{m}:** ${c:.4f}")
        if not cost_by_model:
            lines.append("- (keine Modell-Kosten erfasst)")
        lines += [
            "",
            "## Top 5 teuerste Tasks",
            "",
        ]
        for i, t in enumerate(top5_list, 1):
            lines.append(f"{i}. **{t['title'][:60]}** — ${t['cost_usd']:.4f} (`{t['id'][:12]}`)")
        if not top5_list:
            lines.append("- (keine Tasks mit Kosten erfasst)")

        return "\n".join(lines)
