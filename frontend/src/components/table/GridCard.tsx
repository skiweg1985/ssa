import { Badge } from "@/components/ui/badge"
import { Tooltip } from "@/components/ui/tooltip"
import { Info, CheckCircle2, XCircle, Loader2, Clock } from "lucide-react"
import { TableActions } from "./TableActions"
import { getStatusConfig, formatDateShort, formatRelativeTime, buildScanTooltipContent, formatSizeCompact } from "@/lib/utils"
import { useScanProgress } from "@/hooks/useScanProgress"
import type { ScanStatus } from "@/types/api"
import { cn } from "@/lib/cn"

interface GridCardProps {
  scan: ScanStatus
  onRun: (scanName: string) => void
  onShowResults: (scanName: string) => void
  onShowHistory: (scanName: string) => void
  onShowDetail: (scan: ScanStatus) => void
  onShowApiInfo: (scan: ScanStatus) => void
}

const statusIcons = {
  completed: CheckCircle2,
  failed: XCircle,
  running: Loader2,
  pending: Clock,
}

export function GridCard({
  scan,
  onRun,
  onShowResults,
  onShowHistory,
  onShowDetail,
  onShowApiInfo,
}: GridCardProps) {
  // Fetch progress only for running scans
  // Don't fetch for completed scans to avoid 404s after grace period
  const isRunning = scan.status === "running"
  // Verwende slug für Progress-Aufrufe
  const { progress } = useScanProgress(scan.scan_slug, isRunning, 1000)
  
  // Determine effective status: use progress status if completed, otherwise use scan status
  const effectiveStatus = (progress?.status === "completed") ? "completed" : scan.status
  const status = getStatusConfig(effectiveStatus)
  const StatusIcon = statusIcons[effectiveStatus as keyof typeof statusIcons] || Clock
  
  // Check if progress info is displayed
  const hasProgressInfo = isRunning && progress && progress.progress
  const hasProgressPercent = hasProgressInfo && progress.progress.progress_percent !== null && progress.progress.progress_percent !== undefined
  
  // Check if progress has meaningful data (not all zeros)
  const hasProgressData = hasProgressInfo && (
    (progress.progress.total_size || 0) > 0 ||
    (progress.progress.num_dir || 0) > 0 ||
    (progress.progress.num_file || 0) > 0
  )

  return (
    <div
      className={cn(
        "border border-slate-200 dark:border-slate-700 rounded-lg bg-white dark:bg-slate-800 p-4 transition-all duration-150",
        "hover:shadow-md hover:border-slate-300 dark:hover:border-slate-600",
        "focus-within:ring-2 focus-within:ring-primary-500 focus-within:ring-offset-2",
        "flex flex-col h-full",
        isRunning && effectiveStatus !== "completed" && "bg-blue-50/30 dark:bg-blue-900/20 border-blue-200 dark:border-blue-800",
        effectiveStatus === "completed" && "bg-emerald-50/30 dark:bg-emerald-900/20 border-emerald-200 dark:border-emerald-800"
      )}
    >
      {/* Header with Title and Info Icon - Fixed Top Row */}
      <div className="flex items-start justify-between mb-3 flex-shrink-0">
        <div className="flex-1 min-w-0">
          <button
            onClick={() => onShowDetail(scan)}
            className="font-normal text-sm text-slate-700 dark:text-slate-300 hover:text-primary-600 dark:hover:text-primary-400 transition-colors cursor-pointer text-left focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-1 rounded truncate block w-full"
            title={scan.scan_name}
          >
            <div className="flex flex-col gap-0.5">
              <span className="truncate">{scan.scan_name}</span>
              <div className="text-[10px] text-slate-500 dark:text-slate-400">
                <span className="font-mono">ID: {scan.scan_slug}</span>
              </div>
            </div>
          </button>
        </div>
        <Tooltip content={buildScanTooltipContent(scan)}>
          <button
            className="text-slate-400 dark:text-slate-500 hover:text-slate-600 dark:hover:text-slate-300 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-1 rounded transition-colors flex-shrink-0 ml-2"
            aria-label="Weitere Informationen"
          >
            <Info className="h-4 w-4" />
          </button>
        </Tooltip>
      </div>

      {/* Status Badge - Fixed Row */}
      <div className="mb-3 flex-shrink-0">
        <Badge variant={status.variant} className="w-fit justify-start overflow-visible min-w-fit">
          <StatusIcon
            className={cn(
              "h-3.5 w-3.5",
              isRunning && effectiveStatus !== "completed" && "animate-spin"
            )}
          />
          <span>{status.text}</span>
        </Badge>
      </div>

      {/* Reserved Progress Slot - Fixed Height Container */}
      <div className="min-h-[35px] mb-0 flex-shrink-0 flex items-start w-full">
        {hasProgressInfo ? (
          <Tooltip
            fullWidth
            content={
              progress.progress.current_path
                ? `Aktueller Pfad: ${progress.progress.current_path}\n${formatSizeCompact(progress.progress.total_size)} • ${(progress.progress.num_dir || 0).toLocaleString()} Ordner • ${(progress.progress.num_file || 0).toLocaleString()} Dateien${hasProgressPercent ? `\nFortschritt: ${progress.progress.progress_percent}%` : ''}`
                : `${formatSizeCompact(progress.progress.total_size)} • ${(progress.progress.num_dir || 0).toLocaleString()} Ordner • ${(progress.progress.num_file || 0).toLocaleString()} Dateien${hasProgressPercent ? `\nFortschritt: ${progress.progress.progress_percent}%` : ''}`
            }
          >
            <div className="w-full cursor-help min-w-0 block">
              {hasProgressData ? (
                <>
                  {hasProgressPercent && (
                    <div className="h-1.5 bg-slate-200 dark:bg-slate-700 rounded-full overflow-hidden relative mb-0.5 w-full">
                      {(progress.progress.finished || progress.status === "completed") ? (
                        <div className="h-full bg-emerald-500 rounded-full w-full transition-all duration-500 animate-in fade-in" />
                      ) : (
                        <>
                          <div 
                            className="h-full bg-primary-500 rounded-full animate-pulse" 
                            style={{ width: `${Math.min(100, Math.max(0, progress.progress.progress_percent || 0))}%` }} 
                          />
                          <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/20 dark:via-white/10 to-transparent animate-shimmer" />
                        </>
                      )}
                    </div>
                  )}
                  <div className={cn("text-[10px] text-slate-500 dark:text-slate-400", hasProgressPercent && "mt-0.5")}>
                    <div className="flex items-center justify-between gap-1 flex-wrap">
                      <span className="whitespace-nowrap truncate">
                        {formatSizeCompact(progress.progress.total_size)} • {(progress.progress.num_dir || 0).toLocaleString()} Ordner • {(progress.progress.num_file || 0).toLocaleString()} Dateien
                      </span>
                      {hasProgressPercent && (
                        <span className={cn(
                          "font-semibold flex-shrink-0",
                            (progress.progress.finished || progress.status === "completed") 
                            ? "text-emerald-600 dark:text-emerald-400" 
                            : "text-primary-600 dark:text-primary-400"
                        )}>
                          {progress.progress.progress_percent}%
                        </span>
                      )}
                    </div>
                  </div>
                </>
              ) : (
                <div className="text-[10px] text-slate-500 dark:text-slate-400 italic">
                  Warte auf Ergebnisse...
                </div>
              )}
            </div>
          </Tooltip>
        ) : null}
      </div>

      {/* Details - Fixed Row with 2-column layout */}
      <div className="space-y-2 mb-4 text-xs flex-shrink-0">
        <div className="flex items-center justify-between gap-2">
          <span className="text-slate-500 dark:text-slate-400 flex-shrink-0">Letzter Lauf:</span>
          {scan.last_run ? (
            <Tooltip content={formatDateShort(scan.last_run)}>
              <span className="text-slate-700 dark:text-slate-300 cursor-help font-medium truncate text-right">
                {formatRelativeTime(scan.last_run)}
              </span>
            </Tooltip>
          ) : (
            <span className="text-slate-400 dark:text-slate-500">-</span>
          )}
        </div>
        <div className="flex items-center justify-between gap-2">
          <span className="text-slate-500 dark:text-slate-400 flex-shrink-0">Nächster Lauf:</span>
          {scan.next_run ? (
            <Tooltip content={formatDateShort(scan.next_run)}>
              <span className="text-slate-700 dark:text-slate-300 cursor-help font-medium truncate text-right">
                {formatRelativeTime(scan.next_run)}
              </span>
            </Tooltip>
          ) : (
            <span className="text-slate-400 dark:text-slate-500">-</span>
          )}
        </div>
      </div>

      {/* Actions - Fixed Bottom Row */}
      <div className="flex items-center justify-end pt-3 border-t border-slate-100 dark:border-slate-700 mt-auto flex-shrink-0">
        <TableActions
          scan={scan}
          onRun={onRun}
          onShowResults={onShowResults}
          onShowHistory={onShowHistory}
          onShowDetail={onShowDetail}
          onShowApiInfo={onShowApiInfo}
        />
      </div>
    </div>
  )
}
