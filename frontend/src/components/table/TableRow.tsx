import { Badge } from "@/components/ui/badge"
import { Tooltip } from "@/components/ui/tooltip"
import { Info, CheckCircle2, XCircle, Loader2, Clock } from "lucide-react"
import { TableActions } from "./TableActions"
import { getStatusConfig, formatDateShort, formatRelativeTime, buildScanTooltipContent, formatSizeCompact } from "@/lib/utils"
import { useScanProgress } from "@/hooks/useScanProgress"
import type { ScanStatus } from "@/types/api"
import { cn } from "@/lib/cn"

interface TableRowProps {
  scan: ScanStatus
  density: "compact" | "normal"
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

export function TableRow({
  scan,
  density,
  onRun,
  onShowResults,
  onShowHistory,
  onShowDetail,
  onShowApiInfo,
}: TableRowProps) {
  // Fetch progress only for running scans
  // Don't fetch for completed scans to avoid 404s after grace period
  const isRunning = scan.status === "running"
  const { progress } = useScanProgress(scan.scan_name, isRunning, 1000)
  
  // Determine effective status: use progress status if completed, otherwise use scan status
  const effectiveStatus = (progress?.status === "completed") ? "completed" : scan.status
  const status = getStatusConfig(effectiveStatus)
  const StatusIcon = statusIcons[effectiveStatus as keyof typeof statusIcons] || Clock
  
  // Check if progress info is displayed (with or without percent)
  const hasProgressInfo = isRunning && progress && progress.progress
  const hasProgressPercent = hasProgressInfo && progress.progress.progress_percent !== null && progress.progress.progress_percent !== undefined
  
  // Adjust padding based on density and whether progress info is shown
  // When progress info is shown, add extra top padding to prevent "Läuft" from touching the top
  const paddingClasses = hasProgressInfo 
    ? (density === "compact" ? "pt-5 pb-4" : "pt-6 pb-5")
    : (density === "compact" ? "py-3" : "py-4")

  return (
    <tr
      className={cn(
        "border-b border-slate-100 transition-all duration-150 group",
        "hover:bg-slate-50/50 focus-within:bg-slate-50",
        "hover:shadow-sm",
        isRunning && effectiveStatus !== "completed" && "bg-blue-50/30",
        effectiveStatus === "completed" && "bg-emerald-50/30",
        paddingClasses
      )}
    >
      {/* Status */}
      <td className={cn("px-3 sm:px-4", hasProgressInfo && "align-top")}>
        <div className={cn("flex flex-col", hasProgressInfo ? "gap-1.5 pt-0.5" : "gap-1.5")}>
          <Badge variant={status.variant} className="w-fit">
            <StatusIcon
              className={cn(
                "h-3.5 w-3.5",
                isRunning && effectiveStatus !== "completed" && "animate-spin"
              )}
            />
            <span className="whitespace-nowrap">{status.text}</span>
          </Badge>
          {hasProgressInfo && (
            <Tooltip
              content={
                progress.progress.current_path
                  ? `Aktueller Pfad: ${progress.progress.current_path}\n${formatSizeCompact(progress.progress.total_size)} • ${(progress.progress.num_dir || 0).toLocaleString()} Ordner • ${(progress.progress.num_file || 0).toLocaleString()} Dateien${hasProgressPercent ? `\nFortschritt: ${progress.progress.progress_percent}%` : ''}`
                  : `${formatSizeCompact(progress.progress.total_size)} • ${(progress.progress.num_dir || 0).toLocaleString()} Ordner • ${(progress.progress.num_file || 0).toLocaleString()} Dateien${hasProgressPercent ? `\nFortschritt: ${progress.progress.progress_percent}%` : ''}`
              }
            >
              <div className="w-full max-w-[200px] sm:max-w-[220px] cursor-help">
                {hasProgressPercent && (
                  <div className="h-1.5 bg-slate-200 rounded-full overflow-hidden relative">
                    {(progress.progress.finished || progress.status === "completed") ? (
                      <div className="h-full bg-emerald-500 rounded-full w-full transition-all duration-500 animate-in fade-in" />
                    ) : (
                      <>
                        <div 
                          className="h-full bg-primary-500 rounded-full animate-pulse" 
                          style={{ width: `${Math.min(100, Math.max(0, progress.progress.progress_percent || 0))}%` }} 
                        />
                        <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/20 to-transparent animate-shimmer" />
                      </>
                    )}
                  </div>
                )}
                <div className={cn("text-[10px] text-slate-500 flex items-center justify-between gap-1", hasProgressPercent && "mt-0.5")}>
                  <span className="truncate flex-1">
                    {formatSizeCompact(progress.progress.total_size)} • {(progress.progress.num_dir || 0).toLocaleString()} Ordner • {(progress.progress.num_file || 0).toLocaleString()} Dateien
                  </span>
                  {hasProgressPercent && (
                    <span className={cn(
                      "font-semibold flex-shrink-0",
                      (progress.progress.finished || progress.status === "completed") 
                        ? "text-emerald-600" 
                        : "text-primary-600"
                    )}>
                      {progress.progress.progress_percent}%
                    </span>
                  )}
                </div>
              </div>
            </Tooltip>
          )}
        </div>
      </td>

      {/* Job Name */}
      <td className="px-3 sm:px-4 min-w-0">
        <button
          onClick={() => onShowDetail(scan)}
          className="font-medium text-slate-900 hover:text-primary-600 transition-colors cursor-pointer text-left focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-1 rounded truncate block w-full"
          aria-label={`Details für ${scan.scan_name} anzeigen`}
        >
          {scan.scan_name}
        </button>
      </td>

      {/* Last Run */}
      <td className={cn("px-3 sm:px-4 whitespace-nowrap", density === "compact" && "text-sm")}>
        {scan.last_run ? (
          <Tooltip content={formatDateShort(scan.last_run)}>
            <span className="text-xs text-slate-600 cursor-help">
              {formatRelativeTime(scan.last_run)}
            </span>
          </Tooltip>
        ) : (
          <span className="text-slate-400 text-xs">-</span>
        )}
      </td>

      {/* Next Run */}
      <td className={cn("px-3 sm:px-4 whitespace-nowrap", density === "compact" && "text-sm")}>
        {scan.next_run ? (
          <Tooltip content={formatDateShort(scan.next_run)}>
            <span className="text-xs text-slate-600 cursor-help">
              {formatRelativeTime(scan.next_run)}
            </span>
          </Tooltip>
        ) : (
          <span className="text-slate-400 text-xs">-</span>
        )}
      </td>

      {/* Info */}
      <td className="px-3 sm:px-4">
        <Tooltip content={buildScanTooltipContent(scan)}>
          <button
            className="text-slate-400 hover:text-slate-600 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-1 rounded transition-colors h-10 w-10 min-h-[40px] min-w-[40px] flex items-center justify-center"
            aria-label="Weitere Informationen"
          >
            <Info className="h-4 w-4" />
          </button>
        </Tooltip>
      </td>

      {/* Actions */}
      <td className="px-3 sm:px-4">
        <TableActions
          scan={scan}
          onRun={onRun}
          onShowResults={onShowResults}
          onShowHistory={onShowHistory}
          onShowDetail={onShowDetail}
          onShowApiInfo={onShowApiInfo}
        />
      </td>
    </tr>
  )
}
