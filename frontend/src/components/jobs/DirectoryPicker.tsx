import { useState, useEffect, useCallback } from "react"
import {
  ChevronRight,
  Folder,
  FolderOpen,
  Loader2,
  Plus,
  RefreshCw,
  X,
} from "lucide-react"
import { browseNas } from "@/lib/api"
import type { BrowseEntry } from "@/types/api"
import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/cn"

interface TreeNode {
  name: string
  path: string
  expanded: boolean
  loading: boolean
  error: string | null
  children: TreeNode[] | null // null = noch nicht geladen
}

interface DirectoryPickerProps {
  nasConnectionId: number | null
  selectedPaths: string[]
  onChange: (paths: string[]) => void
}

/**
 * Lazy-Verzeichnisbaum zum Auswählen der Scan-Pfade.
 *
 * Root = Shares des NAS; Knoten laden ihre Unterordner beim Aufklappen.
 * Gewählte Pfade erscheinen als entfernbare Chips; zusätzlich gibt es ein
 * manuelles Pfad-Eingabefeld als Fallback (z.B. NAS gerade offline).
 */
export function DirectoryPicker({
  nasConnectionId,
  selectedPaths,
  onChange,
}: DirectoryPickerProps) {
  const [roots, setRoots] = useState<TreeNode[] | null>(null)
  const [rootLoading, setRootLoading] = useState(false)
  const [rootError, setRootError] = useState<string | null>(null)
  const [manualPath, setManualPath] = useState("")

  const loadRoots = useCallback(async () => {
    if (nasConnectionId == null) return
    setRootLoading(true)
    setRootError(null)
    try {
      const response = await browseNas(nasConnectionId)
      setRoots(
        response.entries.map((entry: BrowseEntry) => ({
          name: entry.name,
          path: entry.path,
          expanded: false,
          loading: false,
          error: null,
          children: null,
        }))
      )
    } catch (err) {
      setRoots(null)
      setRootError(
        err instanceof Error ? err.message : "Verzeichnisse konnten nicht geladen werden"
      )
    } finally {
      setRootLoading(false)
    }
  }, [nasConnectionId])

  // Bei Verbindungswechsel neu laden
  useEffect(() => {
    setRoots(null)
    setRootError(null)
    if (nasConnectionId != null) {
      loadRoots()
    }
  }, [nasConnectionId, loadRoots])

  function updateNode(
    nodes: TreeNode[],
    path: string,
    updater: (node: TreeNode) => TreeNode
  ): TreeNode[] {
    return nodes.map((node) => {
      if (node.path === path) return updater(node)
      if (node.children && path.startsWith(node.path + "/")) {
        return { ...node, children: updateNode(node.children, path, updater) }
      }
      return node
    })
  }

  async function toggleExpand(node: TreeNode) {
    if (nasConnectionId == null) return
    if (node.expanded) {
      setRoots((prev) =>
        prev ? updateNode(prev, node.path, (n) => ({ ...n, expanded: false })) : prev
      )
      return
    }
    // Aufklappen; Kinder ggf. lazy laden
    setRoots((prev) =>
      prev
        ? updateNode(prev, node.path, (n) => ({
            ...n,
            expanded: true,
            loading: n.children === null,
            error: null,
          }))
        : prev
    )
    if (node.children !== null) return
    try {
      const response = await browseNas(nasConnectionId, node.path)
      setRoots((prev) =>
        prev
          ? updateNode(prev, node.path, (n) => ({
              ...n,
              loading: false,
              children: response.entries.map((entry: BrowseEntry) => ({
                name: entry.name,
                path: entry.path,
                expanded: false,
                loading: false,
                error: null,
                children: null,
              })),
            }))
          : prev
      )
    } catch (err) {
      setRoots((prev) =>
        prev
          ? updateNode(prev, node.path, (n) => ({
              ...n,
              loading: false,
              error:
                err instanceof Error ? err.message : "Fehler beim Laden",
            }))
          : prev
      )
    }
  }

  function togglePath(path: string) {
    if (selectedPaths.includes(path)) {
      onChange(selectedPaths.filter((p) => p !== path))
    } else {
      onChange([...selectedPaths, path])
    }
  }

  function addManualPath() {
    const path = manualPath.trim()
    if (!path) return
    const normalized = path.startsWith("/") ? path : `/${path}`
    if (!selectedPaths.includes(normalized)) {
      onChange([...selectedPaths, normalized])
    }
    setManualPath("")
  }

  function renderNode(node: TreeNode, depth: number) {
    const isSelected = selectedPaths.includes(node.path)
    // Ein übergeordneter Pfad ist gewählt => Kind implizit enthalten
    const isCovered = selectedPaths.some(
      (p) => p !== node.path && node.path.startsWith(p + "/")
    )
    return (
      <div key={node.path}>
        <div
          className={cn(
            "flex items-center gap-1.5 rounded-md px-1.5 py-1 hover:bg-slate-100 dark:hover:bg-slate-700/60 transition-colors",
            isSelected && "bg-primary-50 dark:bg-primary-500/10"
          )}
          style={{ paddingLeft: `${depth * 20 + 6}px` }}
        >
          <button
            type="button"
            onClick={() => toggleExpand(node)}
            className="flex h-6 w-6 flex-shrink-0 items-center justify-center rounded hover:bg-slate-200 dark:hover:bg-slate-600 text-slate-500 dark:text-slate-400"
            aria-label={node.expanded ? "Zuklappen" : "Aufklappen"}
          >
            {node.loading ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <ChevronRight
                className={cn(
                  "h-3.5 w-3.5 transition-transform",
                  node.expanded && "rotate-90"
                )}
              />
            )}
          </button>
          <Checkbox
            checked={isSelected}
            indeterminate={!isSelected && isCovered}
            onCheckedChange={() => togglePath(node.path)}
            aria-label={`${node.path} auswählen`}
          />
          <button
            type="button"
            onClick={() => toggleExpand(node)}
            className="flex min-w-0 flex-1 items-center gap-1.5 text-left"
          >
            {node.expanded ? (
              <FolderOpen className="h-4 w-4 flex-shrink-0 text-amber-500" />
            ) : (
              <Folder className="h-4 w-4 flex-shrink-0 text-amber-500" />
            )}
            <span className="truncate text-sm text-slate-700 dark:text-slate-300">
              {node.name}
            </span>
          </button>
        </div>
        {node.expanded && node.error && (
          <div
            className="flex items-center gap-2 py-1 text-xs text-red-600 dark:text-red-400"
            style={{ paddingLeft: `${(depth + 1) * 20 + 6}px` }}
          >
            <span className="truncate">{node.error}</span>
            <button
              type="button"
              onClick={() => toggleExpand({ ...node, expanded: false })}
              className="inline-flex items-center gap-1 font-medium underline"
            >
              <RefreshCw className="h-3 w-3" /> Erneut versuchen
            </button>
          </div>
        )}
        {node.expanded && node.children && node.children.length === 0 && !node.error && (
          <div
            className="py-1 text-xs text-slate-400 dark:text-slate-500"
            style={{ paddingLeft: `${(depth + 1) * 20 + 6}px` }}
          >
            Keine Unterordner
          </div>
        )}
        {node.expanded &&
          node.children &&
          node.children.map((child) => renderNode(child, depth + 1))}
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {/* Gewählte Pfade als Chips */}
      {selectedPaths.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {selectedPaths.map((path) => (
            <Badge
              key={path}
              variant="default"
              className="max-w-full gap-1 pr-1 font-mono text-xs"
            >
              <span className="truncate">{path}</span>
              <button
                type="button"
                onClick={() => togglePath(path)}
                className="rounded-full p-0.5 hover:bg-slate-300 dark:hover:bg-slate-600"
                aria-label={`${path} entfernen`}
              >
                <X className="h-3 w-3" />
              </button>
            </Badge>
          ))}
        </div>
      )}

      {/* Baum */}
      <div className="rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50/50 dark:bg-slate-800/50">
        {nasConnectionId == null ? (
          <p className="px-4 py-6 text-center text-sm text-slate-400 dark:text-slate-500">
            Bitte zuerst eine NAS-Verbindung auswählen
          </p>
        ) : rootLoading ? (
          <div className="space-y-2 p-3">
            {[...Array(4)].map((_, i) => (
              <div
                key={i}
                className="h-7 animate-pulse rounded bg-slate-200 dark:bg-slate-700"
              />
            ))}
          </div>
        ) : rootError ? (
          <div className="px-4 py-6 text-center">
            <p className="mb-2 text-sm text-red-600 dark:text-red-400 break-words">
              {rootError}
            </p>
            <Button variant="secondary" size="sm" onClick={loadRoots}>
              <RefreshCw className="mr-1.5 h-3.5 w-3.5" /> Erneut versuchen
            </Button>
          </div>
        ) : roots && roots.length > 0 ? (
          <div
            className="max-h-64 overflow-y-auto p-1.5"
            style={{ WebkitOverflowScrolling: "touch" }}
          >
            {roots.map((node) => renderNode(node, 0))}
          </div>
        ) : (
          <p className="px-4 py-6 text-center text-sm text-slate-400 dark:text-slate-500">
            Keine Freigaben gefunden
          </p>
        )}
      </div>

      {/* Manuelle Pfad-Eingabe (Fallback) */}
      <div className="flex gap-2">
        <Input
          value={manualPath}
          onChange={(e) => setManualPath(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault()
              addManualPath()
            }
          }}
          placeholder="/freigabe/ordner manuell hinzufügen"
          className="font-mono text-xs"
        />
        <Button
          type="button"
          variant="secondary"
          size="sm"
          onClick={addManualPath}
          disabled={!manualPath.trim()}
          aria-label="Pfad hinzufügen"
        >
          <Plus className="h-4 w-4" />
        </Button>
      </div>
    </div>
  )
}
