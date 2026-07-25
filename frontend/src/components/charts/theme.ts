/* Die Diagramme lagen bisher außerhalb des Designsystems: `rgba(102, 126, 234, …)`
 * stand vier Mal fest im JS — das ist die alte Primärfarbe, die weiße Schrift nur
 * mit 3.66:1 getragen hat. Chart.js zeichnet auf Canvas und erbt keine
 * CSS-Klassen, also müssen die Tokens hier aktiv ausgelesen werden.
 *
 * Der Wert wird bei jedem Render frisch geholt, damit ein Wechsel zwischen Hell
 * und Dunkel mitgeht.
 */

/** Liest eine OKLCH-Komponenten-Tripel-Variable und setzt sie mit Alpha zusammen. */
function oklchToken(name: string, alpha = 1): string {
  const raw = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
  if (!raw) return alpha === 1 ? "currentColor" : "transparent"
  return alpha === 1 ? `oklch(${raw})` : `oklch(${raw} / ${alpha})`
}

function cssVar(name: string, fallback: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback
}

export interface ChartTokens {
  accent: string
  accentFill: string
  ink: string
  muted: string
  grid: string
  surface: string
  fontBody: string
  fontMono: string
}

export function chartTokens(): ChartTokens {
  const dark = document.documentElement.classList.contains("dark")
  return {
    // Im Dunkeln trägt der hellere Akzentschritt — derselbe, den auch Links und
    // Fokusringe dort verwenden.
    accent: oklchToken(dark ? "--a-400" : "--a-500"),
    accentFill: oklchToken(dark ? "--a-400" : "--a-500", 0.12),
    ink: oklchToken(dark ? "--n-200" : "--n-700"),
    muted: oklchToken(dark ? "--n-400" : "--n-500"),
    grid: oklchToken(dark ? "--n-700" : "--n-200"),
    surface: oklchToken(dark ? "--n-800" : "--n-paper"),
    fontBody: cssVar("--font-body", "Inter, sans-serif"),
    fontMono: cssVar("--font-mono", "monospace"),
  }
}

/**
 * Achsen, Raster und Tooltip in der Systemstimme.
 * Zahlen an den Achsen und im Tooltip laufen in Mono — es sind Messwerte.
 */
export function axisStyle(t: ChartTokens) {
  return {
    ticks: {
      color: t.muted,
      font: { family: t.fontMono, size: 11 },
    },
    grid: { color: t.grid, drawTicks: false },
    border: { color: t.grid },
  }
}

export function tooltipStyle(t: ChartTokens) {
  return {
    backgroundColor: t.surface,
    titleColor: t.ink,
    bodyColor: t.ink,
    borderColor: t.grid,
    borderWidth: 1,
    cornerRadius: 6,
    padding: 10,
    displayColors: false,
    titleFont: { family: t.fontBody, size: 12, weight: 600 as const },
    bodyFont: { family: t.fontMono, size: 12 },
  }
}
