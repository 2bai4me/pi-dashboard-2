"""Tests fuer ImplementationPlan-Schema (FIX 23.06.2026, Task 9f2f473bf1cc)."""
import pytest
from pydantic import ValidationError

from app.schemas.task import (
    ImplementationPlan,
    AffectedFile,
    FileChangeType,
    ApiChange,
    SubTask,
    AcceptanceCriterion,
    Risk,
    Dependency,
)


class TestImplementationPlanSchema:
    def test_minimal_valid(self):
        """Mindestfuellung: nur summary ist pflicht."""
        plan = ImplementationPlan(summary="Login mit OAuth2 einbauen")
        assert plan.summary == "Login mit OAuth2 einbauen"
        assert plan.affected_files == []
        assert plan.sub_tasks == []
        assert plan.version == 1

    def test_full_valid(self):
        """Vollstaendige Ausfuellung."""
        plan = ImplementationPlan(
            summary="Login mit OAuth2",
            context="User-Direktive",
            affected_files=[
                AffectedFile(path="src/api/auth.py", change_type=FileChangeType.MODIFY, description="Auth-Provider"),
            ],
            api_changes=[
                ApiChange(method="POST", path="/api/auth/login", request_schema="OAuth2Request", response_schema="TokenResponse", breaking=False),
            ],
            sub_tasks=[
                SubTask(id="st1", title="Auth-Provider-Setup", assigned_role="pi-coder", depends_on=[], estimate_min=60),
                SubTask(id="st2", title="Login-Endpoint", assigned_role="pi-coder", depends_on=["st1"], estimate_min=90),
            ],
            acceptance_criteria=[
                AcceptanceCriterion(id="ac1", description="POST /api/auth/login liefert 200 + Token", test_method="integration", expected="HTTP 200 mit JWT"),
            ],
            risks=[
                Risk(id="r1", description="Google OAuth kann ausfallen", likelihood=2, impact=4, mitigation="Fallback auf Email-Login"),
            ],
            dependencies=[
                Dependency(type="service", ref="service:oauth-provider", status="ready"),
            ],
            test_strategy="Unit-Tests fuer Auth-Mock + Integration-Tests fuer /api/auth/login",
            rollout_plan="Feature-Flag 'auth_oauth' auf 10% User ausrollen, dann 100%",
            notes="Mit Security-Team absprechen",
            created_by="pi-architect",
            version=1,
        )
        assert len(plan.sub_tasks) == 2
        assert plan.sub_tasks[1].depends_on == ["st1"]
        assert plan.risks[0].likelihood == 2
        assert plan.version == 1

    def test_summary_required(self):
        """summary ist Pflicht, leerer String nicht erlaubt."""
        with pytest.raises(ValidationError) as exc:
            ImplementationPlan(summary="")
        assert "summary" in str(exc.value)

    def test_summary_too_long(self):
        """summary darf max 500 Zeichen sein."""
        with pytest.raises(ValidationError) as exc:
            ImplementationPlan(summary="x" * 501)
        assert "500" in str(exc.value) or "at most" in str(exc.value).lower()

    def test_subtask_id_pattern(self):
        """Sub-Task-IDs muessen dem Format st1, st2, ... entsprechen."""
        with pytest.raises(ValidationError) as exc:
            ImplementationPlan(
                summary="Test",
                sub_tasks=[SubTask(id="task-1", title="x", assigned_role="pi-coder", estimate_min=30)],
            )
        assert "sub_tasks" in str(exc.value) or "id" in str(exc.value)

    def test_subtask_unique_ids(self):
        """Sub-Task-IDs muessen eindeutig sein."""
        with pytest.raises(ValidationError) as exc:
            ImplementationPlan(
                summary="Test",
                sub_tasks=[
                    SubTask(id="st1", title="A", assigned_role="pi-coder", estimate_min=30),
                    SubTask(id="st1", title="B", assigned_role="pi-coder", estimate_min=30),
                ],
            )
        assert "eindeutig" in str(exc.value).lower() or "unique" in str(exc.value).lower()

    def test_subtask_estimate_min_max(self):
        """estimate_min muss zwischen 1 und 480 sein."""
        with pytest.raises(ValidationError):
            ImplementationPlan(
                summary="Test",
                sub_tasks=[SubTask(id="st1", title="x", assigned_role="pi-coder", estimate_min=0)],
            )
        with pytest.raises(ValidationError):
            ImplementationPlan(
                summary="Test",
                sub_tasks=[SubTask(id="st1", title="x", assigned_role="pi-coder", estimate_min=600)],
            )

    def test_risk_likelihood_impact_range(self):
        """Risk likelihood/impact muessen zwischen 1 und 5 sein."""
        with pytest.raises(ValidationError):
            ImplementationPlan(
                summary="Test",
                risks=[Risk(id="r1", description="x", likelihood=0, impact=3, mitigation="y")],
            )
        with pytest.raises(ValidationError):
            ImplementationPlan(
                summary="Test",
                risks=[Risk(id="r1", description="x", likelihood=3, impact=6, mitigation="y")],
            )

    def test_api_change_method_pattern(self):
        """HTTP-Methode muss GET/POST/PUT/PATCH/DELETE sein."""
        with pytest.raises(ValidationError):
            ImplementationPlan(
                summary="Test",
                api_changes=[ApiChange(method="FOOBAR", path="/api/x")],
            )

    def test_dependency_type(self):
        """Dependency-Typ muss internal/external/service sein."""
        with pytest.raises(ValidationError):
            ImplementationPlan(
                summary="Test",
                dependencies=[Dependency(type="unknown", ref="x", status="ready")],
            )

    def test_optional_fields_default(self):
        """Optionale Felder haben sinnvolle Defaults."""
        plan = ImplementationPlan(summary="x")
        assert plan.context is None
        assert plan.affected_files == []
        assert plan.api_changes == []
        assert plan.db_changes == []
        assert plan.sub_tasks == []
        assert plan.acceptance_criteria == []
        assert plan.risks == []
        assert plan.dependencies == []
        assert plan.test_strategy is None
        assert plan.rollout_plan is None
        assert plan.notes is None
        assert plan.created_by is None
        assert plan.created_at is None
        assert plan.version == 1
