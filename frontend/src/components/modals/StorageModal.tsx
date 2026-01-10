import { useState, useEffect } from "react"
import {
  Dialog,
  DialogHeader,
  DialogTitle,
  DialogContent,
  DialogFooter,
  DialogClose,
} from "@/components/ui/dialog"
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  fetchStorageStats,
  fetchFolders,
  previewCleanup,
  executeCleanup,
  deleteFolderResults,
} from "@/lib/api"
import type { StorageStats, FoldersResponse, CleanupPreview } from "@/types/api"
import { Loader2, Trash2, Database, BarChart3, FolderOpen, CheckCircle2, XCircle } from "lucide-react"
import { useToast } from "@/components/ui/toast"

interface StorageModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function StorageModal({ open, onOpenChange }: StorageModalProps) {
  const [activeTab, setActiveTab] = useState<"stats" | "folders" | "cleanup">("stats")
  const [stats, setStats] = useState<StorageStats | null>(null)
  const [folders, setFolders] = useState<FoldersResponse | null>(null)
  const [cleanupPreview, setCleanupPreview] = useState<CleanupPreview | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [cleanupDays, setCleanupDays] = useState(90)
  const { showToast } = useToast()

  useEffect(() => {
    if (open) {
      loadData()
    }
  }, [open, activeTab])

  async function loadData() {
    setLoading(true)
    setError(null)
    try {
      if (activeTab === "stats") {
        const data = await fetchStorageStats()
        setStats(data)
      } else if (activeTab === "folders") {
        const data = await fetchFolders()
        setFolders(data)
      } else if (activeTab === "cleanup") {
        const preview = await previewCleanup({ days: cleanupDays })
        setCleanupPreview(preview)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Fehler beim Laden")
    } finally {
      setLoading(false)
    }
  }

  async function handleCleanup() {
    try {
      setLoading(true)
      await executeCleanup({ days: cleanupDays })
      showToast("Erfolg", "Bereinigung erfolgreich durchgeführt", "success")
      loadData()
    } catch (err) {
      showToast("Fehler", `Fehler bei Bereinigung: ${err instanceof Error ? err.message : "Unbekannt"}`, "error")
    } finally {
      setLoading(false)
    }
  }

  async function handleDeleteFolder(nasHost: string, folderPath: string) {
    if (!confirm(`Möchten Sie wirklich alle Ergebnisse für ${folderPath} löschen?`)) return

    try {
      setLoading(true)
      await deleteFolderResults({ nas_host: nasHost, folder_path: folderPath })
      showToast("Erfolg", "Ordner-Ergebnisse gelöscht", "success")
      loadData()
    } catch (err) {
      showToast("Fehler", `Fehler beim Löschen: ${err instanceof Error ? err.message : "Unbekannt"}`, "error")
    } finally {
      setLoading(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogHeader className="bg-gradient-to-r from-purple-500 to-purple-600 text-white px-6 py-4">
        <div className="flex items-center justify-between">
          <DialogTitle className="text-white flex items-center gap-2">
            <Database className="h-5 w-5" />
            Storage-Management
          </DialogTitle>
          <DialogClose className="text-white hover:bg-white/20" />
        </div>
      </DialogHeader>

      <DialogContent>
        <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as typeof activeTab)}>
          <TabsList>
            <TabsTrigger value="stats" className="flex items-center gap-2">
              <BarChart3 className="h-4 w-4" />
              Statistiken
            </TabsTrigger>
            <TabsTrigger value="folders" className="flex items-center gap-2">
              <FolderOpen className="h-4 w-4" />
              Ordner
            </TabsTrigger>
            <TabsTrigger value="cleanup" className="flex items-center gap-2">
              <Trash2 className="h-4 w-4" />
              Bereinigung
            </TabsTrigger>
          </TabsList>

          <TabsContent value="stats" className="mt-6">
            {loading ? (
              <div className="flex items-center justify-center py-12">
                <Loader2 className="h-6 w-6 animate-spin text-slate-400" />
                <span className="ml-2 text-slate-500">Lade Statistiken...</span>
              </div>
            ) : error ? (
              <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-red-800">
                <div className="font-semibold mb-1">Fehler beim Laden</div>
                <div className="text-sm">{error}</div>
                <Button variant="primary" size="sm" onClick={loadData} className="mt-3">
                  Erneut versuchen
                </Button>
              </div>
            ) : stats ? (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="bg-slate-50 rounded-lg p-4">
                  <div className="text-sm text-slate-600 mb-1">Scans</div>
                  <div className="text-2xl font-bold text-slate-900">{stats.scan_count}</div>
                </div>
                <div className="bg-slate-50 rounded-lg p-4">
                  <div className="text-sm text-slate-600 mb-1">NAS-Systeme</div>
                  <div className="text-2xl font-bold text-slate-900">{stats.nas_count}</div>
                </div>
                <div className="bg-slate-50 rounded-lg p-4">
                  <div className="text-sm text-slate-600 mb-1">Ordner</div>
                  <div className="text-2xl font-bold text-slate-900">{stats.folder_count}</div>
                </div>
                <div className="bg-slate-50 rounded-lg p-4">
                  <div className="text-sm text-slate-600 mb-1">Gesamt Ergebnisse</div>
                  <div className="text-2xl font-bold text-slate-900">
                    {stats.total_results_db.toLocaleString()}
                  </div>
                </div>
                <div className="bg-slate-50 rounded-lg p-4">
                  <div className="text-sm text-slate-600 mb-1">Datenbank-Größe</div>
                  <div className="text-2xl font-bold text-slate-900">{stats.db_size_mb.toFixed(2)} MB</div>
                </div>
                <div className="bg-slate-50 rounded-lg p-4">
                  <div className="text-sm text-slate-600 mb-1">Auto-Bereinigung</div>
                  <div className="text-sm font-semibold text-slate-900">
                    {stats.auto_cleanup_enabled ? (
                      <span className="flex items-center gap-1.5">
                        <CheckCircle2 className="h-4 w-4 text-green-600" />
                        Aktiv ({stats.auto_cleanup_days} Tage)
                      </span>
                    ) : (
                      <span className="flex items-center gap-1.5">
                        <XCircle className="h-4 w-4 text-red-600" />
                        Deaktiviert
                      </span>
                    )}
                  </div>
                </div>
              </div>
            ) : null}
          </TabsContent>

          <TabsContent value="folders" className="mt-6">
            {loading ? (
              <div className="flex items-center justify-center py-12">
                <Loader2 className="h-6 w-6 animate-spin text-slate-400" />
                <span className="ml-2 text-slate-500">Lade Ordner...</span>
              </div>
            ) : error ? (
              <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-red-800">
                <div className="font-semibold mb-1">Fehler beim Laden</div>
                <div className="text-sm">{error}</div>
                <Button variant="primary" size="sm" onClick={loadData} className="mt-3">
                  Erneut versuchen
                </Button>
              </div>
            ) : folders ? (
              <div className="space-y-4">
                <div className="text-sm text-slate-600">{folders.count} Ordner gefunden</div>
                <div className="space-y-2 max-h-96 overflow-y-auto">
                  {folders.folders.map((folder, idx) => (
                    <div key={idx} className="bg-slate-50 rounded-lg p-4 flex items-center justify-between">
                      <div>
                        <div className="font-semibold text-slate-900">{folder.folder_path}</div>
                        <div className="text-sm text-slate-600">{folder.nas_host}</div>
                      </div>
                      <Button
                        variant="destructive"
                        size="sm"
                        onClick={() => handleDeleteFolder(folder.nas_host, folder.folder_path)}
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
          </TabsContent>

          <TabsContent value="cleanup" className="mt-6">
            <div className="space-y-4">
              <div>
                <label className="text-sm font-semibold text-slate-900 mb-2 block">
                  Tage (älter als):
                </label>
                <Input
                  type="number"
                  value={cleanupDays}
                  onChange={(e) => setCleanupDays(parseInt(e.target.value) || 90)}
                  min={1}
                  className="max-w-xs"
                />
              </div>
              <Button variant="secondary" size="sm" onClick={loadData}>
                Vorschau aktualisieren
              </Button>
              {cleanupPreview && (
                <div className="bg-slate-50 rounded-lg p-4 space-y-2">
                  <div className="text-sm text-slate-600">Gesamt Ergebnisse: {cleanupPreview.total_results}</div>
                  <div className="text-sm text-slate-600">
                    Zu löschen: {cleanupPreview.results_to_delete}
                  </div>
                  <div className="text-sm text-slate-600">
                    Zu behalten: {cleanupPreview.results_to_keep}
                  </div>
                </div>
              )}
              <Button variant="destructive" onClick={handleCleanup} isLoading={loading}>
                Bereinigung ausführen
              </Button>
            </div>
          </TabsContent>
        </Tabs>
      </DialogContent>

      <DialogFooter>
        <Button variant="secondary" onClick={() => onOpenChange(false)}>
          Schließen
        </Button>
      </DialogFooter>
    </Dialog>
  )
}
