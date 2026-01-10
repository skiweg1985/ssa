import { useState, useEffect, useRef } from "react"
import { Search } from "lucide-react"
import { Input } from "@/components/ui/input"
import { useDebounce } from "@/hooks/useDebounce"
import type { ScanStatus } from "@/types/api"

interface CommandPaletteProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  scans: ScanStatus[]
  onSelectScan: (scanName: string, action: "results" | "history") => void
}

export function CommandPalette({
  open,
  onOpenChange,
  scans,
  onSelectScan,
}: CommandPaletteProps) {
  const [query, setQuery] = useState("")
  const [selectedIndex, setSelectedIndex] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)
  const debouncedQuery = useDebounce(query, 200)

  useEffect(() => {
    if (open) {
      setQuery("")
      setSelectedIndex(0)
      setTimeout(() => inputRef.current?.focus(), 100)
    }
  }, [open])

  useEffect(() => {
    if (!open) return

    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        onOpenChange(false)
      } else if (e.key === "ArrowDown") {
        e.preventDefault()
        setSelectedIndex((prev) => Math.min(prev + 1, filteredScans.length - 1))
      } else if (e.key === "ArrowUp") {
        e.preventDefault()
        setSelectedIndex((prev) => Math.max(prev - 1, 0))
      } else if (e.key === "Enter") {
        e.preventDefault()
        if (filteredScans[selectedIndex]) {
          const action = e.shiftKey ? "history" : "results"
          onSelectScan(filteredScans[selectedIndex].scan_name, action)
          onOpenChange(false)
        }
      }
    }

    window.addEventListener("keydown", handleKeyDown)
    return () => window.removeEventListener("keydown", handleKeyDown)
  }, [open, selectedIndex, onOpenChange, onSelectScan])

  const filteredScans = scans.filter((scan) => {
    if (!debouncedQuery) return true
    const q = debouncedQuery.toLowerCase()
    return (
      scan.scan_name.toLowerCase().includes(q) ||
      scan.nas?.host.toLowerCase().includes(q) ||
      scan.shares?.some((s) => s.toLowerCase().includes(q)) ||
      scan.folders?.some((f) => f.toLowerCase().includes(q)) ||
      scan.status.toLowerCase().includes(q)
    )
  })

  if (!open) return null

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 animate-in fade-in"
      onClick={() => onOpenChange(false)}
    >
      <div
        className="relative z-50 w-full max-w-2xl bg-white rounded-xl shadow-2xl max-h-[80vh] flex flex-col overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="p-4 border-b border-slate-200">
          <div className="flex items-center gap-3 mb-3">
            <h2 className="text-lg font-semibold text-slate-900">🔍 Scan suchen</h2>
          </div>
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
            <Input
              ref={inputRef}
              type="text"
              value={query}
              onChange={(e) => {
                setQuery(e.target.value)
                setSelectedIndex(0)
              }}
              placeholder="Scan-Name, Host, Share oder Status eingeben..."
              className="pl-10"
            />
          </div>
        </div>

        {/* Results */}
        <div className="flex-1 overflow-y-auto p-4">
          {filteredScans.length === 0 ? (
            <div className="text-center text-slate-500 text-sm py-8">
              {debouncedQuery ? "Keine Ergebnisse gefunden" : "Tippen Sie, um zu suchen..."}
            </div>
          ) : (
            <div className="space-y-1">
              {filteredScans.map((scan, index) => (
                <button
                  key={scan.scan_name}
                  onClick={() => {
                    onSelectScan(scan.scan_name, "results")
                    onOpenChange(false)
                  }}
                  className={`w-full text-left px-4 py-3 rounded-lg transition-colors ${
                    index === selectedIndex
                      ? "bg-primary-50 border border-primary-200"
                      : "hover:bg-slate-50"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <div>
                      <div className="font-semibold text-slate-900">{scan.scan_name}</div>
                      <div className="text-sm text-slate-500">
                        {scan.nas?.host} • {scan.status}
                      </div>
                    </div>
                    <div className="text-xs text-slate-400">Enter</div>
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-slate-200 bg-slate-50 text-xs text-slate-600">
          <div className="flex items-center justify-between flex-wrap gap-2">
            <div className="flex items-center gap-2">
              <kbd className="px-2 py-1 bg-white border border-slate-300 rounded text-xs">↑</kbd>
              <kbd className="px-2 py-1 bg-white border border-slate-300 rounded text-xs">↓</kbd>
              <span>Navigieren</span>
            </div>
            <div className="flex items-center gap-2">
              <kbd className="px-2 py-1 bg-white border border-slate-300 rounded text-xs">Enter</kbd>
              <span>Ergebnisse öffnen</span>
            </div>
            <div className="flex items-center gap-2">
              <kbd className="px-2 py-1 bg-white border border-slate-300 rounded text-xs">Shift</kbd>
              <kbd className="px-2 py-1 bg-white border border-slate-300 rounded text-xs">Enter</kbd>
              <span>oder</span>
              <kbd className="px-2 py-1 bg-white border border-slate-300 rounded text-xs">H</kbd>
              <span>Historie</span>
            </div>
            <div className="flex items-center gap-2">
              <kbd className="px-2 py-1 bg-white border border-slate-300 rounded text-xs">Esc</kbd>
              <span>Schließen</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
