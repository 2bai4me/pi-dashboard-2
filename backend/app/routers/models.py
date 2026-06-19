"""Models + Pricing Router (Providers, Modelle, Preise)."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional, List, Dict, Any
from pathlib import Path
import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from pydantic import BaseModel

from ..db.base import get_db
from ..auth import require_auth
from ..config import settings, get_models_json_path, get_auth_json_path, get_settings_json_path
from ..models.pricing import ModelPricing
from ..schemas.pricing import (
    ModelPricingRead, PricingUpdateRequest, PricingRefreshResult,
    ModelInfo, ProviderInfo,
)
from ..services.pricing_service import PricingService

logger = logging.getLogger("pi-dashboard-2")
router = APIRouter(prefix="/api/models", tags=["models"])


# === Helpers ===
def _read_models_json() -> Dict[str, Any]:
    """Liest models.json (Provider + Modelle, ohne Preise)."""
    p = get_models_json_path()
    if not p.exists():
        return {"providers": {}}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        logger.error(f"models.json read failed: {e}")
        return {"providers": {}}


@router.get("/providers", response_model=List[ProviderInfo])
async def list_providers(
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    cfg = _read_models_json()
    auth = {}
    auth_path = get_auth_json_path()
    if auth_path.exists():
        try:
            auth = json.loads(auth_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    out = []
    for name, prov in (cfg.get("providers") or {}).items():
        has_key = bool(prov.get("apiKey")) or bool(prov.get("authHeader"))
        if isinstance(auth, dict) and name in auth:
            has_key = has_key or bool(auth[name])
        out.append(ProviderInfo(
            name=name, api=prov.get("api"), base_url=prov.get("baseUrl"),
            model_count=len(prov.get("models") or []),
            has_key=has_key, has_pricing=bool(prov.get("pricing")),
        ))
    return out


@router.get("", response_model=List[ModelInfo])
async def list_models(
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    cfg = _read_models_json()
    s = get_settings_json_path()
    settings_data = {}
    if s.exists():
        try:
            settings_data = json.loads(s.read_text(encoding="utf-8"))
        except Exception:
            pass
    enabled = set(settings_data.get("enabledModels", []) or [])
    default = settings_data.get("defaultModel", "")

    # SQL-Pricing (Quelle der Wahrheit in v2.0)
    pricing_rows = {
        (r.provider, r.model_id): r
        for r in db.execute(select(ModelPricing)).scalars()
    }

    out: List[ModelInfo] = []
    for prov_name, prov in (cfg.get("providers") or {}).items():
        for m in prov.get("models", []) or []:
            full_id = f"{prov_name}/{m['id']}"
            p = pricing_rows.get((prov_name, m["id"])) or pricing_rows.get((prov_name, "default"))
            out.append(ModelInfo(
                id=m["id"], provider=prov_name, full_id=full_id,
                input_per_1m=Decimal(str(p.input_per_1m)) if p else None,
                output_per_1m=Decimal(str(p.output_per_1m)) if p else None,
                price_source=p.source if p else None,
                price_last_updated=p.last_updated if p else None,
                context_window=m.get("contextWindow"),
                reasoning=m.get("reasoning"),
                enabled=full_id in enabled,
                is_default=(full_id == default),
            ))
    return out


# === Pricing ===
@router.get("/pricing", response_model=Dict[str, Dict[str, ModelPricingRead]])
async def get_pricing(
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    """Aktuelle Provider-Preise aus der SQL-DB."""
    rows = db.execute(select(ModelPricing).order_by(ModelPricing.provider, ModelPricing.model_id)).scalars()
    out: Dict[str, Dict[str, ModelPricingRead]] = {}
    for r in rows:
        out.setdefault(r.provider, {})[r.model_id] = ModelPricingRead.model_validate(r)
    return out


@router.post("/pricing/refresh", response_model=PricingRefreshResult)
async def refresh_pricing(
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    """Aktualisiert alle Provider-Preise aus der statischen Preisdatenbank."""
    result = PricingService.refresh_all(db)
    return PricingRefreshResult(**result)


@router.post("/pricing/update", response_model=ModelPricingRead)
async def update_pricing(
    req: PricingUpdateRequest,
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    """Manuelles Override pro Provider/Modell."""
    key = req.model_id or "default"
    row = db.execute(
        select(ModelPricing).where(
            ModelPricing.provider == req.provider,
            ModelPricing.model_id == key,
        )
    ).scalar_one_or_none()
    if row is None:
        row = ModelPricing(
            provider=req.provider, model_id=key,
            input_per_1m=req.input_per_1m, output_per_1m=req.output_per_1m,
            currency="USD", source="manual",
            last_updated=datetime.utcnow(), is_default=(key == "default"),
        )
        db.add(row)
    else:
        row.input_per_1m = req.input_per_1m
        row.output_per_1m = req.output_per_1m
        row.source = "manual"
        row.last_updated = datetime.utcnow()
    if req.note:
        row.note = req.note
    db.commit()
    db.refresh(row)
    return ModelPricingRead.model_validate(row)
