import {
  Dialog,
  DialogHeader,
  DialogTitle,
  DialogContent,
  DialogFooter,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Code, Copy, CheckCircle2, ExternalLink, BookOpen, FileJson, Lightbulb } from "lucide-react"
import { useCopyToClipboard } from "@/hooks/useCopyToClipboard"

interface ApiInfoModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onOpenApiTokens?: () => void
}

const API_BASE = "/api"

export function ApiInfoModal({ open, onOpenChange, onOpenApiTokens }: ApiInfoModalProps) {
  const { copiedKey, copy } = useCopyToClipboard()

  const apiExamples = [
    {
      title: "Gesamtzustand abrufen",
      description:
        "Ein Check für die ganze Instanz: severity 0 = OK, 1 = Warnung, 2 = kritisch",
      method: "GET",
      endpoint: `${API_BASE}/monitor`,
      curl: `curl -H "Authorization: Bearer $SSA_TOKEN" "${window.location.origin}${API_BASE}/monitor"`,
    },
    {
      title: "Zustand aller Scan-Jobs",
      description:
        "Roll-up über alle Jobs mit Problemliste; ?include_scans=0 liefert nur die Zusammenfassung",
      method: "GET",
      endpoint: `${API_BASE}/monitor/scans`,
      curl: `curl -H "Authorization: Bearer $SSA_TOKEN" "${window.location.origin}${API_BASE}/monitor/scans"`,
    },
    {
      title: "Zustand eines Scan-Jobs",
      description:
        "Schweregrad, Fehlertext, Ordnerbilanz und Überfälligkeit - fertig ausgewertet",
      method: "GET",
      endpoint: `${API_BASE}/monitor/scans/{scan_slug}`,
      curl: `curl -H "Authorization: Bearer $SSA_TOKEN" "${window.location.origin}${API_BASE}/monitor/scans/mein-scan"`,
    },
    {
      title: "Zustand der Infrastruktur",
      description: "Scheduler, Systemressourcen, Storage und Konfigurationswarnungen",
      method: "GET",
      endpoint: `${API_BASE}/monitor/server`,
      curl: `curl -H "Authorization: Bearer $SSA_TOKEN" "${window.location.origin}${API_BASE}/monitor/server"`,
    },
    {
      title: "PRTG-Sensordaten (Job)",
      description: 'Fertige Kanäle im Format "HTTP Data Advanced" - ein Sensor pro Scan-Job',
      method: "GET",
      endpoint: `${API_BASE}/prtg/scans/{scan_slug}`,
      curl: `curl -H "Authorization: Bearer $SSA_TOKEN" "${window.location.origin}${API_BASE}/prtg/scans/mein-scan"`,
    },
    {
      title: "PRTG-Sensordaten (Server)",
      description:
        "Ein Sensor für den Server selbst. CPU, RAM und Disk beziehen sich auf den "
        + "SSA-Host - für die Werte des NAS die nas-Sensoren verwenden.",
      method: "GET",
      endpoint: `${API_BASE}/prtg/server`,
      curl: `curl -H "Authorization: Bearer $SSA_TOKEN" "${window.location.origin}${API_BASE}/prtg/server"`,
    },
    {
      title: "PRTG-Sensordaten (NAS-Kapazität)",
      description:
        "Volume-Belegung, schreibgeschützte Volumes und Freigaben eines NAS. "
        + "Adressierbar per Verbindungs-ID oder -Name.",
      method: "GET",
      endpoint: `${API_BASE}/prtg/nas/{id_oder_name}/capacity`,
      curl: `curl -H "Authorization: Bearer $SSA_TOKEN" "${window.location.origin}${API_BASE}/prtg/nas/NAS-01/capacity"`,
    },
    {
      title: "PRTG-Sensordaten (NAS-Systemzustand)",
      description:
        "Temperatur, Lüfter, Plattenstatus, RAID und USV über SNMP. "
        + "Setzt einen hinterlegten SNMP-Zugang an der NAS-Verbindung voraus.",
      method: "GET",
      endpoint: `${API_BASE}/prtg/nas/{id_oder_name}/health`,
      curl: `curl -H "Authorization: Bearer $SSA_TOKEN" "${window.location.origin}${API_BASE}/prtg/nas/NAS-01/health"`,
    },
    {
      title: "NAS-Systemmetriken (JSON)",
      description:
        "Kapazität und Systemzustand aller NAS als rohes JSON, für Grafana und "
        + "eigene Auswertungen. ?groups=capacity,health schränkt die Quellen ein.",
      method: "GET",
      endpoint: `${API_BASE}/nas-metrics/{id_oder_name}`,
      curl: `curl -H "Authorization: Bearer $SSA_TOKEN" "${window.location.origin}${API_BASE}/nas-metrics/NAS-01"`,
    },
    {
      title: "Alle Scans abrufen",
      description: "Gibt eine Liste aller konfigurierten Scans mit Status zurück",
      method: "GET",
      endpoint: `${API_BASE}/scans`,
      curl: `curl -H "Authorization: Bearer $SSA_TOKEN" "${window.location.origin}${API_BASE}/scans"`,
    },
    {
      title: "Scan-Ergebnisse abrufen",
      description: "Gibt die neuesten Ergebnisse eines Scans zurück",
      method: "GET",
      endpoint: `${API_BASE}/scans/{scan_slug}/results`,
      curl: `curl -H "Authorization: Bearer $SSA_TOKEN" "${window.location.origin}${API_BASE}/scans/mein-scan/results"`,
    },
    {
      title: "Scan-Historie abrufen",
      description: "Gibt die komplette Historie aller Ergebnisse eines Scans zurück",
      method: "GET",
      endpoint: `${API_BASE}/scans/{scan_slug}/history`,
      curl: `curl -H "Authorization: Bearer $SSA_TOKEN" "${window.location.origin}${API_BASE}/scans/mein-scan/history"`,
    },
    {
      title: "Scan-Status abrufen (veraltet)",
      description:
        "Gibt den aktuellen Status eines Scans zurück. Für Monitoring abgelöst von /api/monitor/scans/{scan_slug}",
      method: "GET",
      endpoint: `${API_BASE}/scans/{scan_slug}/status`,
      curl: `curl -H "Authorization: Bearer $SSA_TOKEN" "${window.location.origin}${API_BASE}/scans/mein-scan/status"`,
    },
    {
      title: "Scan-Progress abrufen",
      description: "Gibt den Fortschritt eines laufenden Scans zurück",
      method: "GET",
      endpoint: `${API_BASE}/scans/{scan_slug}/progress`,
      curl: `curl -H "Authorization: Bearer $SSA_TOKEN" "${window.location.origin}${API_BASE}/scans/mein-scan/progress"`,
    },
    {
      title: "Scan manuell starten",
      description:
        "Startet einen Scan manuell. Erfordert ein Login-Token - read-only "
        + "API-Tokens dürfen nur GET und werden hier mit 403 abgelehnt.",
      method: "POST",
      endpoint: `${API_BASE}/scans/{scan_slug}/trigger`,
      curl: `curl -X POST -H "Authorization: Bearer $SSA_LOGIN_TOKEN" "${window.location.origin}${API_BASE}/scans/mein-scan/trigger"`,
    },
  ]

  if (!open) return null

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogHeader>
        <DialogTitle className="flex items-center gap-2 min-w-0">
          <BookOpen className="h-5 w-5 flex-shrink-0" />
          <span className="truncate">API-Dokumentation</span>
        </DialogTitle>
      </DialogHeader>

      <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto">
        <div className="space-y-6">
          {/* Einleitung */}
          <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-700 rounded-lg p-4">
            <h3 className="font-semibold text-blue-900 dark:text-blue-200 mb-2 flex items-center gap-2">
              <ExternalLink className="h-4 w-4" />
              API-Integration für Monitoring-Systeme
            </h3>
            <p className="text-sm text-blue-800 dark:text-blue-200 mb-3">
              Die <code className="bg-blue-100 dark:bg-blue-900/40 dark:text-blue-200 px-1.5 py-0.5 rounded">/api/monitor*</code>-Endpunkte
              liefern den Zustand fertig ausgewertet: das Feld{" "}
              <code className="bg-blue-100 dark:bg-blue-900/40 dark:text-blue-200 px-1.5 py-0.5 rounded">severity</code>{" "}
              (0 = OK, 1 = Warnung, 2 = kritisch) genügt für die
              Alarmentscheidung — ohne Zweit-Abfrage und ohne eigene Logik. Für
              PRTG gibt es stattdessen fertige Sensordaten unter{" "}
              <code className="bg-blue-100 dark:bg-blue-900/40 dark:text-blue-200 px-1.5 py-0.5 rounded">/api/prtg/*</code>.
            </p>
            <div className="text-sm text-blue-700 dark:text-blue-300 space-y-1">
              <p><strong>Base URL:</strong> <code className="bg-blue-100 dark:bg-blue-900/40 dark:text-blue-200 px-1.5 py-0.5 rounded">{window.location.origin}{API_BASE}</code></p>
              <p><strong>Content-Type:</strong> <code className="bg-blue-100 dark:bg-blue-900/40 dark:text-blue-200 px-1.5 py-0.5 rounded">application/json</code></p>
              <p><strong>Authentifizierung:</strong> <code className="bg-blue-100 dark:bg-blue-900/40 dark:text-blue-200 px-1.5 py-0.5 rounded">Authorization: Bearer &lt;token&gt;</code> — lesende Beispiele erwarten ein read-only API-Token in <code className="bg-blue-100 dark:bg-blue-900/40 dark:text-blue-200 px-1.5 py-0.5 rounded">SSA_TOKEN</code>, schreibende ein Login-Token in <code className="bg-blue-100 dark:bg-blue-900/40 dark:text-blue-200 px-1.5 py-0.5 rounded">SSA_LOGIN_TOKEN</code> (aus <code className="bg-blue-100 dark:bg-blue-900/40 dark:text-blue-200 px-1.5 py-0.5 rounded">POST /api/auth/login</code>)</p>
            </div>
          </div>

          {/* API-Endpunkte */}
          <div className="space-y-4">
            <h3 className="text-lg font-semibold text-slate-900 dark:text-slate-100 flex items-center gap-2">
              <Code className="h-5 w-5" />
              Verfügbare Endpunkte
            </h3>

            {apiExamples.map((example, index) => (
              <div
                key={index}
                className="border border-slate-200 dark:border-slate-700 rounded-lg overflow-hidden"
              >
                <div className="bg-slate-50 dark:bg-slate-800 px-4 py-3 border-b border-slate-200 dark:border-slate-700">
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-1">
                        <span className={`rounded-sm border px-1.5 py-0.5 font-mono text-[11px] font-medium uppercase tracking-label ${
                          example.method === "GET"
                            ? "border-slate-200 dark:border-slate-600 bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-300"
                            : "border-primary-200 dark:border-primary-700 bg-primary-50 dark:bg-primary-900/30 text-primary-700 dark:text-primary-300"
                        }`}>
                          {example.method}
                        </span>
                        <h4 className="font-semibold text-slate-900 dark:text-slate-100">{example.title}</h4>
                      </div>
                      <p className="text-sm text-slate-600 dark:text-slate-400 mt-1">{example.description}</p>
                      <code className="text-xs text-slate-700 dark:text-slate-300 mt-2 block bg-white dark:bg-slate-700 px-2 py-1 rounded border border-slate-200 dark:border-slate-700">
                        {example.endpoint}
                      </code>
                    </div>
                  </div>
                </div>
                <div className="p-4 bg-slate-900 text-slate-100">
                  <div className="flex items-center justify-between mb-2">
                    <span className="label-mono text-slate-400 dark:text-slate-500">cURL-Beispiel</span>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => copy(example.curl, `${index}:curl`)}
                      className="h-7 px-2 text-xs text-slate-300 hover:text-white hover:bg-slate-800"
                    >
                      {copiedKey === `${index}:curl` ? (
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
                  </div>
                  <pre className="text-xs text-slate-300 overflow-x-auto">
                    <code>{example.curl}</code>
                  </pre>
                </div>
              </div>
            ))}
          </div>

          {/* Monitoring-Integration Beispiele */}
          <div className="bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg p-4">
            <h3 className="font-semibold text-slate-900 dark:text-slate-100 mb-3 flex items-center gap-2">
              <Lightbulb className="h-4 w-4" />
              Monitoring-Integration
            </h3>
            <div className="space-y-3 text-sm text-slate-700 dark:text-slate-300">
              <div>
                <strong className="text-slate-900 dark:text-slate-100">PRTG:</strong>
                <p className="mt-1">
                  Sensortyp <strong>HTTP Data Advanced</strong> auf{" "}
                  <code className="bg-white dark:bg-slate-700 dark:text-slate-300 px-1.5 py-0.5 rounded border">{"/api/prtg/scans/{scan_slug}"}</code>{" "}
                  bzw. <code className="bg-white dark:bg-slate-700 dark:text-slate-300 px-1.5 py-0.5 rounded border">/api/prtg/server</code>.
                  PRTG legt die Kanäle selbst an.
                </p>
              </div>
              <div>
                <strong className="text-slate-900 dark:text-slate-100">PRTG für die NAS selbst:</strong>
                <p className="mt-1">
                  <code className="bg-white dark:bg-slate-700 dark:text-slate-300 px-1.5 py-0.5 rounded border">{"/api/prtg/nas/{id}/capacity"}</code>{" "}
                  liefert Volume-Belegung und Freigaben,{" "}
                  <code className="bg-white dark:bg-slate-700 dark:text-slate-300 px-1.5 py-0.5 rounded border">{"/api/prtg/nas/{id}/health"}</code>{" "}
                  Temperatur, Plattenstatus und RAID-Zustand über SNMP. Beachten:
                  CPU und RAM in{" "}
                  <code className="bg-white dark:bg-slate-700 dark:text-slate-300 px-1.5 py-0.5 rounded border">/api/prtg/server</code>{" "}
                  messen den SSA-Host, nicht das NAS.
                </p>
              </div>
              <div>
                <strong className="text-slate-900 dark:text-slate-100">Zabbix, Checkmk, Nagios, Icinga:</strong>
                <p className="mt-1">
                  <code className="bg-white dark:bg-slate-700 dark:text-slate-300 px-1.5 py-0.5 rounded border">/api/monitor</code>{" "}
                  abrufen und <code className="bg-white dark:bg-slate-700 dark:text-slate-300 px-1.5 py-0.5 rounded border">$.severity</code>{" "}
                  auswerten. Werkzeuge, die nur den Statuscode lesen, ergänzen{" "}
                  <code className="bg-white dark:bg-slate-700 dark:text-slate-300 px-1.5 py-0.5 rounded border">?http_status=1</code> —
                  dann wird „kritisch" zu HTTP 503. Der Schweregrad steht außerdem
                  im Header{" "}
                  <code className="bg-white dark:bg-slate-700 dark:text-slate-300 px-1.5 py-0.5 rounded border">X-SSA-Severity</code>.
                </p>
              </div>
              <div>
                <strong className="text-slate-900 dark:text-slate-100">Grafana, Prometheus:</strong>
                <p className="mt-1">
                  <code className="bg-white dark:bg-slate-700 dark:text-slate-300 px-1.5 py-0.5 rounded border">/api/monitor/scans</code>{" "}
                  liefert alle Jobs in einem Aufruf — inklusive Größen, Ordnerbilanz
                  und Schweregrad je Job. Für die Rohdaten einzelner Läufe{" "}
                  <code className="bg-white dark:bg-slate-700 dark:text-slate-300 px-1.5 py-0.5 rounded border">{"/api/scans/{scan_slug}/results"}</code>.
                </p>
              </div>
            </div>
          </div>

          {/* Response-Beispiel */}
          <div className="bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg p-4">
            <h3 className="font-semibold text-slate-900 dark:text-slate-100 mb-2 flex items-center gap-2">
              <FileJson className="h-4 w-4" />
              Response-Format
            </h3>
            <p className="text-sm text-slate-600 dark:text-slate-400 mb-3">
              Alle Endpunkte liefern JSON. Beispiel für{" "}
              <code className="bg-white dark:bg-slate-700 dark:text-slate-300 px-1.5 py-0.5 rounded border">{"/api/monitor/scans/{scan_slug}"}</code>{" "}
              — gekürzt; alle Felder sind immer vorhanden, Unbekanntes ist <code className="bg-white dark:bg-slate-700 dark:text-slate-300 px-1.5 py-0.5 rounded border">null</code>:
            </p>
            <pre className="text-xs bg-slate-900 text-slate-100 p-3 rounded overflow-x-auto">
              <code>{`{
  "severity": 1,
  "severity_text": "warning",
  "state": "partial",
  "reasons": ["partial"],
  "message": "Letzter Lauf abgeschlossen, aber 1 von 3 Ordnern fehlgeschlagen: /photo",
  "scan": { "slug": "mein-scan", "name": "Mein Scan", "enabled": true },
  "run": { "active": false },
  "last_run": {
    "at": "2026-07-25T09:00:00Z",
    "age_seconds": 764.0,
    "status": "completed",
    "error": null,
    "folders_total": 3,
    "folders_ok": 2,
    "folders_failed": 1,
    "folders_failed_names": ["/photo"]
  },
  "last_success": {
    "at": "2026-07-25T09:00:00Z",
    "total_bytes": 1073741824,
    "total_directories": 50,
    "total_files": 1000
  },
  "schedule": {
    "scheduled": true,
    "expected_interval_seconds": 21600.0,
    "overdue": false,
    "overdue_after_seconds": 64800.0
  }
}`}</code>
            </pre>
          </div>
        </div>
      </DialogContent>

      <DialogFooter>
        {onOpenApiTokens && (
          <Button
            variant="secondary"
            onClick={() => {
              onOpenChange(false)
              onOpenApiTokens()
            }}
            className="mr-auto"
          >
            API-Tokens verwalten
          </Button>
        )}
        <Button variant="secondary" onClick={() => onOpenChange(false)}>
          Schließen
        </Button>
      </DialogFooter>
    </Dialog>
  )
}
