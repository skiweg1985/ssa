import {
  Dialog,
  DialogHeader,
  DialogTitle,
  DialogContent,
  DialogFooter,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Code, Copy, CheckCircle2, ExternalLink, BookOpen, Lightbulb } from "lucide-react"
import { useState } from "react"

interface ApiInfoModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

const API_BASE = "/api"

export function ApiInfoModal({ open, onOpenChange }: ApiInfoModalProps) {
  const [copiedIndex, setCopiedIndex] = useState<number | null>(null)

  const copyToClipboard = async (text: string, index: number) => {
    try {
      // Moderne Clipboard API (benötigt HTTPS oder localhost)
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(text)
        setCopiedIndex(index)
        setTimeout(() => setCopiedIndex(null), 2000)
        return
      }
      
      // Fallback: Alte Methode mit execCommand
      const textArea = document.createElement("textarea")
      textArea.value = text
      textArea.style.position = "fixed"
      textArea.style.left = "-999999px"
      textArea.style.top = "-999999px"
      document.body.appendChild(textArea)
      textArea.focus()
      textArea.select()
      
      const successful = document.execCommand("copy")
      document.body.removeChild(textArea)
      
      if (successful) {
        setCopiedIndex(index)
        setTimeout(() => setCopiedIndex(null), 2000)
      } else {
        console.error("Kopieren fehlgeschlagen")
      }
    } catch (err) {
      console.error("Fehler beim Kopieren:", err)
      // Optional: Fehlermeldung anzeigen
    }
  }

  const apiExamples = [
    {
      title: "Alle Scans abrufen",
      description: "Gibt eine Liste aller konfigurierten Scans mit Status zurück",
      method: "GET",
      endpoint: `${API_BASE}/scans`,
      curl: `curl -X GET "${window.location.origin}${API_BASE}/scans"`,
    },
    {
      title: "Scan-Ergebnisse abrufen",
      description: "Gibt die neuesten Ergebnisse eines Scans zurück",
      method: "GET",
      endpoint: `${API_BASE}/scans/{scan_slug}/results`,
      curl: `curl -X GET "${window.location.origin}${API_BASE}/scans/mein-scan/results"`,
    },
    {
      title: "Scan-Historie abrufen",
      description: "Gibt die komplette Historie aller Ergebnisse eines Scans zurück",
      method: "GET",
      endpoint: `${API_BASE}/scans/{scan_slug}/history`,
      curl: `curl -X GET "${window.location.origin}${API_BASE}/scans/mein-scan/history"`,
    },
    {
      title: "Scan-Status abrufen",
      description: "Gibt den aktuellen Status eines Scans zurück",
      method: "GET",
      endpoint: `${API_BASE}/scans/{scan_slug}/status`,
      curl: `curl -X GET "${window.location.origin}${API_BASE}/scans/mein-scan/status"`,
    },
    {
      title: "Scan-Progress abrufen",
      description: "Gibt den Fortschritt eines laufenden Scans zurück",
      method: "GET",
      endpoint: `${API_BASE}/scans/{scan_slug}/progress`,
      curl: `curl -X GET "${window.location.origin}${API_BASE}/scans/mein-scan/progress"`,
    },
    {
      title: "Scan manuell starten",
      description: "Startet einen Scan manuell",
      method: "POST",
      endpoint: `${API_BASE}/scans/{scan_slug}/trigger`,
      curl: `curl -X POST "${window.location.origin}${API_BASE}/scans/mein-scan/trigger"`,
    },
  ]

  if (!open) return null

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogHeader className="bg-gradient-to-r from-primary-500 to-purple-600 text-white px-6 py-4">
        <DialogTitle className="text-white flex items-center gap-2 min-w-0">
          <BookOpen className="h-5 w-5 flex-shrink-0" />
          <span className="truncate">API-Dokumentation</span>
        </DialogTitle>
      </DialogHeader>

      <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto">
        <div className="space-y-6">
          {/* Einleitung */}
          <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
            <h3 className="font-semibold text-blue-900 mb-2 flex items-center gap-2">
              <ExternalLink className="h-4 w-4" />
              API-Integration für Monitoring-Systeme
            </h3>
            <p className="text-sm text-blue-800 mb-3">
              Diese API ermöglicht es Ihnen, Scan-Ergebnisse in externe Monitoring-Systeme wie Prometheus, Grafana, 
              Nagios oder andere Tools zu integrieren. Alle Endpunkte liefern JSON-Daten und können mit Standard-HTTP-Requests 
              abgerufen werden.
            </p>
            <div className="text-sm text-blue-700 space-y-1">
              <p><strong>Base URL:</strong> <code className="bg-blue-100 px-1.5 py-0.5 rounded">{window.location.origin}{API_BASE}</code></p>
              <p><strong>Content-Type:</strong> <code className="bg-blue-100 px-1.5 py-0.5 rounded">application/json</code></p>
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
                        <span className={`px-2 py-0.5 rounded text-xs font-semibold ${
                          example.method === "GET" 
                            ? "bg-green-100 text-green-700" 
                            : "bg-blue-100 text-blue-700"
                        }`}>
                          {example.method}
                        </span>
                        <h4 className="font-semibold text-slate-900 dark:text-slate-100">{example.title}</h4>
                      </div>
                      <p className="text-sm text-slate-600 dark:text-slate-400 mt-1">{example.description}</p>
                      <code className="text-xs text-slate-700 mt-2 block bg-white dark:bg-slate-700 px-2 py-1 rounded border border-slate-200 dark:border-slate-700">
                        {example.endpoint}
                      </code>
                    </div>
                  </div>
                </div>
                <div className="p-4 bg-slate-900 text-slate-100">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs text-slate-400">cURL-Beispiel:</span>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => copyToClipboard(example.curl, index)}
                      className="h-7 px-2 text-xs text-slate-300 hover:text-white hover:bg-slate-800"
                    >
                      {copiedIndex === index ? (
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
            <div className="space-y-3 text-sm text-slate-700">
              <div>
                <strong className="text-slate-900 dark:text-slate-100">Prometheus Exporter:</strong>
                <p className="mt-1">
                  Erstellen Sie einen Prometheus Exporter, der regelmäßig <code className="bg-white dark:bg-slate-700 px-1.5 py-0.5 rounded border">{"/api/scans/{scan_slug}/results"}</code> abruft 
                  und die Daten als Metriken bereitstellt.
                </p>
              </div>
              <div>
                <strong className="text-slate-900 dark:text-slate-100">Grafana Dashboard:</strong>
                <p className="mt-1">
                  Verwenden Sie die JSON-API-Endpunkte als Datenquelle in Grafana und visualisieren Sie 
                  die Scan-Ergebnisse in Echtzeit.
                </p>
              </div>
              <div>
                <strong className="text-slate-900 dark:text-slate-100">Webhook-Integration:</strong>
                <p className="mt-1">
                  Richten Sie einen Cron-Job oder Webhook ein, der regelmäßig die API-Endpunkte abruft 
                  und die Daten an Ihr Monitoring-System weiterleitet.
                </p>
              </div>
            </div>
          </div>

          {/* Response-Beispiel */}
          <div className="bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg p-4">
            <h3 className="font-semibold text-slate-900 dark:text-slate-100 mb-2">📄 Response-Format</h3>
            <p className="text-sm text-slate-600 dark:text-slate-400 mb-3">
              Alle Endpunkte liefern JSON-Daten. Beispiel für <code className="bg-white dark:bg-slate-700 px-1.5 py-0.5 rounded border">{"/scans/{scan_slug}/results"}</code>:
            </p>
            <pre className="text-xs bg-slate-900 text-slate-100 p-3 rounded overflow-x-auto">
              <code>{`{
  "scan_slug": "mein-scan",
  "scan_name": "mein_scan",
  "status": "completed",
  "timestamp": "2024-01-15T10:30:00Z",
  "results": [
    {
      "folder_name": "/volume1/data",
      "success": true,
      "total_size": {
        "bytes": 1073741824,
        "formatted": "1.0 GB"
      },
      "num_file": 1000,
      "num_dir": 50
    }
  ]
}`}</code>
            </pre>
          </div>
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
