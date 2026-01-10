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
  const { progress } = useScanProgress(scan.scan_name, isRunning, 1000)
  
  // Determine effective status: use progress status if completed, otherwise use scan status
  const effectiveStatus = (progress?.status === "completed") ? "completed" : scan.status
  const status = getStatusConfig(effectiveStatus)
  const StatusIcon = statusIcons[effectiveStatus as keyof typeof statusIcons] || Clock

  return (
    <div
      className={cn(
        "border border-slate-200 rounded-lg bg-white p-4 transition-all duration-150",
        "hover:shadow-md hover:border-slate-300",
        "focus-within:ring-2 focus-within:ring-primary-500 focus-within:ring-offset-2",
        isRunning && effectiveStatus !== "completed" && "bg-blue-50/30 border-blue-200",
        effectiveStatus === "completed" && "bg-emerald-50/30 border-emerald-200"
      )}
    >
      {/* Header with Status and Info */}
      <div className="flex items-start justify-between mb-3">
        <div className="flex-1 min-w-0">
          <button
            onClick={() => onShowDetail(scan)}
            className="font-semibold text-slate-900 hover:text-primary-600 transition-colors cursor-pointer text-left focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-1 rounded truncate block w-full"
            title={scan.scan_name}
          >
            {scan.scan_name}
          </button>
        </div>
        <Tooltip content={buildScanTooltipContent(scan)}>
          <button
            className="text-slate-400 hover:text-slate-600 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-1 rounded transition-colors flex-shrink-0 ml-2"
            aria-label="Weitere Informationen"
          >
            <Info className="h-4 w-4" />
          </button>
        </Tooltip>
      </div>

      {/* Status Badge */}
      <div className="mb-3">
        <Badge variant={status.variant} className="w-fit">
          <StatusIcon
            className={cn(
              "h-3.5 w-3.5",
              isRunning && effectiveStatus !== "completed" && "animate-spin"
            )}
          />
          <span>{status.text}</span>
        </Badge>
      </div>

      {/* Progress Bar for Running Scans */}
      {isRunning && progress && progress.progress && progress.progress.progress_percent !== null && progress.progress.progress_percent !== undefined && (
        <div className="mb-3">
          <Tooltip
            content={
              progress.progress.current_path
                ? `Aktueller Pfad: ${progress.progress.current_path}\n${formatSizeCompact(progress.progress.total_size)} • ${(progress.progress.num_dir || 0).toLocaleString()} Ordner • ${(progress.progress.num_file || 0).toLocaleString()} Dateien\nFortschritt: ${progress.progress.progress_percent}%`
                : `${formatSizeCompact(progress.progress.total_size)} • ${(progress.progress.num_dir || 0).toLocaleString()} Ordner • ${(progress.progress.num_file || 0).toLocaleString()} Dateien\nFortschritt: ${progress.progress.progress_percent}%`
            }
          >
            <div className="w-full cursor-help">
              <div className="h-1.5 bg-slate-200 rounded-full overflow-hidden relative">
                {(progress.progress.finished || progress.status === "completed") ? (
                  <div className="h-full bg-emerald-500 rounded-full w-full transition-all duration-500 animate-in fade-in" />
                ) : (
                  <>
                    <div 
                      className="h-full bg-primary-500 rounded-full animate-pulse" 
                      style={{ width: `${Math.min(100, Math.max(0, progress.progress.progress_percent))}%` }} 
                    />
                    <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/20 to-transparent animate-shimmer" />
                  </>
                )}
              </div>
              <div className="text-[10px] text-slate-500 mt-1 flex items-center justify-between gap-1">
                <span className="truncate flex-1">
                  {formatSizeCompact(progress.progress.total_size)} • {(progress.progress.num_dir || 0).toLocaleString()} Ordner
                </span>
                <span className={cn(
                  "font-semibold flex-shrink-0",
                  (progress.progress.finished || progress.status === "completed") 
                    ? "text-emerald-600" 
                    : "text-primary-600"
                )}>
                  {progress.progress.progress_percent}%
                </span>
              </div>
            </div>
          </Tooltip>
        </div>
      )}

      {/* Details */}
      <div className="space-y-2 mb-4 text-xs">
        <div className="flex items-center justify-between">
          <span className="text-slate-500">Letzter Lauf:</span>
          {scan.last_run ? (
            <Tooltip content={formatDateShort(scan.last_run)}>
              <span className="text-slate-700 cursor-help font-medium">
                {formatRelativeTime(scan.last_run)}
              </span>
            </Tooltip>
          ) : (
            <span className="text-slate-400">-</span>
          )}
        </div>
        <div className="flex items-center justify-between">
          <span className="text-slate-500">Nächster Lauf:</span>
          {scan.next_run ? (
            <Tooltip content={formatDateShort(scan.next_run)}>
              <span className="text-slate-700 cursor-help font-medium">
                {formatRelativeTime(scan.next_run)}
              </span>
            </Tooltip>
          ) : (
            <span className="text-slate-400">-</span>
          )}
        </div>
      </div>

      {/* Actions */}
      <div className="flex items-center justify-end pt-3 border-t border-slate-100">
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
