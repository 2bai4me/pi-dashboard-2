"""Tests fuer SOP-getriebene LLM-Call-Architektur (User-Direktive 23.06.2026).

Konzept:
  - SOP-Step = aufgabenspezifische Anweisung (user_prompt, ai_instructions_md)
  - Rolle   = aufgabenunabhaengige Persona (system_prompt, provider, model, api_key)
  - System-Prompt = role.system_prompt + step.ai_instructions_md
  - Model/Provider aus Role, nicht aus action_params
  - Jeder LLM-Call wird in task_history dokumentiert
"""
from __future__ import annotations

import os

# Env-Defaults MUSSEN vor dem Import von app-Modulen gesetzt sein
os.environ.setdefault("JWT_SECRET", "test-secret-for-unit-tests-32bytes")
os.environ.setdefault("AUTH_ENABLED", "false")

import json
from decimal import Decimal
from unittest.mock import patch, MagicMock, AsyncMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.role import Role
from app.models.sop import SOPStep, SOP, SOPInstance
from app.models.task import Task
from app.models.history import TaskHistory
from app.services.sop_engine import (
    _load_role_for_step,
    _build_system_prompt,
    _resolve_model_from_role,
    _try_parse_json,
    _extract_step_approved_from_response,
    _extract_issues_from_response,
    _extract_questions_from_response,
)


# === Fixtures ===

@pytest.fixture
def db():
    """Frische In-Memory-SQLite-Session pro Test."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = Session()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def cio_role(db):
    """CIO-Rolle mit Persona + Model."""
    return Role(
        id="role-cio",
        name="CIO",
        display_name="Chief Information Officer",
        role_type="org",
        provider="ollama",
        model="gemma4:12b",
        description="CIO-Test-Rolle",
        system_prompt=(
            "## Aufgabe\n"
            "Du bist CIO. Pruefe Tasks auf Vollstaendigkeit, Klarheit, Konflikte.\n"
            "Liefere JSON: {ok, issues, questions}."
        ),
        timeout_sec=300,
    )


@pytest.fixture
def pi_architect_role(db):
    """pi-architect-Rolle mit anderem Model."""
    return Role(
        id="role-pi-architect",
        name="pi-architect",
        role_type="org",
        provider="minimax-direct",
        model="minimax-m3",
        system_prompt=(
            "## Rolle\n"
            "Du bist pi-architect. Erstelle Implementierungsplaene als JSON."
        ),
        timeout_sec=300,
    )


@pytest.fixture
def llm_step(db):
    """Ein SOP-Step mit llm_call Action und Prompt + Workflow."""
    sop = SOP(
        id="sop-test",
        name="Test-SOP",
        description="Test",
        category="task",
    )
    db.add(sop)
    db.flush()
    return SOPStep(
        id="step-test-1",
        sop_id="sop-test",
        step_order=0,
        name="Test-Step",
        phase="triage",
        trigger="step_completed",
        action="llm_call",
        agent="CIO",
        action_params={
            "user_prompt": "Analysiere Task: {task_title}",
            "ai_instructions_md": (
                "## Vorgehen\n"
                "1. Lese task.title + description\n"
                "2. Pruefe Vollstaendigkeit\n"
                "3. Liefere JSON {ok, issues, questions}"
            ),
        },
        delay_s=0.0,
    )


# === Test: _load_role_for_step ===

class TestLoadRoleForStep:
    def test_loads_existing_role(self, db, cio_role, llm_step):
        db.add(cio_role)
        db.add(llm_step)
        db.commit()
        role = _load_role_for_step(db, llm_step)
        assert role is not None
        assert role.name == "CIO"
        assert role.model == "gemma4:12b"

    def test_returns_none_for_missing_role(self, db, llm_step):
        db.add(llm_step)
        db.commit()
        role = _load_role_for_step(db, llm_step)
        assert role is None

    def test_returns_none_for_empty_agent(self, db):
        step = SOPStep(
            id="step-no-agent",
            sop_id="sop-test",
            step_order=0,
            name="No-Agent",
            phase="triage",
            trigger="step_completed",
            action="noop",
            agent="",
        )
        role = _load_role_for_step(db, step)
        assert role is None


# === Test: _build_system_prompt ===

class TestBuildSystemPrompt:
    def test_combines_role_prompt_and_workflow(self, cio_role, llm_step):
        prompt = _build_system_prompt(cio_role, llm_step.action_params)
        assert "Du bist CIO" in prompt
        assert "WORKFLOW-ANWEISUNGEN" in prompt
        assert "Vorgehen" in prompt
        assert "---" in prompt  # Separator

    def test_falls_back_to_params_system_prompt(self, db):
        role = None
        params = {"system_prompt": "Fallback-Prompt"}
        prompt = _build_system_prompt(role, params)
        assert prompt == "Fallback-Prompt"

    def test_falls_back_to_default_when_empty(self, db):
        prompt = _build_system_prompt(None, {})
        assert "hilfreicher Assistent" in prompt

    def test_workflow_optional(self, cio_role):
        params = {"ai_instructions_md": ""}  # leer
        prompt = _build_system_prompt(cio_role, params)
        assert "Du bist CIO" in prompt
        assert "WORKFLOW-ANWEISUNGEN" not in prompt


# === Test: _resolve_model_from_role ===

class TestResolveModelFromRole:
    def test_uses_role_model(self, cio_role):
        params = {"model": "should-be-ignored"}
        model = _resolve_model_from_role(cio_role, params)
        assert model == "gemma4:12b"  # Aus Rolle, nicht aus params

    def test_falls_back_to_params_model(self):
        role = None
        params = {"model": "custom-model"}
        model = _resolve_model_from_role(role, params)
        assert model == "custom-model"

    def test_falls_back_to_default(self):
        role = None
        model = _resolve_model_from_role(role, {})
        assert model == "minimax-m3"


# === Test: _try_parse_json ===

class TestTryParseJson:
    def test_parses_pure_json(self):
        text = '{"ok": true, "issues": []}'
        data = _try_parse_json(text)
        assert data == {"ok": True, "issues": []}

    def test_parses_json_in_code_fence(self):
        text = 'Hier meine Antwort:\n```json\n{"ok": false}\n```\nGruss'
        data = _try_parse_json(text)
        assert data == {"ok": False}

    def test_parses_json_with_surrounding_text(self):
        text = 'Meine Analyse: {"ok": true, "x": 1} Ende.'
        data = _try_parse_json(text)
        assert data == {"ok": True, "x": 1}

    def test_returns_none_for_empty(self):
        assert _try_parse_json("") is None
        assert _try_parse_json(None) is None

    def test_returns_none_for_invalid_json(self):
        assert _try_parse_json("kein json hier") is None
        assert _try_parse_json("{broken") is None


# === Test: _extract_step_approved_from_response ===

class TestExtractStepApproved:
    def test_extracts_ok_true(self):
        assert _extract_step_approved_from_response('{"ok": true}') is True

    def test_extracts_ok_false(self):
        assert _extract_step_approved_from_response('{"ok": false}') is False

    def test_extracts_step_approved_field(self):
        assert _extract_step_approved_from_response('{"step_approved": false}') is False

    def test_falls_back_to_true_for_ambiguous_text(self):
        # Konservativ: wenn nichts Negatives erkannt -> True
        assert _extract_step_approved_from_response("Sieht gut aus.") is True

    def test_falls_back_to_false_for_negative_keywords(self):
        assert _extract_step_approved_from_response("Es gibt Issues gefunden") is False
        assert _extract_step_approved_from_response('"ok": false, "issues": []') is False


# === Test: _extract_issues_from_response ===

class TestExtractIssues:
    def test_extracts_issues_list(self):
        text = '{"ok": false, "issues": [{"title": "Bug", "severity": "high"}]}'
        issues = _extract_issues_from_response(text)
        assert len(issues) == 1
        assert issues[0]["title"] == "Bug"

    def test_returns_empty_for_missing_field(self):
        assert _extract_issues_from_response('{"ok": true}') == []

    def test_returns_empty_for_invalid_json(self):
        assert _extract_issues_from_response("kein json") == []


# === Test: _extract_questions_from_response ===

class TestExtractQuestions:
    def test_extracts_questions_list(self):
        text = '{"ok": false, "questions": [{"question": "Was?"}]}'
        questions = _extract_questions_from_response(text)
        assert len(questions) == 1

    def test_returns_empty_for_missing(self):
        assert _extract_questions_from_response('{"ok": true}') == []


# === Test: SOPEngine._llm_call_async (mit gemocktem LLM) ===

class TestSOPEngineLLMCallAsync:
    """Test der vollstaendigen _llm_call_async-Methode mit gemocktem chat_completion."""

    @pytest.fixture
    def setup_env(self, db, cio_role, llm_step):
        """Setup: Rolle + Step + Task in DB."""
        task = Task(
            id="task-test-1",
            title="Test-Task",
            description="Test-Beschreibung",
            status="triage",
        )
        from app.models.task import JSONType
        # Task braucht project_id, also Project anlegen
        from app.models.project import Project
        proj = Project(
            id="proj-test",
            name="Test-Project",
            description="",
            status="active",
            mode="preparation",
        )
        db.add(proj)
        db.flush()
        task.project_id = proj.id
        db.add(task)
        db.add(cio_role)
        db.add(llm_step)
        db.commit()
        # Instance anlegen
        from app.models.sop import SOPInstance
        inst = SOPInstance(
            id="inst-test",
            sop_id="sop-test",
            task_id=task.id,
            current_step_id=llm_step.id,
            status="running",
        )
        db.add(inst)
        db.commit()
        return db, task, llm_step, inst

    @pytest.mark.asyncio
    async def test_llm_call_uses_role_model_and_writes_history(self, setup_env):
        """Test: Model kommt aus Rolle, History-Eintrag wird geschrieben."""
        from app.services.sop_engine import SOPEngine
        db, task, step, instance = setup_env
        engine = SOPEngine(db)

        mock_response = {
            "content": '{"ok": true, "issues": []}',
            "model": "gemma4:12b",
            "provider": "ollama",
            "usage": {"tokens_in": 100, "tokens_out": 50},
        }
        with patch(
            "app.services.sop_engine.chat_completion",
            new_callable=AsyncMock,
            return_value=mock_response,
        ) as mock_chat:
            result = await engine._llm_call_async(
                instance, step, task, step.action_params
            )

        # 1. Model wurde aus der Rolle aufgeloest
        assert result["ok"] is True
        assert result["model"] == "gemma4:12b"  # Aus CIO-Rolle
        assert result["provider"] == "ollama"
        assert result["agent"] == "CIO"
        # chat_completion wurde mit role="CIO" aufgerufen
        mock_chat.assert_called_once()
        call_kwargs = mock_chat.call_args.kwargs
        assert call_kwargs["model"] == "gemma4:12b"
        assert call_kwargs["role"] == "CIO"

        # 2. History-Eintrag wurde geschrieben
        history_entries = db.query(TaskHistory).filter_by(task_id=task.id).all()
        llm_entries = [h for h in history_entries if h.event == "llm_call"]
        assert len(llm_entries) == 1
        h = llm_entries[0]
        assert h.agent == "CIO"
        assert h.model == "gemma4:12b"
        assert h.tokens_in == 100
        assert h.tokens_out == 50
        assert h.details["provider"] == "ollama"
        assert h.details["role_id"] == "role-cio"
        assert h.details["system_prompt_chars"] > 0
        assert h.details["user_prompt_chars"] == len(step.action_params["user_prompt"])
        assert h.details["ok"] is True

    @pytest.mark.asyncio
    async def test_llm_call_writes_history_even_on_error(self, setup_env):
        """Test: History-Eintrag wird auch bei LLM-Fehler geschrieben (Audit-Trail)."""
        from app.services.sop_engine import SOPEngine
        db, task, step, instance = setup_env
        engine = SOPEngine(db)

        with patch(
            "app.services.sop_engine.chat_completion",
            new_callable=AsyncMock,
            side_effect=RuntimeError("Ollama down"),
        ):
            result = await engine._llm_call_async(
                instance, step, task, step.action_params
            )

        assert result["ok"] is False
        # History trotzdem geschrieben
        llm_entries = db.query(TaskHistory).filter_by(
            task_id=task.id, event="llm_call"
        ).all()
        assert len(llm_entries) == 1
        assert llm_entries[0].details["ok"] is False
        assert "Ollama down" in llm_entries[0].details["error"]

    @pytest.mark.asyncio
    async def test_llm_call_fails_without_user_prompt(self, setup_env):
        """Test: Ohne user_prompt wird der Call abgelehnt."""
        from app.services.sop_engine import SOPEngine
        db, task, step, instance = setup_env
        engine = SOPEngine(db)

        result = await engine._llm_call_async(
            instance, step, task, {}  # Leerer params
        )
        assert result["ok"] is False
        assert "user_prompt" in result["error"]

    @pytest.mark.asyncio
    async def test_llm_call_uses_different_role_model(self, db, pi_architect_role):
        """Test: Andere Rolle -> anderes Model (aus der Rolle)."""
        from app.services.sop_engine import SOPEngine
        from app.models.task import Task
        from app.models.project import Project
        from app.models.sop import SOPInstance

        # Setup mit pi-architect
        proj = Project(
            id="proj-2", name="P2", description="", status="active", mode="preparation"
        )
        db.add(proj)
        db.flush()
        task = Task(
            id="task-2", title="T2", description="", status="triage", project_id="proj-2"
        )
        step = SOPStep(
            id="step-2",
            sop_id="sop-test",
            step_order=1,
            name="Arch",
            phase="go",
            trigger="step_completed",
            action="llm_call",
            agent="pi-architect",
            action_params={"user_prompt": "Erstelle Plan"},
            delay_s=0.0,
        )
        db.add_all([task, pi_architect_role, step])
        db.commit()
        inst = SOPInstance(
            id="inst-2", sop_id="sop-test", task_id=task.id,
            current_step_id=step.id, status="running"
        )
        db.add(inst)
        db.commit()

        engine = SOPEngine(db)
        mock_resp = {
            "content": "{}", "model": "minimax-m3", "provider": "minimax-direct",
            "usage": {"tokens_in": 10, "tokens_out": 20},
        }
        with patch(
            "app.services.sop_engine.chat_completion",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ) as mock_chat:
            result = await engine._llm_call_async(
                inst, step, task, step.action_params
            )

        # Model kommt aus pi-architect-Rolle, NICHT aus CIO
        assert result["model"] == "minimax-m3"
        assert result["provider"] == "minimax-direct"
        assert result["agent"] == "pi-architect"
        mock_chat.assert_called_once()
        assert mock_chat.call_args.kwargs["model"] == "minimax-m3"
