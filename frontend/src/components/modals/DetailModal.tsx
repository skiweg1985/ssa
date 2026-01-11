import {
  Dialog,
  DialogHeader,
  DialogTitle,
  DialogContent,
  DialogFooter,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { fetchScan, fetchScanProgress } from "@/lib/api"
import { getStatusConfig, formatDate, getScanFolders, formatSizeCompact } from "@/lib/utils"
import { useScanProgress } from "@/hooks/useScanProgress"
import type { ScanStatus } from "@/types/api"
import { Play, BarChart3, History, FolderOpen, CheckCircle2, XCircle, Settings, Server, FileText, Calendar } from "lucide-react"
import { useState, useEffect } from "react"
import { cn } from "@/lib/cn"

interface DetailModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  scan: ScanStatus | null
  onTriggerScan: (scanName: string) => void
  onShowResults: (scanName: string) => void
  onShowHistory: (scanName: string) => void
}

export function DetailModal({
  open,
  onOpenChange,
  scan,
  onTriggerScan,
  onShowResults,
  onShowHistory,
}: DetailModalProps) {
  const [detailedScan, setDetailedScan] = useState<ScanStatus | null>(scan)

  // Reset detailedScan immediately when scan prop changes
  useEffect(() => {
    if (scan) {
      setDetailedScan(scan)
    }
  }, [scan?.scan_slug]) // Use scan_slug to detect when a different scan is selected

  useEffect(() => {
    if (open && scan) {
      loadDetails()
    } else if (!open) {
      // Reset when modal closes
      setDetailedScan(scan)
    }
  }, [open, scan?.scan_slug]) // Use scan_slug to detect scan changes

  async function loadDetails() {
    if (!scan) return
    try {
      // Verwende slug für API-Aufruf (unterstützt auch name für Rückwärtskompatibilität)
      const data = await fetchScan(scan.scan_slug)
      setDetailedScan(data)
    } catch (err) {
      console.error("Error loading scan details:", err)
      setDetailedScan(scan)
    }
  }

  // Always call hook (React rules) - but only poll when conditions are met
  // Verwende slug für Progress-Aufrufe - use scan prop directly to ensure correct identifier
  const scanIdentifier = scan?.scan_slug || scan?.scan_name || detailedScan?.scan_slug || detailedScan?.scan_name || ""
  // Poll if scan is running - also poll once if completed to get final progress
  const isRunning = (detailedScan?.status === "running" || scan?.status === "running") && open
  const { progress } = useScanProgress(scanIdentifier, isRunning, 1000)
  
  // Also fetch progress once if scan is completed but we don't have progress yet
  const [completedProgress, setCompletedProgress] = useState<typeof progress>(null)
  
  // Reset completedProgress when scan changes
  useEffect(() => {
    setCompletedProgress(null)
  }, [scan?.scan_slug])
  
  useEffect(() => {
    if ((detailedScan?.status === "completed" || scan?.status === "completed") && open && scanIdentifier && !progress && !completedProgress) {
      fetchScanProgress(scanIdentifier).then(data => {
        if (data && (data.status === "completed" || data.progress?.finished)) {
          setCompletedProgress(data)
        }
      }).catch(() => {
        // Ignore errors (404 is expected after grace period)
      })
    }
  }, [detailedScan?.status, scan?.status, open, scanIdentifier, progress, completedProgress])
  
  // Use progress if available, or completed progress, even if scan status is completed
  const displayProgress = progress || completedProgress

  if (!detailedScan && !scan) return null

  const currentScan = detailedScan || scan
  if (!currentScan) return null

  const status = getStatusConfig(currentScan.status)
  const folders = getScanFolders(currentScan)
  const canRun = currentScan.status !== "running" && currentScan.enabled

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogHeader className="bg-gradient-to-r from-primary-500 to-purple-600 text-white px-6 py-4">
        <div className="flex items-center gap-2 sm:gap-3 min-w-0">
          <DialogTitle className="text-white flex items-center gap-2 min-w-0 flex-1">
            <FileText className="h-5 w-5 flex-shrink-0" />
            <span className="truncate">Job-Details: {currentScan.scan_name}</span>
          </DialogTitle>
          <Badge variant={status.variant} className="flex-shrink-0">
            <span>{status.text}</span>
          </Badge>
        </div>
      </DialogHeader>

      <DialogContent>
        {/* Progress Section for Running/Completed Scans */}
        {(currentScan.status === "running" || displayProgress?.status === "completed") && (
          <div className={cn(
            "mb-6 p-4 rounded-lg border transition-all duration-500",
            displayProgress?.status === "completed" 
              ? "bg-emerald-50 dark:bg-emerald-900/20 border-emerald-200 dark:border-emerald-700" 
              : "bg-blue-50 dark:bg-blue-900/20 border-blue-200 dark:border-blue-700"
          )}>
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">Scan-Fortschritt</h3>
              {displayProgress?.status === "completed" ? (
                <Badge variant="success" className="animate-in fade-in slide-in-from-top-2 duration-500">
                  <span className="text-xs">Abgeschlossen</span>
                </Badge>
              ) : (
                <Badge variant="running">
                  <span className="text-xs">Läuft</span>
                </Badge>
              )}
            </div>
            <div className="space-y-3">
              {/* Progress Bar und Prozentangabe nur anzeigen wenn progress_percent vorhanden ist */}
              {displayProgress?.progress?.progress_percent !== null && displayProgress?.progress?.progress_percent !== undefined && (
                <div>
                  <div className="h-2 bg-slate-200 dark:bg-slate-700 rounded-full overflow-hidden">
                    <div
                      className={cn(
                        "h-full bg-primary-500 transition-all duration-500 rounded-full",
                        (displayProgress.progress.finished || displayProgress.status === "completed") && "bg-emerald-500"
                      )}
                      style={{
                        width: (displayProgress.progress.finished || displayProgress.status === "completed")
                          ? "100%" 
                          : `${Math.min(100, Math.max(0, displayProgress.progress.progress_percent))}%`,
                      }}
                    />
                  </div>
                  <div className="text-xs text-slate-600 dark:text-slate-400 mt-1 text-right">
                    {displayProgress.progress.progress_percent}%
                  </div>
                </div>
              )}
              {displayProgress?.progress && (
                <>
                  <div className="grid grid-cols-3 gap-4 text-xs">
                    <div>
                      <div className="text-slate-500 dark:text-slate-400">Größe</div>
                      <div className="font-semibold text-slate-900 dark:text-slate-100">{formatSizeCompact(displayProgress.progress.total_size)}</div>
                    </div>
                    <div>
                      <div className="text-slate-500 dark:text-slate-400">Ordner</div>
                      <div className="font-semibold text-slate-900 dark:text-slate-100">{(displayProgress.progress.num_dir || 0).toLocaleString()}</div>
                    </div>
                    <div>
                      <div className="text-slate-500 dark:text-slate-400">Dateien</div>
                      <div className="font-semibold text-slate-900 dark:text-slate-100">{(displayProgress.progress.num_file || 0).toLocaleString()}</div>
                    </div>
                  </div>
                  {displayProgress.progress.current_path && (
                    <div className="flex items-start gap-2 text-xs">
                      <FolderOpen className="h-3.5 w-3.5 text-slate-400 dark:text-slate-500 mt-0.5 flex-shrink-0" />
                      <div className="flex-1 min-w-0">
                        <div className="text-slate-500 dark:text-slate-400 mb-1">Aktueller Pfad:</div>
                        <div className="text-slate-900 dark:text-slate-100 font-mono truncate">{displayProgress.progress.current_path}</div>
                      </div>
                    </div>
                  )}
                </>
              )}
            </div>
          </div>
        )}

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Left Column */}
          <div className="space-y-4">
            <div>
              <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-300 mb-2 flex items-center gap-1.5">
                <Calendar className="h-4 w-4" />
                Zeitplan
              </h3>
              <div className="bg-slate-50 dark:bg-slate-800 rounded-lg p-4 space-y-2">
                <div className="flex justify-between">
                  <span className="text-slate-600 dark:text-slate-400">Letzter Lauf:</span>
                  <span className="font-medium">
                    {currentScan.last_run ? formatDate(currentScan.last_run) : "-"}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-600 dark:text-slate-400">Nächster Lauf:</span>
                  <span className="font-medium text-slate-900 dark:text-slate-100">
                    {currentScan.next_run ? formatDate(currentScan.next_run) : "-"}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-600 dark:text-slate-400">Intervall:</span>
                  <span className="font-medium text-slate-900 dark:text-slate-100">{currentScan.interval || "-"}</span>
                </div>
              </div>
            </div>

            <div>
              <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-300 mb-2 flex items-center gap-1.5">
                <Settings className="h-4 w-4" />
                Konfiguration
              </h3>
              <div className="bg-slate-50 dark:bg-slate-800 rounded-lg p-4 space-y-2">
                <div className="flex justify-between">
                  <span className="text-slate-600 dark:text-slate-400">Status:</span>
                  <span className="font-medium">
                    {currentScan.enabled ? (
                      <span className="flex items-center gap-1.5">
                        <CheckCircle2 className="h-4 w-4 text-green-600" />
                        Aktiviert
                      </span>
                    ) : (
                      <span className="flex items-center gap-1.5">
                        <XCircle className="h-4 w-4 text-red-600 dark:text-red-400" />
                        Deaktiviert
                      </span>
                    )}
                  </span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-slate-600 dark:text-slate-400">ID:</span>
                  <span className="font-mono text-xs text-slate-900 dark:text-slate-100 bg-white dark:bg-slate-700 px-2 py-1 rounded border border-slate-200 dark:border-slate-600">
                    {currentScan.scan_slug}
                  </span>
                </div>
              </div>
            </div>
          </div>

          {/* Right Column */}
          <div className="space-y-4">
            {currentScan.nas && (
              <div>
                <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-300 mb-2 flex items-center gap-1.5">
                  <Server className="h-4 w-4" />
                  NAS-Verbindung
                </h3>
                <div className="bg-slate-50 dark:bg-slate-800 rounded-lg p-4 space-y-2">
                  <div className="flex justify-between">
                    <span className="text-slate-600 dark:text-slate-400">Host:</span>
                    <span className="font-medium text-slate-900 dark:text-slate-100">{currentScan.nas.host}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-600 dark:text-slate-400">Port:</span>
                    <span className="font-medium text-slate-900 dark:text-slate-100">
                      {currentScan.nas.port || (currentScan.nas.use_https ? 5001 : 5000)}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-600 dark:text-slate-400">Protokoll:</span>
                    <span className="font-medium text-slate-900 dark:text-slate-100">
                      {currentScan.nas.use_https ? "HTTPS" : "HTTP"}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-600 dark:text-slate-400">Benutzer:</span>
                    <span className="font-medium text-slate-900 dark:text-slate-100">{currentScan.nas.username}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-600 dark:text-slate-400">SSL-Verifizierung:</span>
                    <span className="font-medium text-slate-900 dark:text-slate-100">{currentScan.nas.verify_ssl ? "Ja" : "Nein"}</span>
                  </div>
                </div>
              </div>
            )}

            <div>
              <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-300 mb-2 flex items-center gap-1.5">
                <FolderOpen className="h-4 w-4" />
                Pfade
              </h3>
              <div className="bg-slate-50 dark:bg-slate-800 rounded-lg p-4">
                {folders.length > 0 ? (
                  <ul className="space-y-1">
                    {folders.map((folder, idx) => (
                      <li key={idx} className="text-sm text-slate-700 dark:text-slate-300">
                        • {folder}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-sm text-slate-400 dark:text-slate-500">Keine Pfade konfiguriert</p>
                )}
              </div>
            </div>
          </div>
        </div>

        <div className="pt-6 border-t border-slate-200 dark:border-slate-700">
          <div className="flex gap-3">
            <Button
              variant="primary"
              onClick={() => {
                onShowResults(currentScan.scan_slug)
                onOpenChange(false)
              }}
            >
              <BarChart3 className="h-4 w-4 mr-2" />
              Ergebnisse anzeigen
            </Button>
            <Button
              variant="secondary"
              onClick={() => {
                onShowHistory(currentScan.scan_slug)
                onOpenChange(false)
              }}
            >
              <History className="h-4 w-4 mr-2" />
              Historie anzeigen
            </Button>
          </div>
        </div>
      </DialogContent>

      <DialogFooter>
        <Button variant="secondary" onClick={() => onOpenChange(false)}>
          Schließen
        </Button>
        <Button
          variant="primary"
          onClick={() => {
            onTriggerScan(currentScan.scan_slug)
            onOpenChange(false)
          }}
          disabled={!canRun}
        >
          <Play className="h-4 w-4 mr-2" />
          Scan starten
        </Button>
      </DialogFooter>
    </Dialog>
  )
}
