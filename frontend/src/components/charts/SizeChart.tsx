import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  Title,
  Tooltip,
  Legend,
  type ChartOptions,
} from "chart.js"
import { Bar } from "react-chartjs-2"
import type { ScanResult } from "@/types/api"
import { chartTokens, axisStyle, tooltipStyle } from "./theme"

ChartJS.register(
  CategoryScale,
  LinearScale,
  BarElement,
  Title,
  Tooltip,
  Legend
)

interface SizeChartProps {
  result: ScanResult
  height?: number
}

export function SizeChart({ result, height = 400 }: SizeChartProps) {
  // Filter successful results with actual data
  const validResults = result.results.filter(
    (item) => item.success && item.total_size
  )

  if (validResults.length === 0) {
    return (
      <div className="flex items-center justify-center h-64 text-slate-500">
        Keine Daten verfügbar
      </div>
    )
  }

  const labels = validResults.map((item) => item.folder_name)
  const sizes = validResults.map((item) => item.total_size!.bytes)

  // Format bytes to human readable
  const formatBytes = (bytes: number): string => {
    const units = ["B", "KB", "MB", "GB", "TB", "PB"]
    let size = bytes
    let unitIndex = 0
    while (size >= 1024 && unitIndex < units.length - 1) {
      size /= 1024
      unitIndex++
    }
    return `${size.toFixed(2)} ${units[unitIndex]}`
  }

  // Farben und Schrift kommen aus dem Token-Layer. Chart.js zeichnet auf Canvas
  // und erbt keine CSS-Klassen, deshalb werden die Werte hier aktiv gelesen.
  const t = chartTokens()

  const chartData = {
    labels,
    datasets: [
      {
        label: "Größe",
        data: sizes,
        backgroundColor: t.accentFill,
        borderColor: t.accent,
        borderWidth: 1.5,
        borderRadius: 3,
      },
    ],
  }

  // Bar liefert parsed als {x, y}; der Byte-Wert wird beim Aufruf extrahiert
  // und hier nur noch formatiert.
  const tooltipLabel = (bytes: number, dataIndex: number): string => {
    const item = validResults[dataIndex]
    let label = formatBytes(bytes)
    if (item?.num_file !== undefined) {
      label += ` (${item.num_file} Dateien`
      if (item.num_dir !== undefined) {
        label += `, ${item.num_dir} Ordner`
      }
      label += ")"
    }
    return label
  }

  const barOptions: ChartOptions<"bar"> = {
    responsive: true,
    maintainAspectRatio: false,
    layout: { padding: { bottom: 20 } },
    plugins: {
      legend: { display: false },
      tooltip: {
        ...tooltipStyle(t),
        callbacks: {
          label: (context) => tooltipLabel(context.parsed.y ?? 0, context.dataIndex),
        },
      },
    },
    scales: {
      y: {
        beginAtZero: true,
        ...axisStyle(t),
        ticks: {
          ...axisStyle(t).ticks,
          callback: (value) => formatBytes(Number(value)),
        },
      },
      x: {
        ...axisStyle(t),
        ticks: { ...axisStyle(t).ticks, maxRotation: 0, minRotation: 0, autoSkip: false },
      },
    },
  }

  return (
    <div style={{ height: `${height}px` }}>
      <Bar data={chartData} options={barOptions} />
    </div>
  )
}
