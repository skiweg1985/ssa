"""Gemeinsame Test-Voraussetzungen.

frontend/dist ist nicht versioniert (siehe frontend/.gitignore) - in einem
frischen Klon und in der CI existiert es also nicht. app/main.py registriert
die SPA-Routen aber nur, wenn das Verzeichnis beim Import vorhanden ist. Ohne
Vorkehrung schlagen dadurch die Auslieferungs- und Path-Traversal-Tests fehl,
und zwar nicht wegen eines Fehlers, sondern wegen einer fehlenden Datei.

Deshalb wird hier bei Bedarf ein minimaler Platzhalter angelegt. Ein echter
Build wird nie überschrieben - liegt einer vor, testen wir gegen ihn.

Das passiert absichtlich auf Modulebene: pytest importiert conftest.py vor der
Sammlung der Testmodule, also verlässlich bevor irgendein Test app.main
importiert. Ein Fixture käme dafür zu spät.

Zweiter Punkt hier: die Datenbank-Isolation (siehe _isolate_database).
"""
from pathlib import Path

import pytest

# Muss den Marker '<div id="root">' enthalten, an dem die Tests die SPA erkennen.
#
# Der sichtbare Hinweis ist Absicht: Wer nach einem Testlauf den Server startet,
# bekommt sonst eine weisse Seite und sucht den Fehler an der falschen Stelle.
_PLACEHOLDER_INDEX = """<!doctype html>
<html lang="de">
  <head><meta charset="utf-8" /><title>SSA - kein Frontend-Build</title></head>
  <body style="font-family: system-ui, sans-serif; max-width: 40rem; margin: 4rem auto;">
    <div id="root">
      <h1>Kein Frontend-Build vorhanden</h1>
      <p>
        Diese Seite ist ein Platzhalter, den die Testsuite angelegt hat
        (<code>conftest.py</code>) - <code>frontend/dist</code> ist nicht
        versioniert.
      </p>
      <p>Fuer die echte Oberflaeche:</p>
      <pre><code>npm --prefix frontend ci
npm --prefix frontend run build</code></pre>
      <p>Waehrend der Frontend-Entwicklung stattdessen den Dev-Server nutzen:</p>
      <pre><code>npm --prefix frontend run dev</code></pre>
    </div>
  </body>
</html>
"""


def _ensure_frontend_build() -> None:
    dist = Path(__file__).parent / "frontend" / "dist"
    index = dist / "index.html"
    if index.exists():
        return
    (dist / "assets").mkdir(parents=True, exist_ok=True)
    index.write_text(_PLACEHOLDER_INDEX, encoding="utf-8")


_ensure_frontend_build()


@pytest.fixture(autouse=True)
def _isolate_database(monkeypatch, tmp_path):
    """
    Hält jeden Test von der echten data/history.db fern.

    Ohne das greift ein Test, der weder Storage noch Jobs-Store selbst umbiegt,
    über get_storage() auf die Produktionsdatenbank im Projekt zu - seit der
    Admin-Login auch dort nachschlägt (verify_admin) betrifft das auch Tests,
    die mit Persistenz nichts zu tun haben.

    Umgebogen wird der Default-Pfad, nicht die Instanz: Tests, die selbst eine
    ScanStorage mit explizitem db_path bauen (z.B. test_auth_api.py), laufen
    unverändert weiter.
    """
    import app.services.jobs_store as jobs_store_module
    import app.services.storage as storage_module

    real_init = storage_module.ScanStorage.__init__

    def init_in_tmp(self, *args, **kwargs):
        # len(args) < 2: ab dem zweiten positionalen Argument sind storage_dir
        # bzw. db_path selbst gesetzt und haben Vorrang.
        if (
            len(args) < 2
            and kwargs.get("db_path") is None
            and kwargs.get("storage_dir") is None
        ):
            kwargs["db_path"] = tmp_path / "history.db"
        real_init(self, *args, **kwargs)

    monkeypatch.setattr(storage_module.ScanStorage, "__init__", init_in_tmp)
    monkeypatch.setattr(storage_module, "_storage_instance", None)
    monkeypatch.setattr(jobs_store_module, "_jobs_store_instance", None)
