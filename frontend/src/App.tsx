import { useState } from "react"
import { Loader2 } from "lucide-react"
import { ToastProvider, useToast } from "@/components/ui/toast"
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
import { LoginScreen } from "@/components/auth/LoginScreen"
import { useScans } from "@/hooks/useScans"
import { useAuth } from "@/hooks/useAuth"
import { triggerScan, reloadConfig, deleteScanJob } from "@/lib/api"
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
  const [editingJob, setEditingJob] = useState<ScanStatus | null>(null)
  const [selectedScanName, setSelectedScanName] = useState<string | null>(null)
  const [selectedScan, setSelectedScan] = useState<ScanStatus | null>(null)

  const handleRun = async (scanName: string) => {
    try {
      await triggerScan(scanName)
      showToast("Erfolg", `Scan '${scanName}' wurde gestartet`, "success")
      setTimeout(() => refetch(), 1000)
    } catch (err) {
      showToast("Fehler", `Fehler beim Starten: ${err instanceof Error ? err.message : "Unbekannt"}`, "error")
    }
  }

  const handleReloadConfig = async () => {
    try {
      await reloadConfig()
      showToast("Erfolg", "Scheduler wurde neu synchronisiert", "success")
      setTimeout(() => refetch(), 1000)
    } catch (err) {
      showToast("Fehler", `Fehler beim Neuladen: ${err instanceof Error ? err.message : "Unbekannt"}`, "error")
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

  const handleDeleteJob = async (scan: ScanStatus) => {
    const deleteHistory = confirm(
      `Scan-Job '${scan.scan_name}' löschen?\n\nOK = Job UND Verlauf löschen\nAbbrechen = nichts löschen`
    )
    if (!deleteHistory) return
    try {
      await deleteScanJob(scan.scan_slug, true)
      showToast("Erfolg", `Scan '${scan.scan_name}' wurde gelöscht`, "success")
      refetch()
    } catch (err) {
      showToast("Fehler", `Löschen fehlgeschlagen: ${err instanceof Error ? err.message : "Unbekannt"}`, "error")
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
    <div className="min-h-screen bg-slate-50 dark:bg-slate-900 flex flex-col">
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

      <ApiInfoModal open={apiInfoModalOpen} onOpenChange={setApiInfoModalOpen} />

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
    </div>
  )
}

function AuthGate() {
  const { status, login, logout } = useAuth()

  if (status === "checking") {
    return (
      <div className="min-h-screen bg-slate-50 dark:bg-slate-900 flex items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-primary-500" />
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
