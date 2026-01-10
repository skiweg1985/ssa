import { useState, useEffect, useMemo } from "react"
import {
  Dialog,
  DialogHeader,
  DialogTitle,
  DialogContent,
  DialogFooter,
  DialogClose,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { SizeChart } from "@/components/charts/SizeChart"
import { HistoryTrendChart } from "@/components/charts/HistoryTrendChart"
import { fetchScanHistory } from "@/lib/api"
import { getStatusConfig, formatDate, formatSize, formatBytes } from "@/lib/utils"
import type { ScanHistoryResponse, ScanResult } from "@/types/api"
import { Loader2, ArrowLeft, History, CheckCircle2, XCircle, TrendingUp, Download, FileDown } from "lucide-react"

interface HistoryModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  scanName: string
}

type HistoryFilter = "all" | "completed" | "failed"

export function HistoryModal({ open, onOpenChange, scanName }: HistoryModalProps) {
  const [history, setHistory] = useState<ScanHistoryResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null)
  const [filter, setFilter] = useState<HistoryFilter>("all")
  const [searchQuery, setSearchQuery] = useState("")

  useEffect(() => {
    if (open && scanName) {
      loadHistory()
    }
  }, [open, scanName])

  async function loadHistory() {
    setLoading(true)
    setError(null)
    try {
      const data = await fetchScanHistory(scanName)
      setHistory(data)
      setSelectedIndex(null) // Start ohne Auswahl
    } catch (err) {
      setError(err instanceof Error ? err.message : "Fehler beim Laden")
    } finally {
      setLoading(false)
    }
  }

  // Berechne Gesamtgröße für einen Scan
  function getTotalSize(scanResult: ScanResult): number {
    return scanResult.results
      .filter((item) => item.success && item.total_size)
      .reduce((sum, item) => sum + (item.total_size?.bytes || 0), 0)
  }

  // Berechne Statistiken für die Historie
  const historyStats = useMemo(() => {
    if (!history || history.results.length === 0) return null

    const completedScans = history.results.filter((r) => r.status === "completed")
    if (completedScans.length === 0) return null

    const sizes = completedScans.map((result) => {
      return result.results
        .filter((item) => item.success && item.total_size)
        .reduce((sum, item) => sum + (item.total_size?.bytes || 0), 0)
    })

    const sortedSizes = [...sizes].sort((a, b) => a - b)
    const min = sortedSizes[0] || 0
    const max = sortedSizes[sortedSizes.length - 1] || 0
    const avg = sizes.reduce((sum, s) => sum + s, 0) / sizes.length

    // Wachstumsrate (letzter vs. erster Scan)
    let growthRate = 0
    if (sizes.length >= 2) {
      const first = sizes[0]
      const last = sizes[sizes.length - 1]
      if (first > 0) {
        growthRate = ((last - first) / first) * 100
      }
    }

    return { min, max, avg, growthRate, count: completedScans.length }
  }, [history])

  function exportHistory() {
    if (!history) return

    // Export als JSON
    const dataStr = JSON.stringify(history, null, 2)
    const dataBlob = new Blob([dataStr], { type: "application/json" })
    const url = URL.createObjectURL(dataBlob)
    const link = document.createElement("a")
    link.href = url
    link.download = `${scanName}_history_${new Date().toISOString()}.json`
    link.click()
    URL.revokeObjectURL(url)
  }

  function exportHistoryCSV() {
    if (!history) return

    // CSV Header
    const headers = ["Zeitstempel", "Status", "Anzahl Ergebnisse", "Gesamtgröße (Bytes)", "Gesamtgröße (Formatiert)", "Dateien", "Ordner"]
    const rows = [headers.join(",")]

    history.results.forEach((item) => {
      const successfulResults = item.results.filter((r) => r.success)
      const totalSize = successfulResults.reduce((sum, r) => sum + (r.total_size?.bytes || 0), 0)
      const totalFiles = successfulResults.reduce((sum, r) => sum + (r.num_file || 0), 0)
      const totalDirs = successfulResults.reduce((sum, r) => sum + (r.num_dir || 0), 0)

      rows.push([
        item.timestamp,
        item.status,
        item.results.length.toString(),
        totalSize.toString(),
        formatBytes(totalSize),
        totalFiles.toString(),
        totalDirs.toString(),
      ].join(","))
    })

    const csvContent = rows.join("\n")
    const dataBlob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" })
    const url = URL.createObjectURL(dataBlob)
    const link = document.createElement("a")
    link.href = url
    link.download = `${scanName}_history_${new Date().toISOString()}.csv`
    link.click()
    URL.revokeObjectURL(url)
  }

  const filteredHistory = useMemo(() => {
    if (!history) return []
    let filtered = history.results

    // Filter nach Status
    if (filter !== "all") {
      filtered = filtered.filter((r) => r.status === filter)
    }

    // Suche
    if (searchQuery) {
      const q = searchQuery.toLowerCase()
      filtered = filtered.filter(
        (r) =>
          formatDate(r.timestamp).toLowerCase().includes(q) ||
          r.status.toLowerCase().includes(q) ||
          r.results.some((item) => item.folder_name.toLowerCase().includes(q))
      )
    }

    return filtered
  }, [history, filter, searchQuery])

  // Finde den ausgewählten Eintrag in der originalen Liste
  const selectedResult = selectedIndex !== null && history
    ? history.results[selectedIndex]
    : null

  if (!open) return null

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogHeader className="bg-gradient-to-r from-primary-500 to-purple-600 text-white px-6 py-4">
        <div className="flex items-center justify-between">
          <DialogTitle className="text-white flex items-center gap-2">
            <History className="h-5 w-5" />
            Historie: {scanName}
          </DialogTitle>
          <DialogClose className="text-white hover:bg-white/20" />
        </div>
      </DialogHeader>

      <DialogContent>
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-6 w-6 animate-spin text-slate-400" />
            <span className="ml-2 text-slate-500">Lade Historie...</span>
          </div>
        ) : error ? (
          <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-red-800">
            <div className="font-semibold mb-1">Fehler beim Laden</div>
            <div className="text-sm">{error}</div>
            <Button variant="primary" size="sm" onClick={loadHistory} className="mt-3">
              Erneut versuchen
            </Button>
          </div>
        ) : history ? (
          selectedIndex === null ? (
            <div className="space-y-4">
              {/* Statistiken */}
              {historyStats && (
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                  <div className="bg-gradient-to-br from-blue-500 to-blue-600 text-white rounded-lg p-3">
                    <div className="text-xs opacity-90 mb-1">Durchschnitt</div>
                    <div className="text-lg font-bold">{formatBytes(historyStats.avg)}</div>
                  </div>
                  <div className="bg-gradient-to-br from-green-500 to-green-600 text-white rounded-lg p-3">
                    <div className="text-xs opacity-90 mb-1">Minimum</div>
                    <div className="text-lg font-bold">{formatBytes(historyStats.min)}</div>
                  </div>
                  <div className="bg-gradient-to-br from-purple-500 to-purple-600 text-white rounded-lg p-3">
                    <div className="text-xs opacity-90 mb-1">Maximum</div>
                    <div className="text-lg font-bold">{formatBytes(historyStats.max)}</div>
                  </div>
                  <div className={`bg-gradient-to-br rounded-lg p-3 ${
                    historyStats.growthRate >= 0 
                      ? "from-red-500 to-red-600" 
                      : "from-green-500 to-green-600"
                  } text-white`}>
                    <div className="text-xs opacity-90 mb-1 flex items-center gap-1">
                      <TrendingUp className="h-3 w-3" />
                      Wachstum
                    </div>
                    <div className="text-lg font-bold">
                      {historyStats.growthRate >= 0 ? "+" : ""}{historyStats.growthRate.toFixed(1)}%
                    </div>
                  </div>
                </div>
              )}

              {/* Trend-Diagramm */}
              {history.results.length > 1 && (
                <div className="bg-slate-50 rounded-lg p-4">
                  <div className="text-sm font-semibold text-slate-900 mb-3 flex items-center gap-2">
                    <TrendingUp className="h-4 w-4" />
                    Speicherverbrauch über Zeit
                  </div>
                  <HistoryTrendChart history={history.results} height={250} />
                </div>
              )}

              {/* Filter und Suche */}
              <div className="flex flex-col sm:flex-row gap-3 items-start sm:items-center justify-between">
                <div className="flex-1 w-full sm:w-auto">
                  <Input
                    type="text"
                    placeholder="🔍 Historie durchsuchen..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="mb-2 sm:mb-0"
                  />
                </div>
                <div className="flex gap-2 flex-wrap">
                  {(["all", "completed", "failed"] as HistoryFilter[]).map((f) => (
                    <Button
                      key={f}
                      variant={filter === f ? "default" : "secondary"}
                      size="sm"
                      onClick={() => setFilter(f)}
                      className={f === "failed" ? "border-red-300" : ""}
                    >
                      {f === "all"
                        ? "Alle"
                        : f === "completed"
                        ? (
                          <span className="flex items-center gap-1.5">
                            <CheckCircle2 className="h-4 w-4" />
                            Abgeschlossen
                          </span>
                        )
                        : (
                          <span className="flex items-center gap-1.5">
                            <XCircle className="h-4 w-4" />
                            Fehlgeschlagen
                          </span>
                        )}
                    </Button>
                  ))}
                </div>
              </div>

              {/* Historie-Liste */}
              <div className="flex items-center justify-between mb-2">
                <div className="text-sm text-slate-600">
                  {filteredHistory.length} von {history.total_count} Einträgen
                  {filter === "failed" && (
                    <span className="ml-2 text-red-600 font-semibold">
                      ({filteredHistory.length} fehlerhafte)
                    </span>
                  )}
                </div>
                <div className="flex gap-2">
                  <Button variant="secondary" size="sm" onClick={exportHistoryCSV}>
                    <FileDown className="h-4 w-4 mr-1" />
                    CSV
                  </Button>
                  <Button variant="secondary" size="sm" onClick={exportHistory}>
                    <Download className="h-4 w-4 mr-1" />
                    JSON
                  </Button>
                </div>
              </div>
              <div className="space-y-2 max-h-96 overflow-y-auto">
                {filteredHistory.length === 0 ? (
                  <div className="text-center py-8 text-slate-500">
                    {filter === "failed" 
                      ? "Keine fehlerhaften Scans gefunden" 
                      : "Keine Einträge gefunden"}
                  </div>
                ) : (
                  filteredHistory.map((result, idx) => {
                    const originalIdx = history.results.indexOf(result)
                    const totalSize = getTotalSize(result)
                    return (
                      <button
                        key={idx}
                        onClick={() => setSelectedIndex(originalIdx)}
                        className="w-full text-left bg-slate-50 rounded-lg p-4 hover:bg-slate-100 transition-colors border border-transparent hover:border-primary-200"
                      >
                        <div className="flex items-center justify-between mb-2">
                          <div className="font-semibold text-sm">{formatDate(result.timestamp)}</div>
                          <Badge variant={getStatusConfig(result.status).variant}>
                            {getStatusConfig(result.status).text}
                          </Badge>
                        </div>
                        <div className="flex items-center gap-4 text-sm text-slate-600">
                          <span>{result.results.length} Ergebnisse</span>
                          {totalSize > 0 && (
                            <span className="font-semibold text-slate-900">
                              Gesamt: {formatBytes(totalSize)}
                            </span>
                          )}
                          {result.status === "failed" && result.error && (
                            <span className="text-red-600 text-xs truncate max-w-xs">
                              {result.error}
                            </span>
                          )}
                        </div>
                      </button>
                    )
                  })
                )}
              </div>
            </div>
          ) : (
            <div className="space-y-4">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setSelectedIndex(null)}
                className="mb-2"
              >
                <ArrowLeft className="h-4 w-4 mr-2" />
                Zurück zur Historie
              </Button>
              
              {selectedResult && (
                <div className="space-y-3">
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
                    <div className="bg-slate-50 rounded-lg p-2">
                      <div className="text-xs text-slate-600">Zeitstempel</div>
                      <div className="font-semibold text-sm text-slate-900">
                        {formatDate(selectedResult.timestamp)}
                      </div>
                    </div>
                    <div className="bg-slate-50 rounded-lg p-2">
                      <div className="text-xs text-slate-600">Status</div>
                      <div className="font-semibold text-sm text-slate-900">
                        {getStatusConfig(selectedResult.status).text}
                      </div>
                    </div>
                    <div className="bg-slate-50 rounded-lg p-2">
                      <div className="text-xs text-slate-600">Anzahl Ergebnisse</div>
                      <div className="font-semibold text-sm text-slate-900">
                        {selectedResult.results.length}
                      </div>
                    </div>
                  </div>

                  {selectedResult.results.length > 0 && (
                    <div className="space-y-2">
                      <h3 className="font-semibold text-sm text-slate-900">Ergebnisse</h3>
                      <div className="overflow-x-auto max-h-[300px] overflow-y-auto border border-slate-200 rounded-lg">
                        <table className="w-full border-collapse">
                          <thead className="bg-slate-50 border-b border-slate-200 sticky top-0">
                            <tr>
                              <th className="px-3 py-1.5 text-left text-xs font-semibold text-slate-600">Ordner</th>
                              <th className="px-3 py-1.5 text-left text-xs font-semibold text-slate-600">Größe</th>
                              <th className="px-3 py-1.5 text-left text-xs font-semibold text-slate-600">Dateien</th>
                              <th className="px-3 py-1.5 text-left text-xs font-semibold text-slate-600">Ordner</th>
                              <th className="px-3 py-1.5 text-left text-xs font-semibold text-slate-600">Status</th>
                            </tr>
                          </thead>
                          <tbody>
                            {selectedResult.results.map((item, idx) => (
                              <tr key={idx} className="border-b border-slate-100 hover:bg-slate-50">
                                <td className="px-3 py-1.5 text-xs">{item.folder_name}</td>
                                <td className="px-3 py-1.5 text-xs font-mono">
                                  {item.total_size ? formatSize(item.total_size) : "-"}
                                </td>
                                <td className="px-3 py-1.5 text-xs">{item.num_file ?? "-"}</td>
                                <td className="px-3 py-1.5 text-xs">{item.num_dir ?? "-"}</td>
                                <td className="px-3 py-1.5 text-xs">
                                  {item.success ? (
                                    <span className="text-green-600 flex items-center gap-1.5">
                                      <CheckCircle2 className="h-4 w-4" />
                                      Erfolg
                                    </span>
                                  ) : (
                                    <span className="text-red-600 flex items-center gap-1.5">
                                      <XCircle className="h-4 w-4" />
                                      Fehler
                                    </span>
                                  )}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>

                      <div className="mt-3" style={{ height: '300px' }}>
                        <SizeChart result={selectedResult} type="bar" height={300} />
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          )
        ) : null}
      </DialogContent>

      <DialogFooter>
        <Button variant="secondary" onClick={() => {
          setSelectedIndex(null)
          onOpenChange(false)
        }}>
          Schließen
        </Button>
        {history && selectedIndex === null && (
          <div className="flex gap-2">
            <Button variant="secondary" onClick={exportHistoryCSV}>
              <FileDown className="h-4 w-4 mr-2" />
              CSV Export
            </Button>
            <Button variant="primary" onClick={exportHistory}>
              <Download className="h-4 w-4 mr-2" />
              JSON Export
            </Button>
          </div>
        )}
      </DialogFooter>
    </Dialog>
  )
}

