"""Credential-Pricing-Service — Ermittelt Kosten per KI und speichert sie.

User-Direktive 20.06.2026: API-Key-Einträge zeigen Kosten für 1 Mio Token
(Input/Output) an. Ein Refresh-Button lässt die KI aktuelle Preise suchen
und alles auf 1 Mio Token umrechnen.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Dict, Any, Optional

from sqlalchemy.orm import Session

from ..models.provider_credential import ProviderCredential
from ..models.pricing import ModelPricing
from .llm_service import chat_completion
from .pricing_service import get_current_pricing

logger = logging.getLogger("pi-dashboard-2.credential-pricing")


_PROMPT_TEMPLATE = """Gib die aktuellen API-Preise für das Modell "{provider}/{model}" an.

Antworte ausschließlich mit diesem JSON-Format (Werte in USD pro 1 Million Tokens):
{{
  "input_per_1m": <zahl>,
  "output_per_1m": <zahl>
}}

Wenn du den genauen Preis nicht kennst, schätze ihn auf Basis des Providers/Modells.
Beispiele:
- ollama/lokale Modelle: 0.0 / 0.0
- minimax-m3: ~0.30 / ~1.20
- openai/gpt-4o: ~2.50 / ~10.00
- deepseek-chat: ~0.14 / ~0.28
"""


def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    """Versucht, ein JSON-Objekt aus dem LLM-Output zu extrahieren."""
    # 1) Direktes JSON-Parsing
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 2) JSON-Block aus Markdown ```json ... ```
    match = re.search(r"```(?:json)?\s*({.*?})\s*```", text, re.DOTALL | re.IGNORECASE)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # 3) Erstes { ... } Objekt im Text
    match = re.search(r"({.*?})", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    return None


def _to_decimal(value: Any) -> Optional[Decimal]:
    """Konvertiert einen Wert sicher zu Decimal."""
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


async def refresh_credential_pricing(
    db: Session,
    credential_id: str,
    force_provider: Optional[str] = None,
    force_model: Optional[str] = None,
) -> Dict[str, Any]:
    """Ermittelt aktuelle Preise für ein Credential per KI und speichert sie.

    Args:
        db: SQLAlchemy Session
        credential_id: ID der ProviderCredential
        force_provider: Optional Provider-Override (für Tests)
        force_model: Optional Modell-Override (für Tests)

    Returns:
        dict mit ok, input_cost_per_1m, output_cost_per_1m, source
    """
    credential = db.get(ProviderCredential, credential_id)
    if not credential:
        raise ValueError(f"ProviderCredential '{credential_id}' nicht gefunden")

    provider = force_provider or credential.provider
    model = force_model or credential.model

    prompt = _PROMPT_TEMPLATE.format(provider=provider, model=model)

    input_cost: Optional[Decimal] = None
    output_cost: Optional[Decimal] = None
    source = "llm_refresh"

    try:
        response = await chat_completion(
            messages=[
                {"role": "system", "content": "Du bist ein Preis-Recherche-Assistent für LLM-APIs."},
                {"role": "user", "content": prompt},
            ],
            model="minimax-m3",
            temperature=0.1,
            max_tokens=500,
            role=None,
        )
        raw_content = response.get("content", "")
        data = _extract_json(raw_content)
        if data:
            input_cost = _to_decimal(data.get("input_per_1m"))
            output_cost = _to_decimal(data.get("output_per_1m"))
        if input_cost is None or output_cost is None:
            logger.warning(f"KI-Antwort enthielt keine gültigen Preise für {provider}/{model}; nutze Fallback")
    except Exception as e:
        logger.warning(f"LLM-Preisermittlung fehlgeschlagen für {provider}/{model}: {e}; nutze Fallback")

    # Fallback auf bekannte/statische Preise, wenn KI nicht verfügbar oder keine Daten liefert
    if input_cost is None or output_cost is None:
        pricing = get_current_pricing(f"{provider}/{model}", db)
        input_cost = _to_decimal(pricing.get("input_per_1m"))
        output_cost = _to_decimal(pricing.get("output_per_1m"))
        if input_cost is None or output_cost is None:
            raise RuntimeError("Keine Preisdaten verfügbar (KI temporär blockiert und kein Fallback bekannt)")
        source = pricing.get("source", "static_fallback")

    # Credential aktualisieren
    credential.input_cost_per_1m = input_cost
    credential.output_cost_per_1m = output_cost

    # Auch in ModelPricing persistieren
    _upsert_model_pricing(db, provider, model, input_cost, output_cost)

    db.commit()
    db.refresh(credential)

    logger.info(f"Preise aktualisiert für {provider}/{model}: in={input_cost}, out={output_cost} (source={source})")

    return {
        "ok": True,
        "credential_id": credential_id,
        "provider": provider,
        "model": model,
        "input_cost_per_1m": str(input_cost),
        "output_cost_per_1m": str(output_cost),
        "source": source,
        "refreshed_at": datetime.utcnow().isoformat(),
    }


def _upsert_model_pricing(
    db: Session,
    provider: str,
    model: str,
    input_cost: Decimal,
    output_cost: Decimal,
) -> None:
    """Speichert / aktualisiert den Preis in der ModelPricing-Tabelle."""
    from sqlalchemy import select

    row = db.execute(
        select(ModelPricing).where(
            ModelPricing.provider == provider,
            ModelPricing.model_id == model,
        )
    ).scalar_one_or_none()

    now = datetime.utcnow()
    if row is None:
        row = ModelPricing(
            provider=provider,
            model_id=model,
            input_per_1m=input_cost,
            output_per_1m=output_cost,
            currency="USD",
            source="llm_refresh",
            last_updated=now,
            is_default=False,
        )
        db.add(row)
    else:
        row.input_per_1m = input_cost
        row.output_per_1m = output_cost
        row.source = "llm_refresh"
        row.last_updated = now
