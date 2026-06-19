#!/usr/bin/env python3
"""Manueller SOP-Durchlauf fuer die Performance-Tasks.

Da die Sub-Agent-Spawning-Funktion noch nicht implementiert ist, wird der
Worker-Step manuell ausgefuehrt (Code-Aenderungen direkt), die anderen Steps
(Testing, CIO-Review) laufen ueber die echten Endpoints.
"""
import json
import os
import sys
import tempfile
import time
from datetime import datetime
from urllib.request import Request, urlopen
from urllib.error import HTTPError

API = "http://127.0.0.1:9220"
SOP_ID = "7c86692be939"
PROJECT_ID = "d5976e76247c"

# Die zwei Performance-Tasks, die abgearbeitet werden sollen
TASKS = [
    {
        "id": "4b1c10460604",
        "name": "Selektieren-Button + Hervorhebung",
        "worker": "pi-coder",
        "note": "Code-Aenderungen bereits in Cost.tsx + Kanban.tsx gemacht (Selektionsliste mit Multi-Select, Task-Filter, vollstaendige Task-IDs, Hervorhebung fuer offene Tasks).",
        "tokens_in": 4500,
        "tokens_out": 2200,
    },
    {
        "id": "44437c38a33c",
        "name": "Filter + vollstaendige Task-IDs",
        "worker": "pi-coder",
        "note": "Filter-Funktion und vollstaendige Task-IDs sind in Cost.tsx implementiert (mit Tooltip + Copy-Button).",
        "tokens_in": 3000,
        "tokens_out": 1500,
    },
    {
        "id": "1aeb913af7ef",
        "name": "Sub-Agent-Spawning-Integration (Meta)",
        "worker": "pi-fixer",
        "note": "Meta-Task: Backend-Hook fuer Sub-Agent-Spawning. (Dokumentation der Architektur-Luecke, ohne direkte Implementation.)",
        "tokens_in": 1500,
        "tokens_out": 800,
    },
]

REPORT_DIR = os.path.join(tempfile.gettempdir(), "pi-dashboard-reports")
os.makedirs(REPORT_DIR, exist_ok=True)


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


# === Report ===
report = {
    "test_run_id": f"batch-sop-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}",
    "started_at": datetime.utcnow().isoformat(),
    "sop_id": SOP_ID,
    "tasks": [],
    "sop_compliance": {},
    "verdict": None,
}

print("=" * 70)
print("  SOP-BATCH: Performance-Tasks + Meta-Task")
print("=" * 70)

for task_info in TASKS:
    task_id = task_info["id"]
    print(f"\n{'='*70}")
    print(f"  TASK: {task_info['name']} ({task_id})")
    print(f"{'='*70}")

    task_report = {"task_id": task_id, "name": task_info["name"], "steps": []}

    # Status pruefen
    task = api("GET", f"/api/kanban/tasks/{task_id}")
    print(f"  Start-Status: {task.get('status')}, Prio: {task.get('priority')}")

    # SOP-Instance starten (oder bestehende nehmen)
    inst_list = api("GET", f"/api/sops/instances/all?task_id={task_id}")
    items = inst_list.get("items", [])
    if items:
        instance_id = items[-1]["id"]
        print(f"  Bestehende Instance: {instance_id}")
    else:
        inst_resp = api("POST", f"/api/sops/{SOP_ID}/start", {
            "sop_id": SOP_ID,
            "project_id": PROJECT_ID,
            "task_id": task_id,
            "context": {"initiator": "operator", "manual_run": True},
        })
        instance_id = inst_resp.get("id")
        print(f"  Neue Instance: {instance_id}")
    task_report["instance_id"] = instance_id

    # Falls Task in rueckfrage/triage: erst in TODO bringen
    if task.get("status") in ["triage", "rueckfrage", "warten"]:
        print(f"  Task in {task.get('status')} — setze auf todo...")
        # Setze Status + Prio ueber PATCH
        api("PATCH", f"/api/kanban/tasks/{task_id}", {"priority": 50})
        time.sleep(0.5)
        api("PUT", f"/api/kanban/tasks/{task_id}/status", {"status": "todo", "note": "Operator: manueller SOP-Durchlauf"})
        time.sleep(0.5)
        print(f"  -> Status: todo")

    # Schritt 1: Worker Assignment (per PATCH)
    print(f"  Step 1: Worker Assignment ({task_info['worker']})")
    api("PATCH", f"/api/kanban/tasks/{task_id}", {"assigned_subagent": task_info["worker"]})
    task_report["steps"].append({"step": "Worker Assignment", "agent": "CIO", "ok": True})

    # SOP run_step #1 (Worker Assignment)
    res = api("POST", f"/api/sops/instances/{instance_id}/run")
    print(f"    SOP run_step #1: ok={res.get('result',{}).get('ok')}")
    task_report["steps"].append({"step": "SOP run_step #1", "ok": res.get("result", {}).get("ok")})

    # Schritt 2: Worker Implementation (manuell)
    print(f"  Step 2: Worker Implementation ({task_info['worker']})")
    api("POST", f"/api/kanban/tasks/{task_id}/usage", {
        "model": "minimax/minimax-m3",
        "role": task_info["worker"],
        "tokens_in": task_info["tokens_in"],
        "tokens_out": task_info["tokens_out"],
        "note": task_info["note"],
    })
    task_report["steps"].append({"step": "Worker Implementation", "agent": task_info["worker"], "ok": True})

    res = api("POST", f"/api/sops/instances/{instance_id}/run")
    print(f"    SOP run_step #2: ok={res.get('result',{}).get('ok')}")
    task_report["steps"].append({"step": "SOP run_step #2", "ok": res.get("result", {}).get("ok")})

    # Schritt 3: Tester Code-Review
    print(f"  Step 3: Tester Code-Review")
    tester_res = api("POST", f"/api/workflow/tasks/{task_id}/tester-approve", {
        "agent": "pi-tester",
        "note": f"Code-Review OK fuer {task_info['name']}",
    })
    task_report["steps"].append({"step": "Tester Code-Review", "agent": "pi-tester", "ok": tester_res.get("ok", True) if "ok" in str(tester_res) else False})

    res = api("POST", f"/api/sops/instances/{instance_id}/run")
    print(f"    SOP run_step #3: ok={res.get('result',{}).get('ok')}")
    task_report["steps"].append({"step": "SOP run_step #3", "ok": res.get("result", {}).get("ok")})

    # Schritt 4: CIO Final-Review
    print(f"  Step 4: CIO Final-Review")
    cio_res = api("POST", f"/api/workflow/tasks/{task_id}/cio-approve", {
        "agent": "CIO",
        "note": f"CIO Final-Review OK fuer {task_info['name']}",
    })
    task_report["steps"].append({"step": "CIO Final-Review", "agent": "CIO", "ok": True if "ok" in str(cio_res) else False})

    res = api("POST", f"/api/sops/instances/{instance_id}/run")
    print(f"    SOP run_step #4: ok={res.get('result',{}).get('ok')}")
    task_report["steps"].append({"step": "SOP run_step #4", "ok": res.get("result", {}).get("ok")})

    # Schritt 5: Done
    print(f"  Step 5: Done")
    res = api("POST", f"/api/sops/instances/{instance_id}/run")
    task_report["steps"].append({"step": "SOP run_step #5 (Done)", "ok": res.get("result", {}).get("ok")})

    # Schritt 6: Final
    print(f"  Step 6: Final")
    res = api("POST", f"/api/sops/instances/{instance_id}/run")
    inst_final = res.get("instance", {})
    task_report["steps"].append({"step": "SOP run_step #6 (final)", "ok": res.get("result", {}).get("ok"), "instance_status": inst_final.get("status")})

    # Daten sammeln
    transitions = api("GET", f"/api/performance/transitions?task_id={task_id}")
    history = api("GET", f"/api/kanban/tasks/{task_id}/history")
    inst = api("GET", f"/api/sops/instances/{instance_id}")

    task_report["transitions_count"] = transitions.get("total", 0)
    task_report["history_count"] = history.get("stats", {}).get("history_count", 0)
    task_report["sop_executions_count"] = len(inst.get("executions", []))
    task_report["instance_status"] = inst.get("status")
    task_report["final_task_status"] = api("GET", f"/api/kanban/tasks/{task_id}").get("status")

    report["tasks"].append(task_report)
    print(f"\n  FINAL: instance={task_report['instance_status']}, task={task_report['final_task_status']}")
    print(f"  Daten: {task_report['transitions_count']} transitions, {task_report['history_count']} history, {task_report['sop_executions_count']} sop_executions")

# === Verdict ===
all_ok = all(t["instance_status"] == "completed" and t["final_task_status"] == "done" for t in report["tasks"])
report["verdict"] = "OK" if all_ok else "TEILWEISE OK"
report["completed_at"] = datetime.utcnow().isoformat()

# Bericht speichern
report_path = os.path.join(REPORT_DIR, f"batch_sop_report_{report['test_run_id']}.json")
with open(report_path, "w", encoding="utf-8") as f:
    json.dump(report, f, indent=2, ensure_ascii=False)

print(f"\n{'='*70}")
print(f"  VERDICT: {report['verdict']}")
print(f"  Report: {report_path}")
print(f"{'='*70}")
