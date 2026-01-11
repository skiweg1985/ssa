import { useState, useEffect } from "react"

type ViewMode = "list" | "grid"

const VIEW_MODE_STORAGE_KEY = "syno-space-analyzer-view-mode"

export function useViewMode() {
  const [viewMode, setViewMode] = useState<ViewMode>(() => {
    // Load from localStorage or default to list
    if (typeof window !== "undefined") {
      const stored = localStorage.getItem(VIEW_MODE_STORAGE_KEY) as ViewMode | null
      if (stored === "list" || stored === "grid") {
        return stored
      }
    }
    return "list"
  })

  useEffect(() => {
    // Save to localStorage whenever viewMode changes
    localStorage.setItem(VIEW_MODE_STORAGE_KEY, viewMode)
  }, [viewMode])

  return { viewMode, setViewMode }
}
