import { useState, FormEvent } from "react"
import { HardDrive, Lock, User, AlertCircle } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"

interface LoginScreenProps {
  onLogin: (username: string, password: string) => Promise<void>
}

export function LoginScreen({ onLogin }: LoginScreenProps) {
  const [username, setUsername] = useState("admin")
  const [password, setPassword] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (loading) return
    setError(null)
    setLoading(true)
    try {
      await onLogin(username, password)
    } catch (err) {
      setError(
        err instanceof Error && err.message && !err.message.startsWith("HTTP error")
          ? err.message
          : "Anmeldung fehlgeschlagen"
      )
    } finally {
      setLoading(false)
    }
  }

  return (
    <div
      className="min-h-[100dvh] bg-slate-50 dark:bg-slate-900 flex items-center justify-center px-4"
      style={{
        paddingTop: "max(1rem, env(safe-area-inset-top))",
        paddingBottom: "max(1rem, env(safe-area-inset-bottom))",
      }}
    >
      <div className="w-full max-w-sm rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 overflow-hidden">
        {/* Kopf in der Systemstimme: Inset-Fläche, Hairline nach unten, EIN Akzent am Icon.
            Kein Farbverlauf — der trug hier keine Information, nur Aufmerksamkeit. */}
        <div className="border-b border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 px-6 py-5">
          <div className="flex items-center gap-3">
            <div className="rounded-md border border-primary-200 dark:border-primary-700 bg-primary-50 dark:bg-primary-900/30 p-2 text-primary-600 dark:text-primary-400">
              <HardDrive className="h-5 w-5" aria-hidden="true" />
            </div>
            <div className="min-w-0">
              <h1 className="font-display text-base font-semibold leading-tight tracking-display truncate text-slate-900 dark:text-slate-50">
                Synology Space Analyzer
              </h1>
              <p className="label-mono mt-1 text-slate-500 dark:text-slate-400">
                Anmeldung erforderlich
              </p>
            </div>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          <div>
            <label
              htmlFor="login-username"
              className="text-sm font-semibold text-slate-700 dark:text-slate-300 mb-2 block"
            >
              Benutzername
            </label>
            <div className="relative">
              <User className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
              <Input
                id="login-username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="username"
                className="pl-9"
              />
            </div>
          </div>

          <div>
            <label
              htmlFor="login-password"
              className="text-sm font-semibold text-slate-700 dark:text-slate-300 mb-2 block"
            >
              Passwort
            </label>
            <div className="relative">
              <Lock className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
              <Input
                id="login-password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                autoFocus
                className="pl-9"
              />
            </div>
          </div>

          {error && (
            <div className="flex items-start gap-2 rounded-md bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 px-3 py-2 text-sm text-red-700 dark:text-red-300">
              <AlertCircle className="h-4 w-4 mt-0.5 flex-shrink-0" />
              <span>{error}</span>
            </div>
          )}

          <Button
            type="submit"
            variant="primary"
            size="lg"
            className="w-full"
            isLoading={loading}
            disabled={!password}
          >
            Anmelden
          </Button>
        </form>
      </div>
    </div>
  )
}
