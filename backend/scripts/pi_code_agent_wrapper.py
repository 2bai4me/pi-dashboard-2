"""Wrapper fuer pi-CLI Code-Agent.

Wird vom WorkerService aufgerufen. Liest Task + Plan aus der Pi Dashboard API,
baut einen sauberen Prompt und startet die pi-CLI ohne komplizierte
Shell-Quoting-Probleme.

Usage:
    python scripts/pi_code_agent_wrapper.py <task_id> [--api-url ...] [--token ...]
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path


def fetch_task(task_id: str, api_url: str, token: str) -> dict:
    """Holt Task-Daten aus der Pi Dashboard API."""
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


def build_prompt(task: dict, api_url: str, token: str, budget_usd: float) -> tuple[str, str]:
    """Baut System-Prompt + User-Prompt fuer den pi-CLI Sub-Agent.

    Der System-Prompt bleibt kurz (Rollen + Regeln), der lange Task-Kontext
    inkl. Plan kommt in den User-Prompt. Das vermeidet Probleme mit sehr
    langen Kommandozeilen-Argumenten.
    """
    task_id = task["id"]
    title = task.get("title", "")
    description = task.get("description", "")
    role = task.get("assigned_role") or "pi-coder"
    criteria = task.get("success_criteria", []) or []
    criteria_text = "\n".join(f"- {c}" for c in criteria) if criteria else "- (keine Kriterien)"

    plan = (task.get("meta") or {}).get("worker_plan", {})
    plan_json = json.dumps(plan, ensure_ascii=False, indent=2)

    report_script = Path(__file__).resolve().parent / "report_task_done.py"
    system_prompt = f"""Du bist {role}. Bearbeite den folgenden Task vollstaendig autonom.

Regeln:
1. Arbeite im Projekt-Verzeichnis: {os.getcwd()}
2. Nutze die Tools read, write, edit, bash.
3. Budget-Limit: {budget_usd} USD. Wenn ueberschritten: stoppe und melde Fehler.
4. Arbeite vollautonom ohne Rueckfragen."""

    user_prompt = f"""Task-ID: {task_id}
Titel: {title}

Beschreibung:
{description}

Erfolgskriterien:
{criteria_text}

Geplanter Umsetzungsplan:
{plan_json}

WICHTIG: Wenn die Umsetzung fertig ist (oder wenn du nicht weiterkommst), melde das Ergebnis zurueck durch Aufruf:
  python {report_script} {task_id}

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
    args = parser.parse_args()

    task = fetch_task(args.task_id, args.api_url, args.token)
    system_prompt, user_prompt = build_prompt(task, args.api_url, args.token, args.budget)

    # pi direkt via node ausfuehren, um Windows-.cmd-Quoting-Probleme zu vermeiden
    node_bin = shutil.which("node") or "node"
    pi_script = Path(os.environ.get("PI_AGENT_DIR", str(Path.home() / ".pi" / "agent"))) / "npm" / "node_modules" / "@earendil-works" / "pi-coding-agent" / "dist" / "cli.js"
    if not pi_script.exists():
        # Fallback: npm global path
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

    try:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] START task={args.task_id}", file=log_file)
        print(f"CMD: {' '.join(str(a) for a in pi_args)}", file=log_file)
        log_file.flush()

        env = {**os.environ, "NO_COLOR": "1"}
        proc = subprocess.run(
            pi_args,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            text=True,
            env=env,
            cwd=str(Path(__file__).resolve().parent.parent),
            timeout=7200,
        )
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] EXIT code={proc.returncode}", file=log_file)
        return proc.returncode
    finally:
        if log_handle:
            log_handle.close()


if __name__ == "__main__":
    sys.exit(main())
