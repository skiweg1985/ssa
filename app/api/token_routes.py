"""API-Routes für die Verwaltung statischer API-Tokens (Monitoring-Zugriff).

Nur per Login-Token erreichbar - API-Tokens selbst haben hier keinen Zugriff
(der Pfad steht nicht in der API_TOKEN_ALLOWED_PREFIXES-Whitelist).
"""
import logging

from fastapi import APIRouter, HTTPException

from app.models.admin import (
    ApiTokenCreated,
    ApiTokenCreateRequest,
    ApiTokenPublic,
)
from app.services.jobs_store import NotFoundError, jobs_store

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("", response_model=list[ApiTokenPublic])
async def list_api_tokens():
    """Alle API-Tokens (nur Metadaten - der Token selbst ist nie abrufbar)"""
    return jobs_store.list_api_tokens()


@router.post("", response_model=ApiTokenCreated, status_code=201)
async def create_api_token(request: ApiTokenCreateRequest):
    """
    Erzeugt ein neues API-Token.

    Der Klartext-Token ist NUR in dieser Response enthalten -
    danach ist er nicht mehr abrufbar (es wird nur der Hash gespeichert).
    """
    try:
        return jobs_store.create_api_token(request.name.strip())
    except Exception as e:
        if "UNIQUE constraint failed" in str(e):
            raise HTTPException(
                status_code=409,
                detail=f"Ein API-Token mit dem Namen '{request.name}' existiert bereits",
            )
        raise


@router.delete("/{token_id}", status_code=204)
async def delete_api_token(token_id: int):
    """Widerruft ein API-Token (sofort wirksam)"""
    try:
        jobs_store.delete_api_token(token_id)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
