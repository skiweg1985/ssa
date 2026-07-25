"""Generische Metrik-Endpoints je NAS-System (JSON).

Bewusst unter /api/nas-metrics und NICHT unter /api/nas: die Whitelist für
Monitoring-Tokens in app/api/deps.py prüft per startswith, und ein Prefix
"/api/nas" würde auch /api/nas-connections freischalten - also die
Verbindungsverwaltung.

Für PRTG gibt es eigene Endpoints unter /api/prtg/nas/... Dieser hier ist
für Grafana, das eigene Frontend und alles, was rohes JSON verarbeitet.
"""
import asyncio
import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query

from app.models.nas_metrics import NASMetrics
from app.services.jobs_store import jobs_store
from app.services.nas_metrics import collect_metrics

logger = logging.getLogger(__name__)

router = APIRouter()

VALID_GROUPS = {"capacity", "health"}


def _parse_groups(groups: Optional[str]) -> Optional[List[str]]:
    """'capacity,health' -> ['capacity', 'health']; None = alle"""
    if not groups:
        return None
    parsed = [group.strip() for group in groups.split(",") if group.strip()]
    unknown = [group for group in parsed if group not in VALID_GROUPS]
    if unknown:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Unbekannte Gruppe(n): {', '.join(unknown)}. "
                f"Erlaubt: {', '.join(sorted(VALID_GROUPS))}"
            ),
        )
    return parsed or None


@router.get("", response_model=List[NASMetrics])
async def list_nas_metrics(
    connection_id: Optional[int] = Query(
        None, description="Nur dieses System abfragen"
    ),
    groups: Optional[str] = Query(
        None, description="Kommasepariert: capacity, health (Default: beide)"
    ),
):
    """
    Metriken aller NAS-Systeme, optional gefiltert.

    Die Systeme werden parallel abgefragt - sonst summieren sich die
    Netzwerk-Wartezeiten bei mehreren NAS.
    """
    wanted_groups = _parse_groups(groups)
    connections = jobs_store.list_connections()
    if connection_id is not None:
        connections = [c for c in connections if c["id"] == connection_id]
        if not connections:
            raise HTTPException(
                status_code=404,
                detail=f"NAS-Verbindung {connection_id} nicht gefunden",
            )

    return await asyncio.gather(
        *(collect_metrics(connection, wanted_groups) for connection in connections)
    )


@router.get("/{connection_identifier}", response_model=NASMetrics)
async def get_nas_metrics(
    connection_identifier: str,
    groups: Optional[str] = Query(
        None, description="Kommasepariert: capacity, health (Default: beide)"
    ),
):
    """Metriken eines Systems - Identifikation per ID oder Verbindungsname"""
    wanted_groups = _parse_groups(groups)
    connection = jobs_store.get_connection_by_identifier(connection_identifier)
    if connection is None:
        raise HTTPException(
            status_code=404,
            detail=f"NAS-Verbindung '{connection_identifier}' nicht gefunden",
        )
    return await collect_metrics(connection, wanted_groups)
