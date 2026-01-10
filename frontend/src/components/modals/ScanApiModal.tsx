import {
  Dialog,
  DialogHeader,
  DialogTitle,
  DialogContent,
  DialogFooter,
  DialogClose,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Code, Copy, CheckCircle2, ExternalLink, Link2 } from "lucide-react"
import { useState } from "react"
import type { ScanStatus } from "@/types/api"

interface ScanApiModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  scan: ScanStatus | null
}

const API_BASE = "/api"

export function ScanApiModal({ open, onOpenChange, scan }: ScanApiModalProps) {
  const [copiedIndex, setCopiedIndex] = useState<number | null>(null)

  const copyToClipboard = (text: string, index: number) => {
    navigator.clipboard.writeText(text)
    setCopiedIndex(index)
    setTimeout(() => setCopiedIndex(null), 2000)
  }

  if (!open || !scan) return null

  const baseUrl = window.location.origin
  const scanName = scan.scan_name

  const apiEndpoints = [
    {
      title: "Scan-Ergebnisse",
      description: "Neueste Ergebnisse dieses Scans abrufen",
      method: "GET",
      endpoint: `${API_BASE}/scans/${scanName}/results`,
      url: `${baseUrl}${API_BASE}/scans/${scanName}/results`,
      curl: `curl -X GET "${baseUrl}${API_BASE}/scans/${scanName}/results"`,
    },
    {
      title: "Scan-Historie",
      description: "Komplette Historie aller Ergebnisse dieses Scans",
      method: "GET",
      endpoint: `${API_BASE}/scans/${scanName}/history`,
      url: `${baseUrl}${API_BASE}/scans/${scanName}/history`,
      curl: `curl -X GET "${baseUrl}${API_BASE}/scans/${scanName}/history"`,
    },
    {
      title: "Scan-Status",
      description: "Aktuellen Status dieses Scans abrufen",
      method: "GET",
      endpoint: `${API_BASE}/scans/${scanName}/status`,
      url: `${baseUrl}${API_BASE}/scans/${scanName}/status`,
      curl: `curl -X GET "${baseUrl}${API_BASE}/scans/${scanName}/status"`,
    },
    {
      title: "Scan-Progress",
      description: "Fortschritt eines laufenden Scans (nur wenn Scan läuft)",
      method: "GET",
      endpoint: `${API_BASE}/scans/${scanName}/progress`,
      url: `${baseUrl}${API_BASE}/scans/${scanName}/progress`,
      curl: `curl -X GET "${baseUrl}${API_BASE}/scans/${scanName}/progress"`,
    },
    {
      title: "Scan starten",
      description: "Diesen Scan manuell starten",
      method: "POST",
      endpoint: `${API_BASE}/scans/${scanName}/trigger`,
      url: `${baseUrl}${API_BASE}/scans/${scanName}/trigger`,
      curl: `curl -X POST "${baseUrl}${API_BASE}/scans/${scanName}/trigger"`,
    },
  ]

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogHeader className="bg-gradient-to-r from-primary-500 to-purple-600 text-white px-6 py-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Link2 className="h-5 w-5" />
            <DialogTitle className="text-white">API-Informationen: {scanName}</DialogTitle>
          </div>
          <DialogClose className="text-white hover:bg-white/20" />
        </div>
      </DialogHeader>

      <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
        <div className="space-y-6">
          {/* Info-Box */}
          <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
            <h3 className="font-semibold text-blue-900 mb-2 flex items-center gap-2">
              <ExternalLink className="h-4 w-4" />
              Job-spezifische API-Endpunkte
            </h3>
            <p className="text-sm text-blue-800">
              Diese URLs und cURL-Befehle sind spezifisch für den Scan-Job <strong>"{scanName}"</strong>. 
              Verwenden Sie diese Endpunkte, um die Ergebnisse dieses Scans in Ihr Monitoring-System zu integrieren.
            </p>
          </div>

          {/* API-Endpunkte */}
          <div className="space-y-4">
            <h3 className="text-lg font-semibold text-slate-900 flex items-center gap-2">
              <Code className="h-5 w-5" />
              Verfügbare Endpunkte
            </h3>

            {apiEndpoints.map((endpoint, index) => (
              <div
                key={index}
                className="border border-slate-200 rounded-lg overflow-hidden"
              >
                <div className="bg-slate-50 px-4 py-3 border-b border-slate-200">
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <span className={`px-2 py-0.5 rounded text-xs font-semibold ${
                        endpoint.method === "GET" 
                          ? "bg-green-100 text-green-700" 
                          : "bg-blue-100 text-blue-700"
                      }`}>
                        {endpoint.method}
                      </span>
                      <h4 className="font-semibold text-slate-900">{endpoint.title}</h4>
                    </div>
                    <p className="text-sm text-slate-600 mt-1">{endpoint.description}</p>
                    <code className="text-xs text-slate-700 mt-2 block bg-white px-2 py-1 rounded border border-slate-200">
                      {endpoint.endpoint}
                    </code>
                  </div>
                </div>
                </div>
                
                {/* URL */}
                <div className="px-4 py-3 bg-slate-100 border-b border-slate-200">
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-slate-600 font-medium">URL:</span>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => copyToClipboard(endpoint.url, index * 2)}
                      className="h-7 px-2 text-xs"
                    >
                      {copiedIndex === index * 2 ? (
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
                  <code className="text-xs text-slate-700 block mt-1 break-all">
                    {endpoint.url}
                  </code>
                </div>

                {/* cURL */}
                <div className="p-4 bg-slate-900 text-slate-100">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs text-slate-400">cURL-Befehl:</span>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => copyToClipboard(endpoint.curl, index * 2 + 1)}
                      className="h-7 px-2 text-xs text-slate-300 hover:text-white hover:bg-slate-800"
                    >
                      {copiedIndex === index * 2 + 1 ? (
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
                    <code>{endpoint.curl}</code>
                  </pre>
                </div>
              </div>
            ))}
          </div>

          {/* Verwendungsbeispiele */}
          <div className="bg-slate-50 border border-slate-200 rounded-lg p-4">
            <h3 className="font-semibold text-slate-900 mb-3">💡 Verwendungsbeispiele</h3>
            <div className="space-y-3 text-sm text-slate-700">
              <div>
                <strong className="text-slate-900">Monitoring-Script (Bash):</strong>
                <pre className="mt-1 text-xs bg-white p-2 rounded border border-slate-200 overflow-x-auto">
                  <code>{`# Scan-Ergebnisse abrufen
RESULT=$(curl -s "${baseUrl}${API_BASE}/scans/${scanName}/results")
echo "$RESULT" | jq '.results[0].total_size.bytes'`}</code>
                </pre>
              </div>
              <div>
                <strong className="text-slate-900">Python-Integration:</strong>
                <pre className="mt-1 text-xs bg-white p-2 rounded border border-slate-200 overflow-x-auto">
                  <code>{`import requests
response = requests.get("${baseUrl}${API_BASE}/scans/${scanName}/results")
data = response.json()
print(f"Gesamtgröße: {data['results'][0]['total_size']['formatted']}")`}</code>
                </pre>
              </div>
            </div>
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
