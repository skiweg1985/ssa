import { useState, useEffect } from "react"
import { Search, RefreshCw, Settings, Database, X, CheckCircle2, BookOpen } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { useDebounce } from "@/hooks/useDebounce"
import { useKeyboardShortcuts } from "@/hooks/useKeyboardShortcuts"
import { formatTimeAgo } from "@/lib/utils"

interface TopbarProps {
  searchQuery: string
  onSearchChange: (query: string) => void
  onReloadConfig: () => void
  onRefresh: () => void
  onOpenStorage: () => void
  onOpenCommandPalette: () => void
  onOpenApiInfo: () => void
  isLoading?: boolean
  autoRefreshActive?: boolean
  lastUpdated?: Date | null
}

export function Topbar({
  searchQuery,
  onSearchChange,
  onReloadConfig,
  onRefresh,
  onOpenStorage,
  onOpenCommandPalette,
  onOpenApiInfo,
  isLoading = false,
  autoRefreshActive = false,
  lastUpdated = null,
}: TopbarProps) {
  const [localSearch, setLocalSearch] = useState(searchQuery)
  const [timeAgo, setTimeAgo] = useState("")
  const debouncedSearch = useDebounce(localSearch, 300)

  useKeyboardShortcuts([
    {
      key: "k",
      metaKey: true,
      handler: onOpenCommandPalette,
    },
  ])

  useEffect(() => {
    if (debouncedSearch !== searchQuery) {
      onSearchChange(debouncedSearch)
    }
  }, [debouncedSearch, searchQuery, onSearchChange])

  // Update time ago every second
  useEffect(() => {
    if (!lastUpdated) {
      setTimeAgo("")
      return
    }

    const updateTime = () => {
      setTimeAgo(formatTimeAgo(lastUpdated))
    }

    updateTime()
    const interval = setInterval(updateTime, 1000)

    return () => clearInterval(interval)
  }, [lastUpdated])

  return (
    <header className="sticky top-0 z-50 w-full border-b border-slate-200/80 bg-white/80 backdrop-blur-md supports-[backdrop-filter]:bg-white/60">
      <div className="mx-auto max-w-screen-xl px-4 sm:px-6 lg:px-8">
        {/* Responsive layout: single row on lg+, two rows on smaller screens */}
        <div className="flex flex-col lg:flex-row lg:h-16 lg:items-center gap-3 lg:gap-4 py-3 lg:py-0">
          {/* Row 1: Brand + Actions (on small screens) / Brand only (on large screens) */}
          <div className="flex items-center justify-between lg:justify-start gap-3 lg:gap-4 flex-shrink-0 min-w-0">
            {/* Left: Brand */}
            <div className="flex items-center gap-2 sm:gap-3 flex-shrink-0 min-w-0">
              <div className="flex h-8 w-8 sm:h-9 sm:w-9 items-center justify-center rounded-lg bg-primary-500 text-white flex-shrink-0">
                <Search className="h-4 w-4 sm:h-4.5 sm:w-4.5" />
              </div>
              <div className="min-w-0">
                <h1 className="text-sm sm:text-base font-semibold text-slate-900 leading-tight truncate">
                  Synology Space Analyzer
                </h1>
                <p className="text-[10px] sm:text-xs text-slate-500 leading-tight truncate">Scan-Status Dashboard</p>
              </div>
            </div>

            {/* Right: Actions (visible on small screens, hidden on lg+) */}
            <div className="flex items-center gap-1.5 sm:gap-2 lg:hidden flex-shrink-0">
              {autoRefreshActive && lastUpdated && (
                <div className="flex items-center gap-1.5 px-2 py-1.5 rounded-md bg-emerald-50 text-emerald-700 text-[10px] sm:text-xs font-medium">
                  <CheckCircle2 className="h-3 w-3 sm:h-3.5 sm:w-3.5" />
                  <span className="hidden sm:inline">Auto</span>
                </div>
              )}
              <Button
                variant="ghost"
                size="sm"
                onClick={onOpenApiInfo}
                className="h-10 min-h-[40px] px-2 sm:px-3"
                title="API-Dokumentation"
                aria-label="API-Dokumentation"
              >
                <BookOpen className="h-4 w-4" />
                <span className="hidden sm:inline ml-1.5">API</span>
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={onReloadConfig}
                disabled={isLoading}
                className="h-10 min-h-[40px] px-2 sm:px-3"
                title="Konfiguration neu laden"
                aria-label="Konfiguration neu laden"
              >
                <Settings className="h-4 w-4" />
                <span className="hidden sm:inline ml-1.5">Config</span>
              </Button>
              <Button
                variant="primary"
                size="sm"
                onClick={onRefresh}
                isLoading={isLoading}
                className="h-10 min-h-[40px] px-2 sm:px-3"
                aria-label="Aktualisieren"
              >
                {!isLoading && <RefreshCw className="h-4 w-4" />}
                <span className="hidden sm:inline ml-1.5">Aktualisieren</span>
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={onOpenStorage}
                className="h-10 min-h-[40px] px-2 sm:px-3"
                title="Storage-Management"
                aria-label="Storage-Management"
              >
                <Database className="h-4 w-4" />
                <span className="hidden sm:inline ml-1.5">Storage</span>
              </Button>
            </div>
          </div>

          {/* Row 2: Search + Auto-Refresh (on small screens) / Center: Search (on large screens) */}
          <div className="flex items-center gap-2 lg:flex-1 lg:max-w-md lg:mx-4 min-w-0">
            <div className="relative flex-1 min-w-0">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400 pointer-events-none" />
              <Input
                type="text"
                placeholder="Suchen..."
                value={localSearch}
                onChange={(e) => setLocalSearch(e.target.value)}
                className="pl-9 pr-20 sm:pr-24 h-10 min-h-[40px] text-sm"
                onKeyDown={(e) => {
                  if ((e.metaKey || e.ctrlKey) && e.key === "k") {
                    e.preventDefault()
                    onOpenCommandPalette()
                  }
                }}
                aria-label="Suche"
              />
              <div className="absolute right-3 top-1/2 -translate-y-1/2 flex items-center gap-1.5">
                {localSearch && (
                  <button
                    onClick={() => {
                      setLocalSearch("")
                      onSearchChange("")
                    }}
                    className="h-8 w-8 min-h-[32px] min-w-[32px] rounded-sm text-slate-400 hover:text-slate-600 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-1 transition-colors flex items-center justify-center"
                    aria-label="Suche löschen"
                  >
                    <X className="h-4 w-4" />
                  </button>
                )}
                <kbd className="hidden sm:inline-flex h-5 select-none items-center gap-1 rounded border border-slate-200 bg-slate-50 px-1.5 font-mono text-[10px] font-medium text-slate-500">
                  <span className="text-xs">⌘</span>K
                </kbd>
              </div>
            </div>

            {/* Auto-Refresh Indicator (visible on small screens, next to search) */}
            {autoRefreshActive && lastUpdated && (
              <div className="lg:hidden flex items-center gap-1.5 px-2.5 py-1.5 rounded-md bg-emerald-50 text-emerald-700 text-xs font-medium flex-shrink-0">
                <CheckCircle2 className="h-3.5 w-3.5" />
                <span className="hidden sm:inline">Auto</span>
              </div>
            )}
          </div>

          {/* Right: Actions (visible on lg+ screens only) */}
          <div className="hidden lg:flex items-center gap-2 flex-shrink-0">
            {autoRefreshActive && lastUpdated && (
              <div className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-md bg-emerald-50 text-emerald-700 text-xs font-medium">
                <CheckCircle2 className="h-3.5 w-3.5" />
                <span className="hidden xl:inline">{timeAgo || "Aktualisiert"}</span>
                <span className="xl:hidden">Auto</span>
              </div>
            )}
            <Button
              variant="ghost"
              size="sm"
              onClick={onOpenApiInfo}
              className="h-10 min-h-[40px]"
              title="API-Dokumentation"
              aria-label="API-Dokumentation"
            >
              <BookOpen className="h-4 w-4" />
              <span className="hidden sm:inline ml-2">API</span>
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={onReloadConfig}
              disabled={isLoading}
              className="h-10 min-h-[40px]"
              title="Konfiguration neu laden"
              aria-label="Konfiguration neu laden"
            >
              <Settings className="h-4 w-4" />
              <span className="hidden sm:inline ml-2">Config</span>
            </Button>
            <Button
              variant="primary"
              size="sm"
              onClick={onRefresh}
              isLoading={isLoading}
              className="h-10 min-h-[40px]"
              aria-label="Aktualisieren"
            >
              {!isLoading && <RefreshCw className="h-4 w-4" />}
              <span className="hidden sm:inline ml-2">Aktualisieren</span>
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={onOpenStorage}
              className="h-10 min-h-[40px]"
              title="Storage-Management"
              aria-label="Storage-Management"
            >
              <Database className="h-4 w-4" />
              <span className="hidden sm:inline ml-2">Storage</span>
            </Button>
          </div>
        </div>
      </div>
    </header>
  )
}
