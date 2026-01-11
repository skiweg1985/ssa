import { useState, useEffect } from "react"
import { Search, Settings, Database, X, BookOpen, Moon, Sun } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { useDebounce } from "@/hooks/useDebounce"
import { useKeyboardShortcuts } from "@/hooks/useKeyboardShortcuts"
import { useTheme } from "@/hooks/useTheme"

interface TopbarProps {
  searchQuery: string
  onSearchChange: (query: string) => void
  onReloadConfig: () => void
  onOpenStorage: () => void
  onOpenCommandPalette: () => void
  onOpenApiInfo: () => void
  isLoading?: boolean
  lastUpdated?: Date | null
}

export function Topbar({
  searchQuery,
  onSearchChange,
  onReloadConfig,
  onOpenStorage,
  onOpenCommandPalette,
  onOpenApiInfo,
  isLoading = false,
  lastUpdated = null,
}: TopbarProps) {
  const [localSearch, setLocalSearch] = useState(searchQuery)
  const [isRefreshing, setIsRefreshing] = useState(false)
  const debouncedSearch = useDebounce(localSearch, 300)
  const { theme, toggleTheme } = useTheme()

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

  // Show refresh indicator when lastUpdated changes
  useEffect(() => {
    if (lastUpdated) {
      setIsRefreshing(true)
      const timer = setTimeout(() => {
        setIsRefreshing(false)
      }, 500) // Blink for 500ms
      return () => clearTimeout(timer)
    }
  }, [lastUpdated])

  return (
    <>
      {/* Refresh Indicator - Blinker oben */}
      {isRefreshing && (
        <div className="fixed top-0 left-0 right-0 h-1 bg-primary-500 z-[60] animate-pulse" />
      )}
      <header className="sticky top-0 z-50 w-full border-b border-slate-200/80 dark:border-slate-700/80 bg-white/80 dark:bg-slate-900/80 backdrop-blur-md supports-[backdrop-filter]:bg-white/60 dark:supports-[backdrop-filter]:bg-slate-900/60">
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
                <h1 className="text-sm sm:text-base font-semibold text-slate-900 dark:text-slate-50 leading-tight truncate">
                  Synology Space Analyzer
                </h1>
                <p className="text-[10px] sm:text-xs text-slate-500 dark:text-slate-400 leading-tight truncate">Scan-Status Dashboard</p>
              </div>
            </div>

            {/* Right: Actions (visible on small screens, hidden on lg+) */}
            <div className="flex items-center gap-1.5 sm:gap-2 lg:hidden flex-shrink-0">
              <Button
                variant="ghost"
                size="sm"
                onClick={toggleTheme}
                className="h-10 min-h-[40px] px-2 sm:px-3"
                title={theme === "light" ? "Dark Mode" : "Light Mode"}
                aria-label={theme === "light" ? "Dark Mode" : "Light Mode"}
              >
                {theme === "light" ? <Moon className="h-4 w-4" /> : <Sun className="h-4 w-4" />}
                <span className="hidden sm:inline ml-1.5">Theme</span>
              </Button>
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

          {/* Row 2: Search (on small screens) / Center: Search (on large screens) */}
          <div className="flex items-center gap-2 lg:flex-1 lg:max-w-md lg:mx-4 min-w-0">
            <div className="relative flex-1 min-w-0">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400 dark:text-slate-500 pointer-events-none" />
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
                    className="h-8 w-8 min-h-[32px] min-w-[32px] rounded-sm text-slate-400 dark:text-slate-500 hover:text-slate-600 dark:hover:text-slate-300 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-1 transition-colors flex items-center justify-center"
                    aria-label="Suche löschen"
                  >
                    <X className="h-4 w-4" />
                  </button>
                )}
                <kbd className="hidden sm:inline-flex h-5 select-none items-center gap-1 rounded border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 px-1.5 font-mono text-[10px] font-medium text-slate-500 dark:text-slate-400">
                  <span className="text-xs">⌘</span>K
                </kbd>
              </div>
            </div>
          </div>

          {/* Right: Actions (visible on lg+ screens only) */}
          <div className="hidden lg:flex items-center gap-2 flex-shrink-0">
            <Button
              variant="ghost"
              size="sm"
              onClick={toggleTheme}
              className="h-10 min-h-[40px]"
              title={theme === "light" ? "Dark Mode" : "Light Mode"}
              aria-label={theme === "light" ? "Dark Mode" : "Light Mode"}
            >
              {theme === "light" ? <Moon className="h-4 w-4" /> : <Sun className="h-4 w-4" />}
              <span className="hidden sm:inline ml-2">Theme</span>
            </Button>
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
    </>
  )
}
