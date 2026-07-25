# Design — Synology Space Analyzer

Das Designsystem dieser App. Verbindlich für alle Ansichten: nicht pro Seite neu
erfinden, bei Bedarf hier erweitern.

## Haltung

Ein B2B-Infrastruktur-Werkzeug: REST-API, ⌘K-Palette, dichte Statustabelle.
Kein Marketing, keine Erzählung — ein Instrument. Zurückhaltend, präzise, schnell.

Konkret: kühl-weißes Papier, kühles Graphit für Text, **ein** blauer Signalakzent
unter 5 % je Ansicht, Hairlines statt Schatten, 6-px-Radien.

Die Werte liegen in `frontend/src/tokens.css`. Zwei Punkte, die beim Lesen
auffallen können:

- `--a-500` sitzt bei **L 52 %**. Erst dort trägt weiße Schrift auf der
  Akzentfläche 5.54:1. Die vorherige Primärfarbe kam auf 3.66:1 und lag damit
  unter WCAG AA.
- Der Dark Mode ist ein vollwertiger zweiter Modus, kein abgedunkelter Ausschnitt.

### Achsen

| Achse | Wert |
| --- | --- |
| Grundhelligkeit | hell (L 98.5 %) · dunkel (L 20 %) |
| Titelschrift | Grotesk-Sans (Space Grotesk 500/600, eng gesetzt) |
| Akzentton | Signalblau, Hue 257 |

## Aufbau der Ansichten

- **App-Ansichten:** Werkbank-Prinzip. Die Oberfläche zeigt Arbeit, nicht Aussagen —
  Tabelle, Filterleiste, Zeilenaktionen. Variieren dürfen: Dichte, Listen- gegen
  Kachelansicht, Spaltenauswahl.
- **Auth:** dasselbe Prinzip, auf eine Karte reduziert.
- **Overlays (Dialoge):** kein eigener Seitenaufbau. Sie tragen die
  Komponentenstimme: Inset-Kopf mit Hairline, Inhalt, Fußleiste mit Aktionen.

Marketing- oder Content-Seiten gibt es in diesem Projekt nicht. Kommt eine dazu,
wird dieses Kapitel erweitert — nicht lokal übersteuert.

## Typografie

Drei Rollen, drei Schnitte. Alle als woff2 unter
`frontend/src/assets/fonts/` (SIL Open Font License 1.1). **Kein CDN** — der Server
liefert das Frontend selbst aus, oft in einem Netz ohne Internetzugang.

- **Display:** Space Grotesk, 500/600, `letter-spacing: -0.02em`, immer aufrecht
- **Body:** Inter, 400/500
- **Mono:** JetBrains Mono, 400/500 — für **jede Maschinenangabe**: IDs, Größen,
  Zeitstempel, Statuslabels, Tastenkürzel, Spaltenköpfe

Versal-Mono-Labels tragen `letter-spacing: 0.06em` (Klasse `.label-mono`).
Kursive Überschriften sind projektweit ausgeschlossen.

## Farbe

Rampen in `tokens.css` als OKLCH-Komponenten, damit Tailwinds Alpha-Modifier greifen.
Die Tailwind-Rampen `slate`, `primary`, `blue`, `emerald`, `green`, `amber`, `yellow`
und `red` sind auf diese Tokens **umgebogen** (`frontend/tailwind.config.js`) — so gilt
das System in allen bestehenden Aufrufen.

Es gibt **einen** Akzent und **drei** Statusfarben. `green` zeigt auf `emerald`,
`yellow` auf `amber`, `blue` auf den Akzent. `purple`, `violet`, `indigo` und `cyan`
sind bewusst nicht definiert.

`bg-white` ist ein kühles Beinahe-Weiß (`oklch(99.4% 0.003 250)`), nicht `#fff`.

Alle Paarungen sind gegen WCAG AA gerechnet: Fließtext ≥ 4.5:1, Icons und Fokusringe
≥ 3:1 — in beiden Modi.

## Abstände

4-pt-Skala, benannt (`--space-3xs` … `--space-3xl`) in `tokens.css`.
Neuer Code referenziert Tokens, keine Rohwerte.

## Radien

`--radius-inset: 4px` · `--radius-control: 6px` · `--radius-card: 10px`.
Keine Pillen, keine 0-px-Brutalität.

## Motion

- Easings: `--ease-out` `cubic-bezier(0.16,1,0.3,1)`, dazu `--ease-in`, `--ease-in-out`.
  Der Browser-Default `ease` wird nicht verwendet.
- Dauern: `--dur-instant 100ms` (Hover) · `--dur-short 180ms` (Zustand) ·
  `--dur-medium 320ms` (Overlay, Fortschritt)
- `transition-all` ist verboten. Eigenschaften werden benannt.
- Fokusringe erscheinen sofort und werden nie animiert.
- Keine Dauerschleifen als Statusanzeige. Ein laufender Scan trägt einen ruhigen
  Punkt plus seinen Fortschrittsbalken — nicht zusätzlich einen Puls.
- `prefers-reduced-motion: reduce` schaltet Animationen global ab und kürzt
  Übergänge auf 150 ms Blende (`index.css`).

## Microinteractions

- **Stiller Erfolg.** Kein Toast für etwas, das man sieht. Zeile verschwindet,
  Liste aktualisiert sich, Dialog schließt — das ist die Quittung.
  Gemeldet wird: jeder Fehler, und Erfolge ohne sichtbare Wirkung
  (z. B. „Scheduler synchronisiert").
- **Kein `window.confirm()`.** Unumkehrbare Aktionen laufen über `ConfirmDialog`;
  wo Daten verloren gehen, muss der Name getippt werden.
- Spinner erst nach 150 ms zeigen — sonst blitzt er bei schnellen Antworten auf.
- Toasts stapeln fest in der Ecke und verschieben kein Layout. `role="status"`,
  `aria-live="polite"`.
- Tooltips: Hover 800 ms, Fokus 0 ms.

## CTA-Stimme

- **Primär:** genau EIN gefüllter Akzentbutton je Ansicht. 6 px Radius, `bg-primary-500`,
  weiße Schrift. Im Dashboard ist das „Neuer Scan".
- **Sekundär / Zeilenaktion:** Umriss (`variant="default"`) oder `ghost`. Eine Tabelle
  mit zwanzig Zeilen darf nicht zwanzig Primärbuttons haben.
- **Destruktiv:** `variant="destructive"`, und nur hinter einem `ConfirmDialog`.

## Was alle Ansichten teilen

- Wortmarke und Kopfzeilenform
- Akzent und seine Sparsamkeit (< 5 % je Viewport)
- Display-, Body- und Mono-Schnitt
- Die CTA-Stimme oben
- Hairlines als Trennung; Schatten nur an schwebenden Ebenen (Dialog, Toast, Menü)
- Mono für Maschinenangaben, `tabular-nums` überall, wo Zahlen untereinanderstehen

## Was sich unterscheiden darf

- Dichte und Ansichtsmodus innerhalb der Workbench-Familie
- Spaltenauswahl und Sortierung
- Anordnung innerhalb eines Dialogs

## Was verboten bleibt

Farbverläufe als Fläche · Verlaufsschrift · Glassmorphismus als Dekoration ·
`transition-all` · reines `#fff` / `#000` als Fläche · Emoji als Icon (das Projekt
nutzt Lucide) · Seitenstreifen-Karten (`border-l-4`) · erfundene Kennzahlen ·
kursive Überschriften · `z-index`-Zahlen außerhalb der benannten Skala.

## Mobile

Jede Ansicht muss bei 320 / 375 / 414 / 768 px fehlerfrei stehen.
`overflow-x: clip` auf `html` **und** `body` — nie `hidden`. Klickbare
Beschriftungen brechen nicht auf zwei Zeilen. Breite Inhalte scrollen in ihrem
eigenen Container, mit **sichtbarer** Scrollbar (`.scrollbar-thin`).
Touch-Ziele ≥ 44 px, aber nur an echten Bedienelementen — nicht an Inline-Links.

## Exports

### tokens.css

Die vollständige Fassung liegt unter `frontend/src/tokens.css`. Kurzform der Anker:

```css
:root {
  --color-paper:       oklch(98.5% 0.004 251);
  --color-surface:     oklch(99.4% 0.003 250);
  --color-ink:         oklch(20%   0.016 260);
  --color-ink-2:       oklch(42.5% 0.018 257);
  --color-rule:        oklch(86.5% 0.009 253);
  --color-accent:      oklch(52%   0.190 257);
  --color-accent-ink:  oklch(99.4% 0.003 250);
  --color-focus:       oklch(52%   0.190 257);

  --font-display: "Space Grotesk", ui-sans-serif, system-ui, sans-serif;
  --font-body:    "Inter", ui-sans-serif, system-ui, sans-serif;
  --font-mono:    "JetBrains Mono", ui-monospace, Menlo, monospace;

  --space-3xs: .25rem; --space-2xs: .5rem;  --space-xs: .75rem;
  --space-sm:  1rem;   --space-md:  1.5rem; --space-lg: 2rem;
  --space-xl:  3rem;   --space-2xl: 4.5rem; --space-3xl: 7rem;

  --ease-out: cubic-bezier(0.16, 1, 0.3, 1);
  --dur-short: 180ms;
  --radius-inset: 4px; --radius-control: 6px; --radius-card: 10px;
}
```

### Tailwind v4 `@theme`

Das Projekt läuft auf Tailwind 3 (Mapping in `frontend/tailwind.config.js`).
Für eine Migration:

```css
@theme {
  --color-paper:  oklch(98.5% 0.004 251);
  --color-ink:    oklch(20%   0.016 260);
  --color-accent: oklch(52%   0.190 257);
  --font-display: "Space Grotesk", sans-serif;
  --font-body:    "Inter", sans-serif;
  --font-mono:    "JetBrains Mono", monospace;
  --spacing-md:   1.5rem;
  --radius-control: 6px;
  --ease-out:     cubic-bezier(0.16, 1, 0.3, 1);
}
```

### DTCG `tokens.json`

```json
{
  "color": {
    "paper":  { "$value": "oklch(98.5% 0.004 251)", "$type": "color" },
    "ink":    { "$value": "oklch(20% 0.016 260)",   "$type": "color" },
    "accent": { "$value": "oklch(52% 0.19 257)",    "$type": "color" }
  },
  "font": {
    "display": { "$value": "Space Grotesk",  "$type": "fontFamily" },
    "body":    { "$value": "Inter",          "$type": "fontFamily" },
    "mono":    { "$value": "JetBrains Mono", "$type": "fontFamily" }
  },
  "space": {
    "md": { "$value": "1.5rem", "$type": "dimension" }
  }
}
```

### shadcn/ui CSS-Variablen

Die semantische Brücke steht bereits in `tailwind.config.js`
(`background`, `foreground`, `card`, `muted`, `border`, `input`, `ring`,
`primary`, `destructive`) und zeigt auf die `--color-*`-Aliase in `tokens.css`.
Diese kippen unter `.dark`; die Rampen bleiben fix.
