import { useState, useEffect, useCallback } from "react"
import {
  Dialog,
  DialogHeader,
  DialogTitle,
  DialogContent,
  DialogFooter,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import { Switch } from "@/components/ui/switch"
import { useToast } from "@/components/ui/toast"
import {
  fetchNasConnections,
  createNasConnection,
  updateNasConnection,
  deleteNasConnection,
  testNasConnection,
} from "@/lib/api"
import type { NASConnectionPublic } from "@/types/api"
import {
  Server,
  Plus,
  Pencil,
  Trash2,
  Loader2,
  CheckCircle2,
  XCircle,
  ArrowLeft,
  PlugZap,
} from "lucide-react"
import { cn } from "@/lib/cn"

interface NasConnectionsModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** Wird nach jeder Änderung aufgerufen (z.B. um Selects zu aktualisieren) */
  onChanged?: () => void
}

interface FormState {
  name: string
  host: string
  port: string
  username: string
  password: string
  use_https: boolean
  verify_ssl: boolean
}

const EMPTY_FORM: FormState = {
  name: "",
  host: "",
  port: "",
  username: "",
  password: "",
  use_https: true,
  verify_ssl: true,
}

export function NasConnectionsModal({
  open,
  onOpenChange,
  onChanged,
}: NasConnectionsModalProps) {
  const { showToast } = useToast()
  const [connections, setConnections] = useState<NASConnectionPublic[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // null = Liste; "new" = Neuanlage; Objekt = Bearbeitung
  const [editing, setEditing] = useState<NASConnectionPublic | "new" | null>(null)
  const [form, setForm] = useState<FormState>(EMPTY_FORM)
  const [saving, setSaving] = useState(false)
  const [testState, setTestState] = useState<
    { kind: "idle" } | { kind: "loading" } | { kind: "ok"; msg: string } | { kind: "error"; msg: string }
  >({ kind: "idle" })

  const loadConnections = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setConnections(await fetchNasConnections())
    } catch (err) {
      setError(err instanceof Error ? err.message : "Fehler beim Laden")
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (open) {
      setEditing(null)
      loadConnections()
    }
  }, [open, loadConnections])

  function startCreate() {
    setForm(EMPTY_FORM)
    setTestState({ kind: "idle" })
    setEditing("new")
  }

  function startEdit(connection: NASConnectionPublic) {
    setForm({
      name: connection.name,
      host: connection.host,
      port: connection.port != null ? String(connection.port) : "",
      username: connection.username,
      password: "",
      use_https: connection.use_https,
      verify_ssl: connection.verify_ssl,
    })
    setTestState({ kind: "idle" })
    setEditing(connection)
  }

  function buildPayload() {
    return {
      name: form.name.trim(),
      host: form.host.trim(),
      username: form.username.trim(),
      password: form.password || undefined,
      port: form.port.trim() ? Number(form.port.trim()) : null,
      use_https: form.use_https,
      verify_ssl: form.verify_ssl,
    }
  }

  const formValid =
    form.name.trim() &&
    form.host.trim() &&
    form.username.trim() &&
    (editing === "new" ? form.password.length > 0 : true) &&
    (!form.port.trim() || !Number.isNaN(Number(form.port.trim())))

  async function handleTest() {
    setTestState({ kind: "loading" })
    try {
      const result = await testNasConnection({
        ...buildPayload(),
        password: form.password || undefined,
        id: editing !== "new" && editing ? editing.id : undefined,
      })
      setTestState(
        result.success
          ? { kind: "ok", msg: result.message }
          : { kind: "error", msg: result.message }
      )
    } catch (err) {
      setTestState({
        kind: "error",
        msg: err instanceof Error ? err.message : "Test fehlgeschlagen",
      })
    }
  }

  async function handleSave() {
    if (!formValid) return
    setSaving(true)
    try {
      if (editing === "new") {
        await createNasConnection({ ...buildPayload(), password: form.password })
        showToast("Erfolg", `Verbindung '${form.name}' angelegt`, "success")
      } else if (editing) {
        await updateNasConnection(editing.id, buildPayload())
        showToast("Erfolg", `Verbindung '${form.name}' aktualisiert`, "success")
      }
      onChanged?.()
      setEditing(null)
      loadConnections()
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

  async function handleDelete(connection: NASConnectionPublic) {
    if (
      !confirm(
        `NAS-Verbindung '${connection.name}' wirklich löschen?`
      )
    ) {
      return
    }
    try {
      await deleteNasConnection(connection.id)
      showToast("Erfolg", `Verbindung '${connection.name}' gelöscht`, "success")
      onChanged?.()
      loadConnections()
    } catch (err) {
      showToast(
        "Fehler",
        err instanceof Error ? err.message : "Löschen fehlgeschlagen",
        "error"
      )
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange} maxWidth="2xl">
      <DialogHeader className="bg-gradient-to-r from-cyan-500 to-blue-600 text-white px-6 py-4">
        <DialogTitle className="text-white flex items-center gap-2 min-w-0">
          {editing !== null && (
            <button
              onClick={() => setEditing(null)}
              className="rounded p-1 hover:bg-white/15 flex-shrink-0"
              aria-label="Zurück zur Liste"
            >
              <ArrowLeft className="h-4 w-4" />
            </button>
          )}
          <Server className="h-5 w-5 flex-shrink-0" />
          <span className="truncate">
            {editing === null
              ? "NAS-Verbindungen"
              : editing === "new"
                ? "Neue NAS-Verbindung"
                : `Verbindung bearbeiten: ${editing.name}`}
          </span>
        </DialogTitle>
      </DialogHeader>

      <DialogContent>
        {editing === null ? (
          // ------- Liste -------
          loading ? (
            <div className="flex justify-center py-10">
              <Loader2 className="h-6 w-6 animate-spin text-slate-400" />
            </div>
          ) : error ? (
            <div className="py-8 text-center">
              <p className="mb-3 text-sm text-red-600 dark:text-red-400">{error}</p>
              <Button variant="secondary" size="sm" onClick={loadConnections}>
                Erneut versuchen
              </Button>
            </div>
          ) : (
            <div className="space-y-3">
              {connections.length === 0 && (
                <p className="py-8 text-center text-sm text-slate-400 dark:text-slate-500">
                  Noch keine NAS-Verbindungen. Lege die erste an, um Scans zu
                  konfigurieren.
                </p>
              )}
              {connections.map((connection) => (
                <div
                  key={connection.id}
                  className="flex items-center gap-3 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-4 py-3"
                >
                  <Server className="h-5 w-5 flex-shrink-0 text-cyan-500" />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-semibold text-slate-900 dark:text-slate-100">
                      {connection.name}
                    </p>
                    <p className="truncate text-xs text-slate-500 dark:text-slate-400">
                      {connection.use_https ? "https" : "http"}://{connection.host}
                      {connection.port ? `:${connection.port}` : ""} · {connection.username}
                    </p>
                  </div>
                  <Badge variant="default" className="flex-shrink-0">
                    {connection.job_count}{" "}
                    {connection.job_count === 1 ? "Scan" : "Scans"}
                  </Badge>
                  <div className="flex flex-shrink-0 gap-1">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => startEdit(connection)}
                      aria-label={`${connection.name} bearbeiten`}
                    >
                      <Pencil className="h-4 w-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      disabled={connection.job_count > 0}
                      title={
                        connection.job_count > 0
                          ? `Wird von ${connection.job_count} Scan(s) verwendet`
                          : undefined
                      }
                      onClick={() => handleDelete(connection)}
                      aria-label={`${connection.name} löschen`}
                      className={cn(
                        connection.job_count === 0 &&
                          "text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/30"
                      )}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              ))}
              <Button variant="primary" onClick={startCreate} className="w-full">
                <Plus className="mr-1.5 h-4 w-4" /> Neue Verbindung
              </Button>
            </div>
          )
        ) : (
          // ------- Formular -------
          <div className="space-y-4">
            <div>
              <label className="mb-2 block text-sm font-semibold text-slate-700 dark:text-slate-300">
                Anzeigename
              </label>
              <Input
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                placeholder="z.B. Mein NAS"
              />
            </div>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
              <div className="sm:col-span-2">
                <label className="mb-2 block text-sm font-semibold text-slate-700 dark:text-slate-300">
                  Host / IP-Adresse
                </label>
                <Input
                  value={form.host}
                  onChange={(e) => setForm({ ...form, host: e.target.value })}
                  placeholder="z.B. 192.168.1.10"
                />
              </div>
              <div>
                <label className="mb-2 block text-sm font-semibold text-slate-700 dark:text-slate-300">
                  Port (optional)
                </label>
                <Input
                  value={form.port}
                  onChange={(e) => setForm({ ...form, port: e.target.value })}
                  placeholder="auto"
                  inputMode="numeric"
                />
              </div>
            </div>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div>
                <label className="mb-2 block text-sm font-semibold text-slate-700 dark:text-slate-300">
                  Benutzername
                </label>
                <Input
                  value={form.username}
                  onChange={(e) => setForm({ ...form, username: e.target.value })}
                  autoComplete="off"
                />
              </div>
              <div>
                <label className="mb-2 block text-sm font-semibold text-slate-700 dark:text-slate-300">
                  Passwort
                </label>
                <Input
                  type="password"
                  value={form.password}
                  onChange={(e) => setForm({ ...form, password: e.target.value })}
                  placeholder={
                    editing !== "new" ? "•••••• (leer lassen zum Beibehalten)" : ""
                  }
                  autoComplete="new-password"
                />
              </div>
            </div>
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:gap-6">
              <Switch
                checked={form.use_https}
                onCheckedChange={(v) => setForm({ ...form, use_https: v })}
                label="HTTPS verwenden"
              />
              <Switch
                checked={form.verify_ssl}
                onCheckedChange={(v) => setForm({ ...form, verify_ssl: v })}
                label="SSL-Zertifikat prüfen"
              />
            </div>

            {/* Test-Ergebnis */}
            {testState.kind === "ok" && (
              <div className="flex items-start gap-2 rounded-md border border-green-200 dark:border-green-800 bg-green-50 dark:bg-green-900/30 px-3 py-2 text-sm text-green-700 dark:text-green-300">
                <CheckCircle2 className="mt-0.5 h-4 w-4 flex-shrink-0" />
                <span>{testState.msg}</span>
              </div>
            )}
            {testState.kind === "error" && (
              <div className="flex items-start gap-2 rounded-md border border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-900/30 px-3 py-2 text-sm text-red-700 dark:text-red-300">
                <XCircle className="mt-0.5 h-4 w-4 flex-shrink-0" />
                <span className="break-words">{testState.msg}</span>
              </div>
            )}

            <Button
              variant="secondary"
              onClick={handleTest}
              isLoading={testState.kind === "loading"}
              disabled={!form.host.trim() || !form.username.trim()}
              className="w-full sm:w-auto"
            >
              <PlugZap className="mr-1.5 h-4 w-4" /> Verbindung testen
            </Button>
          </div>
        )}
      </DialogContent>

      <DialogFooter>
        {editing === null ? (
          <Button variant="secondary" onClick={() => onOpenChange(false)}>
            Schließen
          </Button>
        ) : (
          <>
            <Button variant="secondary" onClick={() => setEditing(null)}>
              Abbrechen
            </Button>
            <Button
              variant="primary"
              onClick={handleSave}
              isLoading={saving}
              disabled={!formValid}
            >
              Speichern
            </Button>
          </>
        )}
      </DialogFooter>
    </Dialog>
  )
}
