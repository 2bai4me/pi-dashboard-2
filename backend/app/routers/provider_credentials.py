"""Provider Credentials Router — zentrale API-Key-Verwaltung."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

logger = logging.getLogger("pi-dashboard-2.provider-credentials-router")

from ..auth import require_auth
from ..db.base import get_db
from ..models.provider_credential import ProviderCredential
from ..schemas.provider_credential import (
    ProviderCredentialCreate,
    ProviderCredentialListResponse,
    ProviderCredentialRead,
    ProviderCredentialUpdate,
)
from ..services.credential_pricing_service import refresh_credential_pricing

router = APIRouter(prefix="/api/provider-credentials", tags=["provider-credentials"])


@router.get("", response_model=ProviderCredentialListResponse)
async def list_provider_credentials(
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    """Liste aller Provider-Credentials (inkl. inaktiver)."""
    credentials = (
        db.execute(select(ProviderCredential).order_by(ProviderCredential.label))
        .scalars()
        .all()
    )
    items = [ProviderCredentialRead.model_validate(c) for c in credentials]
    return ProviderCredentialListResponse(items=items, total=len(items))


@router.post("", response_model=ProviderCredentialRead, status_code=201)
async def create_provider_credential(
    req: ProviderCredentialCreate,
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    """Neue Credential anlegen."""
    credential = ProviderCredential(**req.model_dump())
    db.add(credential)
    db.commit()
    db.refresh(credential)
    return ProviderCredentialRead.model_validate(credential)


@router.get("/{credential_id}", response_model=ProviderCredentialRead)
async def get_provider_credential(
    credential_id: str,
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    """Einzelne Credential abrufen."""
    credential = db.get(ProviderCredential, credential_id)
    if not credential:
        raise HTTPException(404, "Provider credential not found")
    return ProviderCredentialRead.model_validate(credential)


@router.put("/{credential_id}", response_model=ProviderCredentialRead)
async def update_provider_credential(
    credential_id: str,
    req: ProviderCredentialUpdate,
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    """Credential aktualisieren."""
    credential = db.get(ProviderCredential, credential_id)
    if not credential:
        raise HTTPException(404, "Provider credential not found")

    for field, value in req.model_dump(exclude_unset=True).items():
        setattr(credential, field, value)

    db.commit()
    db.refresh(credential)
    return ProviderCredentialRead.model_validate(credential)


@router.delete("/{credential_id}", status_code=204)
async def delete_provider_credential(
    credential_id: str,
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    """Credential löschen.

    Mappings, die auf diese Credential verweisen, erhalten via ON DELETE SET NULL
    einen NULL-Wert für api_key_id und behalten ihre lokalen Werte bei.
    """
    credential = db.get(ProviderCredential, credential_id)
    if not credential:
        raise HTTPException(404, "Provider credential not found")
    db.delete(credential)
    db.commit()
    return None


@router.post("/{credential_id}/refresh-pricing")
async def refresh_provider_credential_pricing(
    credential_id: str,
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    """Aktualisiert die Kosten (USD pro 1M Token) per KI.

    Die KI ermittelt aktuelle Input-/Output-Preise für das Modell des
    Credentials und speichert sie im Credential sowie in der ModelPricing-Tabelle.
    """
    credential = db.get(ProviderCredential, credential_id)
    if not credential:
        raise HTTPException(404, "Provider credential not found")

    try:
        result = await refresh_credential_pricing(db, credential_id)
    except ValueError as e:
        raise HTTPException(404, str(e))
    except RuntimeError as e:
        raise HTTPException(502, str(e))
    except Exception as e:
        logger.exception("Unerwarteter Fehler bei Preisaktualisierung")
        raise HTTPException(500, f"Preisaktualisierung fehlgeschlagen: {e}")

    return result
