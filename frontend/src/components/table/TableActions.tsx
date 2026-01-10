import { Play, BarChart3, History, MoreVertical, Eye, Link2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { DropdownMenu, DropdownMenuItem } from "@/components/ui/dropdown-menu"
import type { ScanStatus } from "@/types/api"

interface TableActionsProps {
  scan: ScanStatus
  onRun: (scanName: string) => void
  onShowResults: (scanName: string) => void
  onShowHistory: (scanName: string) => void
  onShowDetail: (scan: ScanStatus) => void
  onShowApiInfo: (scan: ScanStatus) => void
}

export function TableActions({
  scan,
  onRun,
  onShowResults,
  onShowHistory,
  onShowDetail,
  onShowApiInfo,
}: TableActionsProps) {
  const canRun = scan.status !== "running" && scan.enabled

  return (
    <div className="flex items-center gap-1.5">
      <Button
        variant="primary"
        size="sm"
        onClick={() => onRun(scan.scan_name)}
        disabled={!canRun}
        className="h-10 min-h-[40px] w-10 min-w-[40px] p-0"
        title="Scan starten"
        aria-label="Scan starten"
      >
        <Play className="h-4 w-4" />
      </Button>
      <DropdownMenu
        trigger={
          <Button
            variant="ghost"
            size="sm"
            className="h-10 min-h-[40px] w-10 min-w-[40px] p-0"
            title="Weitere Aktionen"
            aria-label="Weitere Aktionen"
          >
            <MoreVertical className="h-4 w-4" />
          </Button>
        }
      >
        <DropdownMenuItem
          onClick={() => onShowResults(scan.scan_name)}
          className="text-xs min-h-[40px]"
        >
          <BarChart3 className="h-3.5 w-3.5 mr-2" />
          Ergebnisse
        </DropdownMenuItem>
        <DropdownMenuItem
          onClick={() => onShowHistory(scan.scan_name)}
          className="text-xs min-h-[40px]"
        >
          <History className="h-3.5 w-3.5 mr-2" />
          Historie
        </DropdownMenuItem>
        <DropdownMenuItem
          onClick={() => onShowDetail(scan)}
          className="text-xs min-h-[40px]"
        >
          <Eye className="h-3.5 w-3.5 mr-2" />
          Details
        </DropdownMenuItem>
        <DropdownMenuItem
          onClick={() => onShowApiInfo(scan)}
          className="text-xs min-h-[40px]"
        >
          <Link2 className="h-3.5 w-3.5 mr-2" />
          API-Info
        </DropdownMenuItem>
      </DropdownMenu>
    </div>
  )
}
