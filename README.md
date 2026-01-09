# Synology Space Analyzer

Ein Python-Projekt zur Analyse von Verzeichnisgrößen und Statistiken auf einem Synology NAS über die File Station API.

## Features

- Authentifizierung mit der Synology API
- Auflisten von freigegebenen Ordnern
- Berechnung von Verzeichnisgrößen
- Abrufen von Volume-Informationen
- Erkundung von Verzeichnisstrukturen
- **Verbesserte interaktive Auswahl** mit Tastatur-Navigation
- **Mehrstufige Subfolder-Navigation** (bis zu 4 Ebenen tief)
- **Scan-Option für aktuellen Ordner** - Scannen auch wenn keine Unterordner vorhanden sind
- **Rich Progress Indicator** mit Spinner und Echtzeit-Anzeige während des Scans
- **Optimierte Ausgaben** - Kompakte, nicht-redundante Anzeige der Ergebnisse
- JSON-Output für Automatisierung
- Schnelle Auflistung aller verfügbaren Shares mit `--list-shares`
- Direkte Pfad-Angabe mit `--path` für präzise Kontrolle

## Installation

1. Python 3.7+ erforderlich

2. Abhängigkeiten installieren:
```bash
pip install -r requirements.txt
```

## Konfiguration

### Zugangsdaten mit .env Datei

1. Kopieren Sie `.env.example` zu `.env`:
```bash
cp .env.example .env
```

2. Bearbeiten Sie `.env` und tragen Sie Ihre Zugangsdaten ein:
```env
SYNO_HOST=192.168.1.100
SYNO_USERNAME=admin
SYNO_PASSWORD=your_password_here
SYNO_VERIFY_SSL=false  # Bei selbst-signierten Zertifikaten
```

Die `.env` Datei ist bereits in `.gitignore` und wird nicht in Git committed.

### Unterstützte Umgebungsvariablen

**Erforderlich:**
- `SYNO_HOST` oder `SYNO_NAS_HOST` oder `NAS_IP` - Hostname/IP des NAS
- `SYNO_USERNAME` oder `SYNO_USER` oder `SYNO_ACCOUNT` - Benutzername
- `SYNO_PASSWORD` oder `SYNO_PW` oder `SYNO_PASSWD` - Passwort

**Optional:**
- `SYNO_MAX_PARALLEL_TASKS` - Maximale parallele Tasks (Standard: 3, Bereich: 1-10)
- `SYNO_DEFAULT_EXECUTION_MODE` - Standard-Modus (`parallel` oder `sequential`)
- `SYNO_VERIFY_SSL` - SSL-Verifizierung (`true`/`false`, Standard: `true`)
- `SYNO_INSECURE` - Alternative zu `SYNO_VERIFY_SSL=false` (`true`/`false`)

## Übersicht der Optionen

### Optionen-Matrix

| Option | Beschreibung | Wann verwenden | JSON-Modus |
|--------|--------------|---------------|------------|
| `--share` | Spezifische Freigabe | Wenn du genau weißt, welche Freigabe du scannen willst | ✅ |
| `--folder` | Spezifischer Ordner | Für einzelne Ordner innerhalb einer Freigabe | ✅ |
| `--include-subfolders` | Nur Unterordner analysieren | Wenn du einzelne Unterordner vergleichen willst | ✅ |
| `--json` | JSON-Output | Für Automatisierung, Skripte, Weiterverarbeitung | ✅ |
| `--mode sequential` | Einzeln nacheinander | Bei instabiler Verbindung oder zum Debuggen | ✅ |
| `--insecure` | SSL-Verifizierung deaktivieren | Nur bei selbst-signierten Zertifikaten | ✅ |
| `--volumes` | Volume-Informationen anzeigen | Für Storage-Übersicht | ✅ |
| `--list-shares` | Nur Shares auflisten | Für schnelle Übersicht ohne Analyse | ✅ |

### Entscheidungsbaum: Welche Optionen verwenden?

```
Start
│
├─ Willst du JSON-Output? → --json
│
├─ Weißt du genau, was du scannen willst?
│  ├─ Ja, eine Freigabe → --share <name>
│  │  ├─ Nur die Freigabe selbst → (keine weiteren Optionen)
│  │  ├─ Nur Unterordner einzeln → --include-subfolders
│  │  └─ Spezifischer Ordner → --folder <name>
│  │
│  └─ Nein, willst explorieren → (keine Optionen, interaktiv)
│
└─ Hast du SSL-Probleme? → --insecure
```

## Beste Kombinationen

### 🎯 Für interaktive Nutzung (Standard)

```bash
# Einfach starten - interaktive Auswahl aller Optionen
python explore_syno_api.py
```

**Vorteile:**
- ✅ Maximale Flexibilität
- ✅ Siehst alle verfügbaren Shares/Ordner
- ✅ Kannst jederzeit Unterordner auswählen
- ✅ Tastatur-Navigation für einfache Auswahl
- ✅ Mehrstufige Navigation durch Ordnerstrukturen
- ✅ **Beste für:** Exploration und einmalige Analysen

**Ablauf:**
1. Interaktive Auswahl der Shares (mit Tastatur-Navigation)
2. Optionale Frage: "Sollen auch Unterordner analysiert werden?"
3. Bei "ja": Mehrstufige Navigation durch Unterordner möglich
4. Analyse der ausgewählten Shares/Unterordner

### 🚀 Für schnelle Analyse einer Freigabe

```bash
# Gesamte Freigabe scannen (inkl. aller Unterordner)
python explore_syno_api.py --share homes
```

**Vorteile:**
- ✅ Schnell und direkt
- ✅ Keine Interaktion nötig
- ✅ Gut für regelmäßige Checks
- ✅ **Beste für:** Regelmäßige Überwachung

### 📊 Für detaillierte Unterordner-Analyse

```bash
# Nur Unterordner einer Freigabe analysieren (interaktiv auswählbar)
python explore_syno_api.py --share homes --include-subfolders
```

**Vorteile:**
- ✅ Siehst Größe jedes Unterordners einzeln
- ✅ Kannst gezielt bestimmte Ordner auswählen
- ✅ Mehrstufige Navigation möglich
- ✅ **Ideal für:** "Welcher Benutzer nutzt am meisten Speicher?"

### 🤖 Für Automatisierung/Skripte

```bash
# JSON-Output für Weiterverarbeitung
python explore_syno_api.py --share homes --include-subfolders --json > results.json

# Alle Shares auflisten (ohne Analyse)
python explore_syno_api.py --list-shares --json
```

**Vorteile:**
- ✅ Maschinenlesbar
- ✅ Einfach zu parsen
- ✅ Ideal für Monitoring, Reporting, Alerts
- ✅ **Beste für:** CI/CD Pipelines, Automatisierung

### 🔍 Für spezifische Ordner

```bash
# Nur einen bestimmten Ordner analysieren
python explore_syno_api.py --share homes --folder max.mustermann
```

**Vorteile:**
- ✅ Sehr schnell
- ✅ Minimaler API-Overhead
- ✅ Gut für gezielte Checks
- ✅ **Beste für:** Einzelne Ordner-Analysen

## Praktische Anwendungsfälle

### Anwendungsfall 1: "Welcher Benutzer nutzt am meisten Speicher?"

```bash
# Beste Kombination:
python explore_syno_api.py --share homes --include-subfolders --json | \
  jq 'sort_by(.total_size.bytes) | reverse | .[0:5]'
```

**Ergebnis:** Top 5 Benutzer nach Speicherverbrauch

### Anwendungsfall 2: "Regelmäßiger Check aller Shares"

```bash
# Beste Kombination:
python explore_syno_api.py --json > daily_report_$(date +%Y%m%d).json
```

**Ergebnis:** Täglicher Report als JSON-Datei

### Anwendungsfall 3: "Schneller Überblick über alle Shares"

```bash
# Beste Kombination:
python explore_syno_api.py --list-shares
```

**Ergebnis:** Liste aller verfügbaren Shares ohne Analyse

### Anwendungsfall 4: "Detaillierte Analyse mit interaktiver Auswahl"

```bash
# Beste Kombination:
python explore_syno_api.py
# Dann interaktiv Shares und Unterordner auswählen
```

**Ergebnis:** Maximale Flexibilität mit Tastatur-Navigation

### Anwendungsfall 5: "Mehrstufige Ordnerstruktur analysieren"

```bash
# Beste Kombination:
python explore_syno_api.py --share backup --include-subfolders
# Dann in der interaktiven Auswahl:
# - Nummer eingeben zum Auswählen
# - "Nummer e" zum Eintreten in Unterordner (z.B. "1 e")
# - "z" zum Zurückgehen
```

**Ergebnis:** Navigation durch verschachtelte Ordnerstrukturen

## JSON vs. Nicht-JSON: Wann was?

### JSON-Modus (`--json`)

**Verwende wenn:**
- ✅ Automatisierung und Skripte
- ✅ Weiterverarbeitung mit jq, Python, etc.
- ✅ Logging und Monitoring
- ✅ CI/CD Pipelines
- ✅ JSON-Output für weitere Verarbeitung

**Wichtige Hinweise:**
- ✅ **Gleiche UI wie im interaktiven Modus**: Im JSON-Modus wird die gleiche interaktive UI verwendet (Multi-Select mit Checkbox für Freigaben, interaktive Navigation für Unterordner)
- ✅ **Ausgabe ist JSON**: Die Ergebnisse werden als JSON ausgegeben, aber die Auswahl erfolgt über die gleiche UI
- ✅ **`--all` überspringt UI**: Mit `--json --all` werden alle Freigaben automatisch gescannt ohne UI-Interaktion

**Beispiele:**
```bash
# Interaktive Auswahl mit JSON-Output
python explore_syno_api.py --json
# Zeigt die gleiche UI wie ohne --json, aber Ausgabe ist JSON

# Automatisch alle Freigaben scannen (ohne UI)
python explore_syno_api.py --json --all | jq '.[] | select(.total_size.bytes > 1000000000)'

# Spezifische Freigabe mit JSON-Output
python explore_syno_api.py --share homes --json | jq '.[] | select(.total_size.bytes > 1000000000)'
```

### Interaktiver Modus (ohne `--json`)

**Verwende wenn:**
- ✅ Manuelle Analyse
- ✅ Exploration und Entdeckung
- ✅ Farbige, formatierte Ausgabe
- ✅ Interaktive Auswahl mit Tastatur-Navigation
- ✅ Rich Progress Indicator mit Spinner und Echtzeit-Anzeige

**Beispiel:**
```bash
python explore_syno_api.py
# Siehst:
# - Farbige Tabellen
# - Live Progress Indicator mit Spinner während des Scans
# - Kompakte Ergebnisanzeige nach Abschluss
```

**Progress Indicator zeigt:**
- 🔄 Animierter Spinner
- 📊 Fortschrittsbalken
- 📈 Prozentsatz (z.B. "60%")
- ⏱️ Verstrichene Zeit in Echtzeit
- 📝 Aktuell analysierter Ordner

## Subfolder-Optionen erklärt

### `--include-subfolders` MIT `--share`

```bash
python explore_syno_api.py --share homes --include-subfolders
```

**Verhalten:**
- Zeigt **nur** die Unterordner von `homes`
- Interaktive Auswahl möglich
- Mehrstufige Navigation möglich
- Die Freigabe selbst wird **nicht** analysiert

**Beste für:** Vergleich einzelner Unterordner

### `--include-subfolders` OHNE `--share`

```bash
python explore_syno_api.py --include-subfolders
```

**Verhalten:**
- Zeigt Unterordner aller ausgewählten Freigaben
- Alle Unterordner werden automatisch gescannt (keine Auswahl)
- Keine mehrstufige Navigation

**Beste für:** Schnelle Analyse aller Unterordner mehrerer Shares

### OHNE `--include-subfolders` MIT `--share`

```bash
python explore_syno_api.py --share homes
```

**Verhalten:**
- Analysiert die **gesamte** Freigabe inkl. aller Unterordner
- Keine separate Auswahl der Unterordner
- Schnellste Option

**Beste für:** Gesamtgröße einer Freigabe

### Standard-Modus (ohne Optionen)

```bash
python explore_syno_api.py
```

**Verhalten:**
- Interaktive Auswahl der Shares
- Optionale Frage nach Unterordnern
- Maximale Flexibilität
- Tastatur-Navigation verfügbar
- Mehrstufige Navigation möglich

**Beste für:** Exploration und einmalige Analysen

## Interaktive Auswahl mit Pfeiltasten-Navigation

Das Tool verwendet jetzt **Pfeiltasten-Navigation** für eine bessere Benutzererfahrung. Alle Auswahl-Dialoge unterstützen Pfeiltasten zum Navigieren.

### Navigation in der Share-Auswahl

```
Verfügbare Freigaben
┌─────┬─────────────┬──────────┐
│ Nr. │ Name        │ Größe    │
├─────┼─────────────┼──────────┤
│  1  │ homes       │ 500 GB   │
│  2  │ backup      │ 1.2 TB   │
│  3  │ media       │ 800 GB   │
└─────┴─────────────┴──────────┘

Navigation mit Pfeiltasten:
  ↑↓    - Durch Items navigieren
  Leertaste - Item auswählen/abwählen
  Enter - Auswahl bestätigen
```

### Navigation in der Subfolder-Auswahl

Wenn du `--share` mit `--include-subfolders` verwendest oder im Standard-Modus nur eine Freigabe auswählst, erscheint eine **einheitliche Navigationsliste**:

```
Ebene 1: /homes
┌─────┬──────────────────┐
│     │ Ordner           │
├─────┼──────────────────┤
│ 📂  │ max.mustermann   │
│ 📂  │ anna.schmidt     │
├─────┼──────────────────┤
│ 🔍  │ Aktuellen Ordner scannen │
├─────┼──────────────────┤
│ ←   │ Zurück zu Freigaben │
└─────┴──────────────────┘
```

### Navigation erklärt

#### 1. **Ordner öffnen (📂)**
- **Navigation:** ↑↓ Pfeiltasten zum Navigieren, Enter zum Eintreten
- **Verhalten:**
  - Wenn der Ordner Unterordner hat: Zeigt die nächste Ebene
  - Wenn der Ordner keine Unterordner hat: Wird automatisch für Analyse ausgewählt
- **Verwendung:** Tiefer in die Ordnerstruktur navigieren

#### 2. **Aktuellen Ordner scannen (🔍)**
- **Verfügbar:** Immer, sowohl wenn Unterordner vorhanden sind als auch wenn nicht
- **Navigation:** ↑↓ Pfeiltasten zum Navigieren, Enter zum Auswählen
- **Verwendung:** Den aktuell angezeigten Ordner direkt für die Analyse auswählen
- **Vorteil:** Du kannst jederzeit den aktuellen Ordner scannen, ohne tiefer navigieren zu müssen

#### 3. **Zurück**
- **Verfügbar:** 
  - "← Zurück" wenn du nicht auf Ebene 1 bist
  - "← Zurück zu Freigaben" wenn du auf Ebene 1 bist
- **Verwendung:** Zurück zur vorherigen Ebene oder zur Freigabe-Auswahl

### Besonderheiten

- **Keine Unterordner:** Wenn ein Ordner keine Unterordner hat, wird automatisch nur die "🔍 Aktuellen Ordner scannen" Option angezeigt
- **Mit Unterordnern:** Du kannst sowohl in Unterordner navigieren als auch den aktuellen Ordner scannen
- **Mehrstufig:** Navigation bis zu 4 Ebenen tief möglich

### Mehrstufige Navigation - Beispiel-Workflow

```
Ebene 1: /homes
Ordner: max.mustermann, anna.schmidt

→ "max.mustermann" wählen (↑↓ Pfeiltasten, Enter)
→ Zeigt Ebene 2: /homes/max.mustermann

Ebene 2: /homes/max.mustermann
Ordner: Documents, Pictures, Videos

→ "Documents" wählen (↑↓ Pfeiltasten, Enter)
→ Zeigt Ebene 3: /homes/max.mustermann/Documents

Ebene 3: /homes/max.mustermann/Documents
(Keine weiteren Unterordner)

→ "🔍 Aktuellen Ordner scannen" wählen (↑↓ Pfeiltasten, Enter)
→ Ordner wird für Analyse ausgewählt
→ Zurück zu Ebene 2

Ebene 2: /homes/max.mustermann
→ "← Zurück" wählen
→ Zurück zu Ebene 1

Ebene 1: /homes
→ "🔍 Aktuellen Ordner scannen" wählen
→ Auch /homes wird für Analyse ausgewählt

Ergebnis: /homes/max.mustermann/Documents und /homes werden analysiert
```

### Tastenkombinationen Übersicht

| Tastenkombination | Funktion | Wo verwendet |
|-------------------|----------|--------------|
| **↑↓** | Navigieren | Überall (Menüs, Listen) |
| **Leertaste** | Auswählen/Abwählen | Multi-Select Listen |
| **Enter** | Bestätigen | Alle Dialoge |
| **Ctrl+C** | Abbrechen | Überall |

### Vorteile der Pfeiltasten-Navigation

- ✅ **Intuitiv**: Standard-Navigation wie in modernen CLI-Tools
- ✅ **Schnell**: Keine Tippfehler durch Nummerneingabe
- ✅ **Visuell**: Siehst sofort, was ausgewählt ist
- ✅ **Mehrstufig**: Einfache Navigation durch Ordnerstrukturen
- ✅ **Multi-Select**: Mehrere Items gleichzeitig auswählen

## Kommandozeilen-Optionen (Detailliert)

### Basis-Verwendung

```bash
# Standard: Interaktive Auswahl der Freigaben
python explore_syno_api.py

# JSON-Ausgabe
python explore_syno_api.py --json

# Sequenzieller Modus statt parallel
python explore_syno_api.py --mode sequential

# Volume-Informationen anzeigen
python explore_syno_api.py --volumes

# Alle verfügbaren Shares auflisten (ohne Analyse)
python explore_syno_api.py --list-shares

# Alle verfügbaren Shares als JSON auflisten
python explore_syno_api.py --list-shares --json
```

### Direkte Angabe von Freigaben und Ordnern

```bash
# Spezifische Freigabe scannen (scannt die gesamte Freigabe inkl. aller Unterordner)
python explore_syno_api.py --share share_name

# Spezifischen Ordner innerhalb einer Freigabe scannen
python explore_syno_api.py --share share_name --folder folder_name

# Beispiel: Nur den Ordner "user1" innerhalb der Freigabe "homes" scannen
python explore_syno_api.py --share homes --folder user1

# Direkte Pfad-Angabe (mehrere Pfade möglich)
python explore_syno_api.py --path homes/user1/Documents
python explore_syno_api.py --path homes/user1/Documents homes/user2/Projects

# Beispiel: Mehrere Pfade gleichzeitig scannen (getrennt durch Leerzeichen)
python explore_syno_api.py --path share1/folder1 share2/folder2/subfolder

# Alternative: Komma-separierte Liste (nützlich für Pfade mit Leerzeichen)
python explore_syno_api.py --path share1/folder1,share2/folder2/subfolder

# Pfade mit Leerzeichen: Entweder Anführungszeichen oder Komma-separiert
python explore_syno_api.py --path "homes/My Documents" "homes/My Projects"
python explore_syno_api.py --path "homes/My Documents,homes/My Projects"
```

**Vorteile von `--path`:**
- ✅ Präzise Kontrolle über exakte Pfade
- ✅ Mehrere Pfade in einem Befehl (getrennt durch Leerzeichen oder Komma)
- ✅ Flexible Eingabe: Unterstützt sowohl mehrere Argumente als auch Komma-separierte Listen
- ✅ Einfaches Handling von Leerzeichen: Komma-separiert oder Anführungszeichen
- ✅ Keine unnötigen Meldungen (optimierte Ausgabe)
- ✅ Ideal für Skripte und Automatisierung

### Unterordner-Analyse

**Mit einem einzelnen Share (`--share`):**
```bash
# Unterordner einer Freigabe interaktiv auswählen
# Zeigt eine Liste aller Unterordner zur Auswahl an
# Mehrstufige Navigation möglich
python explore_syno_api.py --share share_name --include-subfolders
```

**Mit mehreren Shares (ohne `--share`):**
```bash
# Alle Unterordner aller ausgewählten Freigaben automatisch scannen
# Zuerst werden Freigaben ausgewählt, dann werden alle deren Unterordner automatisch gescannt
python explore_syno_api.py --include-subfolders
```

**Wichtiger Unterschied:**
- **Mit `--share`**: Interaktive Auswahl der Unterordner mit mehrstufiger Navigation
- **Ohne `--share`**: Alle Unterordner werden automatisch gescannt (keine weitere Auswahl)

### Verfügbare Optionen

- `--json`, `-j`: Ausgabe als JSON (Größe in Bytes, Einheit separat)
- `--mode`, `-m`: Ausführungsmodus (`parallel` oder `sequential`)
- `--volumes`, `-v`: Zeige Volume-Informationen an
- `--all`, `-a`: Scanne alle Freigaben automatisch (nur im JSON-Modus, überspringt UI komplett)
- `--share`, `-s`: Direkte Angabe einer Freigabe (Share-Name)
- `--folder`, `-f`: Direkte Angabe eines Ordners innerhalb einer Freigabe (benötigt `--share`)
- `--path`, `-p`: Direkte Angabe von vollständigen Pfaden (z.B. `share/folder/subfolder`)
  - Mehrere Pfade möglich: `--path path1 path2 path3` oder `--path path1,path2,path3`
  - Unterstützt sowohl mehrere Argumente (getrennt durch Leerzeichen) als auch Komma-separierte Listen
  - Für Pfade mit Leerzeichen: Anführungszeichen verwenden oder Komma-separiert angeben
  - Optimierte Ausgabe ohne unnötige Meldungen
- `--include-subfolders`: Analysiere Unterordner statt der Freigaben selbst
  - Mit `--share`: Interaktive Auswahl der Unterordner mit mehrstufiger Navigation
  - Ohne `--share`: Alle Unterordner werden automatisch gescannt
- `--list-shares`: Listet lediglich alle verfügbaren Shares auf (ohne Analyse)
- `--insecure`: Deaktiviere SSL-Zertifikat-Verifizierung (nur für selbst-signierte Zertifikate)

## Zusammenfassung: Wann wird was gescannt?

| Parameter | Was wird gescannt | Interaktiv? |
|----------|-------------------|-------------|
| Keine Parameter | Freigaben (interaktive Auswahl) → Optionale Frage nach Unterordnern → scannt gesamte Freigabe inkl. aller Unterordner ODER nur ausgewählte Unterordner | ✅ Ja, mit Navigation |
| `--list-shares` | Zeigt nur alle verfügbaren Shares an (keine Analyse) | ❌ Nein |
| `--share share_name` | Die gesamte Freigabe `share_name` inkl. aller Unterordner | ❌ Nein |
| `--share share_name --folder folder_name` | Nur der spezifische Ordner `folder_name` innerhalb von `share_name` | ❌ Nein |
| `--path path1 path2 ...` | Die angegebenen vollständigen Pfade (z.B. `homes/user1/Documents`) | ❌ Nein |
| `--json` | Interaktive Auswahl mit JSON-Output (gleiche UI wie ohne --json) | ✅ Ja, mit Navigation |
| `--json --all` | Alle Freigaben automatisch scannen (ohne UI, nur JSON-Output) | ❌ Nein |
| `--share share_name --include-subfolders` | **Nur** die Unterordner von `share_name` (interaktive Auswahl mit mehrstufiger Navigation) | ✅ Ja, mit Navigation |
| `--include-subfolders` (ohne `--share`) | **Nur** die Unterordner aller ausgewählten Freigaben (automatisch, keine Auswahl) | ⚠️ Teilweise (nur Share-Auswahl) |

**Hinweise:**
- Wenn Sie eine Freigabe ohne `--include-subfolders` scannen, werden automatisch alle Unterordner mit einbezogen. Mit `--include-subfolders` werden nur die Unterordner einzeln analysiert, nicht die Freigabe selbst.
- Im **Standard-Modus** (ohne Parameter) wird nach der Share-Auswahl optional gefragt, ob auch Unterordner analysiert werden sollen. Bei "ja" können die Unterordner interaktiv ausgewählt werden mit mehrstufiger Navigation.

## API-Endpunkte

Das Script nutzt folgende Synology File Station API Methoden:

- `SYNO.API.Auth` - Authentifizierung
- `SYNO.FileStation.Info` - Volume-Informationen
- `SYNO.FileStation.List` - Verzeichnis- und Dateiauflistung
- `SYNO.FileStation.DirSize` - Verzeichnisgrößenberechnung (start, status, stop)

## Optimierungen für Synology API

Das Script wurde optimiert, um besser mit der Synology API zu arbeiten:

### Rate Limiting
- **Automatisches Rate Limiting**: Mindestens 500ms zwischen API-Calls
- **Retry-Logik**: Automatische Wiederholung bei Rate-Limit-Fehlern (429, 503)
- **Retry-After Header**: Respektiert Server-Anweisungen für Wartezeiten
- **Jitter**: Zufällige Variationen bei Retries zur Vermeidung synchronisierter Requests
- **Exponentielles Backoff**: Längere Wartezeiten bei wiederholten Fehlern

### Task-Management
- **Längere Timeouts**: 5 Minuten statt 30 Sekunden für große Verzeichnisse
- **Adaptive Polling**: Dynamische Polling-Intervalle (2s-10s) basierend auf Fortschritt
- **Task-Abbruch**: Automatisches Abbrechen von Tasks bei Timeout
- **Task-Cleanup**: Automatische Bereinigung aller aktiven Tasks beim Logout
- **Intelligentes Polling**: Status-Checks mit adaptiven Intervallen

### Fehlerbehandlung
- **Bessere Fehlermeldungen**: Detaillierte Fehlerinformationen
- **Timeout-Handling**: Graceful Handling von Timeouts mit Task-Abbruch
- **Retry-Mechanismus**: Automatische Wiederholung bei temporären Fehlern
- **Unterscheidung**: Permanente vs. temporäre Fehler

### Performance
- **Bounded Concurrency**: ThreadPoolExecutor mit konfigurierbarer Parallelität
- **Optimierte API-Calls**: Reduzierte Anzahl unnötiger Calls
- **Session-Management**: Effiziente Session-Verwaltung
- **Rich Progress Indicator**: Live-Fortschrittsanzeige mit Spinner, Fortschrittsbalken, Prozentsatz und Echtzeit-Anzeige während des gesamten Scans
- **Optimierte Ausgaben**: Kompakte, nicht-redundante Anzeige der Ergebnisse
- **Intelligente Meldungen**: Nur relevante Meldungen werden angezeigt (z.B. keine "Lade Freigaben..." Meldung bei `--path` oder `--share`)

## Sicherheit

### SSL/TLS-Verifizierung

**Standard:** SSL-Verifizierung ist **aktiviert** (sicher)

**Für selbst-signierte Zertifikate:**
```bash
# Option 1: CLI-Flag
python explore_syno_api.py --insecure

# Option 2: Umgebungsvariable in .env
SYNO_VERIFY_SSL=false
# oder
SYNO_INSECURE=true
```

⚠️ **Wichtig**: Deaktiviere SSL-Verifizierung nur bei selbst-signierten Zertifikaten in vertrauenswürdigen Netzwerken!

### Datei-Permissions

Die `.env` Datei wird automatisch mit restriktiven Permissions (0600) gespeichert, sodass nur der Besitzer lesen/schreiben kann.

## FastAPI Webserver

Das Projekt enthält jetzt einen FastAPI-basierten Webserver, der automatisches Scheduling von Scans und eine REST API bietet.

### Features des Webservers

- **REST API** für Scan-Ergebnisse (JSON mit Timestamp)
- **HTML-Formular** für Status-Übersicht und Ergebnis-Anzeige
- **Automatisches Scheduling** mit APScheduler (Cron-Format oder einfaches Interval-Format wie "30s", "5m", "1h")
- **YAML-Konfiguration** für Scan-Tasks mit NAS-Zugangsdaten pro Task
- **In-Memory Storage** für Scan-Ergebnisse mit Timestamp

### Installation und Start

1. **Abhängigkeiten installieren:**
```bash
pip install -r requirements.txt
```

2. **Konfigurationsdatei erstellen:**
Erstelle eine `config.yaml` Datei im Projekt-Root:

```yaml
scans:
  - name: "homes_scan"
    nas:
      host: "192.168.1.100"
      username: "admin"
      password: "password123"
      port: null                    # Optional: Port (null = automatisch)
      use_https: true               # HTTPS verwenden
      verify_ssl: false            # SSL-Verifizierung deaktivieren
    shares:                        # Liste von Freigaben
      - "homes"
    folders: null                  # Optional: Liste von Ordnern
    paths: null                    # Optional: Liste von vollständigen Pfaden
    interval: "0 */6 * * *"        # Alle 6 Stunden (Cron-Format) oder "6h" (Interval-Format)
    enabled: true
```

3. **Server starten:**
```bash
# Mit uvicorn direkt
uvicorn app.main:app --host 0.0.0.0 --port 8000

# Oder mit Python
python -m app.main
```

Der Server läuft dann auf `http://localhost:8000`

### Konfiguration (config.yaml)

Die `config.yaml` Datei definiert alle Scan-Tasks mit ihren NAS-Zugangsdaten und Scheduling-Intervallen.

#### Struktur

```yaml
scans:
  - name: "eindeutiger_scan_name"
    nas:
      host: "192.168.1.100"      # NAS IP oder Hostname
      username: "admin"           # Benutzername
      password: "password123"     # Passwort
      port: null                  # Optional: Port (null = automatisch: 5001 für HTTPS, 5000 für HTTP)
      use_https: true             # Ob HTTPS verwendet werden soll (true = HTTPS, false = HTTP)
      verify_ssl: false           # SSL-Verifizierung (true/false)
    shares:                       # Optional: Liste von Freigabe-Namen
      - "homes"
      - "backup"
    folders: null                 # Optional: Liste von Ordnern (nur mit 1 Share möglich)
    paths: null                   # Optional: Liste von vollständigen Pfaden (z.B. ["homes/user1/Documents", "homes/user2"])
    interval: "0 */6 * * *"       # Cron-Format Intervall (Alternative: "6h" für einfaches Format)
    enabled: true                 # Ob der Scan aktiviert ist
```

#### Pfad-Konfiguration

Die Konfiguration unterstützt mehrere Möglichkeiten, Pfade zu definieren:

1. **`paths`** (höchste Priorität) - Liste von vollständigen Pfaden
   ```yaml
   paths:
     - "homes/user1/Documents"
     - "homes/user2/Music"
   ```

2. **`shares` + `folders`** - Alle Kombinationen werden gescannt
   ```yaml
   shares: ["homes"]
   folders: ["user1", "user2"]
   # Scant: /homes/user1, /homes/user2
   ```
   ⚠️ **Wichtig**: Bei `folders` darf nur **1 Share** in `shares` angegeben werden!

3. **`shares`** (ohne `folders`) - Alle angegebenen Shares werden gescannt
   ```yaml
   shares:
     - "homes"
     - "backup"
   # Scant: /homes, /backup
   ```

4. **Kombinationen**: `shares` + `paths` oder `shares` + `folders` + `paths` sind möglich
   - Alle Pfade werden kombiniert und gescannt
   - Bei `folders` muss nur 1 Share angegeben sein

#### Validierungsregeln

- Mindestens `shares` **ODER** `paths` muss angegeben werden
- `folders` kann nur zusammen mit `shares` verwendet werden
- Wenn `folders` vorhanden ist, darf nur **1 Share** in `shares` angegeben werden
- Leere Listen sind nicht erlaubt

#### Interval-Format

Das `interval` Feld unterstützt zwei Formate:

**1. Cron-Format (Standard Cron-Syntax):**
```
minute hour day month day_of_week
```

Cron-Beispiele:
- `"0 */6 * * *"` - Alle 6 Stunden
- `"0 2 * * *"` - Täglich um 2 Uhr
- `"0 0 * * 0"` - Jeden Sonntag um Mitternacht
- `"*/30 * * * *"` - Alle 30 Minuten

**2. Interval-Format (Einfaches Format):**
Einfache Angabe mit Zahl und Einheit (s = Sekunden, m = Minuten, h = Stunden, d = Tage)

Interval-Beispiele:
- `"30s"` - Alle 30 Sekunden
- `"5m"` - Alle 5 Minuten
- `"1h"` - Alle 1 Stunde
- `"6h"` - Alle 6 Stunden
- `"12h"` - Alle 12 Stunden
- `"1d"` - Alle 1 Tag (täglich)

### API Endpunkte

#### GET `/api/scans`
Gibt eine Liste aller konfigurierten Scans mit Status zurück.

**Response:**
```json
{
  "scans": [
    {
      "scan_name": "homes_scan",
      "status": "completed",
      "last_run": "2024-01-15T14:30:00Z",
      "next_run": "2024-01-15T20:30:00Z",
      "enabled": true
    }
  ]
}
```

#### GET `/api/scans/{scan_name}`
Gibt Details eines spezifischen Scans zurück.

#### GET `/api/scans/{scan_name}/status`
Gibt den Status eines Scans zurück (Alias für `/api/scans/{scan_name}`).

#### GET `/api/scans/{scan_name}/results`
Gibt die Ergebnisse eines Scans zurück (JSON mit Timestamp).

**Query Parameter:**
- `latest=true` (Standard) - Nur das neueste Ergebnis
- `latest=false` - Alle Ergebnisse

**Response:**
```json
{
  "scan_name": "homes_scan",
  "timestamp": "2024-01-15T14:30:00Z",
  "status": "completed",
  "results": [
    {
      "folder_name": "/homes",
      "success": true,
      "num_dir": 150,
      "num_file": 5000,
      "total_size": {
        "bytes": 1073741824,
        "formatted": 1.0,
        "unit": "GB"
      },
      "elapsed_time_ms": 5000
    }
  ]
}
```

#### GET `/api/scans/{scan_name}/history`
Gibt die komplette Historie aller Ergebnisse eines Scans zurück.

**Response:**
```json
{
  "scan_name": "homes_scan",
  "results": [
    {
      "scan_name": "homes_scan",
      "timestamp": "2024-01-15T14:30:00Z",
      "status": "completed",
      "results": [...]
    },
    {
      "scan_name": "homes_scan",
      "timestamp": "2024-01-15T08:30:00Z",
      "status": "completed",
      "results": [...]
    }
  ],
  "total_count": 2
}
```

#### POST `/api/scans/{scan_name}/trigger`
Startet einen Scan manuell.

**Response:**
```json
{
  "scan_name": "homes_scan",
  "message": "Scan 'homes_scan' wurde gestartet",
  "triggered": true
}
```

#### POST `/api/config/reload`
Lädt die Konfiguration manuell neu und aktualisiert alle Jobs im Scheduler.

**Response:**
```json
{
  "success": true,
  "message": "Konfiguration erfolgreich neu geladen",
  "added_scans": ["new_scan"],
  "updated_scans": ["existing_scan"],
  "removed_scans": ["old_scan"],
  "total_scans": 3
}
```

#### GET `/`
HTML-Formular für Status-Übersicht und Ergebnis-Anzeige.

#### GET `/health`
Health-Check Endpoint.

**Response:**
```json
{
  "status": "healthy",
  "scheduler_running": true
}
```

### Web-Interface

Das Web-Interface ist unter `http://localhost:8000` erreichbar und bietet:

- **Scan-Status Übersicht**: Zeigt alle konfigurierten Scans mit ihrem aktuellen Status
- **Ergebnis-Anzeige**: Formular zum Anzeigen der Scan-Ergebnisse
- **Automatische Aktualisierung**: Button zum manuellen Aktualisieren der Status-Übersicht

### Timestamp-Integration

Alle Scan-Ergebnisse enthalten einen Timestamp im ISO 8601 Format (`"timestamp": "2024-01-15T14:30:00Z"`). Der Timestamp wird automatisch beim Speichern der Ergebnisse hinzugefügt und ist in allen JSON-API-Responses enthalten.

### Storage

Die Scan-Ergebnisse werden in einem In-Memory Storage gespeichert. Standardmäßig werden die letzten 100 Scans pro Task gespeichert. Bei Server-Neustart gehen die Daten verloren.

**Verfügbare Operationen:**
- `GET /api/scans/{scan_name}/results?latest=true` - Neuestes Ergebnis
- `GET /api/scans/{scan_name}/results?latest=false` - Neuestes Ergebnis (alle werden zurückgegeben, aber nur das neueste ist relevant)
- `GET /api/scans/{scan_name}/history` - Komplette Historie aller Ergebnisse

### Scheduler

Der APScheduler startet automatisch beim Server-Start und plant alle aktivierten Scans basierend auf ihren Intervallen. Deaktivierte Scans (`enabled: false`) werden nicht geplant.

### Migration von .env zu config.yaml

Die NAS-Zugangsdaten werden jetzt in `config.yaml` pro Scan-Task konfiguriert. Die `.env` Datei kann weiterhin für globale Einstellungen verwendet werden (z.B. `SYNO_MAX_PARALLEL_TASKS`), wird aber für die NAS-Zugangsdaten nicht mehr benötigt.

**Wichtige Änderungen:**
- `share`, `folder` und `path` sind jetzt Listen (`shares`, `folders`, `paths`)
- `port` und `use_https` wurden hinzugefügt für bessere Kontrolle über HTTP/HTTPS
- Mehrere Shares können gleichzeitig konfiguriert werden
- Mehrere Pfade können gleichzeitig gescannt werden

### Entwicklung

Für Entwicklung mit Auto-Reload:
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Beispiele für config.yaml

### Beispiel 1: Einzelne Freigabe scannen
```yaml
scans:
  - name: "homes_scan"
    nas:
      host: "192.168.1.100"
      username: "admin"
      password: "password123"
      use_https: true
      verify_ssl: false
    shares:
      - "homes"
    interval: "0 */6 * * *"
    enabled: true
```

### Beispiel 2: Mehrere Freigaben scannen
```yaml
scans:
  - name: "all_shares_scan"
    nas:
      host: "192.168.1.100"
      username: "admin"
      password: "password123"
      use_https: true
      verify_ssl: false
    shares:
      - "homes"
      - "backup"
      - "media"
    interval: "0 2 * * *"
    enabled: true
```

### Beispiel 3: Mehrere Ordner innerhalb einer Freigabe
```yaml
scans:
  - name: "user_folders_scan"
    nas:
      host: "192.168.1.100"
      username: "admin"
      password: "password123"
      use_https: true
      verify_ssl: false
    shares:
      - "homes"  # WICHTIG: Nur 1 Share erlaubt bei folders!
    folders:
      - "user1"
      - "user2"
      - "user3"
    interval: "0 */12 * * *"
    enabled: true
```

### Beispiel 4: Mehrere vollständige Pfade
```yaml
scans:
  - name: "specific_paths_scan"
    nas:
      host: "192.168.1.100"
      username: "admin"
      password: "password123"
      use_https: true
      verify_ssl: false
    paths:
      - "homes/user1/Documents"
      - "homes/user2/Music"
      - "backup/daily"
    interval: "*/30 * * * *"
    enabled: true
```

### Beispiel 5: Kombination aus Shares und Pfaden
```yaml
scans:
  - name: "combined_scan"
    nas:
      host: "192.168.1.100"
      username: "admin"
      password: "password123"
      use_https: true
      verify_ssl: false
    shares:
      - "homes"
      - "backup"
    paths:
      - "media/movies"
    interval: "0 3 * * *"
    enabled: true
```

### Beispiel 6: HTTP-Verbindung (ohne HTTPS)
```yaml
scans:
  - name: "http_scan"
    nas:
      host: "192.168.1.100"
      username: "admin"
      password: "password123"
      port: 5000          # Port 5000 für HTTP
      use_https: false    # HTTP verwenden
      verify_ssl: false
    shares:
      - "public"
    interval: "0 4 * * *"
    enabled: true
```

## Nächste Schritte

- Erweiterte Statistiken sammeln
- Datenbank-Integration für historische Daten
- Erweiterte Web-UI mit Dashboard
- Automatische Berichte generieren
- Persistenter Storage für Ergebnisse

## Lizenz

Siehe LICENSE-Datei
