"""Auth-Endpoints: Login und Token-Validierung"""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import require_auth
from app.models.admin import LoginRequest, LoginResponse, MeResponse
from app.services.security import (
    admin_password_configured,
    create_token,
    get_token_expiry,
    verify_admin,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest):
    """
    Anmeldung mit Benutzername + Passwort (aus der Server-Umgebung).

    Liefert ein Bearer-Token für alle weiteren API-Aufrufe.
    """
    if not admin_password_configured():
        raise HTTPException(
            status_code=503,
            detail=(
                "Server-Passwort nicht konfiguriert (SSA_ADMIN_PASSWORD). "
                "Bitte die Umgebungsvariable setzen und den Server neu starten."
            ),
        )
    if not verify_admin(request.username, request.password):
        raise HTTPException(
            status_code=401,
            detail="Benutzername oder Passwort falsch",
        )

    token = create_token(request.username)
    expiry = get_token_expiry(token)
    expires_at = (
        datetime.fromtimestamp(expiry, tz=timezone.utc).isoformat()
        if expiry
        else ""
    )
    logger.info(f"Login erfolgreich: {request.username}")
    return LoginResponse(
        token=token, username=request.username, expires_at=expires_at
    )


@router.get("/me", response_model=MeResponse)
async def me(username: str = Depends(require_auth)):
    """Validiert das aktuelle Token (für den Frontend-Boot)"""
    return MeResponse(username=username)
