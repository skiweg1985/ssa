"""Pydantic-Modelle für Auth, NAS-Verbindungen und Scan-Job-Verwaltung"""
from typing import List, Optional

from pydantic import BaseModel, Field


# ----------------------------------------------------------------------
# Auth
# ----------------------------------------------------------------------

class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    username: str
    expires_at: str  # ISO 8601


class MeResponse(BaseModel):
    username: str


# ----------------------------------------------------------------------
# NAS-Verbindungen
# ----------------------------------------------------------------------

class NASConnectionCreate(BaseModel):
    name: str = Field(min_length=1)
    host: str = Field(min_length=1)
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)
    port: Optional[int] = None
    use_https: bool = True
    verify_ssl: bool = True


class NASConnectionUpdate(BaseModel):
    name: str = Field(min_length=1)
    host: str = Field(min_length=1)
    username: str = Field(min_length=1)
    # Leer/None = gespeichertes Passwort behalten
    password: Optional[str] = None
    port: Optional[int] = None
    use_https: bool = True
    verify_ssl: bool = True


class NASConnectionPublic(BaseModel):
    id: int
    name: str
    host: str
    port: Optional[int] = None
    use_https: bool
    verify_ssl: bool
    username: str
    job_count: int = 0
    created_at: str
    updated_at: str


class TestConnectionRequest(BaseModel):
    """Verbindungstest: entweder id (gespeicherte Creds) oder Inline-Felder.

    Inline mit leerem Passwort + gesetzter id => gespeichertes Passwort verwenden
    (damit die Edit-Form ohne Neueingabe testen kann).
    """
    id: Optional[int] = None
    host: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    port: Optional[int] = None
    use_https: bool = True
    verify_ssl: bool = True


class TestConnectionResponse(BaseModel):
    success: bool
    message: str


class BrowseRequest(BaseModel):
    path: Optional[str] = None


class BrowseEntry(BaseModel):
    name: str
    path: str
    is_dir: bool = True


class BrowseResponse(BaseModel):
    path: Optional[str] = None
    entries: List[BrowseEntry]


# ----------------------------------------------------------------------
# API-Tokens (Monitoring)
# ----------------------------------------------------------------------

class ApiTokenCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class ApiTokenPublic(BaseModel):
    id: int
    name: str
    created_at: str
    last_used_at: Optional[str] = None


class ApiTokenCreated(ApiTokenPublic):
    """Nur bei der Erstellung: enthält einmalig den Klartext-Token"""
    token: str


# ----------------------------------------------------------------------
# Scan-Jobs
# ----------------------------------------------------------------------

class ScanJobCreate(BaseModel):
    name: str = Field(min_length=1)
    nas_connection_id: int
    interval: str = Field(min_length=1)
    enabled: bool = True
    paths: Optional[List[str]] = None
    shares: Optional[List[str]] = None
    folders: Optional[List[str]] = None


class ScanJobUpdate(ScanJobCreate):
    pass


class ScanJobPublic(BaseModel):
    slug: str
    name: str
    nas_connection_id: int
    interval: str
    enabled: bool
    paths: Optional[List[str]] = None
    shares: Optional[List[str]] = None
    folders: Optional[List[str]] = None
    created_at: str
    updated_at: str
