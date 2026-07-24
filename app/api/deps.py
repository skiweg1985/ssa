"""Gemeinsame FastAPI-Dependencies (Auth)"""
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.services.security import verify_token

_bearer_scheme = HTTPBearer(auto_error=False)

# Pfade, die statische API-Tokens (Monitoring, z.B. PRTG) lesen dürfen.
# Ausschließlich GET; Verwaltung (Jobs/Verbindungen/Tokens) bleibt dem Login vorbehalten.
API_TOKEN_ALLOWED_PREFIXES = (
    "/api/scans",
    "/api/storage/stats",
)


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=401,
        detail="Nicht angemeldet oder Sitzung abgelaufen",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def require_auth(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
) -> str:
    """
    Erzwingt gültige Authentifizierung. Liefert den Benutzernamen.

    Akzeptiert:
    1. Login-Tokens (HMAC-signiert) - voller Zugriff
    2. Statische API-Tokens (Frontend-verwaltet) - NUR GET auf
       Monitoring-Endpoints (Scans/Status/Ergebnisse, Storage-Stats)

    Raises:
        HTTPException 401 bei fehlendem/ungültigem Token,
        HTTPException 403 wenn ein API-Token außerhalb seines
        Read-only-Umfangs verwendet wird
    """
    if credentials is None or not credentials.credentials:
        raise _unauthorized()

    token = credentials.credentials

    # 1. Login-Token (voller Zugriff)
    username = verify_token(token)
    if username is not None:
        return username

    # 2. Statisches API-Token (read-only, Pfad-Whitelist)
    #    Lazy-Import, um Zyklen beim App-Start zu vermeiden
    from app.services.jobs_store import jobs_store

    token_info = jobs_store.verify_api_token(token)
    if token_info is not None:
        path = request.url.path
        if request.method != "GET" or not path.startswith(
            API_TOKEN_ALLOWED_PREFIXES
        ):
            raise HTTPException(
                status_code=403,
                detail=(
                    "API-Token erlaubt nur Lesezugriff auf "
                    "Scan-Status/Ergebnisse und Storage-Statistiken"
                ),
            )
        return f"api-token:{token_info['name']}"

    raise _unauthorized()
