import { useState, useEffect } from "react"

type Theme = "light" | "dark"

const THEME_STORAGE_KEY = "syno-space-analyzer-theme"

export function useTheme() {
  const [theme, setTheme] = useState<Theme>(() => {
    // Load from localStorage or default to light
    if (typeof window !== "undefined") {
      const stored = localStorage.getItem(THEME_STORAGE_KEY) as Theme | null
      if (stored === "light" || stored === "dark") {
        // Apply theme immediately to prevent flash
        const root = window.document.documentElement
        root.classList.remove("light", "dark")
        root.classList.add(stored)
        return stored
      }
    }
    return "light"
  })

  useEffect(() => {
    const root = window.document.documentElement
    
    // Remove existing theme classes
    root.classList.remove("light", "dark")
    
    // Add current theme class
    root.classList.add(theme)
    
    // Save to localStorage
    localStorage.setItem(THEME_STORAGE_KEY, theme)
  }, [theme])

  const toggleTheme = () => {
    setTheme((prev) => (prev === "light" ? "dark" : "light"))
  }

  return { theme, toggleTheme, setTheme }
}
