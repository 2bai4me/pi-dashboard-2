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


class LLMTransientError(RuntimeError):
    """Temporaerer LLM-Fehler (z.B. 429, 5xx, Timeout). Wiederholbar."""

    def __init__(self, message: str, status_code: Optional[int] = None, retry_after: Optional[float] = None):
        super().__init__(message)
        self.status_code = status_code
        self.retry_after = retry_after


class LLMPermanentError(RuntimeError):
    """Permanenter LLM-Fehler (z.B. 401/403/404). Nicht wiederholbar."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


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
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    provider: Optional[str] = None,
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
    resolved_api_key: Optional[str] = api_key
    resolved_base_url: Optional[str] = base_url
    resolved_model = model
    resolved_provider: Optional[str] = provider

    if role:
        config = resolve_model_config(role)
        resolved_api_key = resolved_api_key or config.get("api_key") or None
        resolved_base_url = resolved_base_url or config.get("base_url") or None
        resolved_model = config.get("model", model)
        resolved_provider = resolved_provider or config.get("provider")

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
        raise LLMTransientError(
            f"Ollama nicht erreichbar unter {url}. "
            f"Stelle sicher, dass Ollama laeuft (ollama serve) und Modell '{ollama_model}' gepullt ist "
            f"(ollama pull {ollama_model})."
        ) from e
    except httpx.TimeoutException as e:
        raise LLMTransientError(f"Ollama-Timeout unter {url}.", status_code=408) from e
    except httpx.HTTPStatusError as e:
        status = e.response.status_code
        if status == 429 or status >= 500:
            raise LLMTransientError(
                f"Ollama-Fehler {status}: {e.response.text[:200]}", status_code=status
            ) from e
        raise LLMPermanentError(
            f"Ollama-Fehler {status}: {e.response.text[:200]}", status_code=status
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
        raise LLMPermanentError("API-Key nicht gesetzt")

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

    try:
        async with httpx.AsyncClient(timeout=timeout_sec) as client:
            r = await client.post(url, headers=headers, json=payload)
            r.raise_for_status()
            data = r.json()
    except httpx.HTTPStatusError as e:
        status = e.response.status_code
        text = e.response.text[:200]
        if status == 429:
            retry_after = None
            try:
                retry_after = float(e.response.headers.get("Retry-After", ""))
            except (ValueError, TypeError):
                pass
            raise LLMTransientError(
                f"Client error '429 Too Many Requests' for url '{url}'",
                status_code=status,
                retry_after=retry_after,
            ) from e
        if status >= 500:
            raise LLMTransientError(
                f"Server error '{status}' for url '{url}': {text}", status_code=status
            ) from e
        raise LLMPermanentError(
            f"Client error '{status}' for url '{url}': {text}", status_code=status
        ) from e
    except httpx.TimeoutException as e:
        raise LLMTransientError(f"Timeout for url '{url}'", status_code=408) from e
    except (httpx.ConnectError, httpx.NetworkError) as e:
        raise LLMTransientError(f"Connection error for url '{url}': {e}") from e

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


def build_bpmn_from_description_prompt(sop_data: dict) -> tuple[List[Dict[str, str]], str]:
    """Baut den System+User-Prompt fuer die LLM-gestuetzte BPMN-Generierung
    aus den Freitext-Beschreibungen einer SOP (Name, Description, alle Step-Descriptions).

    Args:
        sop_data: {
            "id": str,
            "name": str,
            "description": Optional[str],
            "steps": [{"order": int, "name": str, "phase": str,
                       "agent": Optional[str], "trigger": Optional[str],
                       "action": Optional[str], "description": Optional[str],
                       "expected_result": Optional[str]}, ...] (sortiert)
        }

    Returns: (messages, raw_user_input)
    """
    system_prompt = """Du bist ein BPMN-2.0-Architekt. Deine einzige Aufgabe: Aus den nachfolgenden Freitext-Beschreibungen einer SOP (Standard Operating Procedure) generierst du **valides, vollstaendiges BPMN 2.0 XML**, das im bpmn-js Renderer ohne Fehler dargestellt werden kann.

KRITISCHE REGELN:

1. **Antworte NUR mit dem XML**, kein Vor- oder Nachtext, keine Erklaerung, kein Markdown-Codeblock (```xml) drumherum. Beginne direkt mit `<?xml version="1.0" encoding="UTF-8"?>` und ende mit `</bpmn:definitions>`.

2. **Verwende exakt diese Namespaces** (alle 5 sind PFLICHT, damit bpmn-js das XML korrekt einliest):
   - xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
   - xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI"
   - xmlns:dc="http://www.omg.org/spec/DD/20100524/DC"
   - xmlns:di="http://www.omg.org/spec/DD/20100524/DI"
   - xmlns:bpmnjs="http://www.omg.io/schema/bpmn-js" (PFLICHT fuer <bpmnjs:isExpanded>)

3. **Top-Level-Struktur** (in dieser Reihenfolge):
   - `<bpmn:definitions>` mit `id="Definitions_<sop_id>"` und `targetNamespace="http://bpmn.io/schema/bpmn"`
   - `<bpmn:process>` mit `id="Process_<sop_id>"`, `name="<sop-name>"`, `isExecutable="false"`
   - `<bpmn:documentation>` mit der vollstaendigen SOP-Beschreibung (XML-escaped)
   - `<bpmn:startEvent>` mit `id="start_<sop_id>"` und `name="SOP Start"`
   - Beliebig viele `<bpmn:subProcess>` (kollabiert, mit `<bpmnjs:isExpanded>false</bpmnjs:isExpanded>`)
   - `<bpmn:endEvent>` mit `id="end_<sop_id>"` und `name="SOP End"`
   - Dazwischen `<bpmn:sequenceFlow>` Elemente, die die Elemente verbinden
   - NACH `</bpmn:process>` (aber INNERHALB `<bpmn:definitions>`!): ein einzelner Block:
     ```
     <bpmndi:BPMNDiagram id="BPMNDiagram_<sop_id>">
       <bpmndi:BPMNPlane id="BPMNPlane_<sop_id>" bpmnElement="Process_<sop_id>">
         <!-- HIER alle <bpmndi:BPMNShape> und <bpmndi:BPMNEdge> -->
       </bpmndi:BPMNPlane>
     </bpmndi:BPMNDiagram>
     ```
   - WICHTIG: Die DI-Shapes und DI-Edges gehoeren NICHT in die BPMN-Tasks, sondern ALLE zusammen in den BPMNPlane-Block oben!

4. **Innerhalb jedes SubProcess** (alle Elemente haben 6-space indent):
   - `<bpmn:serviceTask>` oder `<bpmn:userTask>` mit `id="step_<step_id>"` und `name="<step-name>"` (XML-escaped)
   - Optional `<bpmn:exclusiveGateway>` mit `id="gw_<step_id>"` und `name="?"` (nur wenn der Step eine Verzweigung hat)
   - `<bpmn:sequenceFlow>` Elemente, die Tasks/Gateways innerhalb des SubProcess verbinden
   - Pro Gateway: ein sequenceFlow mit `<bpmn:conditionExpression>` (Bedingung als Text im Tag)

5. **Jedes Element MUSS eine BPMN-DI-Darstellung haben** (sonst zeigt bpmn-js es nicht an!):
   - **WICHTIG:** Alle `<bpmndi:BPMNShape>` und `<bpmndi:BPMNEdge>` Elemente MUESSEN innerhalb EINES EINZIGEN `<bpmndi:BPMNDiagram>` -> `<bpmndi:BPMNPlane>` Blocks stehen, NICHT innerhalb der BPMN-Tasks/SubProcesses!
   - `<bpmndi:BPMNShape>` mit `<dc:Bounds x=".." y=".." width=".." height=".." />`
   - SubProcesses zusaetzlich: `<bpmndi:BPMNLabel/>` und `<bpmnjs:isExpanded>false</bpmnjs:isExpanded>`
   - Jeder Edge (`<bpmn:sequenceFlow>`) braucht einen `<bpmndi:BPMNEdge>` mit mindestens 2 `<di:waypoint>` Elementen

6. **Layout-Konventionen** (wichtig fuer gute Lesbarkeit):
   - Top-Level horizontal: StartEvent (x=80, y=280), SubProcesses (width=240, height=110) mit Abstand 240 dazwischen, EndEvent am Ende
   - Start-/EndEvents: 50x50 px Box
   - SubProcess Y-Position: 280 - 55 = 225 (mittig zu Y_CENTER=280)
   - Innerhalb SubProcess: Tasks/Gateways vertikal staffeln (z.B. y=40, 110, 180, ...)
   - Sequence-Flows: waypoints entlang der Kanten

7. **Schritt-Logik aus Beschreibungen ableiten**:
   - Wenn ein Step mehrere Verzweigungen, Entscheidungen oder Bedingungen erwaehnt: fuege ein `<bpmn:exclusiveGateway>` ein
   - Wenn ein Step User-Eingaben erfordert (Frage, Genehmigung, Review): verwende `<bpmn:userTask>` statt `<bpmn:serviceTask>`
   - Gruppere logisch zusammengehoerige Steps in eigene `<bpmn:subProcess>` mit aussagekraeftigem Namen
   - Verbinde alle Elemente in sinnvoller Reihenfolge (step_order)
   - Der letzte Step sollte auf das `<bpmn:endEvent>` zeigen

8. **XML-Escaping** (PFLICHT):
   - `<` -> `&lt;`
   - `>` -> `&gt;`
   - `&` -> `&amp;`
   - `"` -> `&quot;` (in Attributen)
   - `' (Apostroph)` -> `&apos;` (in Attributen)

9. **Vollstaendigkeit**: Jeder Step MUSS als Task im XML erscheinen. Jeder Task MUSS eine SequenceFlow-Verbindung haben (Eingang oder Ausgang oder beides). Keine "verwaisten" Elemente.

10. **Keine Kommentare** im XML (bpmn-js kann sie nicht parsen).

11. **VOLLSTAENDIGKEIT IST PFLICHT**: Das XML MUSS mit `</bpmn:definitions>` enden. NIEMALS mitten im Element aufhoeren! Wenn du merkst, dass der Text knapp wird, schliesse zuerst alle offenen SubProcesses/Tasks/Edges und beende dann mit `</bpmn:process>` und `</bpmn:definitions>`. Lieber weniger Schritte vollstaendig als viele halb!"""

    # User-Prompt: SOP-Kontext + alle Step-Beschreibungen
    user_lines = [
        f"## SOP-Metadaten",
        f"- **ID:** {sop_data.get('id', '?')}",
        f"- **Name:** {sop_data.get('name', '?')}",
        f"- **Beschreibung (Freitext):**",
        (sop_data.get('description') or '(keine)').strip() or '(keine)',
        "",
        "## SOP-Steps (in Reihenfolge mit Beschreibungen):",
    ]
    steps = sop_data.get("steps", [])
    if not steps:
        user_lines.append("(keine Steps vorhanden)")
    else:
        for i, s in enumerate(steps, 1):
            user_lines.append(f"\n### Step {i}: {s.get('name', '?')}")
            user_lines.append(f"- **Phase:** {s.get('phase', '?')}")
            user_lines.append(f"- **Agent:** {s.get('agent') or '(nicht gesetzt)'}")
            user_lines.append(f"- **Trigger:** {s.get('trigger') or '(nicht gesetzt)'}")
            user_lines.append(f"- **Action:** {s.get('action') or '(nicht gesetzt)'}")
            if s.get("description"):
                user_lines.append(f"- **Beschreibung (was passiert hier?):**\n{s['description'].strip()}")
            if s.get("expected_result"):
                user_lines.append(f"- **Erwartetes Ergebnis:**\n{s['expected_result'].strip()}")

    user_lines.extend([
        "",
        "---",
        "",
        "Generiere jetzt das vollstaendige BPMN-2.0-XML. Antworte NUR mit dem XML, ohne zusaetzlichen Text.",
    ])

    user_prompt = "\n".join(user_lines)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    return messages, user_prompt
