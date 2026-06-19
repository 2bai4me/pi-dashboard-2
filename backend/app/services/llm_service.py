"""LLM-Service — Wrapper fuer minimax-M3 (OpenAI-kompatibel).

Wird vom SOP-AI-Helper und anderen KI-gestuetzten Features verwendet.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Optional, List, Dict, Any

import httpx

logger = logging.getLogger("pi-dashboard-2.llm")


# === Konfiguration (aus ~/.pi/agent/models.json) ===
DEFAULT_PROVIDER = "minimax-direct"
DEFAULT_MODEL = "minimax-m3"
DEFAULT_BASE_URL = "https://api.minimax.io/v1"
DEFAULT_API_KEY = os.getenv("MINIMAX_API_KEY", "")


def _load_api_credentials() -> tuple[str, str]:
    """Laedt API-Key und baseUrl aus models.json oder Umgebungsvariablen."""
    api_key = DEFAULT_API_KEY
    base_url = DEFAULT_BASE_URL
    # Versuche aus ~/.pi/agent/models.json zu laden
    try:
        import json
        from pathlib import Path
        models_file = Path.home() / ".pi" / "agent" / "models.json"
        if models_file.exists():
            with open(models_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            prov = data.get("providers", {}).get(DEFAULT_PROVIDER, {})
            if prov.get("apiKey"):
                api_key = prov["apiKey"]
            if prov.get("baseUrl"):
                base_url = prov["baseUrl"]
    except Exception as e:
        logger.warning(f"Konnte models.json nicht laden: {e}")
    return api_key, base_url


async def chat_completion(
    messages: List[Dict[str, str]],
    model: str = DEFAULT_MODEL,
    temperature: float = 0.3,
    max_tokens: int = 2000,
    response_format: Optional[Dict[str, str]] = None,
    timeout_sec: float = 60.0,
) -> Dict[str, Any]:
    """OpenAI-kompatibler Chat-Completion-Aufruf.

    messages: [{"role": "system"|"user"|"assistant", "content": "..."}, ...]

    Provider-Resolution:
      - "ollama/<model>" -> lokales Ollama (kein API-Key noetig)
      - alles andere      -> OpenAI-kompatibler Endpoint (MiniMax/OpenRouter/...)

    Returns: {
        "content": str,
        "model": str,
        "provider": str,
        "usage": {"tokens_in": int, "tokens_out": int}
    }
    """
    # === Provider-Resolution ===
    if model.startswith("ollama/"):
        return await _chat_ollama(messages, model, temperature, max_tokens, timeout_sec)
    return await _chat_openai_compatible(messages, model, temperature, max_tokens, response_format, timeout_sec)


async def _chat_ollama(
    messages: List[Dict[str, str]],
    model: str,
    temperature: float,
    max_tokens: int,
    timeout_sec: float,
) -> Dict[str, Any]:
    """Aufruf an lokales Ollama (http://localhost:11434). Kein API-Key noetig.

    Returns: {
        "content": str, "model": str, "provider": "ollama",
        "usage": {"tokens_in": int, "tokens_out": int}
    }
    """
    # model ist z.B. "ollama/qwen3:4b" -> wir nehmen "qwen3:4b"
    ollama_model = model.split("/", 1)[1] if "/" in model else model
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    url = f"{base_url.rstrip('/')}/api/chat"

    payload: Dict[str, Any] = {
        "model": ollama_model,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens,
        },
    }

    logger.info(f"Ollama call: model={ollama_model} url={url}")
    try:
        async with httpx.AsyncClient(timeout=timeout_sec) as client:
            r = await client.post(url, json=payload)
            r.raise_for_status()
            data = r.json()
    except httpx.ConnectError as e:
        raise RuntimeError(
            f"Ollama nicht erreichbar unter {url}. "
            f"Stelle sicher, dass Ollama laeuft (ollama serve) und Modell '{ollama_model}' gepullt ist "
            f"(ollama pull {ollama_model})."
        ) from e
    except httpx.HTTPStatusError as e:
        raise RuntimeError(
            f"Ollama-Fehler {e.response.status_code}: {e.response.text[:200]}"
        ) from e
    # Ollama liefert prompt_eval_count + eval_count im Response
    ollama_model_full = model if not model.startswith("ollama/") else model.split("/", 1)[1] if "/" in model else model
    return {
        "content": data.get("message", {}).get("content", ""),
        "model": ollama_model_full,
        "provider": "ollama",
        "usage": {
            "tokens_in": data.get("prompt_eval_count", 0),
            "tokens_out": data.get("eval_count", 0),
        },
    }


async def _chat_openai_compatible(
    messages: List[Dict[str, str]],
    model: str,
    temperature: float,
    max_tokens: int,
    response_format: Optional[Dict[str, str]],
    timeout_sec: float,
) -> Dict[str, Any]:
    """OpenAI-kompatibler Chat-Completion-Aufruf (MiniMax/OpenRouter/Anthropic/...).

    Returns: {
        "content": str (LLM-Response),
        "model": str (echoed model),
        "provider": "minimax"|"openrouter"|...,
        "usage": {"tokens_in": int, "tokens_out": int}
    }
    """
    # MiniMax hat keinen '/' im model_id, OpenRouter schon. Beide nutzen OpenAI-Format.
    api_key, base_url = _load_api_credentials()
    if not api_key:
        raise RuntimeError("MINIMAX_API_KEY nicht gesetzt und models.json enthaelt keinen Key")

    # Model-Name-Normalisierung: MiniMax API erwartet 'MiniMax-M3' (CamelCase),
    # wir akzeptieren aber auch 'minimax-m3' (klein) als User-Input.
    api_model = _normalize_model_name(model, base_url)

    # Provider-Name ableiten
    provider = "minimax" if "minimax" in base_url.lower() else "openrouter"

    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload: Dict[str, Any] = {
        "model": api_model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if response_format:
        payload["response_format"] = response_format
    # MiniMax M3 hat per Default "thinking mode" an — Denkbloecke verlangsamen und
    # liefern thinking-Output mit. Mit thinking.type=disabled antwortet das Modell
    # direkt ohne Denkblock (viel schneller, sauberer Output).
    if "minimax" in base_url.lower() and api_model.lower().startswith("minimax"):
        payload["thinking"] = {"type": "disabled"}

    async with httpx.AsyncClient(timeout=timeout_sec) as client:
        r = await client.post(url, headers=headers, json=payload)
        r.raise_for_status()
        data = r.json()

    content = data["choices"][0]["message"]["content"]
    # OpenAI-kompatible APIs liefern Token-Usage im `usage`-Feld
    usage_obj = data.get("usage", {}) or {}
    usage = {
        "tokens_in": usage_obj.get("prompt_tokens", 0),
        "tokens_out": usage_obj.get("completion_tokens", 0),
    }
    return {
        "content": content,
        "model": api_model,
        "provider": provider,
        "usage": usage,
    }


def _normalize_model_name(model: str, base_url: str) -> str:
    """Normalisiert Model-Namen je nach Provider.
    MiniMax API erwartet CamelCase ('MiniMax-M3'), nicht 'minimax-m3'.
    Akzeptiert verschiedene Input-Formate:
      - 'minimax-m3'
      - 'minimax-direct/minimax-m3'
      - 'MiniMax-M3'
    """
    if "minimax" not in base_url.lower():
        return model
    # Entferne Provider-Praefix falls vorhanden
    m = model
    if "/" in m:
        m = m.split("/", 1)[1]
    # CamelCase normalisieren
    parts = m.split("-", 1)
    if len(parts) == 2 and parts[0].lower() == "minimax":
        return f"MiniMax-{parts[1]}"
    return m


def build_sop_step_prompt(
    step: dict,
    user_input: str,
    sop_name: str = "",
) -> tuple[List[Dict[str, str]], str]:
    """Baut den System-Prompt + User-Prompt fuer die SOP-Step-Beschreibung.

    Returns: (messages, raw_user_input)
    """
    # System-Prompt: Definiert Rolle + erwartetes JSON-Format
    system_prompt = """Du bist ein erfahrener KI-Workflow-Architekt. Deine Aufgabe ist es, aus einer kurzen, umgangssprachlichen Notiz eines Users eine **optimale, praezise und ausfuehrbare Schritt-Beschreibung** fuer einen automatisierten KI-Worker-Agent zu erstellen.

**Wichtige Regeln:**
1. Die Beschreibung muss klar und eindeutig sein, sodass ein LLM-Worker ohne Rueckfragen weiss, was zu tun ist.
2. Verwende aktive Verben (z.B. "Analysiere", "Erstelle", "Pruefe", "Implementiere").
3. Strukturiere die Beschreibung logisch: WAS (Ziel) -> WIE (Vorgehen) -> WANN FERTIG (Definition of Done).
4. Mindestens 80 Zeichen, ideal 200-400 Zeichen.
5. Expected Result: 1-2 Saetze, was am Ende konkret vorliegt (Datei, Commit, Status, Output, ...).
6. Sprache: Deutsch (sofern nicht anders angegeben).

**Antwort-Format (STRIKTE JSON-Antwort, nichts anderes):**
```json
{
  "description": "Vollstaendige, praezise Schritt-Beschreibung...",
  "expected_result": "Konkretes, pruefbares Ergebnis...",
  "questions": ["Optional: Rueckfragen, falls etwas unklar ist"],
  "suggestions": ["Optional: Verbesserungsvorschlaege"]
}
```

Antworte NUR mit dem JSON-Objekt, ohne zusaetzlichen Text."""

    # User-Prompt: Kontext + User-Notiz
    step_context_lines = [
        f"**SOP:** {sop_name or 'Unbenannt'}",
        f"**Step-Name:** {step.get('name', '?')}",
        f"**Phase:** {step.get('phase', '?')}",
        f"**Agent:** {step.get('agent', '?')}",
        f"**Action:** {step.get('action', '?')}",
        f"**Trigger:** {step.get('trigger', '?')}",
    ]
    if step.get("description"):
        step_context_lines.append(f"**Aktuelle Description:** {step['description']}")
    if step.get("expected_result"):
        step_context_lines.append(f"**Aktuelles Expected Result:** {step['expected_result']}")

    user_prompt = "\n".join(step_context_lines) + "\n\n**User-Notiz (in einfachem Deutsch):**\n" + user_input

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    return messages, user_input
