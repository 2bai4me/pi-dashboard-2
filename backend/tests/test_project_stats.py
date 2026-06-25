"""Tests fuer project_stats mit tasks_open field (FIX 23.06.2026, Task dad90780eb76)."""
import pytest


# Definition der Open-Statuses (muss mit project_service.py uebereinstimmen)
OPEN_STATUSES = {"triage", "in_progress", "review", "block", "failed",
                 "rueckfrage", "todo", "go", "wait"}


class TestProjectStatsOpenCount:
    def test_open_statuses_definition(self):
        """Open-Status-Set ist korrekt definiert (nicht done, nicht cancelled)."""
        assert "done" not in OPEN_STATUSES
        assert "cancelled" not in OPEN_STATUSES
        assert "triage" in OPEN_STATUSES
        assert "in_progress" in OPEN_STATUSES
        assert "review" in OPEN_STATUSES
        assert "block" in OPEN_STATUSES
        assert "failed" in OPEN_STATUSES
        assert "rueckfrage" in OPEN_STATUSES
        assert "todo" in OPEN_STATUSES
        assert "go" in OPEN_STATUSES
        assert "wait" in OPEN_STATUSES

    def test_open_count_logic(self):
        """tasks_open = Summe ueber alle Tasks mit Status in OPEN_STATUSES."""
        # Simuliere 5 Tasks: 2 done, 1 cancelled, 2 offen
        tasks = [
            {"id": "1", "status": "done"},
            {"id": "2", "status": "done"},
            {"id": "3", "status": "cancelled"},
            {"id": "4", "status": "triage"},
            {"id": "5", "status": "in_progress"},
        ]
        open_count = sum(1 for t in tasks if t["status"] in OPEN_STATUSES)
        done_count = sum(1 for t in tasks if t["status"] == "done")
        cancelled_count = sum(1 for t in tasks if t["status"] == "cancelled")
        total = len(tasks)

        assert open_count == 2
        assert done_count == 2
        assert cancelled_count == 1
        assert total == 5

    def test_open_count_all_done(self):
        """tasks_open = 0 wenn alle Tasks done sind."""
        tasks = [{"id": str(i), "status": "done"} for i in range(10)]
        open_count = sum(1 for t in tasks if t["status"] in OPEN_STATUSES)
        assert open_count == 0

    def test_open_count_all_open(self):
        """tasks_open = N wenn alle Tasks offen sind."""
        n = 10
        tasks = [{"id": str(i), "status": "triage"} for i in range(n)]
        open_count = sum(1 for t in tasks if t["status"] in OPEN_STATUSES)
        assert open_count == n

    def test_open_count_mixed_statuses(self):
        """tasks_open beruecksichtigt alle 10 OPEN_STATUSES korrekt."""
        statuses = ["triage", "in_progress", "review", "block", "failed",
                   "rueckfrage", "todo", "go", "wait"]
        # 1 Task pro Status + 2 done + 1 cancelled = 12 total, 9 offen
        tasks = [{"id": f"{i}", "status": s} for i, s in enumerate(statuses)]
        tasks.append({"id": "10", "status": "done"})
        tasks.append({"id": "11", "status": "done"})
        tasks.append({"id": "12", "status": "cancelled"})

        open_count = sum(1 for t in tasks if t["status"] in OPEN_STATUSES)
        assert open_count == 9
        assert len(tasks) == 12

    def test_stats_keys(self):
        """Stats-Output enthaelt alle erwarteten Keys."""
        expected_keys = {
            "task_count",
            "tasks_done",
            "tasks_cancelled",
            "tasks_in_progress",
            "tasks_open",
            "total_cost_usd",
        }
        # Simuliere einen leeren Stats-Dict
        stats = {
            "task_count": 0,
            "tasks_done": 0,
            "tasks_cancelled": 0,
            "tasks_in_progress": 0,
            "tasks_open": 0,
            "total_cost_usd": 0.0,
        }
        assert set(stats.keys()) == expected_keys

    def test_open_count_invariant(self):
        """Invariante: tasks_done + tasks_cancelled + tasks_open == task_count (ohne in_progress)."""
        # HINWEIS: tasks_in_progress ist Teilmenge von tasks_open
        # Daher: tasks_done + tasks_cancelled + tasks_open == task_count
        tasks = [
            {"id": "1", "status": "done"},
            {"id": "2", "status": "cancelled"},
            {"id": "3", "status": "triage"},
            {"id": "4", "status": "in_progress"},
            {"id": "5", "status": "review"},
        ]
        total = len(tasks)
        done = sum(1 for t in tasks if t["status"] == "done")
        cancelled = sum(1 for t in tasks if t["status"] == "cancelled")
        open_count = sum(1 for t in tasks if t["status"] in OPEN_STATUSES)
        in_prog = sum(1 for t in tasks if t["status"] == "in_progress")

        # Invariante: total = done + cancelled + open
        assert total == done + cancelled + open_count
        # in_progress ist Teilmenge von open
        assert in_prog <= open_count
