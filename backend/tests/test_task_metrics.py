"""Tests fuer task_metrics (Phase 5+7+8).

User-Direktive 22.06.2026: Auto-Fix-Loop, Metriken, Cost-Guard.
"""
from __future__ import annotations

import time

import pytest

from app.services.task_metrics import (
    TaskScore, should_auto_fix, get_next_iteration_action,
    CostGuard, STAGE_COST_LIMITS, MAX_AUTO_FIX_ITERATIONS,
)


class TestTaskScore:
    def test_final_score_is_weighted_average(self):
        score = TaskScore(
            task_id="t1",
            test_coverage=80.0,
            reviewer_score=85.0,
            code_quality=90.0,
            performance_score=70.0,
            doc_quality=75.0,
        )
        # Gewichte: 0.25+0.25+0.20+0.15+0.15 = 1.0
        expected = 80*0.25 + 85*0.25 + 90*0.20 + 70*0.15 + 75*0.15
        assert score.final_score == pytest.approx(expected, 0.1)

    def test_final_score_is_zero_when_empty(self):
        score = TaskScore(task_id="t1")
        assert score.final_score == 0.0

    def test_to_dict_includes_final_score(self):
        score = TaskScore(task_id="t1", reviewer_score=92.0)
        d = score.to_dict()
        assert "final_score" in d
        assert d["final_score"] == pytest.approx(92.0 * 0.25, 0.1)


class TestAutoFixLoop:
    def test_should_auto_fix_when_score_below_90(self):
        assert should_auto_fix(85.0, 0) is True
        assert should_auto_fix(89.9, 1) is True

    def test_should_not_auto_fix_when_score_90_or_above(self):
        assert should_auto_fix(90.0, 0) is False
        assert should_auto_fix(95.0, 1) is False

    def test_should_not_auto_fix_after_max_iterations(self):
        assert should_auto_fix(85.0, MAX_AUTO_FIX_ITERATIONS) is False
        assert should_auto_fix(80.0, MAX_AUTO_FIX_ITERATIONS + 1) is False

    def test_next_action_approve_when_score_high(self):
        action = get_next_iteration_action(95.0, 0)
        assert action["action"] == "approve"
        assert action["next_step"] == "stage6_final"

    def test_next_action_auto_fix_when_score_low_and_iterations_available(self):
        action = get_next_iteration_action(80.0, 1)
        assert action["action"] == "auto_fix"
        assert action["next_step"] == "stage5_auto_fix"

    def test_next_action_escalate_when_max_iterations_reached(self):
        action = get_next_iteration_action(80.0, MAX_AUTO_FIX_ITERATIONS)
        assert action["action"] == "escalate"
        assert action["next_step"] == "human_review"


class TestCostGuard:
    def test_can_spend_within_limit(self):
        guard = CostGuard(hourly_limit_usd=1.0)
        # Initial: nichts ausgegeben
        assert guard.can_spend(0.5) is True
        assert guard.can_spend(1.0) is True
        assert guard.can_spend(1.5) is False
        # Nach Aufzeichnung: kumulativ pruefen
        guard.record_spend(0.5)
        assert guard.can_spend(0.4) is True   # 0.5+0.4=0.9 <= 1.0
        assert guard.can_spend(0.6) is False  # 0.5+0.6=1.1 > 1.0

    def test_record_spend_tracks_total(self):
        guard = CostGuard(hourly_limit_usd=1.0)
        guard.record_spend(0.3)
        guard.record_spend(0.2)
        assert guard.get_status()["current_spend_usd"] == pytest.approx(0.5)

    def test_warning_at_80_percent(self):
        guard = CostGuard(hourly_limit_usd=1.0)
        guard.record_spend(0.85)
        assert guard.get_status()["limit_warning_at_80pct"] is True

    def test_hour_rollover_resets_counter(self):
        guard = CostGuard(hourly_limit_usd=1.0)
        guard.record_spend(0.9)
        # Manuelle Simulation: Stunde zurueckdrehen
        guard._hour_start_ts -= 3600
        guard._maybe_rollover_hour()
        assert guard._current_hour_spend == 0.0

    def test_get_status_structure(self):
        guard = CostGuard(hourly_limit_usd=5.0)
        status = guard.get_status()
        assert "hourly_limit_usd" in status
        assert "current_spend_usd" in status
        assert "remaining_usd" in status
        assert status["remaining_usd"] == 5.0


class TestStageCostLimits:
    def test_all_stages_have_limits(self):
        assert len(STAGE_COST_LIMITS) >= 7
        # Wichtige Stages muessen Limits haben
        assert "stage2_implementation" in STAGE_COST_LIMITS
        assert "stage3_multi_test" in STAGE_COST_LIMITS
        assert "stage4_competitive_review" in STAGE_COST_LIMITS

    def test_stage_limits_sum_to_total(self):
        total = sum(STAGE_COST_LIMITS.values())
        # Spec sagt: Total $1.55 pro Task
        assert 1.0 <= total <= 2.0, f"Stage-Limits-Summe {total} ausserhalb des erwarteten Bereichs"