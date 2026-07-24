"""Gemeinsame FastAPI-Dependencies (Auth)"""
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.services.security import verify_token

_bearer_scheme = HTTPBearer(auto_error=False)


async def require_auth(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
) -> str:
    """
    Erzwingt ein gültiges Bearer-Token. Liefert den Benutzernamen.

    Raises:
        HTTPException 401 bei fehlendem/ungültigem/abgelaufenem Token
    """
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=401,
            detail="Nicht angemeldet oder Sitzung abgelaufen",
            headers={"WWW-Authenticate": "Bearer"},
        )
    username = verify_token(credentials.credentials)
    if username is None:
        raise HTTPException(
            status_code=401,
            detail="Nicht angemeldet oder Sitzung abgelaufen",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return username
