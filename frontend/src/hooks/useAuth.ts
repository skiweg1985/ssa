import { useState, useEffect, useCallback } from "react"
import {
  login as apiLogin,
  fetchMe,
  fetchSetupStatus,
  getToken,
  setToken,
  clearToken,
  setupAdmin,
} from "@/lib/api"
import type { SetupStatus } from "@/types/api"

export type AuthStatus = "checking" | "authenticated" | "unauthenticated" | "setup"

/**
 * Auth-Hook: verwaltet Token (localStorage) und Login-Status.
 *
 * Boot-Verhalten: Ist ein Token gespeichert, wird es per /auth/me validiert -
 * wer eingeloggt ist, kostet also keinen zusätzlichen Aufruf. Erst ohne
 * (gültiges) Token wird gefragt, ob die Ersteinrichtung noch offen ist.
 *
 * Bei jeder 401-Antwort im API-Layer wird global "ssa:unauthorized" gefeuert
 * und die Session hier beendet.
 */
export function useAuth() {
  // Startet immer in "checking": ohne Token muss erst der Setup-Status
  // geklärt werden, bevor Login- oder Setup-Bildschirm feststehen.
  const [status, setStatus] = useState<AuthStatus>("checking")
  const [username, setUsername] = useState<string | null>(null)
  const [setupStatus, setSetupStatus] = useState<SetupStatus | null>(null)
  // Überlebt den Logout und füllt danach das Login-Formular vor. Nach einem
  // Reload übernimmt das der Setup-Status, der den gespeicherten Namen kennt.
  const [lastUsername, setLastUsername] = useState<string | null>(null)

  // Token beim Start validieren, sonst Ersteinrichtung prüfen
  useEffect(() => {
    let cancelled = false

    async function boot() {
      if (getToken()) {
        try {
          const me = await fetchMe()
          if (cancelled) return
          setUsername(me.username)
          setLastUsername(me.username)
          setStatus("authenticated")
          return
        } catch {
          if (cancelled) return
          clearToken()
        }
      }

      try {
        const setup = await fetchSetupStatus()
        if (cancelled) return
        setSetupStatus(setup)
        setStatus(setup.setup_required ? "setup" : "unauthenticated")
      } catch {
        // Im Zweifel den Login zeigen: ein zu Unrecht angebotener
        // Setup-Bildschirm wäre der deutlich schlechtere Fehlerfall.
        if (cancelled) return
        setStatus("unauthenticated")
      }
    }

    boot()

    return () => {
      cancelled = true
    }
  }, [])

  // Globales Logout bei 401 (vom API-Layer gefeuert)
  useEffect(() => {
    const handleUnauthorized = () => {
      setUsername(null)
      setStatus("unauthenticated")
    }
    window.addEventListener("ssa:unauthorized", handleUnauthorized)
    return () => window.removeEventListener("ssa:unauthorized", handleUnauthorized)
  }, [])

  const login = useCallback(async (user: string, password: string) => {
    const response = await apiLogin(user, password)
    setToken(response.token)
    setUsername(response.username)
    setLastUsername(response.username)
    setStatus("authenticated")
  }, [])

  const completeSetup = useCallback(
    async (user: string, password: string, setupToken?: string) => {
      const response = await setupAdmin(user, password, setupToken)
      setToken(response.token)
      setUsername(response.username)
      setLastUsername(response.username)
      setStatus("authenticated")
    },
    []
  )

  const logout = useCallback(() => {
    clearToken()
    setUsername(null)
    setStatus("unauthenticated")
  }, [])

  return { status, username, lastUsername, setupStatus, login, completeSetup, logout }
}
