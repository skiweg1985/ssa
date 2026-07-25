import {
  Dialog,
  DialogHeader,
  DialogTitle,
  DialogContent,
  DialogFooter,
} from "@/components/ui/dialog"
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs"
import { Button } from "@/components/ui/button"
import {
  Activity,
  Copy,
  CheckCircle2,
  Database,
  Lightbulb,
  Link2,
  Play,
} from "lucide-react"
import { useState } from "react"
import { useCopyToClipboard } from "@/hooks/useCopyToClipboard"
import type { ScanStatus } from "@/types/api"

interface ScanApiModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  scan: ScanStatus | null
}

const API_BASE = "/api"

type TabId = "monitoring" | "daten" | "aktionen" | "beispiele"

interface Endpoint {
  id: string
  tab: TabId
  title: string
  description: string
  method: "GET" | "POST"
  endpoint: string
  /** Hervorhebung: empfohlener Weg bzw. veralteter Endpunkt */
  badge?: { label: string; tone: "recommended" | "deprecated" }
}

export function ScanApiModal({ open, onOpenChange, scan }: ScanApiModalProps) {
  const [activeTab, setActiveTab] = useState<TabId>("monitoring")
  const { copiedKey, copy } = useCopyToClipboard()

  if (!open || !scan) return null

  // Validierung: Stelle sicher, dass baseUrl und scanSlug vorhanden sind
  const baseUrl = window.location.origin || ""
  const scanSlug = scan.scan_slug || ""
  const scanName = scan.scan_name || ""

  // Wenn kein Slug vorhanden ist, zeige Fehlermeldung
  if (!scanSlug) {
    return (
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 min-w-0">
            <Link2 className="h-5 w-5 flex-shrink-0" />
            <span className="truncate">Fehler</span>
          </DialogTitle>
        </DialogHeader>
        <DialogContent>
          <p className="text-red-600 dark:text-red-400">Kein gültiger Scan-Slug gefunden.</p>
        </DialogContent>
        <DialogFooter>
          <Button variant="secondary" onClick={() => onOpenChange(false)}>
            Schließen
          </Button>
        </DialogFooter>
      </Dialog>
    )
  }

  const fullBaseUrl = baseUrl.trim()

  const apiEndpoints: Endpoint[] = [
    {
      id: "monitor",
      tab: "monitoring",
      title: "Monitoring-Bericht",
      description:
        "Zustand dieses Jobs als severity (0 = OK, 1 = Warnung, 2 = kritisch), " +
        "inklusive Fehlertext, Ordnerbilanz und Überfälligkeit. Von jedem " +
        "Monitoring-System auswertbar — ohne Zweit-Abfrage.",
      method: "GET",
      endpoint: `${API_BASE}/monitor/scans/${scanSlug}`,
      badge: { label: "empfohlen", tone: "recommended" },
    },
    {
      id: "prtg",
      tab: "monitoring",
      title: "PRTG-Sensordaten",
      description:
        'Fertige Kanäle im Format "HTTP Data Advanced" — PRTG legt die Kanäle ' +
        "selbst an, JSONPath-Filter entfallen.",
      method: "GET",
      endpoint: `${API_BASE}/prtg/scans/${scanSlug}`,
    },
    {
      id: "status",
      tab: "monitoring",
      title: "Scan-Status",
      description:
        "Aktueller Status dieses Scans. Für Monitoring ungeeignet: der Status " +
        "mischt Lebenszyklus und Ergebnis, Teilfehler und Fehlertexte fehlen. " +
        "Bleibt aus Kompatibilitätsgründen erhalten.",
      method: "GET",
      endpoint: `${API_BASE}/scans/${scanSlug}/status`,
      badge: { label: "veraltet", tone: "deprecated" },
    },
    {
      id: "results",
      tab: "daten",
      title: "Scan-Ergebnisse",
      description: "Neueste Ergebnisse dieses Scans abrufen",
      method: "GET",
      endpoint: `${API_BASE}/scans/${scanSlug}/results`,
    },
    {
      id: "history",
      tab: "daten",
      title: "Scan-Historie",
      description:
        "Historie aller Ergebnisse dieses Scans. Ohne Parameter komplett; " +
        "mit ?limit=<n> die n neuesten und ?offset=<n> zum Überspringen.",
      method: "GET",
      endpoint: `${API_BASE}/scans/${scanSlug}/history`,
    },
    {
      id: "progress",
      tab: "daten",
      title: "Scan-Fortschritt",
      description: "Fortschritt eines laufenden Scans (nur wenn Scan läuft)",
      method: "GET",
      endpoint: `${API_BASE}/scans/${scanSlug}/progress`,
    },
    {
      id: "trigger",
      tab: "aktionen",
      title: "Scan starten",
      description: "Diesen Scan manuell starten",
      method: "POST",
      endpoint: `${API_BASE}/scans/${scanSlug}/trigger`,
    },
    {
      id: "cancel",
      tab: "aktionen",
      title: "Scan abbrechen",
      description:
        "Einen laufenden Scan beenden. Der Abbruch ist kooperativ: der Lauf " +
        "endet beim nächsten Prüfpunkt, in der Regel innerhalb weniger " +
        "Sekunden. Bereits gemessene Ordner bleiben erhalten, der Lauf wird " +
        "mit Status \"cancelled\" gespeichert.",
      method: "POST",
      endpoint: `${API_BASE}/scans/${scanSlug}/cancel`,
    },
  ]

  const urlFor = (endpoint: Endpoint) => `${fullBaseUrl}${endpoint.endpoint}`
  const curlFor = (endpoint: Endpoint) =>
    [
      "curl",
      ...(endpoint.method === "POST" ? ["-X", "POST"] : []),
      '-H "Authorization: Bearer $SSA_TOKEN"',
      `"${urlFor(endpoint)}"`,
    ].join(" ")

  const tabs: Array<{ id: TabId; label: string; icon: typeof Activity }> = [
    { id: "monitoring", label: "Monitoring", icon: Activity },
    { id: "daten", label: "Daten", icon: Database },
    { id: "aktionen", label: "Aktionen", icon: Play },
    { id: "beispiele", label: "Beispiele", icon: Lightbulb },
  ]

  const copyButton = (text: string, key: string, dark = false) => (
    <Button
      variant="ghost"
      size="sm"
      onClick={() => copy(text, key)}
      className={
        dark
          ? "h-7 px-2 text-xs text-slate-300 hover:text-white hover:bg-slate-800"
          : "h-7 px-2 text-xs"
      }
    >
      {copiedKey === key ? (
        <>
          <CheckCircle2 className="h-3 w-3 mr-1" />
          Kopiert!
        </>
      ) : (
        <>
          <Copy className="h-3 w-3 mr-1" />
          Kopieren
        </>
      )}
    </Button>
  )

  const endpointCard = (endpoint: Endpoint) => (
    <div
      key={endpoint.id}
      className="border border-slate-200 dark:border-slate-600 rounded-lg overflow-hidden"
    >
      <div className="bg-slate-50 dark:bg-slate-800 px-4 py-3 border-b border-slate-200 dark:border-slate-600">
        <div className="flex items-center gap-2 mb-1 flex-wrap">
          <span
            className={`rounded-sm border px-1.5 py-0.5 font-mono text-[11px] font-medium uppercase tracking-label ${
              endpoint.method === "GET"
                ? "border-slate-200 dark:border-slate-600 bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-300"
                : "border-primary-200 dark:border-primary-700 bg-primary-50 dark:bg-primary-900/30 text-primary-700 dark:text-primary-300"
            }`}
          >
            {endpoint.method}
          </span>
          <h4 className="font-semibold text-slate-900 dark:text-slate-100">
            {endpoint.title}
          </h4>
          {endpoint.badge && (
            <span
              className={`rounded-sm border px-1.5 py-0.5 text-[11px] font-medium uppercase tracking-label ${
                endpoint.badge.tone === "recommended"
                  ? "border-emerald-200 dark:border-emerald-700 bg-emerald-50 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300"
                  : "border-amber-200 dark:border-amber-700 bg-amber-50 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300"
              }`}
            >
              {endpoint.badge.label}
            </span>
          )}
        </div>
        <p className="text-sm text-slate-600 dark:text-slate-400 mt-1">
          {endpoint.description}
        </p>
        <code className="text-xs text-slate-700 dark:text-slate-300 mt-2 block bg-white dark:bg-slate-700 px-2 py-1 rounded border border-slate-200 dark:border-slate-600">
          {endpoint.endpoint}
        </code>
      </div>

      {/* URL */}
      <div className="px-4 py-3 bg-slate-100 dark:bg-slate-700 border-b border-slate-200 dark:border-slate-600">
        <div className="flex items-center justify-between">
          <span className="text-xs text-slate-600 dark:text-slate-400 font-medium">
            URL:
          </span>
          {copyButton(urlFor(endpoint), `${endpoint.id}:url`)}
        </div>
        <code className="text-xs text-slate-700 dark:text-slate-300 block mt-1 break-all">
          {urlFor(endpoint)}
        </code>
      </div>

      {/* cURL */}
      <div className="p-4 bg-slate-900 text-slate-100">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs text-slate-400">cURL-Befehl:</span>
          {copyButton(curlFor(endpoint), `${endpoint.id}:curl`, true)}
        </div>
        <pre className="text-xs text-slate-300 overflow-x-auto">
          <code>{curlFor(endpoint)}</code>
        </pre>
      </div>
    </div>
  )

  const endpointsFor = (tab: TabId) =>
    apiEndpoints.filter((endpoint) => endpoint.tab === tab)

  const examples: Array<{ id: string; title: string; code: string }> = [
    {
      id: "shell",
      title: "Alarm-Check (Shell)",
      code: `# severity: 0 = OK, 1 = Warnung, 2 = kritisch
curl -s -H "Authorization: Bearer $SSA_TOKEN" \\
  "${fullBaseUrl}${API_BASE}/monitor/scans/${scanSlug}" \\
  | jq -e '.severity < 2' > /dev/null || echo "${scanSlug} meldet ein Problem"`,
    },
    {
      id: "status-code",
      title: "Nur den Statuscode auswerten",
      code: `# Mit http_status=1 wird "kritisch" zu HTTP 503 - für Uptime-Kuma,
# check_http oder Docker-Healthchecks
curl -fsS -H "Authorization: Bearer $SSA_TOKEN" \\
  "${fullBaseUrl}${API_BASE}/monitor/scans/${scanSlug}?http_status=1" > /dev/null`,
    },
    {
      id: "stuck",
      title: "Hängenden Scan erkennen und abbrechen",
      code: `# run.stuck wird true, wenn der Lauf die erwartete Dauer deutlich
# überschreitet (state wird dann "stuck", severity 2)
REPORT=$(curl -s -H "Authorization: Bearer $SSA_TOKEN" \\
  "${fullBaseUrl}${API_BASE}/monitor/scans/${scanSlug}")

if [ "$(echo "$REPORT" | jq -r '.run.stuck')" = "true" ]; then
  echo "$REPORT" | jq -r '"hängt seit \\(.run.active_seconds | floor)s bei \\(.run.progress_percent // "?")%"'
  # Abbruch erfordert eine angemeldete Sitzung, kein read-only Token
  curl -s -X POST -H "Authorization: Bearer $SSA_LOGIN_TOKEN" \\
    "${fullBaseUrl}${API_BASE}/scans/${scanSlug}/cancel" | jq -r '.message'
fi`,
    },
    {
      id: "python",
      title: "Python-Integration",
      code: `import requests

headers = {"Authorization": "Bearer " + SSA_TOKEN}
report = requests.get(
    "${fullBaseUrl}${API_BASE}/monitor/scans/${scanSlug}", headers=headers
).json()

if report["severity"] >= 2:
    alert(report["message"])          # fertiger Alarmtext
print(report["last_success"]["total_bytes"])`,
    },
    {
      id: "results",
      title: "Rohdaten auslesen",
      code: `RESULT=$(curl -s -H "Authorization: Bearer $SSA_TOKEN" \\
  "${fullBaseUrl}${API_BASE}/scans/${scanSlug}/results")
echo "$RESULT" | jq '.results[0].total_size.bytes'`,
    },
  ]

  return (
    <Dialog open={open} onOpenChange={onOpenChange} maxWidth="3xl">
      <DialogHeader>
        <DialogTitle className="flex items-center gap-2 min-w-0">
          <Link2 className="h-5 w-5 flex-shrink-0" />
          <span className="truncate">API-Informationen: {scanName}</span>
        </DialogTitle>
      </DialogHeader>

      <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
        {/* Kontext für alle Tabs */}
        <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-700 rounded-lg p-4 mb-4">
          <p className="text-sm text-blue-800 dark:text-blue-200">
            Endpunkte für den Scan-Job <strong>„{scanName}"</strong> (ID:{" "}
            <code className="bg-white dark:bg-slate-700 dark:text-slate-300 px-1 py-0.5 rounded text-xs">
              {scanSlug}
            </code>
            ).
          </p>
          <p className="text-sm text-blue-700 dark:text-blue-300 mt-2">
            Alle Endpunkte erfordern den Header{" "}
            <code className="bg-white dark:bg-slate-700 dark:text-slate-300 px-1 py-0.5 rounded text-xs">
              Authorization: Bearer …
            </code>
            . Die cURL-Befehle erwarten das Token in der Umgebungsvariablen{" "}
            <code className="bg-white dark:bg-slate-700 dark:text-slate-300 px-1 py-0.5 rounded text-xs">
              SSA_TOKEN
            </code>
            ; erzeugt wird es über „API-Tokens verwalten".
          </p>
        </div>

        <Tabs value={activeTab} onValueChange={(value) => setActiveTab(value as TabId)}>
          <div className="overflow-x-auto scrollbar-thin">
            <TabsList>
              {tabs.map(({ id, label, icon: Icon }) => (
                <TabsTrigger key={id} value={id} className="flex items-center gap-2">
                  <Icon className="h-4 w-4" />
                  {label}
                </TabsTrigger>
              ))}
            </TabsList>
          </div>

          <TabsContent value="monitoring" className="mt-4 space-y-4">
            {endpointsFor("monitoring").map(endpointCard)}
          </TabsContent>

          <TabsContent value="daten" className="mt-4 space-y-4">
            {endpointsFor("daten").map(endpointCard)}
          </TabsContent>

          <TabsContent value="aktionen" className="mt-4 space-y-4">
            <div className="bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-700 rounded-lg p-4">
              <p className="text-sm text-amber-800 dark:text-amber-200">
                Schreibender Zugriff: read-only API-Tokens dürfen{" "}
                <strong>nicht</strong> triggern — dieser Endpunkt erfordert eine
                angemeldete Sitzung.
              </p>
            </div>
            {endpointsFor("aktionen").map(endpointCard)}
          </TabsContent>

          <TabsContent value="beispiele" className="mt-4 space-y-4">
            {examples.map((example) => (
              <div
                key={example.id}
                className="border border-slate-200 dark:border-slate-600 rounded-lg overflow-hidden"
              >
                <div className="flex items-center justify-between bg-slate-50 dark:bg-slate-800 px-4 py-2 border-b border-slate-200 dark:border-slate-600">
                  <h4 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
                    {example.title}
                  </h4>
                  {copyButton(example.code, `example:${example.id}`)}
                </div>
                <pre className="p-4 bg-slate-900 text-xs text-slate-300 overflow-x-auto">
                  <code>{example.code}</code>
                </pre>
              </div>
            ))}
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
