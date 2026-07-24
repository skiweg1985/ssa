"""Auth-Endpoints: Login und Token-Validierung"""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.deps import require_auth
from app.services.rate_limit import client_key, login_rate_limiter
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
async def login(request: LoginRequest, http_request: Request):
    """
    Anmeldung mit Benutzername + Passwort (aus der Server-Umgebung).

    Liefert ein Bearer-Token für alle weiteren API-Aufrufe.
    Fehlversuche sind pro Client-IP begrenzt (Brute-Force-Schutz).
    """
    key = client_key(http_request)

    allowed, retry_after = login_rate_limiter.check(key)
    if not allowed:
        logger.warning(f"Login-Versuch waehrend aktiver Sperre von {key} abgewiesen")
        raise HTTPException(
            status_code=429,
            detail=(
                "Zu viele fehlgeschlagene Anmeldeversuche. "
                f"Bitte in {retry_after} Sekunden erneut versuchen."
            ),
            headers={"Retry-After": str(retry_after)},
        )

    if not admin_password_configured():
        raise HTTPException(
            status_code=503,
            detail=(
                "Server-Passwort nicht konfiguriert (SSA_ADMIN_PASSWORD). "
                "Bitte die Umgebungsvariable setzen und den Server neu starten."
            ),
        )
    if not verify_admin(request.username, request.password):
        blocked, duration = login_rate_limiter.register_failure(key)
        logger.warning(f"Fehlgeschlagener Login von {key}")
        if blocked:
            raise HTTPException(
                status_code=429,
                detail=(
                    "Zu viele fehlgeschlagene Anmeldeversuche. "
                    f"Bitte in {duration} Sekunden erneut versuchen."
                ),
                headers={"Retry-After": str(duration)},
            )
        raise HTTPException(
            status_code=401,
            detail="Benutzername oder Passwort falsch",
        )

    # Erfolg: Zaehler zuruecksetzen, damit legitime Nutzer nie ausgesperrt werden
    login_rate_limiter.register_success(key)

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
