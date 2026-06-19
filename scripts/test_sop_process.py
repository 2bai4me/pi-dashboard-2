#!/usr/bin/env python3
"""E2E-Test: Standard-Workflow Task SOP durchlaufen + Bericht erstellen.

Testet, ob ein Task korrekt nach der SOP 'Standard-Workflow Task' prozessiert wird.
Jeder Schritt wird in der task_transitions Tabelle dokumentiert.
Am Ende wird ein Bericht erstellt, ob die Verarbeitung der SOP entspricht.
"""
import json
import os
import tempfile
import time
from datetime import datetime
from urllib.request import Request, urlopen
from urllib.error import HTTPError

API = "http://127.0.0.1:9220"
TASK_ID = "8e6ba116eb5b"  # TEST 2: BUGFIX - Initial-Tab soll Board sein
SOP_ID = "7c86692be939"
PROJECT_ID = "d5976e76247c"

# Reports ablegen in tempdir/pi-dashboard-reports (Windows-kompatibel)
REPORT_DIR = os.path.join(tempfile.gettempdir(), "pi-dashboard-reports")
os.makedirs(REPORT_DIR, exist_ok=True)

# === Report-Struktur ===
report = {
    "test_run_id": f"test-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}",
    "task_id": TASK_ID,
    "sop_id": SOP_ID,
    "started_at": datetime.utcnow().isoformat(),
    "sop_definition": {},
    "steps": [],
    "performance_summary": {},
    "sop_compliance": {},
    "verdict": None,
}


def api(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = Request(f"{API}{path}", data=data, method=method)
    req.add_header("Content-Type", "application/json")
    try:
        with urlopen(req) as r:
            text = r.read().decode()
            return json.loads(text) if text else {}
    except HTTPError as e:
        return {"_error": e.code, "_body": e.read().decode()[:500]}


def log_step(step_name, agent, action, result, extra=None):
    entry = {
        "step": step_name,
        "agent": agent,
        "action": action,
        "result": result,
        "timestamp": datetime.utcnow().isoformat(),
    }
    if extra:
        entry.update(extra)
    report["steps"].append(entry)
    print(f"  + {step_name} ({agent}): {action}")


# =========================================================
# SOP-Definition laden
# =========================================================
print("\n=== SOP-Definition laden ===")
sop = api("GET", f"/api/sops/{SOP_ID}")
report["sop_definition"] = {
    "name": sop.get("name"),
    "version": sop.get("version"),
    "step_count": len(sop.get("steps", [])),
    "steps": [
        {
            "order": s.get("step_order"),
            "name": s.get("name"),
            "phase": s.get("phase"),
            "agent": s.get("agent"),
            "action": s.get("action"),
            "trigger": s.get("trigger"),
            "delay_s": s.get("delay_s"),
        }
        for s in sop.get("steps", [])
    ],
}
print(f"  SOP: {sop.get('name')} v{sop.get('version')}, {len(sop.get('steps', []))} Steps")

# SOP-Instance starten (an Task gebunden)
print("\n=== SOP-Instance starten ===")
inst_resp = api("POST", f"/api/sops/{SOP_ID}/start", {
    "sop_id": SOP_ID,
    "project_id": PROJECT_ID,
    "task_id": TASK_ID,
    "context": {"initiator": "user", "test": True},
})
instance_id = inst_resp.get("id")
report["instance_id"] = instance_id
print(f"  Instance-ID: {instance_id}")
print(f"  Status: {inst_resp.get('status')}")
print(f"  Current Step: {inst_resp.get('current_step_id')}")

# =========================================================
# SCHRITT 0: CIO Triage Review (SOP Step 1)
# =========================================================
print("\n=== SCHRITT 0: CIO Triage Review (SOP Step 1) ===")
print("  (alle 4 Pruefungen bereits gesetzt)")
task = api("GET", f"/api/kanban/tasks/{TASK_ID}")
log_step(
    "CIO Triage Review (SOP Step 1)",
    "CIO",
    "review_task",
    {
        "ok": True,
        "task_type": task.get("task_type"),
        "standards_matches": len((task.get("standards_check") or {}).get("matches", [])),
        "implementation_files": len((task.get("implementation_plan") or {}).get("files", [])),
        "subagent_ready": (task.get("subagent_readiness") or {}).get("ready", False),
    },
)

# =========================================================
# SCHRITT 1: Worker Assignment (SOP Step 2)
# =========================================================
print("\n=== SCHRITT 1: Worker Assignment (SOP Step 2) ===")
api("PATCH", f"/api/kanban/tasks/{TASK_ID}", {"assigned_subagent": "pi-coder"})
task = api("GET", f"/api/kanban/tasks/{TASK_ID}")
log_step(
    "Worker Assignment (SOP Step 2)",
    "CIO",
    "assign_worker",
    {
        "ok": True,
        "assigned_subagent": task.get("assigned_subagent"),
    },
)
res = api("POST", f"/api/sops/instances/{instance_id}/run")
log_step("SOP Engine: run_step #1", "SOPEngine", "run_step", {
    "ok": res.get("result", {}).get("ok"),
    "next_step": res.get("instance", {}).get("current_step_id"),
})

# =========================================================
# SCHRITT 2: Worker Implementation (SOP Step 3)
# =========================================================
print("\n=== SCHRITT 2: Worker Implementation (SOP Step 3) ===")
print("  (Simuliert — Sub-Agent spawn.sh existiert, ist aber Mock-Modus)")
api("POST", f"/api/kanban/tasks/{TASK_ID}/usage", {
    "model": "minimax/minimax-m3",
    "role": "pi-coder",
    "tokens_in": 1500,
    "tokens_out": 800,
    "note": "Bugfix in Kanban.tsx: openProject(id, brainstorm) -> openProject(id, board)",
})
log_step(
    "Worker Implementation (SOP Step 3)",
    "pi-coder",
    "start_work",
    {"ok": True, "note": "Code-Aenderung in Kanban.tsx (Zeile 35) — openProject(id, board) statt brainstorm"},
    {"tokens_in": 1500, "tokens_out": 800, "cost_usd": 0.0014},
)
res = api("POST", f"/api/sops/instances/{instance_id}/run")
log_step("SOP Engine: run_step #2", "SOPEngine", "run_step", {
    "ok": res.get("result", {}).get("ok"),
    "next_step": res.get("instance", {}).get("current_step_id"),
})

# =========================================================
# SCHRITT 3: Tester Code-Review (SOP Step 4)
# =========================================================
print("\n=== SCHRITT 3: Tester Code-Review (SOP Step 4) ===")
api("POST", f"/api/workflow/tasks/{TASK_ID}/tester-approve", {
    "agent": "pi-tester",
    "note": "Code-Review OK: Initial-Tab ist 'board'. Test: Klick auf Projekte -> Kachel -> Board-Tab aktiv.",
})
log_step(
    "Tester Code-Review (SOP Step 4)",
    "pi-tester",
    "tester-approve",
    {"ok": True, "note": "Code-Review bestanden"},
)
res = api("POST", f"/api/sops/instances/{instance_id}/run")
log_step("SOP Engine: run_step #3", "SOPEngine", "run_step", {
    "ok": res.get("result", {}).get("ok"),
    "next_step": res.get("instance", {}).get("current_step_id"),
})

# =========================================================
# SCHRITT 4: CIO Final-Review (SOP Step 5)
# =========================================================
print("\n=== SCHRITT 4: CIO Final-Review (SOP Step 5) ===")
api("POST", f"/api/workflow/tasks/{TASK_ID}/cio-approve", {
    "agent": "CIO",
    "note": "CIO Final-Review OK: Task ist klein (1 Zeile) und gut getestet. Freigabe.",
})
log_step(
    "CIO Final-Review (SOP Step 5)",
    "CIO",
    "cio-approve",
    {"ok": True, "note": "Freigabe erteilt"},
)
res = api("POST", f"/api/sops/instances/{instance_id}/run")
log_step("SOP Engine: run_step #4", "SOPEngine", "run_step", {
    "ok": res.get("result", {}).get("ok"),
    "next_step": res.get("instance", {}).get("current_step_id"),
})

# =========================================================
# SCHRITT 5: Done (SOP Step 6)
# =========================================================
print("\n=== SCHRITT 5: Done (SOP Step 6) ===")
res = api("POST", f"/api/sops/instances/{instance_id}/run")
log_step("SOP Engine: run_step #5 (Done)", "SOPEngine", "run_step", {
    "ok": res.get("result", {}).get("ok"),
    "instance_status": res.get("instance", {}).get("status"),
})

# Einmal nachschieben — Done-Step selbst muss auch completed werden
print("  Run Step 6 (Done actually completes instance)...")
res = api("POST", f"/api/sops/instances/{instance_id}/run")
log_step("SOP Engine: run_step #6 (final)", "SOPEngine", "run_step", {
    "ok": res.get("result", {}).get("ok"),
    "instance_status": res.get("instance", {}).get("status"),
    "completed_at": res.get("instance", {}).get("completed_at"),
})

# =========================================================
# DATEN SAMMELN
# =========================================================
print("\n=== DATEN SAMMELN ===")
# 1. task_transitions (Performance)
transitions = api("GET", f"/api/performance/transitions?task_id={TASK_ID}")
report["performance_summary"]["transitions_count"] = transitions.get("total", 0)
report["performance_summary"]["transitions"] = transitions.get("items", [])

# 2. task_history (Audit)
history = api("GET", f"/api/kanban/tasks/{TASK_ID}/history")
report["performance_summary"]["history_count"] = history.get("stats", {}).get("history_count", 0)
report["performance_summary"]["history"] = history.get("history", [])

# 3. SOP-Executions
inst = api("GET", f"/api/sops/instances/{instance_id}")
executions = inst.get("executions", [])
report["performance_summary"]["sop_executions_count"] = len(executions)
report["performance_summary"]["sop_executions"] = executions
report["performance_summary"]["instance_status"] = inst.get("status")
report["performance_summary"]["instance_completed_at"] = inst.get("completed_at")

# 4. Token-Usage
token_usage = api("GET", f"/api/performance/stats")  # overview
report["performance_summary"]["token_usage_summary"] = token_usage

# =========================================================
# SOP-COMPLIANCE-CHECK
# =========================================================
print("\n=== SOP-COMPLIANCE-CHECK ===")
expected_sequence = [
    ("review_task", "CIO", "Step 1: CIO Triage Review"),
    ("assign_worker", "CIO", "Step 2: Worker Assignment"),
    ("start_work", "pi-coder", "Step 3: Worker Implementation"),
    ("tester-approve", "pi-tester", "Step 4: Tester Code-Review"),  # might be different
    ("cio-approve", "CIO", "Step 5: CIO Final-Review"),
    ("noop", "system", "Step 6: Done"),
]

# Check transitions
transition_seq = [(t.get("from_status"), t.get("to_status")) for t in transitions.get("items", [])]
print(f"  Transitions in Performance-Tabelle: {len(transition_seq)}")
for tr in transition_seq:
    print(f"    - {tr[0]} -> {tr[1]}")

# Check history events
history_events = [h.get("event") for h in history.get("history", [])]
print(f"\n  History-Eintraege: {len(history_events)}")
for e in history_events:
    print(f"    - {e}")

# Check SOP executions
sop_events = [e.get("event") for e in executions]
print(f"\n  SOP-Executions: {len(sop_events)}")
for e in sop_events:
    print(f"    - {e}")

# Compliance
report["sop_compliance"] = {
    "expected_sop_steps": len(expected_sequence),
    "actual_sop_executions": len([e for e in sop_events if e == "step_completed"]),
    "transitions_in_perf_table": len(transition_seq),
    "history_entries": len(history_events),
    "instance_status": inst.get("status"),
    "checks": {
        "all_6_sop_steps_executed": len([e for e in sop_events if e == "step_completed"]) == 6,
        "instance_completed": inst.get("status") == "completed",
        "perf_table_has_transitions": len(transition_seq) >= 3,
        "task_history_has_entries": len(history_events) >= 5,
    },
}

# Verdict
all_ok = all(report["sop_compliance"]["checks"].values())
report["verdict"] = "OK — Verarbeitung entspricht der SOP" if all_ok else "FAIL — siehe Compliance-Checks"
report["completed_at"] = datetime.utcnow().isoformat()

# =========================================================
# BERICHT SCHREIBEN
# =========================================================
report_path = os.path.join(REPORT_DIR, f"sop_test_report_{report['test_run_id']}.json")
with open(report_path, "w", encoding="utf-8") as f:
    json.dump(report, f, indent=2, ensure_ascii=False)
print(f"\n=== BERICHT GESPEICHERT: {report_path} ===")
print(f"=== VERDICT: {report['verdict']} ===")
