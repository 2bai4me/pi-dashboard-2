"""Helper fuer Sub-Agent: Meldet Task-Status=review zurueck.

Usage:
    python scripts/report_task_done.py <task_id> [--api-url ...] [--token ...]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
import urllib.error


def report_done(task_id: str, api_url: str, token: str, role: str = "pi-coder", model: str = "minimax-direct/minimax-m3") -> dict:
    """Setzt Task-Status auf review via Status-Endpoint."""
    # 1) Status auf review setzen
    status_url = f"{api_url}/api/kanban/tasks/{task_id}/status"
    status_payload = json.dumps({
        "status": "review",
    }).encode("utf-8")
    status_req = urllib.request.Request(
        status_url,
        data=status_payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="PUT",
    )
    try:
        with urllib.request.urlopen(status_req, timeout=30) as resp:
            status_result = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"ok": False, "error": f"status {e.code} {e.reason}"}
    except Exception as e:
        return {"ok": False, "error": f"status {e}"}

    # 2) Dispatch-Info melden (fuer Tracking)
    dispatch_url = f"{api_url}/api/kanban/tasks/{task_id}/dispatch"
    dispatch_payload = json.dumps({
        "status": "done",
        "role": role,
        "model": model,
        "reason": "pi-code-agent-done",
    }).encode("utf-8")
    dispatch_req = urllib.request.Request(
        dispatch_url,
        data=dispatch_payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="PATCH",
    )
    try:
        with urllib.request.urlopen(dispatch_req, timeout=30) as resp:
            dispatch_result = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        dispatch_result = {"ok": False, "error": str(e)}

    return {
        "ok": status_result.get("status") == "review",
        "task_id": task_id,
        "status_result": status_result,
        "dispatch_result": dispatch_result,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("task_id")
    parser.add_argument("--api-url", default=os.environ.get("CODE_AGENT_API_URL", "http://127.0.0.1:9220"))
    parser.add_argument("--token", default=os.environ.get("CODE_AGENT_API_TOKEN", "dev"))
    parser.add_argument("--role", default="pi-coder")
    parser.add_argument("--model", default="minimax-direct/minimax-m3")
    args = parser.parse_args()

    result = report_done(args.task_id, args.api_url, args.token, args.role, args.model)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
