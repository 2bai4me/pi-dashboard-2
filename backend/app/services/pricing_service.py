"""PricingService â€” Verwaltet Provider-Preise + Task-Snapshots.



Kern-Prinzip (User-Direktive 15.06.2026):

- Beim Task-Start wird ein pricing_snapshot im Task gespeichert.

- Cost-Berechnung nutzt IMMER den Snapshot, nicht den aktuellen Preis.

- So bleiben abgeschlossene Tasks unabhaengig von Provider-Preisaenderungen.

"""

from __future__ import annotations



from datetime import datetime

from decimal import Decimal

from pathlib import Path

from typing import Optional, Dict, Any

import json

import logging



from sqlalchemy import select

from sqlalchemy.orm import Session



from ..config import settings

from ..models.pricing import ModelPricing

from ..models.task import Task

from ..models.token_usage import TokenUsage

from ..models.history import TaskHistory



logger = logging.getLogger("pi-dashboard-2")





# Statische Preisdatenbank (USD pro 1M-Token, Stand 16.06.2026).

# Quelle: https://platform.minimax.io/docs/guides/pricing-paygo (50% off launch promo)

KNOWN_PRICING: Dict[str, Dict[str, Any]] = {

    # === Ollama (Lokale Models - Kostenlos) ===

    "ollama/qwen3:8b":            {"input_per_1m": "0",    "output_per_1m": "0"},

    "ollama/qwen3:4b":            {"input_per_1m": "0",    "output_per_1m": "0"},

    "ollama/gemma3:12b":          {"input_per_1m": "0",    "output_per_1m": "0"},

    "ollama/phi4:latest":         {"input_per_1m": "0",    "output_per_1m": "0"},

    "ollama/gemma3:8b":           {"input_per_1m": "0",    "output_per_1m": "0"},

    # === MiniMax ===

    "minimax-direct/minimax-m3":   {"input_per_1m": "0.30", "output_per_1m": "1.20"},

    "minimax-direct/minimax-m2.7": {"input_per_1m": "0.30", "output_per_1m": "1.20"},

    "minimax-direct/minimax-m2.5": {"input_per_1m": "0.15", "output_per_1m": "1.08"},

    # === OpenRouter ===

    "openrouter/anthropic/claude-sonnet-4": {"input_per_1m": "3.00", "output_per_1m": "15.00"},

    "openrouter/minimax/minimax-m3":        {"input_per_1m": "0.30", "output_per_1m": "1.20"},

    # === DeepSeek (Schätzwerte als Fallback bis KI-Refresh verfügbar) ===

    "deepseek/deepseek-chat":      {"input_per_1m": "0.14", "output_per_1m": "0.28"},

    "deepseek/deepseek-4-pro":     {"input_per_1m": "0.50", "output_per_1m": "2.00"},

    "deepseek/deepseek-4-fast":    {"input_per_1m": "0.10", "output_per_1m": "0.40"},

    "deepseek/default":            {"input_per_1m": "0.14", "output_per_1m": "0.28"},

}



PROVIDER_ALIAS = {"minimax": "minimax-direct"}





def get_current_pricing(model_id: str, db: Optional[Session] = None) -> Dict[str, Any]:

    """Holt aktuellen Provider-Preis (USD/Token) fuer ein Modell.



    Lookup-Reihenfolge:

    1. SQL model_pricing-Tabelle (manuell editierbar, hat last_updated)

    2. Statische KNOWN_PRICING-DB (Fallback)



    Args:

        model_id: z.B. "minimax/minimax-m3" oder "minimax-direct/minimax-m3"

        db: Optional DB-Session (sonst wird Lookup uebersprungen)



    Returns:

        Dict mit input/output (USD/Token), input_per_1m/output_per_1m,

        provider, source, last_updated, note.

    """

    if not model_id:

        return {"input": Decimal("0"), "output": Decimal("0"), "source": "unknown"}



    # 1) SQL Lookup (falls DB-Session vorhanden)

    if db is not None:

        if "/" in model_id:

            prov_part, rest = model_id.split("/", 1)

            real_prov = PROVIDER_ALIAS.get(prov_part, prov_part)

            # Exakter Match

            row = db.execute(

                select(ModelPricing).where(

                    ModelPricing.provider == real_prov,

                    ModelPricing.model_id == rest,

                )

            ).scalar_one_or_none()

            if not row:

                # Letzter Modell-Teil (z.B. "claude-sonnet-4" aus "openrouter/anthropic/claude-sonnet-4")

                last = rest.split("/")[-1]

                row = db.execute(

                    select(ModelPricing).where(

                        ModelPricing.provider == real_prov,

                        ModelPricing.model_id == last,

                    )

                ).scalar_one_or_none()

            if not row:

                # Provider-Default

                row = db.execute(

                    select(ModelPricing).where(

                        ModelPricing.provider == real_prov,

                        ModelPricing.model_id == "default",

                        ModelPricing.is_default == True,

                    )

                ).scalar_one_or_none()

            if row:

                return {

                    "input":  Decimal(str(row.input_per_1m)) / Decimal("1000000"),

                    "output": Decimal(str(row.output_per_1m)) / Decimal("1000000"),

                    "input_per_1m":  Decimal(str(row.input_per_1m)),

                    "output_per_1m": Decimal(str(row.output_per_1m)),

                    "provider":       real_prov,

                    "source":         row.source or "db",

                    "last_updated":   row.last_updated.isoformat() if row.last_updated else None,

                    "note":           row.note or "",

                }



    # 2) Statische DB

    if "/" in model_id:

        prov_part, rest = model_id.split("/", 1)

        real_prov = PROVIDER_ALIAS.get(prov_part, prov_part)

        # Versuche vollqualifiziert

        for key in [

            model_id,

            f"{real_prov}/{rest}",

            f"{real_prov}/{rest.split('/')[-1]}",

        ]:

            if key in KNOWN_PRICING:

                ref = KNOWN_PRICING[key]

                return {

                    "input":  Decimal(ref["input_per_1m"]) / Decimal("1000000"),

                    "output": Decimal(ref["output_per_1m"]) / Decimal("1000000"),

                    "input_per_1m":  Decimal(ref["input_per_1m"]),

                    "output_per_1m": Decimal(ref["output_per_1m"]),

                    "provider": real_prov,

                    "source":  "static_fallback",

                }

        # Provider-Default als letzter statischer Fallback

        default_key = f"{real_prov}/default"

        if default_key in KNOWN_PRICING:

            ref = KNOWN_PRICING[default_key]

            return {

                "input":  Decimal(ref["input_per_1m"]) / Decimal("1000000"),

                "output": Decimal(ref["output_per_1m"]) / Decimal("1000000"),

                "input_per_1m":  Decimal(ref["input_per_1m"]),

                "output_per_1m": Decimal(ref["output_per_1m"]),

                "provider": real_prov,

                "source":  "static_fallback_default",

            }

    return {

        "input":  Decimal("0"),

        "output": Decimal("0"),

        "provider": model_id.split("/")[0] if "/" in model_id else model_id,

        "source":  "unknown",

    }





def take_pricing_snapshot(task: Task, model_id: Optional[str] = None, db: Optional[Session] = None) -> Dict[str, Any]:

    """Speichert aktuellen Provider-Preis im Task.



    Wird aufgerufen bei auto_claim, emergency_watchdog, und erstem dispatch.

    So wird der Preis FIXIERT, mit dem der Task abgerechnet wird - auch

    wenn sich Provider-Preise spaeter aendern.

    """

    if not model_id:

        # Default-Modell: minimax/minimax-m3 (CIO-Standard, User-Direktive 15.06.2026)

        model_id = "minimax/minimax-m3"

    pricing = get_current_pricing(model_id, db)

    snap = {

        "model":         model_id,

        "provider":      pricing.get("provider", model_id.split("/")[0] if "/" in model_id else "unknown"),

        "input_per_1m":  str(pricing.get("input_per_1m", Decimal("0"))),

        "output_per_1m": str(pricing.get("output_per_1m", Decimal("0"))),

        "snapshot_at":   datetime.utcnow().isoformat(),

        "source":        pricing.get("source", "fallback"),

        "note":          pricing.get("note", ""),

    }

    task.pricing_snapshot = snap

    return snap





def calc_cost_from_snapshot(tokens_in: int, tokens_out: int, snap: Optional[Dict[str, Any]]) -> Decimal:

    """Berechnet USD-Kosten basierend auf Task-Snapshot (NICHT aktuellem Preis)."""

    if not snap:

        return Decimal("0")

    in_per_t  = Decimal(str(snap.get("input_per_1m", "0")))  / Decimal("1000000")

    out_per_t = Decimal(str(snap.get("output_per_1m", "0"))) / Decimal("1000000")

    return Decimal(tokens_in) * in_per_t + Decimal(tokens_out) * out_per_t





class PricingService:

    """Service-Klasse fuer Pricing-Operationen."""



    @staticmethod

    def refresh_all(db: Session) -> Dict[str, Any]:

        """Aktualisiert ALLE Provider-Preise aus KNOWN_PRICING."""

        now = datetime.utcnow()

        updated, skipped = [], []

        for full_id, ref in KNOWN_PRICING.items():

            if "/" not in full_id:

                continue

            prov_part, model_key = full_id.split("/", 1)

            real_prov = PROVIDER_ALIAS.get(prov_part, prov_part)

            row = db.execute(

                select(ModelPricing).where(

                    ModelPricing.provider == real_prov,

                    ModelPricing.model_id == model_key,

                )

            ).scalar_one_or_none()

            if row is None:

                row = ModelPricing(

                    provider=real_prov, model_id=model_key,

                    input_per_1m=Decimal(ref["input_per_1m"]),

                    output_per_1m=Decimal(ref["output_per_1m"]),

                    currency="USD", source=ref.get("source", "static"),

                    last_updated=now, is_default=False,

                )

                db.add(row)

            else:

                row.input_per_1m  = Decimal(ref["input_per_1m"])

                row.output_per_1m = Decimal(ref["output_per_1m"])

                row.source        = ref.get("source", "static")

                row.last_updated  = now

            updated.append({"provider": real_prov, "model": model_key,

                            "input_per_1m": str(ref["input_per_1m"]),

                            "output_per_1m": str(ref["output_per_1m"])})

        db.commit()

        return {

            "ok": True,

            "updated_count": len(updated),

            "skipped_count": len(skipped),

            "updated": updated,

            "skipped": skipped,

            "refreshed_at": now.isoformat(),

        }

