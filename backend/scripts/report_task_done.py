"""Helper fuer Sub-Agent: Meldet Task-Status=review zurueck.

Usage (MCP, bevorzugt):
    python scripts/report_task_done.py <task_id> [--status review|failed]

Usage (Legacy HTTP-Fallback):
    python scripts/report_task_done.py <task_id> --api-url <url> --token <token>
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import urllib.request
import urllib.error
from pathlib import Path


def _mcp_report(
    task_id: str,
    status: str,
    role: str,
    model: str,
    endpoint: str,
    api_key: str,
) -> dict:
    """Report via MCP-over-ZMQ bus."""
    # Import app modules lazily so the script can fall back to HTTP when run
    # with an interpreter that does not have the project dependencies.
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from app.mcp_bus.sub_agent_client import (
        report_status,
        report_dispatch,
    )

    async def _call() -> dict:
        status_result = await report_status(
            task_id, status, agent=role, reason="pi-code-agent-done",
            endpoint=endpoint, api_key=api_key,
        )
        dispatch_result = await report_dispatch(
            task_id, role=role, status="done", model=model,
            reason="pi-code-agent-done", endpoint=endpoint, api_key=api_key,
        )
        return {
            "ok": bool(status_result and status_result.get("status") == status),
            "task_id": task_id,
            "status_result": status_result,
            "dispatch_result": dispatch_result,
        }

    return asyncio.run(_call())


def _http_report(
    task_id: str,
    api_url: str,
    token: str,
    role: str,
    model: str,
    status: str,
) -> dict:
    """Legacy HTTP report."""
    status_url = f"{api_url}/api/kanban/tasks/{task_id}/status"
    status_payload = json.dumps({"status": status}).encode("utf-8")
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
        "ok": status_result.get("status") == status,
        "task_id": task_id,
        "status_result": status_result,
        "dispatch_result": dispatch_result,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("task_id")
    parser.add_argument("--status", default="review", choices=["review", "failed", "done"])
    parser.add_argument("--role", default="pi-coder")
    parser.add_argument("--model", default="minimax-direct/minimax-m3")
    parser.add_argument("--endpoint", default=os.environ.get("PI_MCP_ROUTER_ENDPOINT"))
    parser.add_argument("--api-key", default=os.environ.get("PI_MCP_API_KEY", ""))
    parser.add_argument("--api-url", default=os.environ.get("CODE_AGENT_API_URL"))
    parser.add_argument("--token", default=os.environ.get("CODE_AGENT_API_TOKEN"))
    args = parser.parse_args()

    if args.endpoint:
        result = _mcp_report(
            args.task_id, args.status, args.role, args.model,
            args.endpoint, args.api_key,
        )
    else:
        api_url = args.api_url or "http://127.0.0.1:9220"
        token = args.token or "dev"
        result = _http_report(
            args.task_id, api_url, token, args.role, args.model, args.status,
        )

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
