"""Process-Template Model — BPMN Process Designer Vorlagen.

User-Direktive 15.06.2026: User designt Prozesse im BPMN-Designer
(Palette links, Canvas mittig, Properties rechts) und wendet sie
als Sub-Tasks auf einen Board-Task an.

Ein Process-Template enthaelt:
- nodes: Liste von Schritten (id, type, label, x, y, properties)
- edges: Liste von Verbindungen (from, to, label, condition)

Types: start, end, task, decision, parallel, merge
"""
from __future__ import annotations

from typing import Optional, List, Any, Dict
from datetime import datetime
from sqlalchemy import String, Text, ForeignKey, Index, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .task import JSONType
from .project import Project
from ..db.base import Base
from ..services.task_service import _gen_id


class ProcessTemplate(Base):
    __tablename__ = "process_templates"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_gen_id)
    project_id: Mapped[Optional[str]] = mapped_column(
        String(32), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(64), default="workflow", nullable=False)

    # === BPMN Graph (JSON) ===
    # nodes: [{id, type, label, x, y, properties: {assigned_role, priority, success_criteria, on_complete: "submit_review" | "..."}}]
    # edges: [{id, from, to, label, condition, target_status: "triage" | "todo" | "in_progress" | "review" | "block" | "done"}]
    nodes: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(JSONType, default=list)
    edges: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(JSONType, default=list)

    # === Stats ===
    node_count: Mapped[int] = mapped_column(default=0, nullable=False)
    edge_count: Mapped[int] = mapped_column(default=0, nullable=False)

    # === Activation (Workflow-Steuerung) ===
    # Ein Template wird "freigeschaltet" (is_active=True) fuer ein Projekt
    # Der Operator folgt dann den Edges als Transition-Map
    is_active: Mapped[bool] = mapped_column(default=False, nullable=False, index=True)
    activated_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    activated_by: Mapped[Optional[str]] = mapped_column(String(64))
    activated_for_project_id: Mapped[Optional[str]] = mapped_column(
        String(32), ForeignKey("projects.id", ondelete="SET NULL"), index=True
    )
    activation_note: Mapped[Optional[str]] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
    created_by: Mapped[Optional[str]] = mapped_column(String(64))

    project: Mapped[Optional["Project"]] = relationship(foreign_keys=[project_id])
    activated_project: Mapped[Optional["Project"]] = relationship(foreign_keys=[activated_for_project_id])

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "nodes": self.nodes or [],
            "edges": self.edges or [],
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "is_active": self.is_active,
            "activated_at": self.activated_at.isoformat() if self.activated_at else None,
            "activated_by": self.activated_by,
            "activated_for_project_id": self.activated_for_project_id,
            "activation_note": self.activation_note,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "created_by": self.created_by,
        }

    def get_start_edge(self) -> Optional[Dict[str, Any]]:
        """Gibt die Edge zurueck, die am 'Start'-Knoten beginnt.
        Definiert den ersten Status-Transition.
        """
        if not self.nodes or not self.edges:
            return None
        start_node = next((n for n in self.nodes if n.get("type") == "start"), None)
        if not start_node:
            return None
        return next((e for e in self.edges if e.get("from") == start_node.get("id")), None)

    def get_transition(self, from_node_id: str) -> Optional[Dict[str, Any]]:
        """Gibt die naechste Edge ab einem bestimmten Knoten zurueck (single-Transitions).
        """
        if not self.edges:
            return None
        candidates = [e for e in self.edges if e.get("from") == from_node_id]
        if len(candidates) == 0:
            return None
        # Bevorzuge Edge ohne condition (default-Pfad)
        default_edges = [e for e in candidates if not e.get("condition")]
        return default_edges[0] if default_edges else candidates[0]
