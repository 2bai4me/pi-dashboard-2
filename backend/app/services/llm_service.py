"""LLM-Service — Wrapper fuer minimax-M3 (OpenAI-kompatibel).

Wird vom SOP-AI-Helper und anderen KI-gestuetzten Features verwendet.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Optional, List, Dict, Any

import httpx

from .provider_resolver import resolve_model_config

logger = logging.getLogger("pi-dashboard-2.llm")


# === Konfiguration (nur noch aus Umgebungsvariablen / .env) ===
DEFAULT_PROVIDER = "minimax-direct"
DEFAULT_MODEL = "minimax-m3"
DEFAULT_BASE_URL = "https://api.minimax.io/v1"
DEFAULT_API_KEY = os.getenv("MINIMAX_API_KEY", "")


def _load_api_credentials() -> tuple[str, str]:
    """Laedt API-Key und baseUrl ausschliesslich aus Umgebungsvariablen."""
    api_key = os.getenv("MINIMAX_API_KEY", DEFAULT_API_KEY)
    base_url = os.getenv("MINIMAX_BASE_URL", DEFAULT_BASE_URL)
    return api_key, base_url


async def chat_completion(
    messages: List[Dict[str, str]],
    model: str = DEFAULT_MODEL,
    temperature: float = 0.3,
    max_tokens: int = 2000,
    response_format: Optional[Dict[str, str]] = None,
    timeout_sec: float = 60.0,
    role: Optional[str] = None,
) -> Dict[str, Any]:
    """OpenAI-kompatibler Chat-Completion-Aufruf.

    messages: [{"role": "system"|"user"|"assistant", "content": "..."}, ...]

    Provider-Resolution:
      - "ollama/<model>" -> lokales Ollama (kein API-Key noetig)
      - alles andere      -> OpenAI-kompatibler Endpoint (MiniMax/OpenRouter/...)

    Args:
        role: Optional. Wenn gesetzt, wird Provider/Modell/API-Key/Base-URL
              aus dem aktiven Provider-Profil aufgelöst (mit Fallback auf ENV).

    Returns: {
        "content": str,
        "model": str,
        "provider": str,
        "usage": {"tokens_in": int, "tokens_out": int}
    }
    """
    # === Provider-Resolution via Role (Multi-Provider Phase 2) ===
    resolved_api_key: Optional[str] = None
    resolved_base_url: Optional[str] = None
    resolved_model = model
    resolved_provider: Optional[str] = None

    if role:
        config = resolve_model_config(role)
        resolved_api_key = config.get("api_key") or None
        resolved_base_url = config.get("base_url") or None
        resolved_model = config.get("model", model)
        resolved_provider = config.get("provider")

    if resolved_model.startswith("ollama/"):
        return await _chat_ollama(
            messages, resolved_model, temperature, max_tokens, timeout_sec,
            base_url=resolved_base_url,
        )
    return await _chat_openai_compatible(
        messages, resolved_model, temperature, max_tokens, response_format, timeout_sec,
        api_key=resolved_api_key,
        base_url=resolved_base_url,
        provider=resolved_provider,
    )


async def _chat_ollama(
    messages: List[Dict[str, str]],
    model: str,
    temperature: float,
    max_tokens: int,
    timeout_sec: float,
    base_url: Optional[str] = None,
) -> Dict[str, Any]:
    """Aufruf an lokales Ollama (http://localhost:11434). Kein API-Key noetig.

    Returns: {
        "content": str, "model": str, "provider": "ollama",
        "usage": {"tokens_in": int, "tokens_out": int}
    }
    """
    # model ist z.B. "ollama/qwen3:4b" -> wir nehmen "qwen3:4b"
    ollama_model = model.split("/", 1)[1] if "/" in model else model
    base_url = base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
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
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    provider: Optional[str] = None,
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
    env_api_key, env_base_url = _load_api_credentials()
    api_key = api_key or env_api_key
    base_url = base_url or env_base_url
    if not api_key:
        raise RuntimeError("API-Key nicht gesetzt")

    # Model-Name-Normalisierung: MiniMax API erwartet 'MiniMax-M3' (CamelCase),
    # wir akzeptieren aber auch 'minimax-m3' (klein) als User-Input.
    api_model = _normalize_model_name(model, base_url)

    # Provider-Name ableiten (explizit übergeben hat Vorrang)
    if provider:
        pass
    elif "minimax" in base_url.lower():
        provider = "minimax"
    elif "openrouter" in base_url.lower():
        provider = "openrouter"
    elif "moonshot" in base_url.lower() or "kimi" in base_url.lower():
        provider = "kimi"
    elif "openai" in base_url.lower():
        provider = "openai"
    else:
        provider = "openai-compatible"

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
