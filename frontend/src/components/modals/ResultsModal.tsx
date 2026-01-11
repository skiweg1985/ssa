import { useState, useEffect, useMemo } from "react"
import {
  Dialog,
  DialogHeader,
  DialogTitle,
  DialogContent,
  DialogFooter,
} from "@/components/ui/dialog"
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { SizeChart } from "@/components/charts/SizeChart"
import { HistoryTrendChart } from "@/components/charts/HistoryTrendChart"
import { fetchScanResults, fetchScanHistory } from "@/lib/api"
import { getStatusConfig, formatDate, formatSize, formatBytes } from "@/lib/utils"
import type { ScanResult, ScanHistoryResponse } from "@/types/api"
import { Download, Loader2, BarChart3, History, CheckCircle2, XCircle, TrendingUp, FileDown, ArrowLeft } from "lucide-react"

interface ResultsModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  scanName: string
}

export function ResultsModal({ open, onOpenChange, scanName }: ResultsModalProps) {
  const [activeTab, setActiveTab] = useState<"results" | "history">("results")
  const [result, setResult] = useState<ScanResult | null>(null)
  const [history, setHistory] = useState<ScanHistoryResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [selectedHistoryIndex, setSelectedHistoryIndex] = useState<number | null>(null)

  useEffect(() => {
    if (open && scanName) {
      loadData()
    }
  }, [open, scanName, activeTab])

  async function loadData() {
    setLoading(true)
    setError(null)
    try {
      if (activeTab === "results") {
        const data = await fetchScanResults(scanName, true)
        setResult(data)
      } else {
        const data = await fetchScanHistory(scanName)
        setHistory(data)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Fehler beim Laden")
    } finally {
      setLoading(false)
    }
  }

  function exportResults() {
    if (!result) return

    const dataStr = JSON.stringify(result, null, 2)
    const dataBlob = new Blob([dataStr], { type: "application/json" })
    const url = URL.createObjectURL(dataBlob)
    const link = document.createElement("a")
    link.href = url
    link.download = `${scanName}_${new Date().toISOString()}.json`
    link.click()
    URL.revokeObjectURL(url)
  }

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

  // Berechne Gesamtgröße für einen Scan
  function getTotalSize(scanResult: ScanResult): number {
    return scanResult.results
      .filter((item) => item.success && item.total_size)
      .reduce((sum, item) => sum + (item.total_size?.bytes || 0), 0)
  }

  const selectedHistoryResult = selectedHistoryIndex !== null && history
    ? history.results[selectedHistoryIndex]
    : null

  const status = result ? getStatusConfig(result.status) : null

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogHeader className="bg-gradient-to-r from-primary-500 to-purple-600 text-white px-6 py-4">
        <div className="flex items-center gap-2 sm:gap-3 min-w-0">
          <DialogTitle className="text-white flex items-center gap-2 min-w-0 flex-1">
            <BarChart3 className="h-5 w-5 flex-shrink-0" />
            <span className="truncate">Scan-Ergebnisse: {scanName}</span>
          </DialogTitle>
          {status && (
            <Badge variant={status.variant} className="flex-shrink-0">
              <span>{status.text}</span>
            </Badge>
          )}
        </div>
      </DialogHeader>

      <DialogContent>
        <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as "results" | "history")}>
          <TabsList>
            <TabsTrigger value="results" className="flex items-center gap-2">
              <BarChart3 className="h-4 w-4" />
              Ergebnisse
            </TabsTrigger>
            <TabsTrigger value="history" className="flex items-center gap-2">
              <History className="h-4 w-4" />
              Historie
            </TabsTrigger>
          </TabsList>

          <TabsContent value="results" className="mt-3">
            {loading ? (
              <div className="flex items-center justify-center py-12">
                <Loader2 className="h-6 w-6 animate-spin text-slate-400 dark:text-slate-500" />
                <span className="ml-2 text-slate-500 dark:text-slate-400">Lade Ergebnisse...</span>
              </div>
            ) : error ? (
              <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-red-800">
                <div className="font-semibold mb-1">Fehler beim Laden</div>
                <div className="text-sm">{error}</div>
                <Button variant="primary" size="sm" onClick={loadData} className="mt-3">
                  Erneut versuchen
                </Button>
              </div>
            ) : result ? (
              <div className="space-y-3">
                <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
                  <div className="bg-slate-50 dark:bg-slate-800 rounded-lg p-2">
                    <div className="text-xs text-slate-600 dark:text-slate-400">Zeitstempel</div>
                    <div className="font-semibold text-sm text-slate-900 dark:text-slate-100">{formatDate(result.timestamp)}</div>
                  </div>
                  <div className="bg-slate-50 dark:bg-slate-800 rounded-lg p-2">
                    <div className="text-xs text-slate-600 dark:text-slate-400">Status</div>
                    <div className="font-semibold text-sm text-slate-900 dark:text-slate-100">{status?.text}</div>
                  </div>
                  <div className="bg-slate-50 dark:bg-slate-800 rounded-lg p-2">
                    <div className="text-xs text-slate-600 dark:text-slate-400">Anzahl Ergebnisse</div>
                    <div className="font-semibold text-sm text-slate-900 dark:text-slate-100">{result.results.length}</div>
                  </div>
                </div>

                {result.results.length > 0 && (
                  <div className="space-y-2">
                    <h3 className="font-semibold text-sm text-slate-900 dark:text-slate-100">Ergebnisse</h3>
                    <div className="overflow-x-auto max-h-[200px] overflow-y-auto border border-slate-200 dark:border-slate-700 rounded-lg">
                      <table className="w-full border-collapse">
                        <thead className="bg-slate-50 dark:bg-slate-800 border-b border-slate-200 dark:border-slate-700 sticky top-0">
                          <tr>
                            <th className="px-3 py-1.5 text-left text-xs font-semibold text-slate-600 dark:text-slate-400">Ordner</th>
                            <th className="px-3 py-1.5 text-left text-xs font-semibold text-slate-600 dark:text-slate-400">Größe</th>
                            <th className="px-3 py-1.5 text-left text-xs font-semibold text-slate-600 dark:text-slate-400">Dateien</th>
                            <th className="px-3 py-1.5 text-left text-xs font-semibold text-slate-600 dark:text-slate-400">Ordner</th>
                            <th className="px-3 py-1.5 text-left text-xs font-semibold text-slate-600 dark:text-slate-400">Status</th>
                          </tr>
                        </thead>
                        <tbody>
                          {result.results.map((item, idx) => (
                            <tr key={idx} className="border-b border-slate-100 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800">
                              <td className="px-3 py-1.5 text-xs text-slate-900 dark:text-slate-100">{item.folder_name}</td>
                              <td className="px-3 py-1.5 text-xs font-mono text-slate-900 dark:text-slate-100">
                                {item.total_size ? formatSize(item.total_size) : "-"}
                              </td>
                              <td className="px-3 py-1.5 text-xs text-slate-900 dark:text-slate-100">{item.num_file ?? "-"}</td>
                              <td className="px-3 py-1.5 text-xs text-slate-900 dark:text-slate-100">{item.num_dir ?? "-"}</td>
                              <td className="px-3 py-1.5 text-xs">
                                {item.success ? (
                                  <span className="text-green-600 dark:text-green-400 flex items-center gap-1.5">
                                    <CheckCircle2 className="h-4 w-4" />
                                    Erfolg
                                  </span>
                                ) : (
                                  <span className="text-red-600 dark:text-red-400 flex items-center gap-1.5">
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

                    <div className="mt-3" style={{ height: '350px' }}>
                      <SizeChart result={result} type="bar" height={350} />
                    </div>
                  </div>
                )}
              </div>
            ) : null}
          </TabsContent>

          <TabsContent value="history" className="mt-6">
            {loading ? (
              <div className="flex items-center justify-center py-12">
                <Loader2 className="h-6 w-6 animate-spin text-slate-400 dark:text-slate-500" />
                <span className="ml-2 text-slate-500 dark:text-slate-400">Lade Historie...</span>
              </div>
            ) : error ? (
              <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4 text-red-800 dark:text-red-300">
                <div className="font-semibold mb-1">Fehler beim Laden</div>
                <div className="text-sm">{error}</div>
                <Button variant="primary" size="sm" onClick={loadData} className="mt-3">
                  Erneut versuchen
                </Button>
              </div>
            ) : history ? (
              selectedHistoryIndex === null ? (
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
                    <div className="bg-slate-50 dark:bg-slate-800 rounded-lg p-4">
                      <div className="text-sm font-semibold text-slate-900 dark:text-slate-100 mb-3 flex items-center gap-2">
                        <TrendingUp className="h-4 w-4" />
                        Speicherverbrauch über Zeit
                      </div>
                      <HistoryTrendChart history={history.results} height={250} />
                    </div>
                  )}

                  {/* Historie-Liste */}
                  <div className="flex items-center justify-between mb-2">
                    <div className="text-sm text-slate-600 dark:text-slate-400">
                      {history.total_count} Einträge gefunden
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
                    {history.results.map((item, idx) => {
                      const totalSize = getTotalSize(item)
                      return (
                        <button
                          key={idx}
                          onClick={() => setSelectedHistoryIndex(idx)}
                          className="w-full text-left bg-slate-50 dark:bg-slate-800 rounded-lg p-4 hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors border border-transparent hover:border-primary-200 dark:hover:border-primary-700"
                        >
                          <div className="flex items-center justify-between mb-2">
                            <div className="font-semibold text-sm text-slate-900 dark:text-slate-100">{formatDate(item.timestamp)}</div>
                            <Badge variant={getStatusConfig(item.status).variant}>
                              {getStatusConfig(item.status).text}
                            </Badge>
                          </div>
                          <div className="flex items-center gap-4 text-sm text-slate-600 dark:text-slate-400">
                            <span>{item.results.length} Ergebnisse</span>
                            {totalSize > 0 && (
                              <span className="font-semibold text-slate-900 dark:text-slate-100">
                                Gesamt: {formatBytes(totalSize)}
                              </span>
                            )}
                          </div>
                        </button>
                      )
                    })}
                  </div>
                </div>
              ) : (
                <div className="space-y-4">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setSelectedHistoryIndex(null)}
                    className="mb-2"
                  >
                    <ArrowLeft className="h-4 w-4 mr-2" />
                    Zurück zur Historie
                  </Button>
                  
                  {selectedHistoryResult && (
                    <div className="space-y-3">
                      <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
                        <div className="bg-slate-50 dark:bg-slate-800 rounded-lg p-2">
                          <div className="text-xs text-slate-600 dark:text-slate-400">Zeitstempel</div>
                          <div className="font-semibold text-sm text-slate-900 dark:text-slate-100">
                            {formatDate(selectedHistoryResult.timestamp)}
                          </div>
                        </div>
                        <div className="bg-slate-50 dark:bg-slate-800 rounded-lg p-2">
                          <div className="text-xs text-slate-600 dark:text-slate-400">Status</div>
                          <div className="font-semibold text-sm text-slate-900 dark:text-slate-100">
                            {getStatusConfig(selectedHistoryResult.status).text}
                          </div>
                        </div>
                        <div className="bg-slate-50 dark:bg-slate-800 rounded-lg p-2">
                          <div className="text-xs text-slate-600 dark:text-slate-400">Anzahl Ergebnisse</div>
                          <div className="font-semibold text-sm text-slate-900 dark:text-slate-100">
                            {selectedHistoryResult.results.length}
                          </div>
                        </div>
                      </div>

                      {selectedHistoryResult.results.length > 0 && (
                        <div className="space-y-2">
                          <h3 className="font-semibold text-sm text-slate-900 dark:text-slate-100">Ergebnisse</h3>
                          <div className="overflow-x-auto max-h-[300px] overflow-y-auto border border-slate-200 dark:border-slate-700 rounded-lg">
                            <table className="w-full border-collapse">
                              <thead className="bg-slate-50 dark:bg-slate-800 border-b border-slate-200 dark:border-slate-700 sticky top-0">
                                <tr>
                                  <th className="px-3 py-1.5 text-left text-xs font-semibold text-slate-600 dark:text-slate-400">Ordner</th>
                                  <th className="px-3 py-1.5 text-left text-xs font-semibold text-slate-600 dark:text-slate-400">Größe</th>
                                  <th className="px-3 py-1.5 text-left text-xs font-semibold text-slate-600 dark:text-slate-400">Dateien</th>
                                  <th className="px-3 py-1.5 text-left text-xs font-semibold text-slate-600 dark:text-slate-400">Ordner</th>
                                  <th className="px-3 py-1.5 text-left text-xs font-semibold text-slate-600 dark:text-slate-400">Status</th>
                                </tr>
                              </thead>
                              <tbody>
                                {selectedHistoryResult.results.map((item, idx) => (
                                  <tr key={idx} className="border-b border-slate-100 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800">
                                    <td className="px-3 py-1.5 text-xs text-slate-900 dark:text-slate-100">{item.folder_name}</td>
                                    <td className="px-3 py-1.5 text-xs font-mono text-slate-900 dark:text-slate-100">
                                      {item.total_size ? formatSize(item.total_size) : "-"}
                                    </td>
                                    <td className="px-3 py-1.5 text-xs text-slate-900 dark:text-slate-100">{item.num_file ?? "-"}</td>
                                    <td className="px-3 py-1.5 text-xs text-slate-900 dark:text-slate-100">{item.num_dir ?? "-"}</td>
                                    <td className="px-3 py-1.5 text-xs">
                                      {item.success ? (
                                        <span className="text-green-600 dark:text-green-400 flex items-center gap-1.5">
                                          <CheckCircle2 className="h-4 w-4" />
                                          Erfolg
                                        </span>
                                      ) : (
                                        <span className="text-red-600 dark:text-red-400 flex items-center gap-1.5">
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
                            <SizeChart result={selectedHistoryResult} type="bar" height={300} />
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )
            ) : null}
          </TabsContent>
        </Tabs>
      </DialogContent>

      <DialogFooter>
        <Button variant="secondary" onClick={() => {
          setSelectedHistoryIndex(null)
          onOpenChange(false)
        }}>
          Schließen
        </Button>
        {activeTab === "results" && result && (
          <Button variant="primary" onClick={exportResults}>
            <Download className="h-4 w-4 mr-2" />
            Exportieren
          </Button>
        )}
        {activeTab === "history" && history && selectedHistoryIndex === null && (
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
