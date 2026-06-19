"""Pydantic v2 Schemas fuer AgentQuestion-API."""
from __future__ import annotations

from datetime import datetime
from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field, ConfigDict


# === Request Schemas ===

class AgentQuestionCreate(BaseModel):
    """Vom Agent: erstellt eine neue Frage an den User."""
    agent_id: str = Field(..., min_length=1, max_length=64,
                          description="Technische Agent-ID, z.B. 'pi-coder-001' oder 'cio'")
    agent_level: Literal["C-Level", "Worker", "Subagent"] = "Worker"
    agent_label: Optional[str] = Field(None, max_length=128,
                                       description="Anzeige-Name, z.B. 'CIO' oder 'pi-coder (task 12345)'")

    question_type: Literal["text", "confirmation", "choice", "attachment", "image", "any"] = "text"
    title: str = Field(..., min_length=1, max_length=200)
    question: str = Field(..., min_length=1)
    description: Optional[str] = Field(None, description="Mehr Kontext zur Frage (im Dialog angezeigt)")
    recommendation: Optional[str] = Field(None, description="Vom Agent vorgeschlagene Antwort — User kann sie uebernehmen")
    options: List[str] = Field(default_factory=list,
                               description="Bei question_type=choice: Liste der Optionen")
    options_config: Optional[Dict[str, Any]] = Field(
        default=None,
        description=("Konfiguration der sichtbaren Optionen. Beispiel: "
                     "{'show_description': true, 'show_recommendation': true, 'show_tts': true, "
                     "'allow_edit_recommendation': true, 'answer_required': true, 'recommendation_as_default': true}")
    )

    context: Dict[str, Any] = Field(default_factory=dict,
                                    description="Kontext: task_id, project_id, step, etc.")

    priority: Literal["low", "medium", "high", "urgent"] = "medium"
    expires_at: Optional[datetime] = Field(None, description="Timeout; nach Ablauf -> status=expired")


class AgentQuestionAnswer(BaseModel):
    """Vom User: beantwortet eine offene Frage."""
    answer_text: Optional[str] = Field(None, description="Freitext-Antwort")
    answer_choice: Optional[str] = Field(None, max_length=500,
                                         description="Bei choice-Fragen: gewaehlte Option")
    answer_attachments: Optional[list] = Field(default=None, description="Liste der Attachment-IDs, die der User beigefuegt hat")
    answered_by: str = Field(default="user", min_length=1, max_length=64)


# === Response Schemas ===

class AgentQuestionAttachmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    question_id: str
    kind: str
    file_name: str
    mime_type: Optional[str]
    size_bytes: int
    source: str
    uploaded_at: datetime


class AgentQuestionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    agent_id: str
    agent_level: str
    agent_label: Optional[str]
    question_type: str
    title: str
    question: str
    description: Optional[str] = None
    recommendation: Optional[str] = None
    options: List[str] = Field(default_factory=list)
    options_config: Dict[str, Any] = Field(default_factory=dict)
    context: Dict[str, Any] = Field(default_factory=dict)
    status: str
    priority: str
    answer_text: Optional[str]
    answer_choice: Optional[str]
    answer_attachments: List[str] = Field(default_factory=list)
    answered_at: Optional[datetime]
    answered_by: Optional[str]
    created_at: datetime
    updated_at: datetime
    expires_at: Optional[datetime]
    seen_at: Optional[datetime]
    attachment_count: int = 0


class AgentQuestionDetail(AgentQuestionRead):
    """Detail-View inkl. Attachments."""
    attachments: List[AgentQuestionAttachmentRead] = Field(default_factory=list)


class AgentQuestionList(BaseModel):
    items: List[AgentQuestionRead]
    total: int
    pending_count: int
    unseen_count: int
