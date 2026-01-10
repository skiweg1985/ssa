import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  Filler,
} from "chart.js"
import { Line } from "react-chartjs-2"
import type { ScanResult } from "@/types/api"
import { formatDateShort } from "@/lib/utils"

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  Filler
)

interface HistoryTrendChartProps {
  history: ScanResult[]
  height?: number
}

export function HistoryTrendChart({ history, height = 300 }: HistoryTrendChartProps) {
  // Berechne Gesamtgröße für jeden Scan
  const dataPoints = history
    .filter((result) => result.status === "completed")
    .map((result) => {
      const totalSize = result.results
        .filter((item) => item.success && item.total_size)
        .reduce((sum, item) => sum + (item.total_size?.bytes || 0), 0)
      return {
        timestamp: result.timestamp,
        size: totalSize,
        date: new Date(result.timestamp),
      }
    })
    .sort((a, b) => a.date.getTime() - b.date.getTime())

  if (dataPoints.length === 0) {
    return (
      <div className="flex items-center justify-center h-64 text-slate-500">
        Keine Daten verfügbar für Trend-Analyse
      </div>
    )
  }

  const labels = dataPoints.map((point) => formatDateShort(point.timestamp))
  const sizes = dataPoints.map((point) => point.size / (1024 ** 3)) // Konvertiere zu GB

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

  const chartData = {
    labels,
    datasets: [
      {
        label: "Gesamtgröße (GB)",
        data: sizes,
        borderColor: "rgba(102, 126, 234, 1)",
        backgroundColor: "rgba(102, 126, 234, 0.1)",
        borderWidth: 2,
        fill: true,
        tension: 0.4,
        pointRadius: 4,
        pointHoverRadius: 6,
      },
    ],
  }

  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        display: true,
        position: "top" as const,
      },
      tooltip: {
        callbacks: {
          label: function (context: any) {
            const gb = context.parsed.y
            const bytes = gb * 1024 ** 3
            return `Größe: ${formatBytes(bytes)}`
          },
        },
      },
    },
    scales: {
      y: {
        beginAtZero: false,
        title: {
          display: true,
          text: "Größe (GB)",
        },
        ticks: {
          callback: function (value: any) {
            return `${value.toFixed(2)} GB`
          },
        },
      },
      x: {
        title: {
          display: true,
          text: "Zeitpunkt",
        },
        ticks: {
          maxRotation: 45,
          minRotation: 45,
        },
      },
    },
  }

  return (
    <div style={{ height: `${height}px` }}>
      <Line data={chartData} options={chartOptions} />
    </div>
  )
}
