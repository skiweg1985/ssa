import { useState, useEffect } from "react"
import {
  Search,
  Settings,
  Database,
  X,
  BookOpen,
  Moon,
  Sun,
  Plus,
  Server,
  LogOut,
  type LucideIcon,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { useDebounce } from "@/hooks/useDebounce"
import { useKeyboardShortcuts } from "@/hooks/useKeyboardShortcuts"
import { useTheme } from "@/hooks/useTheme"
import { formatTimeAgo } from "@/lib/utils"

/* Kopfzeile: bündige Leiste, EINE Hairline nach unten, Blur beim Scrollen,
 * gerahmte ⌘K-Affordanz, EIN gefüllter Akzentbutton rechts.
 *
 * Zwei Dinge, die hier verschwunden sind:
 * · Der Aktionsblock stand zweimal im Markup (lg:hidden / hidden lg:flex) und war
 *   bereits auseinandergelaufen — „Neu" gegen „Neuer Scan", ml-1.5 gegen ml-2.
 *   Er ist jetzt ein Array, das einmal gerendert wird.
 * · Der pulsierende Balken, der bei jedem 5-Sekunden-Poll 500 ms lang aufblitzte.
 *   Wann zuletzt geladen wurde, steht als Zeitstempel da — das ist dieselbe
 *   Information, ohne dass die Seite dabei zuckt.
 */

interface TopbarProps {
  searchQuery: string
  onSearchChange: (query: string) => void
  onReloadConfig: () => void
  onOpenStorage: () => void
  onOpenCommandPalette: () => void
  onOpenApiInfo: () => void
  onNewScan: () => void
  onOpenNasConnections: () => void
  onLogout: () => void
  isLoading?: boolean
  lastUpdated?: Date | null
}

interface Action {
  id: string
  icon: LucideIcon
  /** Vollständige Beschriftung — trägt title und aria-label. */
  label: string
  /** Kurzform neben dem Icon, sobald Platz ist. Ohne sie bleibt der Knopf ein Icon. */
  short?: string
  onClick: () => void
  disabled?: boolean
}

export function Topbar({
  searchQuery,
  onSearchChange,
  onReloadConfig,
  onOpenStorage,
  onOpenCommandPalette,
  onOpenApiInfo,
  onNewScan,
  onOpenNasConnections,
  onLogout,
  isLoading = false,
  lastUpdated = null,
}: TopbarProps) {
  const [localSearch, setLocalSearch] = useState(searchQuery)
  const debouncedSearch = useDebounce(localSearch, 300)
  const { theme, toggleTheme } = useTheme()

  useKeyboardShortcuts([{ key: "k", metaKey: true, handler: onOpenCommandPalette }])

  useEffect(() => {
    if (debouncedSearch !== searchQuery) {
      onSearchChange(debouncedSearch)
    }
  }, [debouncedSearch, searchQuery, onSearchChange])

  const actions: Action[] = [
    {
      id: "theme",
      icon: theme === "light" ? Moon : Sun,
      label: theme === "light" ? "Dark Mode einschalten" : "Light Mode einschalten",
      onClick: toggleTheme,
    },
    { id: "api", icon: BookOpen, label: "API-Dokumentation", short: "API", onClick: onOpenApiInfo },
    {
      id: "config",
      icon: Settings,
      label: "Scheduler synchronisieren",
      short: "Sync",
      onClick: onReloadConfig,
      disabled: isLoading,
    },
    { id: "storage", icon: Database, label: "Storage-Management", short: "Storage", onClick: onOpenStorage },
    { id: "nas", icon: Server, label: "NAS-Verbindungen", onClick: onOpenNasConnections },
    { id: "logout", icon: LogOut, label: "Abmelden", onClick: onLogout },
  ]

  return (
    <header
      className="sticky top-0 z-header w-full border-b border-slate-200 dark:border-slate-700 bg-white/85 dark:bg-slate-900/85 backdrop-blur-md"
      style={{ paddingTop: "max(0.75rem, env(safe-area-inset-top))" }}
    >
      <div className="mx-auto max-w-screen-xl px-4 sm:px-6 lg:px-8">
        {/* Drei Blöcke, EINE Instanz von jedem. Die Umsortierung macht `order`,
            nicht ein zweiter Render: unter lg steht die Aktionsleiste auf einer
            eigenen Zeile unter der Marke, ab lg rechts neben der Suche.
            Zwei gerenderte Kopien hätten jedes Bedienelement doppelt im DOM. */}
        <div className="flex flex-wrap items-center gap-2 lg:h-16 lg:flex-nowrap lg:gap-4 py-3 lg:py-0">
          <div className="order-1 flex items-center gap-3 min-w-0 flex-1 lg:flex-none">
              <div className="flex h-9 w-9 items-center justify-center rounded-md border border-primary-200 dark:border-primary-700 bg-primary-50 dark:bg-primary-900/30 text-primary-600 dark:text-primary-400 flex-shrink-0">
                <Search className="h-4 w-4" aria-hidden="true" />
              </div>
              <div className="min-w-0">
                <h1 className="font-display text-sm sm:text-base font-semibold tracking-display text-slate-900 dark:text-slate-50 leading-tight truncate">
                  Synology Space Analyzer
                </h1>
                {/* Ersetzt den früheren Blinker: dieselbe Information, ohne Bewegung. */}
                <p className="label-mono text-slate-500 dark:text-slate-400 leading-tight truncate">
                  {lastUpdated ? `Stand ${formatTimeAgo(lastUpdated)}` : "Scan-Status"}
                </p>
              </div>
          </div>

          {/* Aktionen: order-2 unter lg (eigene Zeile), order-3 ab lg (ganz rechts) */}
          <div className="order-2 flex w-full items-center justify-end gap-1 sm:w-auto lg:order-3 lg:ml-auto">
            <ActionRow actions={actions} onNewScan={onNewScan} />
          </div>

          {/* Suche — gerahmt, mit sichtbarem ⌘K-Hinweis */}
          <div className="order-3 flex w-full items-center gap-2 min-w-0 lg:order-2 lg:w-auto lg:flex-1 lg:max-w-md lg:mx-4">
            <div className="relative flex-1 min-w-0">
              <Search
                className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400 dark:text-slate-500 pointer-events-none"
                aria-hidden="true"
              />
              <Input
                type="text"
                placeholder="Suchen …"
                value={localSearch}
                onChange={(e) => setLocalSearch(e.target.value)}
                className="pl-9 pr-20 sm:pr-24 h-9"
                onKeyDown={(e) => {
                  if ((e.metaKey || e.ctrlKey) && e.key === "k") {
                    e.preventDefault()
                    onOpenCommandPalette()
                  }
                }}
                aria-label="Suche"
              />
              <div className="absolute right-2.5 top-1/2 -translate-y-1/2 flex items-center gap-1.5">
                {localSearch && (
                  <button
                    type="button"
                    onClick={() => {
                      setLocalSearch("")
                      onSearchChange("")
                    }}
                    className="h-7 w-7 rounded-sm text-slate-400 dark:text-slate-500 hover:text-slate-900 dark:hover:text-slate-50 hover:bg-slate-100 dark:hover:bg-slate-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-1 transition-[color,background-color] duration-instant ease-out flex items-center justify-center"
                    aria-label="Suche löschen"
                  >
                    <X className="h-4 w-4" aria-hidden="true" />
                  </button>
                )}
                <kbd className="hidden sm:inline-flex h-5 select-none items-center gap-1 rounded-sm border border-slate-200 dark:border-slate-600 bg-slate-100 dark:bg-slate-700 px-1.5 font-mono text-[10px] font-medium text-slate-500 dark:text-slate-400">
                  ⌘K
                </kbd>
              </div>
            </div>
          </div>

        </div>
      </div>
    </header>
  )
}

/* Eine Definition, ein Einbauort. Ursprünglich standen hier zwei Blöcke im
   Markup, die schon auseinandergelaufen waren; die Position regelt jetzt CSS. */
function ActionRow({
  actions,
  onNewScan,
}: {
  actions: Action[]
  onNewScan: () => void
}) {
  return (
    <>
      {actions.map(({ id, icon: Icon, label, short, onClick, disabled }) => (
        <Button
          key={id}
          variant="ghost"
          size="sm"
          onClick={onClick}
          disabled={disabled}
          className={short ? "h-9 w-9 p-0 xl:w-auto xl:px-2.5" : "h-9 w-9 p-0"}
          title={label}
          aria-label={label}
        >
          <Icon className="h-4 w-4 flex-shrink-0" aria-hidden="true" />
          {short && <span className="hidden xl:inline">{short}</span>}
        </Button>
      ))}
      <Button
        variant="primary"
        size="sm"
        onClick={onNewScan}
        className="h-9 ml-1"
        title="Neuen Scan anlegen"
        aria-label="Neuen Scan anlegen"
      >
        <Plus className="h-4 w-4 flex-shrink-0" aria-hidden="true" />
        <span className="hidden sm:inline">Neuer Scan</span>
      </Button>
    </>
  )
}
