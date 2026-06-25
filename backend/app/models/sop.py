"""SOP-Modelle (Standard Operating Procedures) — generische Regelprozesse.

User-Direktive 15.06.2026:
  Der bisherige hartcodierte Workflow (TRIAGE -> GO -> IN_PROGRESS -> REVIEW ->
  BLOCK -> DONE) soll in ein GENERISCHES, wiederverwendbares SOP-System
  ueberfuehrt werden.

Architektur:
  SOP (Definition)         = die Vorlage (z.B. "Standard-Task-Workflow")
   |- Step 1 (Phase: Task, Trigger: task_created, Action: review, Agent: CIO, ...)
   |   |- Rule 1: if cio_approved == true -> move_status to "todo"
   |   |- Rule 2: if conflicts_found == true -> move_status to "block"
   |- Step 2 (Phase: Task, Trigger: status=todo, Action: assign_worker, ...)
   |- ...
  SOP-Instance             = laufende Ausfuehrung (an Projekt/Task gebunden)
  SOP-Execution            = Audit-Log

Sub-SOPs:
  Ein Step kann eine Sub-SOP starten (action_type="spawn_sop") — Parent-Instance
  wartet, bis Sub-SOP-Instance completed ist.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional, List, TYPE_CHECKING
from sqlalchemy import String, Text, DateTime, Integer, Float, Boolean, ForeignKey, Index, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from ..db.base import Base
from .task import JSONType

if TYPE_CHECKING:
    from .project import Project
    from .task import Task


# === SOP-Definition (Vorlage) ===

class SOP(Base):
    """Eine Standard Operating Procedure — wiederverwendbarer Regelprozess.

    Eine SOP enthaelt eine geordnete Liste von Steps. Jeder Step hat einen
    Trigger (wann er feuert), eine Action (was passiert), einen Agent (wer
    arbeitet) und Rules (Wenn-Dann-Logik fuer den Status-Wechsel).
    """
    __tablename__ = "sops"

    # === Primary Key ===
    id: Mapped[str] = mapped_column(String(32), primary_key=True)

    # === Identifikation ===
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(64), default="task", nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # === SOP-Key (User-Direktive 24.06.2026) ===
    # Eindeutiger, stabiler Key fuer den Match bei seed_default_sops().
    # Bleibt unveraendert, auch wenn der User die SOP umbenennt.
    # Default-SOPs haben Keys wie "task_workflow", "cio_triage".
    sop_key: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)

    # === User-Modification-Flag (User-Direktive 24.06.2026) ===
    # Wenn True: Der User hat die SOP manuell geaendert.
    # seed_default_sops() ueberschreibt sie NICHT mehr beim Startup.
    user_modified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # === Hierarchie (Sub-SOPs) ===
    parent_sop_id: Mapped[Optional[str]] = mapped_column(
        String(32), ForeignKey("sops.id", ondelete="SET NULL")
    )
    is_template: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # === BPMN-Visualisierung (optional) ===
    bpmn_xml: Mapped[Optional[str]] = mapped_column(Text)
    uml_sequence_diagram: Mapped[Optional[str]] = mapped_column(Text)

    # === Default-Werte ===
    default_delay_s: Mapped[float] = mapped_column(Float, default=5.0, nullable=False)

    # === Timestamps ===
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # === Relations ===
    steps: Mapped[List["SOPStep"]] = relationship(
        "SOPStep", back_populates="sop", cascade="all, delete-orphan",
        order_by="SOPStep.step_order",
        lazy="selectin",
    )
    parent: Mapped[Optional["SOP"]] = relationship(
        "SOP", remote_side=[id], backref="children"
    )
    instances: Mapped[List["SOPInstance"]] = relationship(
        "SOPInstance", back_populates="sop"
    )

    # === Indizes ===
    __table_args__ = (
        Index("idx_sops_category", "category"),
        Index("idx_sops_parent", "parent_sop_id"),
        Index("idx_sops_name_version", "name", "version"),
    )

    def __repr__(self) -> str:
        return f"<SOP {self.id[:8]} '{self.name}' v{self.version} steps={len(self.steps or [])}>"

    def to_dict(self, include_steps: bool = True) -> dict:
        result = {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "version": self.version,
            "parent_sop_id": self.parent_sop_id,
            "is_template": self.is_template,
            "default_delay_s": self.default_delay_s,
            "step_count": len(self.steps or []),
            "bpmn_xml": self.bpmn_xml,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_steps:
            result["steps"] = [s.to_dict() for s in (self.steps or [])]
        return result


# === SOP-Step (Schritt in einer SOP) ===

class SOPStep(Base):
    """Ein einzelner Schritt in einer SOP.

    Felder gemaess User-Direktive:
      - phase: z.B. "Task", "Decision", "Sub-SOP", "End"
      - trigger: wann feuert der Step (z.B. "task_created", "status=triage", "manual")
      - action: was wird getan (z.B. "review_task", "move_status", "spawn_sop")
      - agent: wer arbeitet (z.B. "CIO", "pi-coder")
      - expected_result: was soll am Ende rauskommen (z.B. "Task in GO")
      - rules: Wenn-Dann-Logik fuer Status-Wechsel
    """
    __tablename__ = "sop_steps"

    # === Primary Key ===
    id: Mapped[str] = mapped_column(String(32), primary_key=True)

    # === Foreign Key ===
    sop_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("sops.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # === Schritt-Reihenfolge ===
    step_order: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    # === Phase (Art des Schritts) ===
    phase: Mapped[str] = mapped_column(String(64), default="Task", nullable=False)
    # Moegliche Phasen: "Task" (Standard-Schritt), "Decision" (Verzweigung),
    # "Sub-SOP" (startet Sub-SOP), "End" (End-State), "Wait" (Timer), "Notification"

    # === Trigger (WANN feuert der Step) ===
    trigger: Mapped[str] = mapped_column(String(255), nullable=False)
    # Beispiele: "task_created", "task_status=triage", "task_priority>=90",
    #            "manual", "sub_sop_completed", "time_elapsed:24h"

    # === Action (WAS wird getan) ===
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    # Beispiele: "review_task", "approve_triage", "assign_worker", "start_work",
    #            "submit_review", "tester_review", "move_status", "spawn_sop"

    # === Action-Parameter (JSON) ===
    action_params: Mapped[Optional[dict]] = mapped_column(JSONType, default=dict)

    # === Agent (WER arbeitet) ===
    agent: Mapped[str] = mapped_column(String(64), nullable=False)
    # Beispiele: "CIO", "pi-coder", "pi-tester", "pi-reviewer", "pi-fixer",
    #            "CEO-digital", "system", "user"

    # === LLM-Modell fuer diesen Step (Optional, default: MiniMax M3) ===
    model: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    # Beispiele: "minimax-direct/minimax-m3", "ollama/gemma3:12b"

    # === Erwartetes Ergebnis ===
    expected_result: Mapped[Optional[str]] = mapped_column(Text)
    success_criteria: Mapped[Optional[list]] = mapped_column(JSONType, default=list)

    # === RACI-Matrix (User-Direktive 15.06.2026) ===
    raci_r: Mapped[Optional[str]] = mapped_column(String(64))  # Responsible
    raci_a: Mapped[Optional[str]] = mapped_column(String(64))  # Accountable
    raci_c: Mapped[Optional[str]] = mapped_column(String(255))  # Consulted (kommagetrennt)
    raci_i: Mapped[Optional[str]] = mapped_column(String(255))  # Informed (kommagetrennt)

    # === Visuelle Position im BPMN-Designer (optional) ===
    x: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    y: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # === Verzweigungen (naechster Step) ===
    next_step_id: Mapped[Optional[str]] = mapped_column(
        String(32), ForeignKey("sop_steps.id", ondelete="SET NULL")
    )
    fail_step_id: Mapped[Optional[str]] = mapped_column(
        String(32), ForeignKey("sop_steps.id", ondelete="SET NULL")
    )
    on_sub_sop_step_id: Mapped[Optional[str]] = mapped_column(
        String(32), ForeignKey("sop_steps.id", ondelete="SET NULL"),
        comment="Wohin geht's, wenn eine Sub-SOP in diesem Step gestartet wurde?"
    )

    # === Delay (Verarbeitungsverzoegerung) ===
    delay_s: Mapped[float] = mapped_column(Float, default=5.0, nullable=False)

    # === Beschreibung ===
    description: Mapped[Optional[str]] = mapped_column(Text)

    # === CIO-Triage-Felder (User-Direktive 16.06.2026, Schritt 0) ===
    # task_types: Welche Task-Typen dieser Step klassifizieren soll
    #            (z.B. ["new_request", "change", "ticket", "bugfix"])
    task_types: Mapped[Optional[list]] = mapped_column(JSONType, default=list)

    # standards_refs: Welche Standardvorgaben der CIO pruefen soll
    #            (Verweise auf architecture_rules.id oder openbrain-tags)
    standards_refs: Mapped[Optional[list]] = mapped_column(JSONType, default=list)

    # change_requirements: Strukturierte Vorgaben fuer die Aenderungsbeschreibung
    #            (z.B. [{"field": "files_to_change", "required": true, "description": "..."}])
    change_requirements: Mapped[Optional[list]] = mapped_column(JSONType, default=list)

    # subagent_requirements: Was der Subagent braucht (gem. Swarm-Anforderungen)
    #            (z.B. [{"name": "model", "required": true}, {"name": "branch", "required": true}])
    subagent_requirements: Mapped[Optional[list]] = mapped_column(JSONType, default=list)

    # === User-Input-Tool (User-Direktive 17.06.2026) ===
    # Wenn input_tool_required=True, wird der Step blockierend:
    #   1) Beim Ausfuehren pruefen ob context[input_tool_context_key] schon existiert
    #   2) Wenn nein: AgentQuestion erstellen mit input_tool_prompt
    #   3) Auf User-Antwort warten (long-poll)
    #   4) Antwort in instance.context[context_key] speichern
    #   5) Step als completed markieren, zum naechsten Step gehen
    input_tool_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    input_tool_type: Mapped[Optional[str]] = mapped_column(String(32))
    # Erlaubte Typen: text | confirmation | choice | image | attachment
    input_tool_prompt: Mapped[Optional[str]] = mapped_column(Text)
    input_tool_description: Mapped[Optional[str]] = mapped_column(Text)  # mehr Kontext zur Frage
    input_tool_recommendation: Mapped[Optional[str]] = mapped_column(Text)  # vorgeschlagene Antwort
    input_tool_options: Mapped[Optional[str]] = mapped_column(Text)  # JSON-Liste (nur bei choice)
    input_tool_options_config: Mapped[Optional[str]] = mapped_column(Text)  # JSON: show_description, show_recommendation, ...
    input_tool_context_key: Mapped[Optional[str]] = mapped_column(String(64))

    # === Relations ===
    sop: Mapped["SOP"] = relationship("SOP", back_populates="steps")
    rules: Mapped[List["SOPStepRule"]] = relationship(
        "SOPStepRule", back_populates="step", cascade="all, delete-orphan",
        order_by="SOPStepRule.rule_order",
        lazy="selectin",
    )

    # === Indizes ===
    __table_args__ = (
        Index("idx_sop_steps_sop_order", "sop_id", "step_order"),
    )

    def __repr__(self) -> str:
        return f"<SOPStep {self.id[:8]} sop={self.sop_id[:8]} #{self.step_order} {self.name!r} phase={self.phase}>"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "sop_id": self.sop_id,
            "step_order": self.step_order,
            "name": self.name,
            "phase": self.phase,
            "trigger": self.trigger,
            "action": self.action,
            "action_params": self.action_params or {},
            "agent": self.agent,
            "model": self.model,
            "expected_result": self.expected_result,
            "success_criteria": self.success_criteria or [],
            "next_step_id": self.next_step_id,
            "fail_step_id": self.fail_step_id,
            "on_sub_sop_step_id": self.on_sub_sop_step_id,
            "delay_s": self.delay_s,
            "description": self.description,
            # CIO-Triage-Felder (User-Direktive 16.06.2026, Schritt 0)
            "task_types": self.task_types or [],
            "standards_refs": self.standards_refs or [],
            "change_requirements": self.change_requirements or [],
            "subagent_requirements": self.subagent_requirements or [],
            # User-Input-Tool (User-Direktive 17.06.2026)
            "input_tool_required": self.input_tool_required,
            "input_tool_type": self.input_tool_type,
            "input_tool_prompt": self.input_tool_prompt,
            "input_tool_description": self.input_tool_description,
            "input_tool_recommendation": self.input_tool_recommendation,
            "input_tool_options": self.input_tool_options,  # JSON-String
            "input_tool_options_config": self.input_tool_options_config,  # JSON-String
            "input_tool_context_key": self.input_tool_context_key,
            "rules": [r.to_dict() for r in (self.rules or [])],
        }


# === SOP-Step-Regel (Wenn-Dann) ===

class SOPStepRule(Base):
    """Eine Wenn-Dann-Regel fuer einen SOP-Step.

    Beispiel:
      Step: "CIO Triage Review"
      Rule 1: if cio_approved == true then move_status to "todo"
      Rule 2: if conflicts_found == true then move_status to "block" + question

    Logik:
      condition_field: "cio_approved" (Name des Felds im Step-Context)
      condition_operator: "eq" | "ne" | "gt" | "lt" | "in" | "contains" | "not_in"
      condition_value: True
      action_type: "move_status" | "create_subtask" | "spawn_sop" | "escalate" | "notify"
      action_target: "todo" | "block" | <sop_id>
      action_params: {}
    """
    __tablename__ = "sop_step_rules"

    # === Primary Key ===
    id: Mapped[str] = mapped_column(String(32), primary_key=True)

    # === Foreign Key ===
    step_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("sop_steps.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # === Regel-Definition ===
    rule_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)

    # === Condition (Wenn) ===
    condition_field: Mapped[str] = mapped_column(String(128), nullable=False)
    condition_operator: Mapped[str] = mapped_column(String(16), default="eq", nullable=False)
    condition_value: Mapped[Optional[dict]] = mapped_column(JSONType)

    # === Action (Dann) ===
    action_type: Mapped[str] = mapped_column(String(64), nullable=False)
    action_target: Mapped[Optional[str]] = mapped_column(String(255))
    action_params: Mapped[Optional[dict]] = mapped_column(JSONType, default=dict)

    # === Relations ===
    step: Mapped["SOPStep"] = relationship("SOPStep", back_populates="rules")

    def __repr__(self) -> str:
        return (
            f"<SOPStepRule {self.id[:8]} step={self.step_id[:8]} "
            f"if {self.condition_field} {self.condition_operator} {self.condition_value!r} "
            f"then {self.action_type}({self.action_target})>"
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "step_id": self.step_id,
            "rule_order": self.rule_order,
            "description": self.description,
            "condition_field": self.condition_field,
            "condition_operator": self.condition_operator,
            "condition_value": self.condition_value,
            "action_type": self.action_type,
            "action_target": self.action_target,
            "action_params": self.action_params or {},
        }


# === SOP-Instance (laufende Ausfuehrung) ===

class SOPInstance(Base):
    """Eine konkrete, laufende SOP-Instanz.

    Wird angelegt, wenn:
      - Ein Board/Projekt eine initiale SOP bekommt
      - Ein Step mit action_type="spawn_sop" eine Sub-SOP startet
      - Manuell vom User/CIO getriggert

    Verfolgt den aktuellen Step, Status, Context-Daten.
    """
    __tablename__ = "sop_instances"

    # === Primary Key ===
    id: Mapped[str] = mapped_column(String(32), primary_key=True)

    # === Foreign Keys ===
    sop_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("sops.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[Optional[str]] = mapped_column(
        String(32), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    task_id: Mapped[Optional[str]] = mapped_column(
        String(32), ForeignKey("tasks.id", ondelete="CASCADE"), index=True
    )

    # === Aktueller Zustand ===
    current_step_id: Mapped[Optional[str]] = mapped_column(
        String(32), ForeignKey("sop_steps.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(String(32), default="running", nullable=False, index=True)
    # Status-Werte: running, paused, waiting_sub_sop, completed, failed, blocked

    # === Hierarchie (Sub-SOPs) ===
    parent_instance_id: Mapped[Optional[str]] = mapped_column(
        String(32), ForeignKey("sop_instances.id", ondelete="SET NULL")
    )

    # === Laufzeit-Context (z.B. Step-Ergebnisse, Variablen) ===
    context: Mapped[Optional[dict]] = mapped_column(JSONType, default=dict)

    # === Timestamps ===
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # === Relations ===
    sop: Mapped["SOP"] = relationship("SOP", back_populates="instances")
    executions: Mapped[List["SOPExecution"]] = relationship(
        "SOPExecution", back_populates="instance", cascade="all, delete-orphan"
    )
    parent: Mapped[Optional["SOPInstance"]] = relationship(
        "SOPInstance", remote_side=[id], backref="children"
    )

    # === Indizes ===
    __table_args__ = (
        Index("idx_sop_inst_project", "project_id"),
        Index("idx_sop_inst_task", "task_id"),
        Index("idx_sop_inst_status", "status"),
        Index("idx_sop_inst_parent", "parent_instance_id"),
    )

    def __repr__(self) -> str:
        return f"<SOPInstance {self.id[:8]} sop={self.sop_id[:8]} project={self.project_id[:8] if self.project_id else '?'} status={self.status}>"

    def to_dict(self, include_executions: bool = False) -> dict:
        result = {
            "id": self.id,
            "sop_id": self.sop_id,
            "project_id": self.project_id,
            "task_id": self.task_id,
            "current_step_id": self.current_step_id,
            "status": self.status,
            "parent_instance_id": self.parent_instance_id,
            "context": self.context or {},
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }
        if include_executions:
            result["executions"] = [e.to_dict() for e in (self.executions or [])]
        return result


# === SOP-Execution (Audit-Log) ===

class SOPExecution(Base):
    """Eine Zeile im Audit-Log einer SOP-Instance.

    Wird angelegt fuer:
      - step_started
      - step_completed
      - rule_evaluated
      - sub_sop_spawned
      - sub_sop_completed
      - instance_completed / failed
    """
    __tablename__ = "sop_executions"

    # === Primary Key ===
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # === Foreign Keys ===
    instance_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("sop_instances.id", ondelete="CASCADE"), nullable=False, index=True
    )
    step_id: Mapped[Optional[str]] = mapped_column(
        String(32), ForeignKey("sop_steps.id", ondelete="SET NULL")
    )

    # === Event-Daten ===
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    event: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    agent: Mapped[Optional[str]] = mapped_column(String(64))

    # === Ergebnisse/Details ===
    details: Mapped[Optional[dict]] = mapped_column(JSONType, default=dict)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer)
    success: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # === Relations ===
    instance: Mapped["SOPInstance"] = relationship("SOPInstance", back_populates="executions")

    # === Indizes ===
    __table_args__ = (
        Index("idx_sop_exec_instance_ts", "instance_id", "ts"),
        Index("idx_sop_exec_event", "event"),
        Index("idx_sop_exec_step", "step_id"),
    )

    def __repr__(self) -> str:
        return f"<SOPExecution #{self.id} inst={self.instance_id[:8]} event={self.event} success={self.success}>"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "instance_id": self.instance_id,
            "step_id": self.step_id,
            "ts": self.ts.isoformat() if self.ts else None,
            "event": self.event,
            "agent": self.agent,
            "details": self.details or {},
            "duration_ms": self.duration_ms,
            "success": self.success,
        }
