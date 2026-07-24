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
import { useToast } from "@/components/ui/toast"
import { fetchApiTokens, createApiToken, deleteApiToken } from "@/lib/api"
import type { ApiTokenPublic, ApiTokenCreated } from "@/types/api"
import { formatRelativeTime } from "@/lib/utils"
import {
  KeyRound,
  Plus,
  Trash2,
  Loader2,
  Copy,
  Check,
  AlertTriangle,
} from "lucide-react"

interface ApiTokensModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

/**
 * Verwaltung statischer API-Tokens für Monitoring-Systeme (z.B. PRTG).
 *
 * Tokens sind read-only (nur GET auf Scan-Status/Ergebnisse und
 * Storage-Statistiken) und werden nach der Erstellung genau einmal angezeigt.
 */
export function ApiTokensModal({ open, onOpenChange }: ApiTokensModalProps) {
  const { showToast } = useToast()
  const [tokens, setTokens] = useState<ApiTokenPublic[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [newName, setNewName] = useState("")
  const [creating, setCreating] = useState(false)
  const [created, setCreated] = useState<ApiTokenCreated | null>(null)
  const [copied, setCopied] = useState(false)

  const loadTokens = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setTokens(await fetchApiTokens())
    } catch (err) {
      setError(err instanceof Error ? err.message : "Fehler beim Laden")
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (open) {
      setCreated(null)
      setNewName("")
      setCopied(false)
      loadTokens()
    }
  }, [open, loadTokens])

  async function handleCreate() {
    const name = newName.trim()
    if (!name) return
    setCreating(true)
    try {
      const result = await createApiToken(name)
      setCreated(result)
      setCopied(false)
      setNewName("")
      loadTokens()
    } catch (err) {
      showToast(
        "Fehler",
        err instanceof Error ? err.message : "Erstellen fehlgeschlagen",
        "error"
      )
    } finally {
      setCreating(false)
    }
  }

  async function handleCopy() {
    if (!created) return
    try {
      await navigator.clipboard.writeText(created.token)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      showToast("Fehler", "Kopieren nicht möglich - bitte manuell markieren", "error")
    }
  }

  async function handleDelete(token: ApiTokenPublic) {
    if (
      !confirm(
        `API-Token '${token.name}' widerrufen?\n\nMonitoring-Systeme, die dieses Token verwenden, verlieren sofort den Zugriff.`
      )
    ) {
      return
    }
    try {
      await deleteApiToken(token.id)
      showToast("Erfolg", `Token '${token.name}' widerrufen`, "success")
      if (created?.id === token.id) setCreated(null)
      loadTokens()
    } catch (err) {
      showToast(
        "Fehler",
        err instanceof Error ? err.message : "Widerrufen fehlgeschlagen",
        "error"
      )
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange} maxWidth="2xl">
      <DialogHeader className="bg-gradient-to-r from-emerald-500 to-teal-600 text-white px-6 py-4">
        <DialogTitle className="text-white flex items-center gap-2 min-w-0">
          <KeyRound className="h-5 w-5 flex-shrink-0" />
          <span className="truncate">API-Tokens für Monitoring</span>
        </DialogTitle>
      </DialogHeader>

      <DialogContent>
        <div className="space-y-4">
          <p className="text-sm text-slate-500 dark:text-slate-400">
            Statische Tokens für Monitoring-Systeme (z.B. PRTG, Zabbix, Grafana).
            Sie erlauben <strong>nur Lesezugriff</strong> auf Scan-Status,
            Ergebnisse, Historie und Storage-Statistiken — keine Verwaltung,
            keine Scan-Trigger. Verwendung:{" "}
            <code className="rounded bg-slate-100 dark:bg-slate-800 px-1.5 py-0.5 text-xs">
              Authorization: Bearer &lt;token&gt;
            </code>
          </p>

          {/* Frisch erstelltes Token - einmalige Anzeige */}
          {created && (
            <div className="rounded-lg border border-amber-300 dark:border-amber-700 bg-amber-50 dark:bg-amber-900/30 p-4 space-y-2">
              <div className="flex items-start gap-2 text-sm font-semibold text-amber-800 dark:text-amber-300">
                <AlertTriangle className="h-4 w-4 mt-0.5 flex-shrink-0" />
                <span>
                  Token '{created.name}' erstellt — jetzt kopieren! Es wird aus
                  Sicherheitsgründen nie wieder angezeigt.
                </span>
              </div>
              <div className="flex items-center gap-2">
                <code className="flex-1 min-w-0 truncate rounded-md border border-amber-200 dark:border-amber-800 bg-white dark:bg-slate-900 px-3 py-2 font-mono text-xs text-slate-800 dark:text-slate-200">
                  {created.token}
                </code>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={handleCopy}
                  aria-label="Token kopieren"
                >
                  {copied ? (
                    <Check className="h-4 w-4 text-green-600" />
                  ) : (
                    <Copy className="h-4 w-4" />
                  )}
                </Button>
              </div>
            </div>
          )}

          {/* Neues Token */}
          <div className="flex gap-2">
            <Input
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault()
                  handleCreate()
                }
              }}
              placeholder="Name, z.B. PRTG"
            />
            <Button
              variant="primary"
              onClick={handleCreate}
              isLoading={creating}
              disabled={!newName.trim()}
              className="flex-shrink-0"
            >
              <Plus className="mr-1.5 h-4 w-4" /> Erstellen
            </Button>
          </div>

          {/* Liste */}
          {loading ? (
            <div className="flex justify-center py-8">
              <Loader2 className="h-6 w-6 animate-spin text-slate-400" />
            </div>
          ) : error ? (
            <div className="py-6 text-center">
              <p className="mb-3 text-sm text-red-600 dark:text-red-400">{error}</p>
              <Button variant="secondary" size="sm" onClick={loadTokens}>
                Erneut versuchen
              </Button>
            </div>
          ) : tokens.length === 0 ? (
            <p className="py-6 text-center text-sm text-slate-400 dark:text-slate-500">
              Noch keine API-Tokens vorhanden
            </p>
          ) : (
            <div className="space-y-2">
              {tokens.map((token) => (
                <div
                  key={token.id}
                  className="flex items-center gap-3 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-4 py-3"
                >
                  <KeyRound className="h-4 w-4 flex-shrink-0 text-emerald-500" />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-semibold text-slate-900 dark:text-slate-100">
                      {token.name}
                    </p>
                    <p className="truncate text-xs text-slate-500 dark:text-slate-400">
                      {token.last_used_at
                        ? `Zuletzt benutzt ${formatRelativeTime(token.last_used_at)}`
                        : "Noch nie benutzt"}
                    </p>
                  </div>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => handleDelete(token)}
                    aria-label={`${token.name} widerrufen`}
                    className="flex-shrink-0 text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/30"
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              ))}
            </div>
          )}
        </div>
      </DialogContent>

      <DialogFooter>
        <Button variant="secondary" onClick={() => onOpenChange(false)}>
          Schließen
        </Button>
      </DialogFooter>
    </Dialog>
  )
}
