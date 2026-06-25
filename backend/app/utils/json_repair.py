"""Robuster JSON-Parser mit Auto-Repair (User-Direktive 24.06.2026).

Repariert haeufige LLM-Fehler:
  - Trailing Commas (in Arrays/Objects)
  - Fehlende schliessende Klammern
  - Unescaped Quotes in Strings
  - Markdown-Code-Blocks (```json ... ```)
  - JSON in JSON (extrahiert innerstes Object)
"""
from __future__ import annotations

import json
import re
from typing import Any


def _extract_json_block(text: str) -> str:
    """Extrahiert JSON aus Markdown oder Rohtext."""
    # 1) Markdown-Code-Block
    m = re.search(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", text, re.DOTALL)
    if m:
        return m.group(1)
    # 2) Outer-Match (erstes { bis letztes })
    if "{" in text:
        start = text.find("{")
        end = text.rfind("}")
        if end > start:
            return text[start:end + 1]
    return text


def _repair_json(text: str) -> str:
    """Erste Hilfe: Trailing Commas + fehlende Braces."""
    # Trailing Commas vor } oder ]
    text = re.sub(r",\s*([}\]])", r"\1", text)
    # Fehlendes Top-Level } (z.B. wenn Output abgeschnitten)
    open_braces = text.count("{")
    close_braces = text.count("}")
    if open_braces > close_braces:
        text += "}" * (open_braces - close_braces)
    open_brackets = text.count("[")
    close_brackets = text.count("]")
    if open_brackets > close_brackets:
        text += "]" * (open_brackets - close_brackets)
    return text


def safe_json_loads(text: str, default: Any = None) -> Any:
    """Versucht JSON zu parsen, repariert dabei haeufige Fehler."""
    if not text:
        return default or {}
    text = text.strip()
    if not text:
        return default or {}
    # Versuche direkt
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        pass
    # Extrahiere Block
    candidate = _extract_json_block(text)
    # Repair
    repaired = _repair_json(candidate)
    try:
        return json.loads(repaired)
    except (json.JSONDecodeError, ValueError):
        # Letzter Versuch: ersetze Single-Quotes mit Double-Quotes (nur in JSON-Werten)
        if "'" in repaired and '"' not in repaired:
            try:
                return json.loads(repaired.replace("'", '"'))
            except (json.JSONDecodeError, ValueError):
                pass
    return default or {}