import { useState, useEffect, useCallback, useMemo } from "react"
import {
  Dialog,
  DialogHeader,
  DialogTitle,
  DialogContent,
  DialogFooter,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Select } from "@/components/ui/select"
import { Switch } from "@/components/ui/switch"
import { useToast } from "@/components/ui/toast"
import { DirectoryPicker } from "@/components/jobs/DirectoryPicker"
import {
  fetchNasConnections,
  createScanJob,
  updateScanJob,
} from "@/lib/api"
import type { NASConnectionPublic, ScanStatus } from "@/types/api"
import { CalendarClock, FolderTree, Pencil, Plus, Server } from "lucide-react"
import { cn } from "@/lib/cn"

interface JobEditorModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** null = neuen Job anlegen, sonst bestehenden bearbeiten */
  job: ScanStatus | null
  onSaved: () => void
  onManageConnections: () => void
}

const INTERVAL_PRESETS = [
  { value: "15m", label: "15 Min" },
  { value: "30m", label: "30 Min" },
  { value: "1h", label: "1 Std" },
  { value: "6h", label: "6 Std" },
  { value: "12h", label: "12 Std" },
  { value: "24h", label: "24 Std" },
]

/** Client-seitige Prüfung: Kurzform (10s/10m/10h/10d) oder 5-Feld-Cron */
function isValidInterval(value: string): boolean {
  const trimmed = value.trim()
  if (/^\d+[smhd]$/i.test(trimmed)) return true
  if (trimmed.split(/\s+/).length === 5) return true
  return false
}

/**
 * Leitet die initiale Pfadliste eines bestehenden Jobs ab.
 * shares/folders werden als äquivalente absolute Pfade angezeigt
 * (identisch zu dem, was der Scanner via _determine_paths scannt).
 */
function derivePaths(job: ScanStatus): string[] {
  const paths: string[] = []
  if (job.paths) {
    for (const p of job.paths) {
      paths.push(p.startsWith("/") ? p : `/${p}`)
    }
  }
  if (job.shares) {
    if (job.folders && job.shares.length === 1) {
      for (const folder of job.folders) {
        paths.push(`/${job.shares[0]}/${folder}`)
      }
    } else {
      for (const share of job.shares) {
        paths.push(`/${share}`)
      }
    }
  }
  return [...new Set(paths)]
}

export function JobEditorModal({
  open,
  onOpenChange,
  job,
  onSaved,
  onManageConnections,
}: JobEditorModalProps) {
  const { showToast } = useToast()
  const isEdit = job !== null

  const [connections, setConnections] = useState<NASConnectionPublic[]>([])
  const [connectionsLoading, setConnectionsLoading] = useState(false)

  const [name, setName] = useState("")
  const [connectionId, setConnectionId] = useState<number | null>(null)
  const [enabled, setEnabled] = useState(true)
  const [interval, setIntervalValue] = useState("6h")
  const [customInterval, setCustomInterval] = useState(false)
  const [paths, setPaths] = useState<string[]>([])
  const [saving, setSaving] = useState(false)

  const loadConnections = useCallback(async () => {
    setConnectionsLoading(true)
    try {
      setConnections(await fetchNasConnections())
    } catch {
      // Fehler zeigt sich im leeren Select; Toast wäre hier zu laut
    } finally {
      setConnectionsLoading(false)
    }
  }, [])

  // Formular bei Öffnen (re-)initialisieren
  useEffect(() => {
    if (!open) return
    loadConnections()
    if (job) {
      setName(job.scan_name)
      setConnectionId(job.nas_connection_id ?? null)
      setEnabled(job.enabled)
      const jobInterval = job.interval ?? "6h"
      setIntervalValue(jobInterval)
      setCustomInterval(!INTERVAL_PRESETS.some((p) => p.value === jobInterval))
      setPaths(derivePaths(job))
    } else {
      setName("")
      setConnectionId(null)
      setEnabled(true)
      setIntervalValue("6h")
      setCustomInterval(false)
      setPaths([])
    }
  }, [open, job, loadConnections])

  const intervalValid = isValidInterval(interval)
  const formValid =
    name.trim().length > 0 &&
    connectionId != null &&
    paths.length > 0 &&
    intervalValid

  const connectionOptions = useMemo(
    () =>
      connections.map((c) => ({
        value: String(c.id),
        label: c.name,
        description: `${c.host} · ${c.username}`,
      })),
    [connections]
  )

  async function handleSave() {
    if (!formValid || connectionId == null) return
    setSaving(true)
    try {
      const payload = {
        name: name.trim(),
        nas_connection_id: connectionId,
        interval: interval.trim(),
        enabled,
        paths,
        shares: null,
        folders: null,
      }
      if (isEdit && job) {
        await updateScanJob(job.scan_slug, payload)
      } else {
        await createScanJob(payload)
      }
      onSaved()
      onOpenChange(false)
    } catch (err) {
      showToast(
        "Fehler",
        err instanceof Error ? err.message : "Speichern fehlgeschlagen",
        "error"
      )
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange} maxWidth="2xl">
      <DialogHeader>
        <DialogTitle className="flex items-center gap-2 min-w-0">
          {isEdit ? (
            <Pencil className="h-5 w-5 flex-shrink-0" />
          ) : (
            <Plus className="h-5 w-5 flex-shrink-0" />
          )}
          <span className="truncate">
            {isEdit ? `Scan bearbeiten: ${job?.scan_name}` : "Neuer Scan"}
          </span>
        </DialogTitle>
      </DialogHeader>

      <DialogContent>
        <div className="space-y-5">
          {/* Name + Aktiviert */}
          <div className="flex flex-col gap-4 sm:flex-row sm:items-end">
            <div className="flex-1">
              <label className="mb-2 block text-sm font-semibold text-slate-700 dark:text-slate-300">
                Name
              </label>
              <Input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="z.B. Backup-Ordner"
                autoFocus={!isEdit}
              />
            </div>
            <Switch
              checked={enabled}
              onCheckedChange={setEnabled}
              label="Aktiviert"
              className="pb-1.5"
            />
          </div>

          {/* NAS-Verbindung */}
          <div>
            <div className="mb-2 flex items-center justify-between">
              <label className="flex items-center gap-1.5 text-sm font-semibold text-slate-700 dark:text-slate-300">
                <Server className="h-4 w-4" /> NAS-Verbindung
              </label>
              <button
                type="button"
                onClick={onManageConnections}
                className="text-xs font-medium text-primary-600 dark:text-primary-500 hover:underline"
              >
                Verbindungen verwalten
              </button>
            </div>
            <Select
              value={connectionId != null ? String(connectionId) : null}
              onValueChange={(v) => {
                setConnectionId(Number(v))
                setPaths([])
              }}
              options={connectionOptions}
              placeholder={
                connectionsLoading
                  ? "Lade Verbindungen…"
                  : connections.length === 0
                    ? "Keine Verbindungen - zuerst anlegen"
                    : "Verbindung auswählen…"
              }
              disabled={connectionsLoading}
            />
          </div>

          {/* Intervall */}
          <div>
            <label className="mb-2 flex items-center gap-1.5 text-sm font-semibold text-slate-700 dark:text-slate-300">
              <CalendarClock className="h-4 w-4" /> Intervall
            </label>
            <div className="flex flex-wrap gap-1.5">
              {INTERVAL_PRESETS.map((preset) => (
                <button
                  key={preset.value}
                  type="button"
                  onClick={() => {
                    setIntervalValue(preset.value)
                    setCustomInterval(false)
                  }}
                  className={cn(
                    "rounded-full border px-3 py-1.5 text-sm font-medium transition-colors min-h-[36px]",
                    !customInterval && interval === preset.value
                      ? "border-primary-500 bg-primary-50 dark:bg-primary-500/15 text-primary-700 dark:text-primary-400"
                      : "border-slate-300 dark:border-slate-600 text-slate-600 dark:text-slate-400 hover:border-slate-400 dark:hover:border-slate-500"
                  )}
                >
                  {preset.label}
                </button>
              ))}
              <button
                type="button"
                onClick={() => setCustomInterval(true)}
                className={cn(
                  "rounded-full border px-3 py-1.5 text-sm font-medium transition-colors min-h-[36px]",
                  customInterval
                    ? "border-primary-500 bg-primary-50 dark:bg-primary-500/15 text-primary-700 dark:text-primary-400"
                    : "border-slate-300 dark:border-slate-600 text-slate-600 dark:text-slate-400 hover:border-slate-400 dark:hover:border-slate-500"
                )}
              >
                Benutzerdefiniert
              </button>
            </div>
            {customInterval && (
              <div className="mt-2">
                <Input
                  value={interval}
                  onChange={(e) => setIntervalValue(e.target.value)}
                  placeholder="z.B. 30m oder 0 3 * * *"
                  className={cn(
                    "font-mono",
                    interval.trim() && !intervalValid && "border-red-400 dark:border-red-600"
                  )}
                />
                <p
                  className={cn(
                    "mt-1 text-xs",
                    interval.trim() && !intervalValid
                      ? "text-red-600 dark:text-red-400"
                      : "text-slate-400 dark:text-slate-500"
                  )}
                >
                  Kurzform (z.B. „30m", „12h") oder Cron mit 5 Feldern (z.B. „0 3 * * *")
                </p>
              </div>
            )}
          </div>

          {/* Verzeichnisse */}
          <div>
            <label className="mb-2 flex items-center gap-1.5 text-sm font-semibold text-slate-700 dark:text-slate-300">
              <FolderTree className="h-4 w-4" /> Zu scannende Verzeichnisse
            </label>
            <DirectoryPicker
              nasConnectionId={connectionId}
              selectedPaths={paths}
              onChange={setPaths}
            />
            {paths.length === 0 && (
              <p className="mt-1 text-xs text-slate-400 dark:text-slate-500">
                Mindestens ein Verzeichnis auswählen
              </p>
            )}
          </div>
        </div>
      </DialogContent>

      <DialogFooter>
        <Button variant="secondary" onClick={() => onOpenChange(false)}>
          Abbrechen
        </Button>
        <Button
          variant="primary"
          onClick={handleSave}
          isLoading={saving}
          disabled={!formValid}
        >
          {isEdit ? "Speichern" : "Scan anlegen"}
        </Button>
      </DialogFooter>
    </Dialog>
  )
}
