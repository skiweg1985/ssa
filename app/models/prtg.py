"""Modelle und Builder für PRTG-"HTTP Data Advanced"-Antworten.

Schema (Paessler-Referenz github.com/PRTG/go-prtg-sensor-api):

    {"prtg": {"result": [{"channel": "...", "value": "..."}], "text": "...", "error": "..."}}

Zwei Regeln, die PRTG hart erzwingt und die hier per Konstruktion sichergestellt
werden (siehe make_channel):

1. ALLE Werte sind JSON-Strings - auch Zahlen.
2. Hat ein Wert Nachkommastellen, MUSS `float: "1"` gesetzt sein, sonst zeigt
   PRTG im betroffenen Kanal 0 an.
"""
from typing import List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field


class PrtgChannel(BaseModel):
    """Ein PRTG-Kanal. Alle Felder sind Strings - der Typ erzwingt das."""

    model_config = ConfigDict(populate_by_name=True)

    channel: str
    value: str

    unit: Optional[str] = None
    custom_unit: Optional[str] = Field(None, serialization_alias="customunit")
    # Python-Feldname 'is_float', damit der Builtin nicht verschattet wird
    is_float: Optional[str] = Field(None, serialization_alias="float")
    mode: Optional[str] = None
    decimal_mode: Optional[str] = Field(None, serialization_alias="decimalmode")
    value_lookup: Optional[str] = Field(None, serialization_alias="valuelookup")
    volume_size: Optional[str] = Field(None, serialization_alias="volumesize")
    speed_size: Optional[str] = Field(None, serialization_alias="speedsize")
    speed_time: Optional[str] = Field(None, serialization_alias="speedtime")
    show_chart: Optional[str] = Field(None, serialization_alias="showchart")
    show_table: Optional[str] = Field(None, serialization_alias="showtable")
    warning: Optional[str] = None

    limit_mode: Optional[str] = Field(None, serialization_alias="limitmode")
    limit_min_warning: Optional[str] = Field(None, serialization_alias="limitminwarning")
    limit_max_warning: Optional[str] = Field(None, serialization_alias="limitmaxwarning")
    limit_warning_msg: Optional[str] = Field(None, serialization_alias="limitwarningmsg")
    limit_min_error: Optional[str] = Field(None, serialization_alias="limitminerror")
    limit_max_error: Optional[str] = Field(None, serialization_alias="limitmaxerror")
    limit_error_msg: Optional[str] = Field(None, serialization_alias="limiterrormsg")


class PrtgResult(BaseModel):
    """Inhalt des prtg-Objekts: Kanäle, Statustext und/oder Fehler"""

    result: Optional[List[PrtgChannel]] = None
    text: Optional[str] = None
    error: Optional[str] = None


class PrtgResponse(BaseModel):
    """Wurzelobjekt der Sensor-Antwort"""

    prtg: PrtgResult


def _format_value(value: Optional[Union[int, float]], decimals: int) -> str:
    """Formatiert einen Zahlenwert als PRTG-String (Punkt als Dezimaltrenner)"""
    if value is None:
        return "0"
    if decimals <= 0:
        return str(int(round(value)))
    return f"{value:.{decimals}f}"


def _format_limit(limit: float) -> str:
    """
    Formatiert einen Schwellwert.

    Limits behalten IMMER ihre Nachkommastellen - unabhängig von der Genauigkeit
    des Kanalwerts. Sonst würde z.B. ein Schwellwert 3.5 auf einem Ganzzahl-Kanal
    zu "4" gerundet und der Wert 4 löste keinen Fehler mehr aus.
    """
    if float(limit).is_integer():
        return str(int(limit))
    # Bis zu 4 Nachkommastellen, ohne überflüssige Nullen
    return f"{limit:.4f}".rstrip("0").rstrip(".")


def make_channel(
    name: str,
    value: Optional[Union[int, float]],
    *,
    unit: str = "Count",
    custom_unit: Optional[str] = None,
    decimals: int = 0,
    warn_min: Optional[float] = None,
    warn_max: Optional[float] = None,
    err_min: Optional[float] = None,
    err_max: Optional[float] = None,
    warn_msg: Optional[str] = None,
    err_msg: Optional[str] = None,
    with_limits: bool = True,
) -> PrtgChannel:
    """
    Baut einen PRTG-Kanal und setzt das float-Flag automatisch korrekt.

    Args:
        name: Kanalname (PRTG identifiziert Kanäle über den Namen - stabil halten!)
        value: Zahlenwert, None wird zu 0
        unit: PRTG-Einheit (Count, BytesDisk, BytesFile, BytesMemory,
              Percent, TimeSeconds, ...). Bei "Custom" wird custom_unit gesetzt.
        decimals: Nachkommastellen; > 0 setzt zusätzlich float="1"
        warn_*/err_*: Schwellwerte; gesetzt => limit_mode="1"
        with_limits: False unterdrückt alle Limit-Felder (Query-Parameter ?limits=0)
    """
    channel = PrtgChannel(
        channel=name,
        value=_format_value(value, decimals),
        unit=unit,
    )

    if decimals > 0:
        channel.is_float = "1"

    if unit == "Custom":
        channel.custom_unit = custom_unit or "#"
    elif custom_unit:
        channel.custom_unit = custom_unit

    if with_limits and any(
        limit is not None for limit in (warn_min, warn_max, err_min, err_max)
    ):
        channel.limit_mode = "1"
        if warn_min is not None:
            channel.limit_min_warning = _format_limit(warn_min)
        if warn_max is not None:
            channel.limit_max_warning = _format_limit(warn_max)
        if err_min is not None:
            channel.limit_min_error = _format_limit(err_min)
        if err_max is not None:
            channel.limit_max_error = _format_limit(err_max)
        if warn_msg:
            channel.limit_warning_msg = warn_msg
        if err_msg:
            channel.limit_error_msg = err_msg

    return channel


def ok_response(
    channels: List[PrtgChannel], text: Optional[str] = None
) -> PrtgResponse:
    """Erfolgreiche Sensor-Antwort mit Kanälen"""
    return PrtgResponse(prtg=PrtgResult(result=channels, text=text))


def error_response(text: str) -> PrtgResponse:
    """
    Fehler-Antwort: PRTG setzt den Sensor auf "Down" und zeigt `text` an.

    Nur verwenden, wenn es gar keine sinnvollen Messwerte gibt - sonst besser
    einen Status-Kanal mit limit_max_error nutzen, damit die Historie erhalten bleibt.
    """
    return PrtgResponse(prtg=PrtgResult(error="1", text=text))
