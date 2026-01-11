import { useState, useEffect, useRef } from "react"
import { fetchScanProgress } from "@/lib/api"
import type { ScanProgress } from "@/types/api"

export function useScanProgress(scanName: string, isRunning: boolean, interval: number = 1000) {
  const [progress, setProgress] = useState<ScanProgress | null>(null)
  const [error, setError] = useState<Error | null>(null)
  const isPollingRef = useRef(false)
  const completedProgressRef = useRef<ScanProgress | null>(null)
  const previousScanNameRef = useRef<string>("")

  // Reset progress when scan name changes
  useEffect(() => {
    if (scanName && scanName !== previousScanNameRef.current) {
      // Scan name changed - reset all progress
      completedProgressRef.current = null
      setProgress(null)
      setError(null)
      previousScanNameRef.current = scanName
    } else if (!scanName) {
      // No scan name - clear everything
      completedProgressRef.current = null
      setProgress(null)
      setError(null)
      previousScanNameRef.current = ""
    }
  }, [scanName])

  useEffect(() => {
    // If scan name changes, clear completed progress ref
    if (!scanName) {
      return
    }
    
    if (!isRunning) {
      // If we have a completed progress for this scan, keep it for UI to show final state
      const completed = completedProgressRef.current
      if (completed && (completed.scan_slug === scanName || completed.scan_name === scanName)) {
        setProgress(completed)
        return
      }
      // Clear progress when scan is not running and we don't have completed progress for this scan
      // This prevents stale data and avoids unnecessary API calls
      setProgress(null)
      setError(null)
      return
    }

    let intervalId: number | null = null
    isPollingRef.current = true

    const loadProgress = async () => {
      if (!isPollingRef.current) return

      try {
        const data = await fetchScanProgress(scanName)
        // Validate data structure
        if (data && data.progress) {
          setProgress(data)
          setError(null)

          // Stop polling if scan is finished or completed, but keep the progress state
          if (data.progress.finished || data.status === "completed") {
            isPollingRef.current = false
            if (intervalId) {
              clearInterval(intervalId)
            }
            // Keep progress state for completed scans so UI can show final state
            completedProgressRef.current = data
          }
        } else {
          // Invalid data structure, stop polling
          isPollingRef.current = false
          if (intervalId) {
            clearInterval(intervalId)
          }
        }
      } catch (err) {
        // 404 means scan is not running or finished - this is normal, don't show error
        if (err instanceof Error) {
          const is404 = err.message.includes("404") || 
                       err.message.includes("status: 404") ||
                       (err as any).status === 404
          if (!is404) {
            setError(err)
          } else {
            // 404 is expected when scan is not running, clear any previous errors
            setError(null)
          }
        }
        // Stop polling on error (including 404)
        isPollingRef.current = false
        if (intervalId) {
          clearInterval(intervalId)
        }
      }
    }

    // Initial load
    loadProgress()

    // Polling interval
    intervalId = setInterval(() => {
      if (isPollingRef.current) {
        loadProgress()
      }
    }, interval)

    return () => {
      isPollingRef.current = false
      if (intervalId) {
        clearInterval(intervalId)
      }
    }
  }, [scanName, isRunning, interval])
  
  // Return completed progress if available, even if not currently running
  return { progress: progress || completedProgressRef.current, error }
}
