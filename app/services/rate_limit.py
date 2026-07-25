"""Einfaches In-Memory-Rate-Limit für den Login (Brute-Force-Schutz).

Bewusst ohne externe Abhängigkeit und ohne Persistenz: Die Anwendung läuft als
einzelner Uvicorn-Prozess. Bei mehreren Workern/Instanzen zählt jeder Prozess
für sich - dann gehört ein Limit zusätzlich in den vorgelagerten Reverse-Proxy.

Zählt ausschließlich FEHLGESCHLAGENE Versuche; ein erfolgreicher Login setzt den
Zähler zurück, damit legitime Nutzer nie ausgesperrt werden.
"""
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)

DEFAULT_MAX_ATTEMPTS = 5
DEFAULT_WINDOW_SECONDS = 300  # Zeitfenster, in dem Fehlversuche zählen
DEFAULT_BLOCK_SECONDS = 300  # Basis-Sperrdauer
MAX_BLOCK_SECONDS = 3600  # Obergrenze der progressiven Sperre

# Ab dieser Anzahl Einträge wird beim nächsten Zugriff aufgeräumt. Die Map
# wächst sonst unbegrenzt: pro Client-Schlüssel bleibt ein Eintrag liegen, und
# mit SSA_TRUST_PROXY_HEADERS=true bestimmt der Client diesen Schlüssel selbst
# (X-Forwarded-For) - dann lässt sie sich mit erfundenen Werten vollschreiben.
PRUNE_THRESHOLD = 1000
# Harte Obergrenze; wird sie trotz Aufräumen erreicht, fliegen die am längsten
# untätigen Einträge raus (gesperrte zuletzt).
MAX_ENTRIES = 10000
# Mindestabstand zwischen zwei Aufräumläufen, damit der O(n)-Durchlauf nicht
# an jedem Login-Versuch hängt.
PRUNE_MIN_INTERVAL_SECONDS = 60


@dataclass
class _Entry:
    failures: int = 0
    first_failure: float = 0.0
    blocked_until: float = 0.0
    block_level: int = 0
    last_seen: float = 0.0
    lock: threading.Lock = field(default_factory=threading.Lock)


class LoginRateLimiter:
    """Begrenzt Login-Fehlversuche pro Client mit progressiver Sperre."""

    def __init__(
        self,
        max_attempts: Optional[int] = None,
        window_seconds: Optional[int] = None,
        block_seconds: Optional[int] = None,
    ):
        self.max_attempts = max_attempts or _env_int(
            "SSA_LOGIN_MAX_ATTEMPTS", DEFAULT_MAX_ATTEMPTS
        )
        self.window_seconds = window_seconds or _env_int(
            "SSA_LOGIN_WINDOW_SECONDS", DEFAULT_WINDOW_SECONDS
        )
        self.block_seconds = block_seconds or _env_int(
            "SSA_LOGIN_BLOCK_SECONDS", DEFAULT_BLOCK_SECONDS
        )
        self._entries: Dict[str, _Entry] = {}
        self._global_lock = threading.Lock()
        self._last_prune = 0.0

    def _entry(self, key: str) -> _Entry:
        now = time.time()
        with self._global_lock:
            if len(self._entries) >= PRUNE_THRESHOLD and (
                now - self._last_prune > PRUNE_MIN_INTERVAL_SECONDS
                or len(self._entries) >= MAX_ENTRIES
            ):
                self._prune_locked(now)
                self._last_prune = now
            entry = self._entries.get(key)
            if entry is None:
                entry = _Entry()
                self._entries[key] = entry
            entry.last_seen = now
            return entry

    def _prune_locked(self, now: float) -> None:
        """
        Verwirft Einträge, die nichts mehr schützen. Aufrufer hält _global_lock.

        Behalten wird alles, was noch eine aktive Sperre, offene Fehlversuche im
        Zeitfenster oder kürzlich Aktivität hatte. Die Ruhefrist orientiert sich
        an der längstmöglichen Sperre, damit die progressive Eskalation
        (block_level) nicht durch simples Abwarten zurückgesetzt werden kann.
        """
        idle_after = max(self.window_seconds, MAX_BLOCK_SECONDS)
        stale = [
            key
            for key, entry in self._entries.items()
            if entry.blocked_until <= now
            and (
                not entry.first_failure
                or now - entry.first_failure > self.window_seconds
            )
            and now - entry.last_seen > idle_after
        ]
        for key in stale:
            del self._entries[key]

        # Notbremse: Feuert jemand schnell genug, sind alle Einträge "frisch"
        # und oben bleibt nichts übrig. Dann die am längsten untätigen
        # verwerfen - aktive Sperren zuletzt, damit der Schutz zuerst greift.
        if len(self._entries) >= MAX_ENTRIES:
            candidates = sorted(
                self._entries.items(),
                key=lambda item: (item[1].blocked_until > now, item[1].last_seen),
            )
            for key, _ in candidates[: len(self._entries) - MAX_ENTRIES // 2]:
                del self._entries[key]
            logger.warning(
                "Rate-Limit: Obergrenze erreicht, älteste Einträge verworfen "
                f"(jetzt {len(self._entries)})"
            )

        if stale:
            logger.debug(f"Rate-Limit: {len(stale)} verwaiste Einträge verworfen")

    def check(self, key: str) -> Tuple[bool, int]:
        """
        Prüft, ob ein Login-Versuch erlaubt ist.

        Returns:
            (erlaubt, verbleibende_sperrsekunden)
        """
        entry = self._entry(key)
        with entry.lock:
            now = time.time()
            if entry.blocked_until > now:
                return False, int(entry.blocked_until - now) + 1
            return True, 0

    def register_failure(self, key: str) -> Tuple[bool, int]:
        """
        Verbucht einen Fehlversuch und sperrt ggf.

        Returns:
            (jetzt_gesperrt, sperrsekunden)
        """
        entry = self._entry(key)
        with entry.lock:
            now = time.time()

            # Zeitfenster abgelaufen -> Zähler zurücksetzen
            if entry.first_failure and now - entry.first_failure > self.window_seconds:
                entry.failures = 0
                entry.first_failure = 0.0

            if entry.failures == 0:
                entry.first_failure = now
            entry.failures += 1

            if entry.failures >= self.max_attempts:
                # Progressiv: jede weitere Sperre verdoppelt die Dauer (gedeckelt)
                entry.block_level += 1
                duration = min(
                    self.block_seconds * (2 ** (entry.block_level - 1)),
                    MAX_BLOCK_SECONDS,
                )
                entry.blocked_until = now + duration
                entry.failures = 0
                entry.first_failure = 0.0
                logger.warning(
                    f"Login-Sperre aktiv für {key}: {duration}s "
                    f"(Stufe {entry.block_level})"
                )
                return True, int(duration)
            return False, 0

    def register_success(self, key: str) -> None:
        """Erfolgreicher Login: Zähler und Sperrstufe zurücksetzen"""
        with self._global_lock:
            self._entries.pop(key, None)

    def reset(self) -> None:
        """Kompletter Reset (für Tests)"""
        with self._global_lock:
            self._entries.clear()
            self._last_prune = 0.0


def _env_int(name: str, default: int) -> int:
    try:
        value = int(os.environ.get(name, default))
        return value if value > 0 else default
    except (TypeError, ValueError):
        return default


def client_key(request) -> str:
    """
    Ermittelt den Schlüssel für das Rate-Limit (Client-IP).

    Hinter einem Reverse-Proxy steht die echte IP in X-Forwarded-For. Das wird
    nur ausgewertet, wenn SSA_TRUST_PROXY_HEADERS=true gesetzt ist - sonst
    koennte sich ein Angreifer das Limit durch gefaelschte Header umgehen.
    """
    if os.environ.get("SSA_TRUST_PROXY_HEADERS", "").lower() in ("1", "true", "yes"):
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    client = getattr(request, "client", None)
    return client.host if client and client.host else "unknown"


# Globale Instanz
login_rate_limiter = LoginRateLimiter()
