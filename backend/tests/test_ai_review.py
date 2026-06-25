"""Tests fuer den AI-Review-Endpoint (User-Direktive 24.06.2026).

Prueft 3 Dimensionen: Redundanz, Widersprueche, OpenBrain-Compliance.
"""
from __future__ import annotations

import os

os.environ.setdefault("JWT_SECRET", "test-secret-for-unit-tests-32bytes")
os.environ.setdefault("AUTH_ENABLED", "false")

import pytest
import json
from unittest.mock import patch, AsyncMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.architecture_rule import ArchitectureRule
from app.models.sop import SOP, SOPStep


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = Session()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def openbrain_rules(db):
    """10 Default-OpenBrain-Vorgaben."""
    rules_data = [
        ("Service-Oriented Architecture (SOA)", "Lose gekoppelte Services.", "must", "openbrain-tag:SOA"),
        ("Microservices-Architektur", "Eigenstaendige Deployments.", "must", "openbrain-tag:Microservices"),
        ("Python 3.11+ / FastAPI als Backend-Standard", "Backend-Sprache/Framework.", "should", "openbrain-tag:ME4-Stack"),
        ("Kein Node.js im Backend", "Backend-Konsistenz.", "should", "openbrain-tag:Stack-Policy"),
        ("LLM: MiniMax M3 als PRIMARY", "Sub-Agents laufen mit minimax.", "should", "openbrain-tag:LLM-Standard"),
        ("Sub-Agent-Rollen-Set", "pi-coder, pi-tester, etc.", "must", "openbrain-tag:Sub-Agents"),
        ("Token-Budget + Cost-Limit pro Sub-Agent", "Cost-Tracking aktivieren.", "must", "openbrain-tag:Cost-Policy"),
        ("Git-Branch pro Task", "Hauptbranch bleibt unveraendert.", "must", "openbrain-tag:Git-Workflow"),
        ("Task-Locking mit TTL", "LOCKED_BY + TTL fuer parallele Worker.", "may", "openbrain-tag:Concurrency"),
        ("PR mit Post-Task Evaluation", "docs/evaluations/<task-id>.md", "should", "openbrain-tag:PostTaskEval"),
    ]
    for name, desc, sev, ref in rules_data:
        db.add(ArchitectureRule(
            id=f"rule-{ref.split(':')[-1]}",
            name=name,
            description=desc,
            source="openbrain",
            source_ref=ref,
            severity=sev,
            is_active=True,
        ))
    db.commit()
    return db


class TestAiReviewEndpoint:
    """Prueft die JSON-Struktur und Logik des ai-review Endpoints."""

    @pytest.mark.asyncio
    async def test_clean_text_returns_ok_true(self, openbrain_rules):
        """Ein sauberer Text ohne Issues gibt ok=true zurueck."""
        from app.routers.sops import ai_step_review, AiReviewBody
        clean_text = (
            "## Verantwortlich\n"
            "pi-coder fuehrt diesen Schritt aus.\n\n"
            "## Ziel\n"
            "Eine saubere Implementation erstellen.\n\n"
            "## Vorgehen\n"
            "1. Lese die Anforderungen.\n"
            "2. Implementiere mit Python 3.11+ / FastAPI.\n"
            "3. Schreibe Tests.\n\n"
            "## KPIs\n"
            "Test-Coverage > 80%, Token-Budget: 50k.\n"
        )
        mock_resp = {
            "content": json.dumps({
                "ok": True,
                "summary": "Keine Probleme gefunden.",
                "issues": [],
            }),
            "model": "minimax-m3",
            "provider": "minimax-direct",
            "usage": {"tokens_in": 100, "tokens_out": 50},
        }
        with patch(
            "app.services.llm_service.chat_completion",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ):
            body = AiReviewBody(text=clean_text)
            result = await ai_step_review(
                sop_id="dummy", step_id="dummy", body=body, db=openbrain_rules, _user="test"
            )
        assert result["ok"] is True
        assert result["issues"] == []
        assert "Keine Probleme" in result["summary"]

    @pytest.mark.asyncio
    async def test_contradiction_returns_ok_false(self, openbrain_rules):
        """Ein Widerspruch fuehrt zu ok=false."""
        from app.routers.sops import ai_step_review, AiReviewBody
        import json
        contradictory_text = (
            "Schreibe KEINEN Test, aber schreibe Tests."
        )
        mock_resp = {
            "content": json.dumps({
                "ok": False,
                "summary": "Widerspruch gefunden.",
                "issues": [{
                    "type": "contradiction",
                    "severity": "must",
                    "problem": "Schreibe keinen Test vs. schreibe Tests",
                    "location": "Vorgehen",
                    "suggestion": "Entscheidung treffen.",
                    "rule_ref": None,
                }],
            }),
            "model": "minimax-m3",
            "provider": "minimax-direct",
            "usage": {"tokens_in": 100, "tokens_out": 50},
        }
        with patch(
            "app.services.llm_service.chat_completion",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ):
            body = AiReviewBody(text=contradictory_text)
            result = await ai_step_review(
                sop_id="dummy", step_id="dummy", body=body, db=openbrain_rules, _user="test"
            )
        assert result["ok"] is False
        assert len(result["issues"]) == 1
        assert result["issues"][0]["type"] == "contradiction"
        assert result["issues"][0]["severity"] == "must"

    @pytest.mark.asyncio
    async def test_openbrain_violation_includes_rule_ref(self, openbrain_rules):
        """OpenBrain-Verstoesse haben rule_ref mit source_ref."""
        from app.routers.sops import ai_step_review, AiReviewBody
        import json
        text = "Verwende Node.js im Backend."
        mock_resp = {
            "content": json.dumps({
                "ok": False,
                "summary": "Stack-Policy verletzt.",
                "issues": [{
                    "type": "openbrain_compliance",
                    "severity": "should",
                    "problem": "Node.js im Backend verletzt Stack-Policy",
                    "location": "Vorgehen",
                    "suggestion": "Python 3.11+ / FastAPI verwenden.",
                    "rule_ref": "openbrain-tag:Stack-Policy",
                }],
            }),
            "model": "minimax-m3",
            "provider": "minimax-direct",
            "usage": {"tokens_in": 100, "tokens_out": 50},
        }
        with patch(
            "app.services.llm_service.chat_completion",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ):
            body = AiReviewBody(text=text)
            result = await ai_step_review(
                sop_id="dummy", step_id="dummy", body=body, db=openbrain_rules, _user="test"
            )
        assert result["ok"] is False
        assert result["issues"][0]["rule_ref"] == "openbrain-tag:Stack-Policy"

    @pytest.mark.asyncio
    async def test_may_severity_keeps_ok_true(self, openbrain_rules):
        """'may'-Issues blockieren nicht (ok bleibt true)."""
        from app.routers.sops import ai_step_review, AiReviewBody
        import json
        text = "Etwas redundanter Text."
        mock_resp = {
            "content": json.dumps({
                "ok": True,
                "summary": "Optionale Redundanz.",
                "issues": [{
                    "type": "redundancy",
                    "severity": "may",
                    "problem": "Leichte Redundanz.",
                    "location": "Ziel",
                    "suggestion": "Konsolidieren.",
                    "rule_ref": None,
                }],
            }),
            "model": "minimax-m3",
            "provider": "minimax-direct",
            "usage": {"tokens_in": 100, "tokens_out": 50},
        }
        with patch(
            "app.services.llm_service.chat_completion",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ):
            body = AiReviewBody(text=text)
            result = await ai_step_review(
                sop_id="dummy", step_id="dummy", body=body, db=openbrain_rules, _user="test"
            )
        # 'may' ist nicht blockierend
        assert result["ok"] is True
        assert len(result["issues"]) == 1

    @pytest.mark.asyncio
    async def test_response_includes_openbrain_rule_count(self, openbrain_rules):
        """Antwort enthaelt openbrain_rules_checked."""
        from app.routers.sops import ai_step_review, AiReviewBody
        import json
        text = "Test text with at least 20 chars."
        mock_resp = {
            "content": json.dumps({"ok": True, "summary": "OK", "issues": []}),
            "model": "minimax-m3",
            "provider": "minimax-direct",
            "usage": {"tokens_in": 10, "tokens_out": 5},
        }
        with patch(
            "app.services.llm_service.chat_completion",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ):
            body = AiReviewBody(text=text)
            result = await ai_step_review(
                sop_id="dummy", step_id="dummy", body=body, db=openbrain_rules, _user="test"
            )
        assert result["openbrain_rules_checked"] == 10
        assert "redundancy" in result["checked_dimensions"]
        assert "contradiction" in result["checked_dimensions"]
        assert "openbrain_compliance" in result["checked_dimensions"]
        assert "checked_at" in result

    @pytest.mark.asyncio
    async def test_selective_dimension_check(self, openbrain_rules):
        """check_dimensions erlaubt selektive Pruefung."""
        from app.routers.sops import ai_step_review, AiReviewBody
        import json
        text = "Test text with at least 20 chars."
        mock_resp = {
            "content": json.dumps({"ok": True, "summary": "OK", "issues": []}),
            "model": "minimax-m3",
            "provider": "minimax-direct",
            "usage": {"tokens_in": 10, "tokens_out": 5},
        }
        with patch(
            "app.services.llm_service.chat_completion",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ):
            body = AiReviewBody(text=text, check_dimensions=["redundancy"])
            result = await ai_step_review(
                sop_id="dummy", step_id="dummy", body=body, db=openbrain_rules, _user="test"
            )
        assert result["checked_dimensions"] == ["redundancy"]
