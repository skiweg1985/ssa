# Sicherheitsrichtlinie

## Sicherheitslücke melden

**Bitte melde Sicherheitslücken nicht über öffentliche GitHub-Issues,
Pull Requests oder Diskussionen.**

Nutze stattdessen den privaten Meldeweg:

1. Öffne den Tab **Security** dieses Repositories
2. **Report a vulnerability** → Formular ausfüllen

Damit ist die Meldung nur für die Maintainer sichtbar, bis ein Fix bereitsteht.

Hilfreich für eine schnelle Einordnung:

- betroffene Version / Commit
- Beschreibung der Lücke und der praktischen Auswirkung
- Schritte zur Reproduktion (gern mit minimalem Proof of Concept)
- ggf. Vorschlag zur Behebung

## Ablauf

| Schritt | Zeitrahmen |
|---|---|
| Eingangsbestätigung | innerhalb von 7 Tagen |
| Erste Einschätzung (Schweregrad, Betroffenheit) | innerhalb von 14 Tagen |
| Fix bzw. Zeitplan für einen Fix | abhängig von Schweregrad und Aufwand |

Nach der Behebung wird die Lücke im Release beschrieben. Auf Wunsch erfolgt eine
Nennung als Melder — sag einfach Bescheid, ob und wie du genannt werden möchtest.

## Unterstützte Versionen

Sicherheitsfixes werden für den aktuellen Stand von `main` und das jeweils
neueste Release bereitgestellt. Ältere Releases werden nicht rückportiert.

## Betriebshinweise

Diese Anwendung verarbeitet NAS-Zugangsdaten und Admin-Tokens. Für einen
sicheren Betrieb:

- **Ersteinrichtung sofort abschließen.** Ist noch kein Admin-Konto angelegt
  und kein `SSA_ADMIN_PASSWORD` gesetzt, kann jeder, der den Port erreicht, das
  Konto für sich beanspruchen. Das Fenster schließt sich mit dem ersten
  erfolgreichen Setup; ein zweiter Versuch wird abgewiesen (HTTP 409). Der
  Vorgang wird mit Zeitpunkt und Client-IP protokolliert.
- **`SSA_SETUP_TOKEN` setzen**, wenn der Dienst aus einem nicht
  vertrauenswürdigen Netz erreichbar ist. Die Ersteinrichtung verlangt dann
  zusätzlich genau dieses Token aus der Server-Umgebung.
- **Nicht ungeschützt ins Internet stellen.** Empfohlen: Bindung an das lokale
  Netz bzw. Zugriff ausschließlich über einen TLS-Reverse-Proxy.
- **`data/`-Verzeichnis schützen.** Dort liegen die SQLite-Datenbank und
  `secret.key`. Der Key signiert Admin-Tokens **und** verschlüsselt die
  gespeicherten NAS-Passwörter — wer ihn lesen kann, übernimmt die Anwendung
  und die hinterlegten NAS-Zugänge. In der Datenbank liegt zusätzlich das
  Admin-Passwort als scrypt-Hash (gesalzen, nicht umkehrbar, aber angreifbar
  per Wörterbuch — entsprechend lang wählen).
- **Bei Verdacht auf Kompromittierung** rotieren: `SSA_SECRET_KEY` bzw.
  `data/secret.key`, das Admin-Passwort, alle Monitoring-API-Tokens und die
  im Frontend hinterlegten NAS-Passwörter. Nach einem Key-Wechsel müssen die
  NAS-Passwörter neu eingegeben werden (sie sind dann nicht mehr entschlüsselbar);
  das Admin-Konto bleibt gültig, sein Hash hängt nicht am Key.

  Das Admin-Passwort wechselt man über die Umgebung (`SSA_ADMIN_PASSWORD` hat
  Vorrang) oder indem man das gespeicherte Konto verwirft und die
  Ersteinrichtung erneut durchläuft:

  ```bash
  sqlite3 data/history.db "DELETE FROM app_meta WHERE key LIKE 'admin_%'"
  ```

  **Bekannte Einschränkung:** Auth-Tokens sind zustandslos signiert und lassen
  sich derzeit nicht einzeln widerrufen. Ein Passwortwechsel beendet bestehende
  Sitzungen also nicht — dafür `SSA_SECRET_KEY` bzw. `data/secret.key` rotieren
  (danach müssen die NAS-Passwörter neu eingegeben werden).
- **Monitoring-API-Tokens** haben ausschließlich Lesezugriff auf Scan-Status,
  Ergebnisse und PRTG-Sensordaten. Sie können weder Scans auslösen noch
  Verbindungen oder Jobs verwalten. Nicht mehr benötigte Tokens im Frontend
  widerrufen.
