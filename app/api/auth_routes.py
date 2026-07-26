"""Auth-Endpoints: Ersteinrichtung, Login und Token-Validierung"""
import asyncio
import logging
import os
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.deps import require_auth
from app.services.jobs_store import jobs_store
from app.services.rate_limit import client_key, login_rate_limiter
from app.models.admin import (
    LoginRequest,
    LoginResponse,
    MeResponse,
    SetupRequest,
    SetupStatusResponse,
)
from app.services.security import (
    admin_password_configured,
    create_token,
    get_admin_user,
    get_token_expiry,
    hash_password,
    setup_required,
    verify_admin,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _login_response(username: str) -> LoginResponse:
    """Token + Ablaufzeitpunkt für einen angemeldeten Benutzer"""
    token = create_token(username)
    expiry = get_token_expiry(token)
    expires_at = (
        datetime.fromtimestamp(expiry, tz=timezone.utc).isoformat() if expiry else ""
    )
    return LoginResponse(token=token, username=username, expires_at=expires_at)


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

    if not await asyncio.to_thread(admin_password_configured):
        raise HTTPException(
            status_code=503,
            detail=(
                "Die Ersteinrichtung ist noch nicht abgeschlossen. Bitte die "
                "Startseite aufrufen und das Admin-Konto anlegen (alternativ "
                "SSA_ADMIN_PASSWORD in der Umgebung setzen)."
            ),
        )
    # verify_admin rechnet einen scrypt-Hash (~80 ms CPU) - im Event-Loop würde
    # das jeden parallelen Request so lange blockieren.
    if not await asyncio.to_thread(verify_admin, request.username, request.password):
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

    logger.info(f"Login erfolgreich: {request.username}")
    return _login_response(request.username)


@router.get("/me", response_model=MeResponse)
async def me(username: str = Depends(require_auth)):
    """Validiert das aktuelle Token (für den Frontend-Boot)"""
    return MeResponse(username=username)


@router.get("/setup-status", response_model=SetupStatusResponse)
async def setup_status():
    """
    Sagt dem Frontend beim Boot, ob die Ersteinrichtung noch offen ist.

    Eigener Endpoint statt "Login versuchen und die 503 auswerten": ein
    Fehlversuch würde das Rate-Limit belasten, obwohl niemand etwas falsch
    gemacht hat. Zusätzliches Wissen gibt er nicht preis - die 503-Antwort des
    Logins verrät denselben Zustand.
    """
    required = await asyncio.to_thread(setup_required)
    return SetupStatusResponse(
        setup_required=required,
        username=await asyncio.to_thread(get_admin_user),
        token_required=bool(os.environ.get("SSA_SETUP_TOKEN")),
    )


@router.post("/setup", response_model=LoginResponse)
async def setup(request: SetupRequest, http_request: Request):
    """
    Ersteinrichtung: legt das Admin-Konto an und meldet direkt an.

    Funktioniert genau einmal. Solange sie offen ist, kann jeder das Konto
    beanspruchen, der den Port erreicht - wer den Dienst exponiert, sollte
    SSA_SETUP_TOKEN setzen (dann ist zusätzlich das Token aus der Umgebung
    nötig).

    Antwortet bewusst mit 403/409 statt 401: das Frontend behandelt jede
    401-Antwort ausserhalb des Logins als globalen Logout und würde den
    Setup-Bildschirm abräumen.
    """
    key = f"setup:{client_key(http_request)}"

    allowed, retry_after = login_rate_limiter.check(key)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=(
                "Zu viele Versuche. "
                f"Bitte in {retry_after} Sekunden erneut versuchen."
            ),
            headers={"Retry-After": str(retry_after)},
        )

    expected_token = os.environ.get("SSA_SETUP_TOKEN")
    if expected_token and not secrets.compare_digest(
        (request.setup_token or "").encode("utf-8"), expected_token.encode("utf-8")
    ):
        login_rate_limiter.register_failure(key)
        logger.warning(f"Ersteinrichtung mit falschem Setup-Token abgelehnt ({key})")
        raise HTTPException(status_code=403, detail="Setup-Token fehlt oder ist falsch")

    if await asyncio.to_thread(admin_password_configured):
        raise HTTPException(
            status_code=409, detail="Die Ersteinrichtung ist bereits abgeschlossen."
        )

    password_hash = await asyncio.to_thread(hash_password, request.password)
    # Verbindlich ist allein dieser Rückgabewert. Die Prüfung oben liefert nur
    # den freundlicheren Fehlertext und kann von einem zeitgleichen zweiten
    # Request überholt werden; wer hier verliert, bekommt kein Token.
    created = await asyncio.to_thread(
        jobs_store.create_admin_credentials, request.username, password_hash
    )
    if not created:
        raise HTTPException(
            status_code=409, detail="Die Ersteinrichtung ist bereits abgeschlossen."
        )

    login_rate_limiter.register_success(key)
    logger.warning(
        f"Admin-Konto '{request.username}' per Ersteinrichtung angelegt "
        f"(von {client_key(http_request)})"
    )
    return _login_response(request.username)
