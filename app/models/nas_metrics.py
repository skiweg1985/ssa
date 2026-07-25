"""Pydantic-Modelle für die NAS-Systemmetriken.

Zwei Quellen, bewusst getrennt gehalten:

- `filestation`: Kapazität auf Share-/Volume-Ebene, aus der offiziell
  dokumentierten File Station API (`volume_status` aus `list_share`).
- `snmp`: Systemgesundheit (Temperatur, Platten, RAID, UPS) nach dem
  Synology DiskStation MIB Guide - der einzigen öffentlich dokumentierten
  Schnittstelle für diese Werte.

Jede Quelle trägt ihren eigenen `available`/`error`-Status: ein NAS ohne
SNMP-Zugang liefert weiterhin vollständige Kapazitätsdaten, und ein
Anmeldeproblem an der HTTP-API verdeckt nicht die SNMP-Werte.
"""
from typing import List, Optional

from pydantic import BaseModel


# ----------------------------------------------------------------------
# Kapazität (File Station)
# ----------------------------------------------------------------------

class VolumeMetrics(BaseModel):
    """Ein Volume, aggregiert über alle darauf liegenden Freigaben"""

    name: str
    total_bytes: int
    free_bytes: int
    used_bytes: int
    used_percent: float
    readonly: bool
    share_count: int


class CapacityMetrics(BaseModel):
    volumes: List[VolumeMetrics] = []
    share_count: int = 0
    shares_without_write: int = 0
    virtual_mounts: int = 0
    response_seconds: float = 0.0


# ----------------------------------------------------------------------
# Systemgesundheit (SNMP)
# ----------------------------------------------------------------------

class DiskMetrics(BaseModel):
    name: str
    model: Optional[str] = None
    status: str          # "ok" | "busy" | "error" | "unknown"
    status_label: str    # Klartext aus dem MIB Guide, z.B. "Crashed"
    temperature_celsius: Optional[float] = None


class RaidMetrics(BaseModel):
    """
    Ein Eintrag der RAID-MIB - das kann ein Volume ODER ein Storage Pool sein.

    `used_percent` ist deshalb nicht zum Alarmieren geeignet: bei einem Pool
    zählt SNMP den nicht zugewiesenen Platz als "frei", ein vollständig
    zugewiesener Pool meldet also ~100 %. Für Kapazitätsalarme die Volumes aus
    `CapacityMetrics` verwenden.
    """

    name: str
    status: str          # "ok" | "busy" | "error" | "unknown"
    status_label: str
    total_bytes: Optional[int] = None
    free_bytes: Optional[int] = None
    used_percent: Optional[float] = None


class UpsMetrics(BaseModel):
    status: Optional[str] = None
    battery_charge_percent: Optional[float] = None
    load_percent: Optional[float] = None


class SystemMetrics(BaseModel):
    model_name: Optional[str] = None
    dsm_version: Optional[str] = None
    system_status: Optional[str] = None       # "ok" | "error" | "unknown"
    power_status: Optional[str] = None
    system_fan_status: Optional[str] = None
    cpu_fan_status: Optional[str] = None
    temperature_celsius: Optional[float] = None
    upgrade_available: Optional[bool] = None
    cpu_percent: Optional[float] = None
    memory_total_bytes: Optional[int] = None
    memory_available_bytes: Optional[int] = None
    memory_used_percent: Optional[float] = None


class HealthMetrics(BaseModel):
    system: SystemMetrics = SystemMetrics()
    disks: List[DiskMetrics] = []
    raids: List[RaidMetrics] = []
    ups: Optional[UpsMetrics] = None
    response_seconds: float = 0.0


# ----------------------------------------------------------------------
# Hülle
# ----------------------------------------------------------------------

class CapacitySource(BaseModel):
    """Ergebnis der File-Station-Quelle - `available=False` trägt immer einen `error`"""

    available: bool
    error: Optional[str] = None
    data: Optional[CapacityMetrics] = None


class HealthSource(BaseModel):
    """Ergebnis der SNMP-Quelle - `available=False` trägt immer einen `error`"""

    available: bool
    error: Optional[str] = None
    data: Optional[HealthMetrics] = None


class MetricsSources(BaseModel):
    """
    Je Quelle ein eigenes Feld statt eines generischen Dicts.

    So beschreibt das OpenAPI-Schema die tatsächliche Struktur, und Clients
    bekommen für `filestation` und `snmp` die jeweils passenden Felder.

    Eine nicht angefragte Quelle (?groups=) ist `null` - die Antwortstruktur
    bleibt damit unabhängig von Abfrage und NAS-Modell konstant. Deshalb wird
    auf den Endpoints bewusst kein response_model_exclude_none gesetzt.
    """

    filestation: Optional[CapacitySource] = None
    snmp: Optional[HealthSource] = None


class NASMetrics(BaseModel):
    connection_id: int
    name: str
    host: str
    collected_at: str
    cached: bool = False
    sources: MetricsSources = MetricsSources()
