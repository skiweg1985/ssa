import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  Title,
  Tooltip,
  Legend,
  ArcElement,
} from "chart.js"
import { Bar, Doughnut } from "react-chartjs-2"
import type { ScanResult } from "@/types/api"

ChartJS.register(
  CategoryScale,
  LinearScale,
  BarElement,
  Title,
  Tooltip,
  Legend,
  ArcElement
)

interface SizeChartProps {
  result: ScanResult
  type?: "bar" | "doughnut"
  height?: number
}

export function SizeChart({ result, type = "bar", height = 400 }: SizeChartProps) {
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

  const chartData = {
    labels,
    datasets: [
      {
        label: "Größe",
        data: sizes,
        backgroundColor: "rgba(102, 126, 234, 0.8)",
        borderColor: "rgba(102, 126, 234, 1)",
        borderWidth: 1,
      },
    ],
  }

  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    layout: {
      padding: {
        bottom: 20,
      },
    },
    plugins: {
      legend: {
        display: false,
      },
      tooltip: {
        callbacks: {
          label: function (context: any) {
            const bytes = context.parsed.y
            const item = validResults[context.dataIndex]
            let label = formatBytes(bytes)
            if (item.num_file !== undefined) {
              label += ` (${item.num_file} Dateien`
              if (item.num_dir !== undefined) {
                label += `, ${item.num_dir} Ordner`
              }
              label += ")"
            }
            return label
          },
        },
      },
    },
    scales:
      type === "bar"
        ? {
            y: {
              beginAtZero: true,
              ticks: {
                callback: function (value: any) {
                  return formatBytes(value)
                },
              },
            },
            x: {
              ticks: {
                maxRotation: 0,
                minRotation: 0,
                autoSkip: false,
              },
            },
          }
        : undefined,
  }

  if (type === "doughnut") {
    return (
      <div style={{ height: `${height}px` }}>
        <Doughnut data={chartData} options={chartOptions} />
      </div>
    )
  }

  return (
    <div style={{ height: `${height}px` }}>
      <Bar data={chartData} options={chartOptions} />
    </div>
  )
}
