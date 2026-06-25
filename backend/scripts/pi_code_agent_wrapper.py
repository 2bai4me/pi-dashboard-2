"""Wrapper fuer pi-CLI Code-Agent.

Wird vom WorkerService aufgerufen. Liest Task + Plan ueber den MCP-over-ZMQ-Bus
(oder per HTTP-Fallback), baut einen sauberen Prompt und startet die pi-CLI.
Nach Beendigung der pi-CLI meldet der Wrapper den Status selbst zurueck.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path


def _mcp_get_task(task_id: str, endpoint: str, api_key: str) -> dict:
    """Fetch a task via MCP-over-ZMQ."""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from app.mcp_bus.sub_agent_client import get_task

    async def _call() -> dict:
        result = await get_task(task_id, endpoint=endpoint, api_key=api_key)
        if result is None:
            raise RuntimeError(f"Task {task_id} not found via MCP")
        return result

    return asyncio.run(_call())


def _http_get_task(task_id: str, api_url: str, token: str) -> dict:
    """Fetch a task via legacy HTTP API."""
    import urllib.request
    import urllib.error

    url = f"{api_url}/api/kanban/tasks/{task_id}"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"API-Fehler: {e.code} {e.reason}") from e
    except Exception as e:
        raise RuntimeError(f"Konnte Task nicht laden: {e}") from e


def _mcp_report(
    task_id: str,
    status: str,
    role: str,
    model: str,
    endpoint: str,
    api_key: str,
) -> dict:
    """Report final status via MCP-over-ZMQ."""
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
    status: str,
    role: str,
    model: str,
    api_url: str,
    token: str,
) -> dict:
    """Report final status via legacy HTTP API."""
    import urllib.request
    import urllib.error

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


def build_prompt(task: dict, budget_usd: float) -> tuple[str, str]:
    """Baut System-Prompt + User-Prompt fuer den pi-CLI Sub-Agent."""
    task_id = task["id"]
    title = task.get("title", "")
    description = task.get("description", "")
    role = task.get("assigned_role") or "pi-coder"
    criteria = task.get("success_criteria", []) or []
    criteria_text = "\n".join(f"- {c}" for c in criteria) if criteria else "- (keine Kriterien)"

    plan = (task.get("meta") or {}).get("worker_plan", {})
    plan_json = json.dumps(plan, ensure_ascii=False, indent=2)

    system_prompt = f"""Du bist {role}. Bearbeite den folgenden Task vollstaendig autonom.

Regeln:
1. Arbeite im Projekt-Verzeichnis: {os.getcwd()}
2. Nutze die Tools read, write, edit, bash.
3. Budget-Limit: {budget_usd} USD. Wenn ueberschritten: stoppe und melde Fehler.
4. Arbeite vollautonom ohne Rueckfragen.
5. Der Wrapper meldet den finalen Status selbst zurueck — du musst keine HTTP-Calls ausfuehren."""

    user_prompt = f"""Task-ID: {task_id}
Titel: {title}

Beschreibung:
{description}

Erfolgskriterien:
{criteria_text}

Geplanter Umsetzungsplan:
{plan_json}

Starte die Arbeit jetzt."""

    return system_prompt, user_prompt


def main() -> int:
    parser = argparse.ArgumentParser(description="pi-CLI Code-Agent Wrapper")
    parser.add_argument("task_id", help="Task-ID")
    parser.add_argument("--api-url", default=os.environ.get("CODE_AGENT_API_URL", "http://127.0.0.1:9220"))
    parser.add_argument("--token", default=os.environ.get("CODE_AGENT_API_TOKEN", "dev"))
    parser.add_argument("--model", default=os.environ.get("CODE_AGENT_MODEL", "minimax-m3"))
    parser.add_argument("--provider", default=os.environ.get("CODE_AGENT_PROVIDER", "minimax-direct"))
    parser.add_argument("--budget", type=float, default=float(os.environ.get("CODE_AGENT_MAX_COST_USD", "0.50")))
    parser.add_argument("--log", default=None, help="Log-Datei (optional)")
    parser.add_argument("--endpoint", default=os.environ.get("PI_MCP_ROUTER_ENDPOINT"))
    parser.add_argument("--api-key", default=os.environ.get("PI_MCP_API_KEY", ""))
    args = parser.parse_args()

    if args.endpoint:
        task = _mcp_get_task(args.task_id, args.endpoint, args.api_key)
    else:
        task = _http_get_task(args.task_id, args.api_url, args.token)

    system_prompt, user_prompt = build_prompt(task, args.budget)

    node_bin = shutil.which("node") or "node"
    pi_script = Path(os.environ.get("PI_AGENT_DIR", str(Path.home() / ".pi" / "agent"))) / "npm" / "node_modules" / "@earendil-works" / "pi-coding-agent" / "dist" / "cli.js"
    if not pi_script.exists():
        pi_script = Path.home() / "AppData" / "Roaming" / "npm" / "node_modules" / "@earendil-works" / "pi-coding-agent" / "dist" / "cli.js"
    pi_args = [
        node_bin,
        str(pi_script),
        "--provider", args.provider,
        "--model", args.model,
        "--system-prompt", system_prompt,
        "--no-session",
        "--tools", "read,write,edit,bash",
        user_prompt,
    ]

    log_file = sys.stdout
    log_handle = None
    if args.log:
        log_dir = Path(args.log).parent
        log_dir.mkdir(parents=True, exist_ok=True)
        log_handle = open(args.log, "w", encoding="utf-8")
        log_file = log_handle

    exit_code = 1
    try:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] START task={args.task_id}", file=log_file)
        print(f"CMD: {' '.join(str(a) for a in pi_args)}", file=log_file)
        log_file.flush()

        proc = subprocess.run(
            pi_args,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            text=True,
            env={**os.environ, "NO_COLOR": "1"},
            cwd=str(Path(__file__).resolve().parent.parent),
            timeout=7200,
        )
        exit_code = proc.returncode
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] EXIT code={exit_code}", file=log_file)
    finally:
        if log_handle:
            log_handle.close()

    final_status = "review" if exit_code == 0 else "failed"
    if args.endpoint:
        result = _mcp_report(
            args.task_id, final_status,
            task.get("assigned_role") or "pi-coder",
            f"{args.provider}/{args.model}",
            args.endpoint, args.api_key,
        )
    else:
        result = _http_report(
            args.task_id, final_status,
            task.get("assigned_role") or "pi-coder",
            f"{args.provider}/{args.model}",
            args.api_url, args.token,
        )

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
