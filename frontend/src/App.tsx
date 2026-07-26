import { useState } from "react"
import { Loader2 } from "lucide-react"
import { ToastProvider, useToast } from "@/components/ui/toast"
import { ConfirmDialog } from "@/components/ui/confirm-dialog"
import { Topbar } from "@/components/layout/Topbar"
import { CommandPalette } from "@/components/layout/CommandPalette"
import { ScanTable } from "@/components/table/ScanTable"
import { ResultsModal } from "@/components/modals/ResultsModal"
import { HistoryModal } from "@/components/modals/HistoryModal"
import { DetailModal } from "@/components/modals/DetailModal"
import { StorageModal } from "@/components/modals/StorageModal"
import { ApiInfoModal } from "@/components/modals/ApiInfoModal"
import { ScanApiModal } from "@/components/modals/ScanApiModal"
import { JobEditorModal } from "@/components/modals/JobEditorModal"
import { NasConnectionsModal } from "@/components/modals/NasConnectionsModal"
import { ApiTokensModal } from "@/components/modals/ApiTokensModal"
import { LoginScreen } from "@/components/auth/LoginScreen"
import { useScans } from "@/hooks/useScans"
import { useAuth } from "@/hooks/useAuth"
import { cancelScan, triggerScan, reloadConfig, deleteScanJob } from "@/lib/api"
import type { ScanStatus } from "@/types/api"

function AppContent({ onLogout }: { onLogout: () => void }) {
  const { scans, loading, error, lastUpdated, refetch } = useScans(true, 5000)
  const { showToast } = useToast()

  const [searchQuery, setSearchQuery] = useState("")
  const [commandPaletteOpen, setCommandPaletteOpen] = useState(false)
  const [resultsModalOpen, setResultsModalOpen] = useState(false)
  const [historyModalOpen, setHistoryModalOpen] = useState(false)
  const [detailModalOpen, setDetailModalOpen] = useState(false)
  const [storageModalOpen, setStorageModalOpen] = useState(false)
  const [apiInfoModalOpen, setApiInfoModalOpen] = useState(false)
  const [scanApiModalOpen, setScanApiModalOpen] = useState(false)
  const [jobEditorOpen, setJobEditorOpen] = useState(false)
  const [nasConnectionsOpen, setNasConnectionsOpen] = useState(false)
  const [apiTokensOpen, setApiTokensOpen] = useState(false)
  const [editingJob, setEditingJob] = useState<ScanStatus | null>(null)
  const [selectedScanName, setSelectedScanName] = useState<string | null>(null)
  const [selectedScan, setSelectedScan] = useState<ScanStatus | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<ScanStatus | null>(null)
  const [cancelTarget, setCancelTarget] = useState<ScanStatus | null>(null)

  /* Stiller Erfolg.
     Ein Toast „Erfolg — Scan wurde gestartet", während die Zeile daneben sichtbar auf
     „läuft" springt, sagt nichts, was nicht schon dasteht. Gemeldet wird nur noch,
     was fehlschlägt — oder was man sonst nirgends sehen würde. */
  const handleRun = async (scanName: string) => {
    try {
      await triggerScan(scanName)
      setTimeout(() => refetch(), 1000)
    } catch (err) {
      showToast("Start fehlgeschlagen", err instanceof Error ? err.message : "Unbekannter Fehler", "error")
    }
  }

  const handleCancel = (scan: ScanStatus) => {
    setCancelTarget(scan)
  }

  const confirmCancel = async () => {
    if (!cancelTarget) return
    const scan = cancelTarget
    setCancelTarget(null)
    try {
      const result = await cancelScan(scan.scan_slug)
      if (result.cancelling) {
        // Der Abbruch ist kooperativ - der Lauf endet erst beim nächsten
        // Prüfpunkt, deshalb eine Rückmeldung statt stiller Erwartung.
        showToast("Abbruch angefordert", result.message, "info")
      } else {
        showToast("Kein laufender Scan", result.message, "info")
      }
      setTimeout(() => refetch(), 1500)
    } catch (err) {
      showToast(
        "Abbruch fehlgeschlagen",
        err instanceof Error ? err.message : "Unbekannter Fehler",
        "error"
      )
    }
  }

  const handleReloadConfig = async () => {
    try {
      await reloadConfig()
      // Diese Aktion hat keine sichtbare Wirkung in der Tabelle — sie bleibt gemeldet.
      showToast("Scheduler synchronisiert", "Zeitpläne mit der Datenbank abgeglichen.", "info")
      setTimeout(() => refetch(), 1000)
    } catch (err) {
      showToast("Neuladen fehlgeschlagen", err instanceof Error ? err.message : "Unbekannter Fehler", "error")
    }
  }

  const handleShowResults = (scanName: string) => {
    setSelectedScanName(scanName)
    setResultsModalOpen(true)
  }

  const handleShowHistory = (scanName: string) => {
    setSelectedScanName(scanName)
    setHistoryModalOpen(true)
  }

  const handleShowDetail = (scan: ScanStatus) => {
    setSelectedScan(scan)
    setDetailModalOpen(true)
  }

  const handleShowApiInfo = (scan: ScanStatus) => {
    setSelectedScan(scan)
    setScanApiModalOpen(true)
  }

  const handleNewScan = () => {
    setEditingJob(null)
    setJobEditorOpen(true)
  }

  const handleEditJob = (scan: ScanStatus) => {
    setEditingJob(scan)
    setJobEditorOpen(true)
  }

  /* Löschen nimmt den kompletten Verlauf mit und ist nicht rückholbar — hier ist ein
     Dialog richtig, aber der native confirm() war es nicht: ungestylt, und „OK" stand
     für „Job UND Verlauf löschen". Jetzt muss der Name getippt werden. */
  const handleDeleteJob = (scan: ScanStatus) => {
    setDeleteTarget(scan)
  }

  const confirmDeleteJob = async () => {
    if (!deleteTarget) return
    const scan = deleteTarget
    try {
      await deleteScanJob(scan.scan_slug, true)
      refetch() // die Zeile verschwindet — das ist die Quittung
    } catch (err) {
      showToast("Löschen fehlgeschlagen", err instanceof Error ? err.message : "Unbekannter Fehler", "error")
    }
  }

  const handleCommandPaletteSelect = (scanName: string, action: "results" | "history") => {
    setSelectedScanName(scanName)
    if (action === "results") {
      setResultsModalOpen(true)
    } else {
      setHistoryModalOpen(true)
    }
  }

  return (
    <div className="min-h-[100dvh] bg-slate-50 dark:bg-slate-900 flex flex-col">
      <Topbar
        searchQuery={searchQuery}
        onSearchChange={setSearchQuery}
        onReloadConfig={handleReloadConfig}
        onOpenStorage={() => setStorageModalOpen(true)}
        onOpenCommandPalette={() => setCommandPaletteOpen(true)}
        onOpenApiInfo={() => setApiInfoModalOpen(true)}
        onNewScan={handleNewScan}
        onOpenNasConnections={() => setNasConnectionsOpen(true)}
        onLogout={onLogout}
        isLoading={loading}
        lastUpdated={lastUpdated}
      />

      {/* Main content area with consistent spacing scale (4/6/8/12/16) */}
      <main className="flex-1 mx-auto w-full max-w-screen-xl px-4 sm:px-6 lg:px-8 py-6 sm:py-8 flex flex-col min-h-0">
        {error ? (
          <div className="mb-6 sm:mb-8 rounded-lg border border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-900/20 p-4 sm:p-6 flex-shrink-0">
            <div className="mb-3 flex items-start gap-3">
              <div className="flex-1 min-w-0">
                <h3 className="text-sm sm:text-base font-semibold text-red-900 dark:text-red-300 mb-1">
                  Fehler beim Laden der Scans
                </h3>
                <p className="text-xs sm:text-sm text-red-700 dark:text-red-400 break-words">{error.message}</p>
              </div>
            </div>
            <button
              onClick={refetch}
              className="mt-3 rounded-md bg-red-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-2 transition-colors h-10 min-h-[40px]"
              aria-label="Erneut versuchen"
            >
              Erneut versuchen
            </button>
          </div>
        ) : null}

        {/* ScanTable with flex-1 to fill available space */}
        <div className="flex-1 flex flex-col min-h-0">
          <ScanTable
            scans={scans}
            loading={loading}
            lastUpdated={lastUpdated}
            onRun={handleRun}
            onCancel={handleCancel}
            onShowResults={handleShowResults}
            onShowHistory={handleShowHistory}
            onShowDetail={handleShowDetail}
            onShowApiInfo={handleShowApiInfo}
            onEdit={handleEditJob}
            onDelete={handleDeleteJob}
            searchQuery={searchQuery}
          />
        </div>
      </main>

      <CommandPalette
        open={commandPaletteOpen}
        onOpenChange={setCommandPaletteOpen}
        scans={scans}
        onSelectScan={handleCommandPaletteSelect}
        onNewScan={handleNewScan}
        onOpenNasConnections={() => setNasConnectionsOpen(true)}
        onOpenApiTokens={() => setApiTokensOpen(true)}
        onLogout={onLogout}
      />

      {selectedScanName && (
        <>
          <ResultsModal
            open={resultsModalOpen}
            onOpenChange={setResultsModalOpen}
            scanName={selectedScanName}
          />
          <HistoryModal
            open={historyModalOpen}
            onOpenChange={setHistoryModalOpen}
            scanName={selectedScanName}
          />
        </>
      )}

      <DetailModal
        open={detailModalOpen}
        onOpenChange={setDetailModalOpen}
        scan={selectedScan}
        onTriggerScan={handleRun}
        onShowResults={handleShowResults}
        onShowHistory={handleShowHistory}
      />

      <StorageModal open={storageModalOpen} onOpenChange={setStorageModalOpen} />

      <ApiInfoModal
        open={apiInfoModalOpen}
        onOpenChange={setApiInfoModalOpen}
        onOpenApiTokens={() => setApiTokensOpen(true)}
      />

      <ScanApiModal
        open={scanApiModalOpen}
        onOpenChange={setScanApiModalOpen}
        scan={selectedScan}
      />

      <JobEditorModal
        open={jobEditorOpen}
        onOpenChange={setJobEditorOpen}
        job={editingJob}
        onSaved={refetch}
        onManageConnections={() => setNasConnectionsOpen(true)}
      />

      <NasConnectionsModal
        open={nasConnectionsOpen}
        onOpenChange={setNasConnectionsOpen}
        onChanged={refetch}
      />

      <ApiTokensModal open={apiTokensOpen} onOpenChange={setApiTokensOpen} />

      <ConfirmDialog
        open={deleteTarget !== null}
        onOpenChange={(open) => !open && setDeleteTarget(null)}
        title="Scan-Job löschen"
        description={
          <>
            Der Job <strong>{deleteTarget?.scan_name}</strong> wird aus der Konfiguration
            entfernt und aus dem Zeitplan genommen.
          </>
        }
        consequence="Der komplette Verlauf dieses Jobs wird mitgelöscht. Frühere Scan-Ergebnisse und Größenverläufe sind danach nicht wiederherstellbar."
        requireTyping={deleteTarget?.scan_name}
        confirmLabel="Job und Verlauf löschen"
        onConfirm={confirmDeleteJob}
      />

      <ConfirmDialog
        open={cancelTarget !== null}
        onOpenChange={(open) => !open && setCancelTarget(null)}
        title="Laufenden Scan abbrechen"
        description={
          <>
            Der laufende Scan von <strong>{cancelTarget?.scan_name}</strong> wird
            beendet. Bereits gemessene Ordner bleiben erhalten, der Lauf zählt
            aber nicht als erfolgreich.
          </>
        }
        consequence="Der Abbruch wirkt nicht sofort: der Scan beendet sich beim nächsten Prüfpunkt, in der Regel innerhalb weniger Sekunden."
        // Nicht beide Knöpfe "abbrechen" nennen - hier hieße das einmal
        // "Lauf beenden" und einmal "Dialog schließen".
        confirmLabel="Lauf beenden"
        cancelLabel="Weiterlaufen lassen"
        onConfirm={confirmCancel}
      />
    </div>
  )
}

function AuthGate() {
  const { status, login, logout } = useAuth()

  if (status === "checking") {
    return (
      <div className="min-h-[100dvh] bg-slate-50 dark:bg-slate-900 flex items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-primary-500" aria-label="Wird geladen" />
      </div>
    )
  }

  if (status === "unauthenticated") {
    return <LoginScreen onLogin={login} />
  }

  return <AppContent onLogout={logout} />
}

export default function App() {
  return (
    <ToastProvider>
      <AuthGate />
    </ToastProvider>
  )
}
