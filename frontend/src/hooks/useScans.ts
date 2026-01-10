import { useState, useEffect, useRef, useCallback } from "react"
import { fetchScans } from "@/lib/api"
import type { ScanStatus } from "@/types/api"

export function useScans(autoRefresh: boolean = true, baseInterval: number = 5000) {
  const [scans, setScans] = useState<ScanStatus[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<Error | null>(null)
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null)
  const isRefreshingRef = useRef(false)
  const isInitialLoadRef = useRef(true)

  const loadScans = useCallback(async (silent: boolean = false) => {
    // Prevent overlapping requests
    if (isRefreshingRef.current) {
      return
    }

    try {
      isRefreshingRef.current = true
      
      // Only show loading state on initial load or manual refresh
      if (!silent && isInitialLoadRef.current) {
        setLoading(true)
      }
      
      setError(null)
      const data = await fetchScans()
      setScans(data.scans)
      setLastUpdated(new Date())
    } catch (err) {
      // Only show error on initial load or manual refresh
      if (!silent) {
        setError(err instanceof Error ? err : new Error("Unknown error"))
      }
    } finally {
      if (!silent && isInitialLoadRef.current) {
        setLoading(false)
        isInitialLoadRef.current = false
      }
      isRefreshingRef.current = false
    }
  }, [])

  // Initial load
  useEffect(() => {
    loadScans(false)
  }, [loadScans])

  // Auto-refresh with dynamic interval based on running scans
  useEffect(() => {
    if (!autoRefresh) return

    // Calculate current interval based on running scans
    const hasRunningScans = scans.some(scan => scan.status === "running")
    // Wenn Jobs laufen: öfter pollen (1.5 Sekunden), sonst seltener (5 Sekunden)
    const currentInterval = hasRunningScans ? 1500 : baseInterval

    const intervalId = setInterval(() => {
      // Only refresh if not currently loading
      if (!isRefreshingRef.current) {
        // Silent refresh - no loading state, no error display
        loadScans(true)
      }
    }, currentInterval)

    return () => clearInterval(intervalId)
  }, [autoRefresh, baseInterval, loadScans, scans])

  // Manual refetch always shows loading
  const refetch = useCallback(() => {
    isInitialLoadRef.current = false
    loadScans(false)
  }, [loadScans])

  return {
    scans,
    loading,
    error,
    lastUpdated,
    refetch,
  }
}
