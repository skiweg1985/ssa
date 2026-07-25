import { Play, BarChart3, History, MoreVertical, Eye, Link2, Pencil, Trash2, Square } from "lucide-react"
import { Button } from "@/components/ui/button"
import { DropdownMenu, DropdownMenuItem } from "@/components/ui/dropdown-menu"
import type { ScanStatus } from "@/types/api"

interface TableActionsProps {
  scan: ScanStatus
  onRun: (scanName: string) => void
  onCancel?: (scan: ScanStatus) => void
  onShowResults: (scanName: string) => void
  onShowHistory: (scanName: string) => void
  onShowDetail: (scan: ScanStatus) => void
  onShowApiInfo: (scan: ScanStatus) => void
  onEdit?: (scan: ScanStatus) => void
  onDelete?: (scan: ScanStatus) => void
}

export function TableActions({
  scan,
  onRun,
  onCancel,
  onShowResults,
  onShowHistory,
  onShowDetail,
  onShowApiInfo,
  onEdit,
  onDelete,
}: TableActionsProps) {
  const canRun = scan.status !== "running" && scan.enabled
  const isRunning = scan.status === "running"

  return (
    <div className="flex items-center gap-1.5">
      {/* Zeilenaktion, nicht die Hauptaktion der Seite: Umriss statt Füllung.
          Gefüllt ist in dieser Ansicht nur „Neuer Scan" — eine Tabelle mit zwanzig
          Zeilen hätte sonst zwanzig Primärbuttons, und keiner davon führt mehr. */}
      <Button
        variant="default"
        size="sm"
        onClick={() => onRun(scan.scan_slug)}
        disabled={!canRun}
        className="h-9 w-9 p-0 text-primary-600 dark:text-primary-400 hover:border-primary-400 dark:hover:border-primary-500 hover:bg-primary-50 dark:hover:bg-primary-900/30"
        title="Scan starten"
        aria-label={`Scan „${scan.scan_name}" starten`}
      >
        <Play className="h-4 w-4" aria-hidden="true" />
      </Button>
      <DropdownMenu
        trigger={
          <Button
            variant="ghost"
            size="sm"
            className="h-9 w-9 p-0"
            title="Weitere Aktionen"
            aria-label={`Weitere Aktionen für „${scan.scan_name}"`}
          >
            <MoreVertical className="h-4 w-4" aria-hidden="true" />
          </Button>
        }
      >
        {/* Nur während eines Laufs - der einzige Zeitpunkt, an dem der
            Abbruch überhaupt etwas tut. Steht oben, weil er dann die
            dringlichste Aktion ist. */}
        {isRunning && onCancel && (
          <DropdownMenuItem
            onClick={() => onCancel(scan)}
            className="text-xs min-h-[40px] text-amber-700 dark:text-amber-400"
          >
            <Square className="h-3.5 w-3.5 mr-2" />
            Scan abbrechen
          </DropdownMenuItem>
        )}
        <DropdownMenuItem
          onClick={() => onShowResults(scan.scan_slug)}
          className="text-xs min-h-[40px]"
        >
          <BarChart3 className="h-3.5 w-3.5 mr-2" />
          Ergebnisse
        </DropdownMenuItem>
        <DropdownMenuItem
          onClick={() => onShowHistory(scan.scan_slug)}
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
        {onEdit && (
          <DropdownMenuItem
            onClick={() => onEdit(scan)}
            className="text-xs min-h-[40px] border-t border-slate-100 dark:border-slate-700"
          >
            <Pencil className="h-3.5 w-3.5 mr-2" />
            Bearbeiten
          </DropdownMenuItem>
        )}
        {onDelete && (
          <DropdownMenuItem
            onClick={() => onDelete(scan)}
            className="text-xs min-h-[40px] text-red-600 dark:text-red-400"
          >
            <Trash2 className="h-3.5 w-3.5 mr-2" />
            Löschen
          </DropdownMenuItem>
        )}
      </DropdownMenu>
    </div>
  )
}
