import { useState, useEffect, useCallback } from "react"
import { login as apiLogin, fetchMe, getToken, setToken, clearToken } from "@/lib/api"

export type AuthStatus = "checking" | "authenticated" | "unauthenticated"

/**
 * Auth-Hook: verwaltet Token (localStorage) und Login-Status.
 *
 * Boot-Verhalten: Ist ein Token gespeichert, wird es per /auth/me validiert.
 * Bei jeder 401-Antwort im API-Layer wird global "ssa:unauthorized" gefeuert
 * und die Session hier beendet.
 */
export function useAuth() {
  const [status, setStatus] = useState<AuthStatus>(() =>
    getToken() ? "checking" : "unauthenticated"
  )
  const [username, setUsername] = useState<string | null>(null)

  // Token beim Start validieren
  useEffect(() => {
    let cancelled = false
    if (status !== "checking") return

    fetchMe()
      .then((me) => {
        if (cancelled) return
        setUsername(me.username)
        setStatus("authenticated")
      })
      .catch(() => {
        if (cancelled) return
        clearToken()
        setStatus("unauthenticated")
      })

    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
    setStatus("authenticated")
  }, [])

  const logout = useCallback(() => {
    clearToken()
    setUsername(null)
    setStatus("unauthenticated")
  }, [])

  return { status, username, login, logout }
}
