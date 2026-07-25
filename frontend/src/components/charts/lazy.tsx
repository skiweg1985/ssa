import { lazy, Suspense, type ComponentProps } from "react"
// `import type` — nur die Signatur, kein Wert. Ein normaler Import würde die
// Implementierung samt Chart.js zurück in den Hauptchunk ziehen.
import type { SizeChart as SizeChartImpl } from "./SizeChart"
import type { HistoryTrendChart as HistoryTrendChartImpl } from "./HistoryTrendChart"

/* Chart.js und react-chartjs-2 sind zusammen 193 KB (67 KB gzip) und werden
 * ausschließlich in HistoryModal und ResultsModal gebraucht — also in Dialogen,
 * die beim Laden des Dashboards gar nicht existieren. Statisch importiert zahlte
 * jeder Seitenaufruf diese 193 KB für Diagramme, die viele Sitzungen nie öffnen.
 *
 * Der dynamische Import zieht sie in einen eigenen Chunk, den Vite erst holt,
 * wenn wirklich ein Diagramm gerendert wird.
 *
 * Aufrufer importieren `SizeChart` / `HistoryTrendChart` aus dieser Datei statt
 * direkt aus dem Modul — Props und Aufrufform bleiben unverändert.
 */

type SizeChartProps = ComponentProps<typeof SizeChartImpl>
type HistoryTrendChartProps = ComponentProps<typeof HistoryTrendChartImpl>

const LazySizeChart = lazy(() =>
  import("./SizeChart").then((m) => ({ default: m.SizeChart }))
)
const LazyHistoryTrendChart = lazy(() =>
  import("./HistoryTrendChart").then((m) => ({ default: m.HistoryTrendChart }))
)

/* Platzhalter in exakter Diagrammhöhe: der Dialog springt nicht, wenn der Chunk
 * ankommt. Kein Spinner — die Fläche ist bekannt, also ist ein Skelett ehrlicher.
 * Die Pulsanimation hält sich an den globalen prefers-reduced-motion-Block. */
function ChartSkeleton({ height }: { height: number }) {
  return (
    <div
      style={{ height }}
      className="flex w-full items-end gap-2 rounded-md border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 p-4"
      role="status"
      aria-label="Diagramm wird geladen"
    >
      {[45, 70, 30, 85, 55, 65, 40].map((h, i) => (
        <div
          key={i}
          className="flex-1 animate-pulse rounded-sm bg-slate-200 dark:bg-slate-700"
          style={{ height: `${h}%` }}
        />
      ))}
    </div>
  )
}

export function SizeChart(props: SizeChartProps) {
  return (
    <Suspense fallback={<ChartSkeleton height={props.height ?? 400} />}>
      <LazySizeChart {...props} />
    </Suspense>
  )
}

export function HistoryTrendChart(props: HistoryTrendChartProps) {
  return (
    <Suspense fallback={<ChartSkeleton height={props.height ?? 300} />}>
      <LazyHistoryTrendChart {...props} />
    </Suspense>
  )
}
