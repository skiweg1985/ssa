# Monitoring-Anbindung

SSA liefert seinen Zustand für Monitoring-Systeme fertig ausgewertet aus. Diese
Datei beschreibt alle dafür vorgesehenen Endpoints — generisch für beliebige
Werkzeuge, speziell für PRTG, und den offenen Health-Check.

## Welchen Endpoint für welches Werkzeug

| Endpoint | Wofür | Token nötig |
|---|---|---|
| `GET /api/monitor` | Gesamtzustand — ein Check für die ganze Instanz | ja |
| `GET /api/monitor/scans` | alle Scan-Jobs, mit Roll-up und Problemliste | ja |
| `GET /api/monitor/scans/<slug>` | ein einzelner Scan-Job | ja |
| `GET /api/monitor/server` | Infrastruktur — Scheduler, System, Storage | ja |
| `GET /api/prtg/scans/<slug>` | PRTG-Sensor **pro Scan-Job** | ja |
| `GET /api/prtg/server` | PRTG-Sensor für den **Server selbst** | ja |
| `GET /health` | reiner Up/Down-Check, z.B. Docker-Healthcheck | nein |
| `POST /api/scans/<slug>/cancel` | laufenden Scan abbrechen — nur mit Login | ja |
| `GET /api/scans/<slug>/results` | Rohdaten und Historie zur Auswertung | ja |

Für PRTG die `/api/prtg/*`-Sensoren nehmen — sie legen ihre Kanäle selbst an.
Für **alles andere** die `/api/monitor*`-Endpoints: dort genügt ein einziger
Feldzugriff, um zu entscheiden, ob alarmiert werden muss.

## Zugriff und Tokens

Alle Endpoints außer `/health` erwarten ein Bearer-Token. Für Monitoring gibt es
**statische, read-only API-Tokens**, die im Frontend verwaltet werden — siehe
[README.md](README.md), Kapitel „Monitoring".

```bash
curl -H "Authorization: Bearer ssa_..." http://nas:8080/api/monitor
```

Ein solches Token darf ausschließlich `GET` auf `/api/monitor*`, `/api/prtg*`,
`/api/scans*` und `/api/storage/stats` — kein Triggern, keine Verwaltung.

## Generische Monitoring-Endpoints

### Das Prinzip: eine Zahl entscheidet

Jede Antwort trägt ein Feld `severity`. Das ist die **einzige** Achse, die ein
Monitoring-System auswerten muss:

| `severity` | `severity_text` | Bedeutung |
|---|---|---|
| `0` | `ok` | kein Handlungsbedarf |
| `1` | `warning` | auffällig, aber nicht kritisch |
| `2` | `critical` | Eingriff nötig |

Die Werte sind streng monoton — `>= 1` und `>= 2` funktionieren immer als
Schwellwert. Ein `UNKNOWN(3)` wie bei Nagios wird **nie** geliefert; es wäre
nicht monoton und würde jede Schwellwertlogik verfälschen.

Daneben steht `state` als maschinenlesbarer Grund und `message` als fertiger
Alarmtext. `reasons` listet **alle** zutreffenden Gründe in
Auswertungsreihenfolge; `reasons[0]` ist immer identisch mit `state`.

### Die Zustände eines Scan-Jobs

Es gilt der erste zutreffende Grund von oben:

| `state` | `severity` | Bedeutung |
|---|---|---|
| `error` | 2 | Zustand nicht ermittelbar — Details im Server-Log |
| `disabled` | **0** | Job ist deaktiviert |
| `stuck` | 2 | läuft ungewöhnlich lange — hängt vermutlich |
| `failed` | 2 | letzter beendeter Lauf ist fehlgeschlagen |
| `overdue` | 2 | Lauf deutlich überfällig — ab 3x Intervall |
| `never_run` | 1 | noch keine Ergebnisse vorhanden |
| `unscheduled` | 1 | aktiviert, aber nicht im Scheduler eingeplant |
| `cancelled` | 1 | letzter Lauf wurde abgebrochen |
| `stale` | 1 | länger nicht gelaufen als erwartet — ab 2x Intervall |
| `partial` | 1 | Lauf abgeschlossen, aber Ordner fehlgeschlagen |
| `ok` | 0 | letzter Lauf erfolgreich, alle Ordner gescannt |

`stuck` steht **vor** `failed`: der Zustand ist akut und blockiert den Job
gerade, während `failed` einen bereits beendeten Lauf beschreibt.

`disabled` steht bewusst **vor** allen Fehlergründen und hat Severity 0: ein
absichtlich deaktivierter Job darf nicht alarmieren. Der Fehlergrund bleibt in
`reasons` sichtbar, ohne einen Alarm auszulösen.

### Ein laufender Scan ist keine Zustandsangabe

„Läuft gerade" steht in `run.active`, **nicht** in `state`. Das ist der
wichtigste Unterschied zum alten Status-Endpoint: dort überschrieb `"running"`
das Ergebnis des vorherigen Laufs, sodass ein Monitoring während jedes Laufs
blind war — bei einem Sechs-Stunden-Job mit 40 Minuten Laufzeit rund 10 % der
Zeit.

Ein laufender Scan kann die Severity nie verschlechtern und setzt die
Überfälligkeit aus. Nur ein **beendeter** Lauf ändert `state` — mit einer
Ausnahme: einem Lauf, der hängt.

### Hängende Läufe

Genau weil ein laufender Scan die Überfälligkeit aussetzt, wäre ein Lauf, der
nie endet, ein blinder Fleck: der Job gilt dauerhaft als „läuft", und kein
Alter-Schwellwert greift mehr. Deshalb bekommt ein zu lange laufender Scan
`run.stuck: true` und `state: "stuck"` mit **severity 2**.

Die Schwelle steht in `run.stuck_after_seconds` und wird aus der **Pfadanzahl**
abgeleitet, nicht aus dem Intervall: der Scanner räumt jedem Pfad ein Timeout
von 300 s ein, also ist die plausible Obergrenze eines Laufs berechenbar —
`Pfadanzahl × 300 s × 2`, mindestens 30 Minuten. Das funktioniert auch für Jobs,
deren Intervall sich nicht ermitteln lässt.

```json
{
  "severity": 2,
  "severity_text": "critical",
  "state": "stuck",
  "reasons": ["stuck"],
  "message": "Scan läuft seit 5 Stunden und hängt vermutlich bei 12 %, zuletzt '/photo' - Abbruch über POST /api/scans/<slug>/cancel möglich",
  "run": {
    "active": true,
    "started_at": "2026-07-25T04:12:00Z",
    "active_seconds": 18000.0,
    "progress_percent": 12.4,
    "current_path": "/photo",
    "stuck_after_seconds": 1800.0,
    "stuck": true,
    "cancel_requested": false
  }
}
```

Ein **deaktivierter** Job alarmiert auch dann nicht — `disabled` überstimmt
`stuck`, der Grund bleibt in `reasons` sichtbar.

### Laufenden Scan abbrechen

```http
POST /api/scans/{scan_slug}/cancel
```

Erfordert eine **angemeldete Sitzung** — read-only API-Tokens dürfen nur `GET`.

Der Abbruch ist **kooperativ**: Scans laufen als Hintergrund-Task bzw. als
Scheduler-Job, es gibt kein Task-Handle zum harten Beenden. Der Lauf prüft den
Wunsch zwischen zwei Pfaden und bei jedem Poll der Größenabfrage, endet also in
der Regel innerhalb weniger Sekunden. Der laufende DirSize-Task wird zusätzlich
am NAS gestoppt, damit dort nicht weitergerechnet wird.

| Feld | Bedeutung |
|---|---|
| `cancelling: true` | Abbruch wurde hinterlegt |
| `cancelling: false` | es lief gerade kein Scan — **kein Fehler**, damit ein doppelter Klick keine Fehlermeldung erzeugt |

Ein unbekannter Slug ergibt HTTP 404. Solange der Wunsch hinterlegt und der Lauf
noch nicht beendet ist, steht `run.cancel_requested: true` im Bericht.

Der abgebrochene Lauf landet mit Status `cancelled` in der Historie: bereits
gemessene Ordner bleiben erhalten, der Lauf zählt aber **nicht** als
erfolgreicher Lauf — `last_success` bleibt also auf dem vorherigen guten Lauf
stehen. Im Bericht wird daraus `state: "cancelled"` mit severity 1: keine
frischen Daten, aber eine bewusste Handlung und damit kein Grund, jemanden aus
dem Bett zu holen.

Ein automatischer Abbruch hängender Läufe findet **nicht** statt — ein Job mit
zwanzig Pfaden darf zulässig über eine Stunde brauchen, und ein Watchdog würde
solche Läufe abschießen. `stuck` meldet, die Entscheidung bleibt beim Menschen
oder bei einer Automatik, die ihr eigenes Urteil mitbringt.

### Felder des Job-Berichts

Alle Felder sind **immer** vorhanden; unbekannte Werte sind `null`. Damit
funktioniert ein JSONPath-Ausdruck in Zabbix oder Grafana unabhängig vom
Zustand des Jobs.

| Feld | Bedeutung |
|---|---|
| `schema_version` | `ssa.monitor.scan/1` — Version dieses Schemas |
| `generated_at` | Zeitpunkt der Auswertung |
| `severity`, `severity_text`, `state`, `reasons`, `message` | siehe oben |
| `scan.slug`, `scan.name`, `scan.enabled` | Identität des Jobs |
| `run.active` | ob gerade ein Lauf aktiv ist |
| `run.started_at`, `run.active_seconds` | Start und bisherige Laufzeit des aktiven Scans |
| `run.progress_percent`, `run.current_path` | Fortschritt und aktueller Pfad, sofern ermittelbar |
| `run.stuck`, `run.stuck_after_seconds` | ob der Lauf hängt, und ab wann er als hängend gilt |
| `run.cancel_requested` | ob für diesen Lauf ein Abbruch angefordert wurde |
| `last_run.at`, `last_run.age_seconds` | Zeitpunkt und Alter des letzten Laufs |
| `last_run.status` | roher Lauf-Status: `completed`, `failed`, `cancelled`, `running` |
| `last_run.error` | Fehlermeldung des letzten Laufs |
| `last_run.duration_seconds` | summierte Scan-Dauer |
| `last_run.folders_total`, `folders_ok`, `folders_failed` | Ordnerbilanz des letzten Laufs |
| `last_run.folders_failed_names` | Namen der fehlgeschlagenen Ordner |
| `last_success.at`, `last_success.age_seconds` | letzter **erfolgreicher** Lauf |
| `last_success.total_bytes`, `total_directories`, `total_files` | die Messwerte |
| `last_success.folders_ok` | Ordner mit Messwerten |
| `schedule.scheduled` | ob der Job im Scheduler eingeplant ist |
| `schedule.interval` | konfiguriertes Intervall, roh — Cron oder Kurzform |
| `schedule.expected_interval_seconds` | erwarteter Abstand zweier Läufe |
| `schedule.next_run_at`, `next_run_in_seconds` | nächster geplanter Lauf |
| `schedule.overdue`, `overdue_by_seconds` | Überfälligkeit, serverseitig gerechnet |
| `schedule.stale_after_seconds`, `overdue_after_seconds` | die verwendeten Schwellwerte |

Zwei Festlegungen, die Rückfragen erübrigen:

- Die **Ordnerzahlen** stehen in `last_run` und beziehen sich auf den letzten
  Lauf. Die **Messwerte** stehen in `last_success` und stammen vom letzten
  erfolgreichen Lauf. Ein Fehllauf setzt also `severity` auf 2, lässt die
  Messwerte aber stehen — die Charts reißen nicht auf 0.
- `folders_failed` wird als `max(Sollwert des Laufs - erfolgreiche, explizite
  Fehler, 0)` berechnet. Nötig, weil nur erfolgreiche Ordner gespeichert werden:
  nach einem Neustart stünde dort sonst fälschlich 0. Der **Sollwert gehört zum
  Lauf**, nicht zum Job — damit ist ein Pfad, der erst nach dem Lauf
  konfiguriert wurde, kein rückwirkender Fehlschlag, und ein echter Fehler
  bleibt trotz Job-Änderungen sichtbar. Läufe aus Versionen vor dieser
  Änderung tragen keinen Sollwert; dort gilt die aktuelle Konfiguration, und
  im Zweifel wird ein Fehler gemeldet statt verschwiegen.

### Beispiel: alles in Ordnung

```json
{
  "schema_version": "ssa.monitor.scan/1",
  "generated_at": "2026-07-25T09:12:44.512000Z",
  "severity": 0,
  "severity_text": "ok",
  "state": "ok",
  "reasons": [],
  "message": "Letzter Lauf erfolgreich vor 12 Minuten, 2 von 2 Ordnern OK",
  "scan": { "slug": "design-scan", "name": "Design Scan", "enabled": true },
  "run": {
    "active": false,
    "started_at": null,
    "active_seconds": null,
    "progress_percent": null,
    "current_path": null
  },
  "last_run": {
    "at": "2026-07-25T09:00:00Z",
    "age_seconds": 764.0,
    "status": "completed",
    "error": null,
    "duration_seconds": 25.06,
    "folders_total": 2,
    "folders_ok": 2,
    "folders_failed": 0,
    "folders_failed_names": []
  },
  "last_success": {
    "at": "2026-07-25T09:00:00Z",
    "age_seconds": 764.0,
    "folders_ok": 2,
    "total_bytes": 1573741824,
    "total_directories": 20,
    "total_files": 200
  },
  "schedule": {
    "scheduled": true,
    "interval": "6h",
    "expected_interval_seconds": 21600.0,
    "next_run_at": "2026-07-25T15:00:00Z",
    "next_run_in_seconds": 20836.0,
    "overdue": false,
    "overdue_by_seconds": 0.0,
    "stale_after_seconds": 43200.0,
    "overdue_after_seconds": 64800.0
  }
}
```

### Beispiel: Teilfehler

Ein Ordner von drei war nicht erreichbar. Der rohe Lauf-Status bleibt
`completed` — genau darum ist er als Alarmkriterium untauglich.

```json
{
  "severity": 1,
  "severity_text": "warning",
  "state": "partial",
  "reasons": ["partial"],
  "message": "Letzter Lauf abgeschlossen, aber 1 von 3 Ordnern fehlgeschlagen: /photo",
  "last_run": {
    "status": "completed",
    "folders_total": 3,
    "folders_ok": 2,
    "folders_failed": 1,
    "folders_failed_names": ["/photo"]
  }
}
```

### Beispiel: letzter Lauf fehlgeschlagen

Der Fehler ist sichtbar **und** die letzten guten Messwerte bleiben erhalten —
genau das konnte der alte Status-Endpoint nicht gleichzeitig ausdrücken.

```json
{
  "severity": 2,
  "severity_text": "critical",
  "state": "failed",
  "reasons": ["failed", "partial"],
  "message": "Letzter Lauf vor 12 Minuten fehlgeschlagen: NAS offline",
  "last_run": {
    "at": "2026-07-25T09:00:00Z",
    "age_seconds": 764.0,
    "status": "failed",
    "error": "NAS offline",
    "folders_total": 2,
    "folders_ok": 0,
    "folders_failed": 2,
    "folders_failed_names": []
  },
  "last_success": {
    "at": "2026-07-25T03:00:00Z",
    "age_seconds": 22364.0,
    "folders_ok": 2,
    "total_bytes": 1573741824,
    "total_directories": 20,
    "total_files": 200
  }
}
```

`reasons` enthält hier zusätzlich `partial`: ein gescheiterter Lauf hat auch
keinen Ordner geschafft. Ausschlaggebend ist der erste Grund — `failed`.
`folders_failed_names` bleibt leer, weil bei einem Fehlschlag vor dem ersten
Ordner keine Einzelergebnisse entstehen; die Zahl stammt dann aus den erwarteten
Pfaden.

### Beispiel: überfällig

30 Stunden alt bei 6-Stunden-Intervall. Die Schwellwerte hat der Server
gerechnet — der Client muss `interval` nicht parsen.

```json
{
  "severity": 2,
  "severity_text": "critical",
  "state": "overdue",
  "reasons": ["overdue", "stale"],
  "message": "Scan ist überfällig: letzter Lauf vor 30 Stunden, erwartet alle 6 Stunden",
  "last_run": { "age_seconds": 108000.0, "status": "completed" },
  "schedule": {
    "overdue": true,
    "overdue_by_seconds": 43200.0,
    "stale_after_seconds": 43200.0,
    "overdue_after_seconds": 64800.0
  }
}
```

### Beispiel: deaktiviert

Der letzte Lauf war ein Fehlschlag — der Job alarmiert trotzdem nicht, der
Grund bleibt aber in `reasons` sichtbar.

```json
{
  "severity": 0,
  "severity_text": "ok",
  "state": "disabled",
  "reasons": ["disabled", "failed", "partial"],
  "message": "Job ist deaktiviert",
  "scan": { "slug": "design-scan", "name": "Design Scan", "enabled": false },
  "schedule": {
    "scheduled": false,
    "expected_interval_seconds": null,
    "next_run_at": null,
    "next_run_in_seconds": null,
    "overdue": false,
    "overdue_by_seconds": 0.0,
    "stale_after_seconds": null,
    "overdue_after_seconds": null
  }
}
```

### Beispiel: läuft gerade

Das Ergebnis des vorherigen Laufs bleibt sichtbar, die Severity unverändert.

```json
{
  "severity": 0,
  "state": "ok",
  "reasons": [],
  "message": "Scan läuft - Letzter Lauf erfolgreich vor 6 Stunden, 2 von 2 Ordnern OK",
  "run": { "active": true },
  "last_run": {
    "at": "2026-07-25T03:00:00Z",
    "age_seconds": 22344.0,
    "status": "completed",
    "folders_failed": 0
  },
  "schedule": { "overdue": false }
}
```

### Beispiel: noch nie gelaufen

Bewusst HTTP 200 mit Daten — anders als der PRTG-Endpoint, der hier einen
Sensorfehler meldet. So kann ein Check schon vor dem ersten Lauf angelegt
werden.

```json
{
  "severity": 1,
  "state": "never_run",
  "reasons": ["never_run"],
  "message": "Job hat noch keine Ergebnisse geliefert",
  "last_run": {
    "at": null,
    "age_seconds": null,
    "status": null,
    "error": null,
    "duration_seconds": null,
    "folders_total": 2,
    "folders_ok": 0,
    "folders_failed": 2,
    "folders_failed_names": []
  },
  "last_success": {
    "at": null,
    "age_seconds": null,
    "folders_ok": 0,
    "total_bytes": null,
    "total_directories": null,
    "total_files": null
  }
}
```

### Alle Jobs auf einmal

`GET /api/monitor/scans` rollt alle Jobs zusammen. `severity` ist das Maximum
über alle Jobs — ein einzelner Check deckt damit die gesamte Job-Landschaft ab.
`problems` enthält nur Jobs mit `severity >= 1`, schlimmste zuerst, sodass ein
Alarmtext ohne Iteration entsteht.

Das folgende Beispiel wurde mit `?include_scans=0` abgerufen — deshalb ist
`scans` gleich `null`. Ohne den Parameter steht dort ein vollständiger Bericht
je Job im oben beschriebenen Schema.

```json
{
  "schema_version": "ssa.monitor.scans/1",
  "generated_at": "2026-07-25T09:12:44Z",
  "severity": 2,
  "severity_text": "critical",
  "state": "failed",
  "message": "1 von 4 Jobs kritisch: design-scan (Letzter Lauf vor 2 Stunden fehlgeschlagen: NAS offline)",
  "summary": {
    "total": 4, "enabled": 3, "disabled": 1, "running": 1,
    "ok": 2, "warning": 0, "critical": 1,
    "never_run": 0, "overdue": 0, "failed": 1, "partial": 0, "unscheduled": 0,
    "worst_slug": "design-scan",
    "stalest_slug": "photo-scan",
    "stalest_age_seconds": 91234.0
  },
  "problems": [
    {
      "slug": "design-scan",
      "name": "Design Scan",
      "severity": 2,
      "state": "failed",
      "message": "Letzter Lauf vor 2 Stunden fehlgeschlagen: NAS offline"
    }
  ],
  "scans": null
}
```

Die Zähler in `summary` zählen jeden Job **einmal**, und zwar für seinen
ausschlaggebenden `state`. `stalest_*` betrachtet nur aktivierte Jobs —
deaktivierte laufen bewusst nicht.

| Parameter | Default | Wirkung |
|---|---|---|
| `include_scans` | `1` | `0` = `scans` bleibt `null`, `summary` und `problems` bleiben |
| `http_status` | `0` | siehe „HTTP-Status" |

### Gesamtzustand

`GET /api/monitor` ist der Endpoint für „ein Werkzeug, ein Check". Die Severity
ist das Maximum aus Infrastruktur und Job-Landschaft; bei Gleichstand
entscheidet die Infrastruktur, weil sie die Ursache ist und die Jobs nur die
Folge.

```json
{
  "schema_version": "ssa.monitor.instance/1",
  "generated_at": "2026-07-25T09:12:44Z",
  "severity": 2,
  "severity_text": "critical",
  "state": "failed",
  "message": "1 von 4 Jobs kritisch: design-scan (...)",
  "components": {
    "server": { "severity": 0, "severity_text": "ok", "state": "ok", "message": "Server in Ordnung" },
    "scans": { "severity": 2, "severity_text": "critical", "state": "failed", "message": "..." }
  },
  "problems": [
    {
      "slug": "design-scan",
      "name": "Design Scan",
      "severity": 2,
      "state": "failed",
      "message": "Letzter Lauf vor 2 Stunden fehlgeschlagen: NAS offline"
    }
  ]
}
```

### Infrastruktur

`GET /api/monitor/server` bewertet **nur** die Infrastruktur. Job-Ergebnisse
gehen hier absichtlich nicht in die Severity ein — sonst alarmieren zwei Checks
für dieselbe Ursache. Die Job-Zähler unter `jobs` sind rein informativ.

| Bedingung | `severity` | `state` |
|---|---|---|
| Scheduler läuft nicht | 2 | `scheduler_down` |
| RAM oder Disk ab 95 % belegt | 2 | `resources_critical` |
| RAM oder Disk ab 85 % belegt | 1 | `resources_warning` |
| Konfigurationswarnungen vorhanden | 1 | `config_warnings` |
| sonst | 0 | `ok` |

Enthaltene Blöcke: `server` — Version, Uptime, Startzeit · `scheduler` —
`running`, `total_jobs`, `enabled_jobs` · `system` — CPU, RAM, Disk ·
`storage` — DB-Größe, Anzahl Ergebnisse, ältester/neuester Eintrag · `jobs` ·
`warnings`.

Ist `psutil` nicht installiert, steht `system.available` auf `false` und **alle**
Systemwerte sind `null` — nicht `0`, das würde als „0 % Disk belegt"
fehlgedeutet. Die Severity bleibt davon unberührt.

### HTTP-Status

Standardmäßig antworten alle Monitoring-Endpoints mit **HTTP 200**, auch bei
`severity: 2`. Grund: viele HTTP-Collectoren verwerfen bei einem Status außerhalb
2xx den Antwortkörper — und damit genau die Details, die hier stehen. Außerdem
wäre ein 503 der Anwendung nicht von einem 503 eines Reverse Proxy zu
unterscheiden.

Der Schweregrad steht zusätzlich in jeder Antwort als Header:

```
X-SSA-Severity: 2
X-SSA-State: failed
```

Wer nur den Statuscode auswerten kann, setzt `?http_status=1`:

| `severity` | Statuscode mit `http_status=1` |
|---|---|
| 0, 1 | `200` |
| 2 | `503` |

Unabhängig davon gilt klassisches REST: **404** bei unbekanntem Slug — das ist
ein Fehler in der URL, kein überwachter Zustand — sowie 401 ohne Token und 403
bei unzureichenden Rechten.

## PRTG: HTTP Data Advanced

Zwei Endpoints liefern fertige Sensordaten im PRTG-Format — PRTG legt die Kanäle
automatisch an, JSONPath-Filter entfallen:

| Endpoint | Sensor |
|---|---|
| `GET /api/prtg/scans/<slug>` | ein Sensor **pro Scan-Job** |
| `GET /api/prtg/server` | ein Sensor für den **Server selbst** |

**Sensor anlegen:** Gerät → *Sensor hinzufügen* → **HTTP Data Advanced** → URL
eintragen → unter den erweiterten Einstellungen den Header
`Authorization: Bearer ssa_...` setzen. Scan-Intervall des Sensors sinnvollerweise
≥ Scan-Intervall des Jobs wählen.

**Kanäle pro Job:** Gesamtgröße · Ordner · Dateien · Scan-Dauer ·
Alter letzter Lauf · Alter letzte Daten · Status · Ordner OK · Ordner Fehler —
plus **ein Kanal je gescanntem Ordner** (Kanalname = Pfad, z.B. `/design`).

**Status-Kanal:**

| Wert | Bedeutung | Sensor |
|---|---|---|
| 0 | letzter Lauf erfolgreich | OK |
| 1 | Scan läuft gerade | OK |
| 2 | Job deaktiviert | OK |
| 3 | Job nicht eingeplant **oder** letzter Lauf abgebrochen | Warning |
| 4 | letzter Lauf fehlgeschlagen | Error |

Messwerte stammen immer vom letzten **erfolgreichen** Lauf — ein Fehllauf macht
den Sensor rot, reißt die Charts aber nicht auf 0.

**Kanäle Server:** Uptime · CPU · RAM belegt/frei · Disk belegt/frei · Scheduler ·
Jobs gesamt/aktiv/laufend · Jobs mit Fehler · Jobs ohne Ergebnisse · Ältester Lauf ·
DB-Größe · Ergebnisse in DB · Konfigurationswarnungen.

**Query-Parameter:**

| Parameter | Default | Wirkung |
|---|---|---|
| `folders` | `1` | `0` = keine Ordner-Kanäle, nur Summen |
| `max_folders` | `40` | Obergrenze für Ordner-Kanäle |
| `limits` | `1` | `0` = keine Schwellwerte (eigene in PRTG pflegen) |

**Gut zu wissen:**
- PRTG identifiziert Kanäle über den **Namen** — wird ein Scan-Pfad umbenannt,
  entsteht ein neuer Kanal; der alte bleibt leer stehen und kann in PRTG gelöscht werden.
- PRTG unterstützt max. **50 Kanäle** pro Sensor; darüber wird gekappt (Hinweis
  erscheint in der Sensormeldung).
- Mitgelieferte Schwellwerte überschreiben in PRTG manuell gesetzte Limits —
  bei eigenen Schwellwerten `?limits=0` verwenden.
- Sensor erst **nach dem ersten erfolgreichen Scan** anlegen; vorher meldet der
  Endpoint bewusst einen Fehler statt Nullwerte.
- Fehler (unbekannter Job, noch keine Daten) kommen als HTTP **200** mit
  `prtg.error` — so wie PRTG es erwartet.

```bash
curl -H "Authorization: Bearer ssa_..." http://nas:8080/api/prtg/scans/design-scan
```

## Zuordnung PRTG-Status zu generischem State

Beide Endpoint-Familien lesen dieselben Daten und verwenden dieselben
Alters-Schwellwerte. Sie stellen sie aber unterschiedlich dar, weil PRTG einen
einzelnen Zahlenkanal mit einem Schwellwertpaar auswertet:

| generischer `state` | `severity` | PRTG-Statuskanal |
|---|---|---|
| `ok` | 0 | 0 |
| `disabled` | **0** | **2** |
| `partial` | 1 | 0 — Signal über den Kanal „Ordner Fehler" |
| `stale` | 1 | 0 — Signal über die Limits des Alters-Kanals |
| `unscheduled` | 1 | **3** |
| `cancelled` | 1 | **3** — teilt den Wert mit `unscheduled` |
| `overdue` | 2 | 0 — Signal über die Limits des Alters-Kanals |
| `failed` | 2 | 4 |
| `never_run` | 1 | `prtg.error`, HTTP 200 |
| `run.active` — eigene Achse | unverändert | 1, überschreibt jeden anderen Wert |

Die beiden auffälligen Abweichungen sind gewollt:

- **`disabled`**: In PRTG ist der Statuskanal aufsteigend nach Schwere sortiert,
  damit ein einzelnes Schwellwertpaar Warning und Error abdeckt — „deaktiviert"
  liegt dort zwangsläufig zwischen „läuft" und „nicht eingeplant". Generisch
  gibt es diese Einschränkung nicht, dort ist ein deaktivierter Job Severity 0.
- **`run.active`**: PRTG kennt nur einen Statuswert, deshalb überschreibt
  „läuft" dort alles. Der generische Bericht hat für den Lauf eine eigene Achse
  und behält das Ergebnis des Vorlaufs.

## /health

`GET /health` ist **ohne Token** erreichbar und für Up/Down-Checks gedacht — etwa
als Docker-Healthcheck. Das Feld `status` ist `healthy` oder `warning`
(letzteres nur bei Konfigurationswarnungen) und wird **nie** `error`, egal wie
viele Jobs fehlgeschlagen sind. Für Job- und Ressourcenalarme daher
`/api/monitor` verwenden.

## Veraltet: GET /api/scans/{slug}/status

Dieser Endpoint bleibt aus Kompatibilitätsgründen unverändert erhalten — es gibt
kein Entfernungsdatum. Er ist in OpenAPI als `deprecated` markiert und sendet
`Deprecation: true` sowie einen `Link`-Header auf den Nachfolger.

Für Monitoring ist seine Antwort schwer auszuwerten:

- `status` mischt Lebenszyklus und Ergebnis: `"running"` überschreibt das
  Ergebnis des vorherigen Laufs.
- `"completed"` bedeutet nicht „alles in Ordnung" — es genügt ein einziger
  erfolgreicher Pfad. Teilfehler sind nur über einen Zweit-Call auf `/results`
  und Auswertung von `results[].success` erkennbar.
- Es gibt kein `error`-Feld und keinen Zeitstempel des letzten **erfolgreichen**
  Laufs.
- Überfälligkeit muss der Client selbst berechnen — inklusive Parsen von
  `interval`, das entweder ein Cron-Ausdruck oder eine Kurzform wie `"10m"` ist.
- `next_run: null` ist dreifach belegt: deaktiviert, nicht eingeplant, oder
  Scheduler nicht gestartet.
- `"pending"` ist doppelt belegt: noch nie gelaufen, oder Ergebnisse gelöscht.
- Es gibt keinen numerischen Schweregrad, und die Antwort enthält
  Verwaltungsdaten (`nas`, `shares`, `folders`, `paths`), die für Monitoring
  irrelevant sind.

### Migration

| alt | neu |
|---|---|
| `status == "running"` | `run.active` |
| `status == "completed"` | `last_run.status` **und** `last_run.folders_failed == 0` |
| `status == "failed"` | `state == "failed"` bzw. `severity == 2` |
| `status == "pending"` | `state == "never_run"` oder `schedule.scheduled == false` |
| `last_run` | `last_run.at` bzw. `last_run.age_seconds` |
| `next_run == null` | `schedule.scheduled` und `schedule.next_run_at` |
| `interval` selbst parsen | `schedule.expected_interval_seconds`, `schedule.overdue` |
| Zweit-Call `/results` für Teilfehler | `last_run.folders_failed` |
| kein Fehlertext | `last_run.error`, `message` |
| eigene OK/Warn/Fehler-Logik | `severity` |
| hängender Lauf nicht erkennbar | `run.stuck`, `state == "stuck"` |

## Rezepte

### Nagios, Icinga, Checkmk

`check_http` wertet den Statuscode aus, deshalb `http_status=1`:

```bash
check_http -H nas -p 8080 -u "/api/monitor?http_status=1" \
  -k "Authorization: Bearer ssa_..." 
```

Alternativ mit eigenem Plugin über den Header:

```bash
curl -sD- -o/dev/null -H "Authorization: Bearer ssa_..." \
  http://nas:8080/api/monitor | awk -F': ' '/^x-ssa-severity/{exit $2}'
```

Der Exit-Code entspricht dann direkt der Nagios-Konvention.

### Zabbix

HTTP-Agent-Item auf `http://nas:8080/api/monitor/scans/design-scan` mit dem
Header `Authorization: Bearer ssa_...`. Dann als abhängige Items:

| Item | JSONPath | Typ |
|---|---|---|
| Schweregrad | `$.severity` | Numerisch, mit Trigger `last()>=2` |
| Zustand | `$.state` | Text, mit Value-Map |
| Meldung | `$.message` | Text, für den Alarmtext |
| Größe | `$.last_success.total_bytes` | Numerisch, für Graphen |

### Grafana

Infinity-Datasource, Typ JSON, URL `/api/monitor/scans`, Root
`$.scans` — die Felder `severity`, `state`, `scan.name` und
`last_success.total_bytes` sind direkt als Spalten nutzbar.

### Uptime-Kuma, Docker-Healthcheck

```bash
curl -fsS -H "Authorization: Bearer ssa_..." \
  "http://nas:8080/api/monitor?http_status=1" > /dev/null
```

### Shell

```bash
curl -s -H "Authorization: Bearer ssa_..." http://nas:8080/api/monitor \
  | jq -e '.severity < 2' > /dev/null || echo "SSA meldet ein Problem"
```

Namen der auffälligen Jobs:

```bash
curl -s -H "Authorization: Bearer ssa_..." \
  "http://nas:8080/api/monitor/scans?include_scans=0" \
  | jq -r '.problems[] | "\(.severity) \(.slug): \(.message)"'
```

## Gut zu wissen

- Alle Felder sind **immer** vorhanden; Unbekanntes ist `null`. Ein
  JSONPath-Ausdruck bricht dadurch nie zustandsabhängig weg.
- `severity` ist monoton und kennt nur 0, 1 und 2 — `UNKNOWN(3)` wird nie
  geliefert.
- Messwerte stammen vom letzten **erfolgreichen** Lauf, die Ordnerbilanz vom
  letzten Lauf.
- Ein laufender Scan verschlechtert die Severity nie und setzt die
  Überfälligkeit aus — es sei denn, er hängt (`state: "stuck"`).
- Der Abbruch wirkt nicht sofort: er ist kooperativ und greift beim nächsten
  Prüfpunkt des Laufs.
- Die Alters-Schwellwerte sind `2x` bzw. `3x` des erwarteten Intervalls, mit
  einer Untergrenze von `Intervall + 300 s` bzw. `+ 600 s` — damit
  Minuten-Jobs bei kleinem Verzug nicht flattern.
- Deaktivierte Jobs haben keine Alters-Schwellwerte und alarmieren nie.
- Ein einzelner nicht auswertbarer Job wird zu `state: "error"` und lässt die
  Sammel-Endpoints weiterlaufen. Details stehen nur im Server-Log, nicht in der
  Antwort — sie erreicht Inhaber eingeschränkter Monitoring-Tokens.
