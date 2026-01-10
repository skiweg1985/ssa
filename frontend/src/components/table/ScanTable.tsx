import { useState, useMemo } from "react"
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import { DropdownMenu, DropdownMenuItem } from "@/components/ui/dropdown-menu"
import { TableRow } from "./TableRow"
import { GridCard } from "./GridCard"
import { formatTimeAgo } from "@/lib/utils"
import type { ScanStatus } from "@/types/api"
import { LayoutGrid, List, ArrowUpDown, ArrowUp, ArrowDown, Clock } from "lucide-react"
import { cn } from "@/lib/cn"

type StatusFilter = "all" | "completed" | "failed" | "running" | "pending"
type SortField = "name" | "last_run" | "next_run"
type SortDirection = "asc" | "desc"
type Density = "compact" | "normal"
type ViewMode = "list" | "grid"

interface ScanTableProps {
  scans: ScanStatus[]
  loading: boolean
  lastUpdated: Date | null
  onRun: (scanName: string) => void
  onShowResults: (scanName: string) => void
  onShowHistory: (scanName: string) => void
  onShowDetail: (scan: ScanStatus) => void
  onShowApiInfo: (scan: ScanStatus) => void
  searchQuery: string
}

const statusLabels: Record<StatusFilter, string> = {
  all: "Alle",
  completed: "Abgeschlossen",
  failed: "Fehlgeschlagen",
  running: "Läuft",
  pending: "Ausstehend",
}

const sortLabels: Record<SortField, string> = {
  name: "Name",
  last_run: "Letzter Lauf",
  next_run: "Nächster Lauf",
}

export function ScanTable({
  scans,
  loading,
  lastUpdated,
  onRun,
  onShowResults,
  onShowHistory,
  onShowDetail,
  onShowApiInfo,
  searchQuery,
}: ScanTableProps) {
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all")
  const [sortField, setSortField] = useState<SortField>("name")
  const [sortDirection, setSortDirection] = useState<SortDirection>("asc")
  const [density] = useState<Density>("normal")
  const [viewMode, setViewMode] = useState<ViewMode>("list")

  // Filter and sort scans
  const filteredAndSortedScans = useMemo(() => {
    let filtered = scans

    // Search filter
    if (searchQuery) {
      const q = searchQuery.toLowerCase()
      filtered = filtered.filter(
        (scan) =>
          scan.scan_name.toLowerCase().includes(q) ||
          scan.nas?.host.toLowerCase().includes(q) ||
          scan.shares?.some((s) => s.toLowerCase().includes(q)) ||
          scan.folders?.some((f) => f.toLowerCase().includes(q))
      )
    }

    // Status filter
    if (statusFilter !== "all") {
      filtered = filtered.filter((scan) => scan.status === statusFilter)
    }

    // Sort
    filtered = [...filtered].sort((a, b) => {
      let aVal: string | number | undefined
      let bVal: string | number | undefined

      if (sortField === "name") {
        aVal = a.scan_name.toLowerCase()
        bVal = b.scan_name.toLowerCase()
      } else if (sortField === "last_run") {
        aVal = a.last_run ? new Date(a.last_run).getTime() : 0
        bVal = b.last_run ? new Date(b.last_run).getTime() : 0
      } else if (sortField === "next_run") {
        aVal = a.next_run ? new Date(a.next_run).getTime() : 0
        bVal = b.next_run ? new Date(b.next_run).getTime() : 0
      }

      if (aVal === undefined || bVal === undefined) return 0
      if (aVal < bVal) return sortDirection === "asc" ? -1 : 1
      if (aVal > bVal) return sortDirection === "asc" ? 1 : -1
      return 0
    })

    return filtered
  }, [scans, searchQuery, statusFilter, sortField, sortDirection])

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDirection(sortDirection === "asc" ? "desc" : "asc")
    } else {
      setSortField(field)
      setSortDirection("asc")
    }
  }

  const statusCounts = useMemo(() => {
    const counts = { all: scans.length, completed: 0, failed: 0, running: 0, pending: 0 }
    scans.forEach((scan) => {
      if (scan.status in counts) {
        counts[scan.status as keyof typeof counts]++
      }
    })
    return counts
  }, [scans])

  const SortIcon = sortDirection === "asc" ? ArrowUp : ArrowDown

  return (
    <Card className="border-slate-200 shadow-sm flex flex-col h-full">
      <CardHeader className="pb-4 flex-shrink-0">
        <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3 sm:gap-4">
          <div className="space-y-1 min-w-0">
            <CardTitle className="text-base sm:text-lg font-semibold">Scan-Status</CardTitle>
            {lastUpdated && (
              <CardDescription className="text-xs text-slate-500">
                Aktualisiert {formatTimeAgo(lastUpdated)}
              </CardDescription>
            )}
          </div>
          <div className="flex items-center gap-2 flex-shrink-0">
            <Badge variant="default" className="text-xs whitespace-nowrap">
              {filteredAndSortedScans.length} {filteredAndSortedScans.length === 1 ? "Scan" : "Scans"}
            </Badge>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setViewMode(viewMode === "list" ? "grid" : "list")}
              className="h-10 min-h-[40px] w-10 min-w-[40px] p-0"
              title={viewMode === "list" ? "Kachelansicht" : "Listenansicht"}
              aria-label={viewMode === "list" ? "Kachelansicht" : "Listenansicht"}
            >
              {viewMode === "list" ? <LayoutGrid className="h-4 w-4" /> : <List className="h-4 w-4" />}
            </Button>
          </div>
        </div>

        {/* Filters and Sort - Responsive layout */}
        <div className="flex flex-col sm:flex-row sm:items-center gap-3 mt-4 sm:mt-6 pt-4 border-t border-slate-100">
          {/* Status Filter Segmented Control */}
          <div className="inline-flex items-center rounded-lg border border-slate-200 bg-slate-50 p-1 shadow-sm overflow-x-auto scrollbar-hide -mx-1 sm:mx-0 sm:overflow-x-visible">
            <div className="flex items-center gap-1 min-w-max">
              {(["all", "completed", "failed", "running", "pending"] as StatusFilter[]).map((status) => {
                const isActive = statusFilter === status
                return (
                  <button
                    key={status}
                    onClick={() => setStatusFilter(status)}
                    className={cn(
                      "relative px-2.5 sm:px-3 py-2 sm:py-1.5 text-xs font-medium rounded-md transition-all focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-1 min-h-[40px] whitespace-nowrap",
                      isActive
                        ? "bg-white text-slate-900 shadow-sm"
                        : "text-slate-600 hover:text-slate-900"
                    )}
                    aria-pressed={isActive}
                    aria-label={`Filter: ${statusLabels[status]}`}
                  >
                    {statusLabels[status]}
                    {statusCounts[status] > 0 && (
                      <span className={cn(
                        "ml-1.5 px-1.5 py-0.5 rounded text-[10px] font-semibold",
                        isActive ? "bg-slate-100 text-slate-700" : "bg-slate-200 text-slate-600"
                      )}>
                        {statusCounts[status]}
                      </span>
                    )}
                  </button>
                )
              })}
            </div>
          </div>

          {/* Sort Dropdown */}
          <div className="sm:ml-auto flex-shrink-0">
            <DropdownMenu
              trigger={
                <Button variant="ghost" size="sm" className="h-10 min-h-[40px] text-xs">
                  <ArrowUpDown className="h-3.5 w-3.5 mr-1.5" />
                  <span className="hidden sm:inline">{sortLabels[sortField]}</span>
                  <span className="sm:hidden">Sort</span>
                  {sortField && <SortIcon className="h-3 w-3 ml-1.5" />}
                </Button>
              }
            >
              {(["name", "last_run", "next_run"] as SortField[]).map((field) => (
                <DropdownMenuItem
                  key={field}
                  onClick={() => handleSort(field)}
                  className="text-xs min-h-[40px]"
                >
                  {sortLabels[field]}
                  {sortField === field && (
                    <SortIcon className="h-3 w-3 ml-auto" />
                  )}
                </DropdownMenuItem>
              ))}
            </DropdownMenu>
          </div>
        </div>
      </CardHeader>

      <CardContent className="p-0 flex-1 flex flex-col min-h-0">
        {loading ? (
          viewMode === "list" ? (
            <div className="p-6 space-y-3 animate-pulse flex-1">
              {[1, 2, 3, 4, 5].map((i) => (
                <div key={i} className="flex items-center gap-4">
                  <Skeleton className="h-6 w-20 rounded-md" />
                  <Skeleton className="h-4 w-48 rounded-md" />
                  <Skeleton className="h-4 w-32 rounded-md" />
                  <Skeleton className="h-4 w-32 rounded-md" />
                  <Skeleton className="h-4 w-8 rounded-md" />
                  <Skeleton className="h-8 w-24 ml-auto rounded-md" />
                </div>
              ))}
            </div>
          ) : (
            <div className="p-6 flex-1 overflow-y-auto">
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
                {[1, 2, 3, 4, 5, 6, 7, 8].map((i) => (
                  <div key={i} className="border border-slate-200 rounded-lg p-4 space-y-3 animate-pulse">
                    <Skeleton className="h-5 w-3/4 rounded-md" />
                    <Skeleton className="h-6 w-20 rounded-md" />
                    <Skeleton className="h-4 w-full rounded-md" />
                    <Skeleton className="h-4 w-2/3 rounded-md" />
                    <Skeleton className="h-4 w-2/3 rounded-md" />
                    <Skeleton className="h-8 w-24 ml-auto rounded-md" />
                  </div>
                ))}
              </div>
            </div>
          )
        ) : filteredAndSortedScans.length === 0 ? (
          <div className="text-center py-16 px-6 flex-1 flex flex-col items-center justify-center">
            <div className="inline-flex h-12 w-12 items-center justify-center rounded-full bg-slate-100 mb-4">
              <Clock className="h-6 w-6 text-slate-400" />
            </div>
            <p className="text-sm font-medium text-slate-900 mb-1">Keine Scans gefunden</p>
            <p className="text-xs text-slate-500 mb-4">
              {searchQuery || statusFilter !== "all"
                ? "Versuchen Sie, Ihre Filter anzupassen"
                : "Es sind noch keine Scans vorhanden"}
            </p>
            {(searchQuery || statusFilter !== "all") && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  setStatusFilter("all")
                  // Note: searchQuery reset would need to be handled in parent
                }}
                className="text-xs h-10 min-h-[40px]"
                aria-label="Filter zurücksetzen"
              >
                Filter zurücksetzen
              </Button>
            )}
          </div>
        ) : viewMode === "list" ? (
          // Table with internal scrolling - max-height calculated to prevent page scroll
          // Responsive max-height: accounts for topbar (~80-100px) + card header (~180-220px) + padding
          <div className="flex-1 flex flex-col min-h-0 overflow-hidden">
            <div className="overflow-x-auto overflow-y-auto flex-1 scrollbar-hide" style={{ 
              maxHeight: 'calc(100vh - 20rem)' // ~320px for topbar + header + padding (responsive)
            }}>
              <table className="w-full border-collapse">
                <colgroup>
                  <col className="w-[200px] sm:w-[220px]" /> {/* Status */}
                  <col className="min-w-[180px]" /> {/* Job-Name - flexible */}
                  <col className="w-[140px] sm:w-[160px]" /> {/* Letzter Lauf */}
                  <col className="w-[140px] sm:w-[160px]" /> {/* Nächster Lauf */}
                  <col className="w-[60px]" /> {/* Info */}
                  <col className="w-[120px]" /> {/* Aktionen */}
                </colgroup>
                <thead className="sticky top-0 z-10 bg-slate-50/95 backdrop-blur-sm">
                  <tr className="border-b border-slate-200">
                    <th className="px-3 sm:px-4 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider">
                      Status
                    </th>
                    <th className="px-3 sm:px-4 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider">
                      Job-Name
                    </th>
                    <th className="px-3 sm:px-4 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider">
                      Letzter Lauf
                    </th>
                    <th className="px-3 sm:px-4 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider">
                      Nächster Lauf
                    </th>
                    <th className="px-3 sm:px-4 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider">
                      Info
                    </th>
                    <th className="px-3 sm:px-4 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider">
                      Aktionen
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {filteredAndSortedScans.map((scan) => (
                    <TableRow
                      key={scan.scan_name}
                      scan={scan}
                      density={density}
                      onRun={onRun}
                      onShowResults={onShowResults}
                      onShowHistory={onShowHistory}
                      onShowDetail={onShowDetail}
                      onShowApiInfo={onShowApiInfo}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ) : (
          <div className="p-4 sm:p-6 flex-1 overflow-y-auto">
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
              {filteredAndSortedScans.map((scan) => (
                <GridCard
                  key={scan.scan_name}
                  scan={scan}
                  onRun={onRun}
                  onShowResults={onShowResults}
                  onShowHistory={onShowHistory}
                  onShowDetail={onShowDetail}
                  onShowApiInfo={onShowApiInfo}
                />
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
