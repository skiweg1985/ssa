import { useState, FormEvent } from "react"
import { HardDrive, Lock, User, AlertCircle, KeyRound } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"

/** Muss zu MIN_ADMIN_PASSWORD_LENGTH in app/models/admin.py passen */
const MIN_PASSWORD_LENGTH = 8

interface SetupScreenProps {
  onSetup: (username: string, password: string, setupToken?: string) => Promise<void>
  defaultUsername: string
  tokenRequired: boolean
}

/**
 * Ersteinrichtung: legt beim ersten Start das Admin-Konto an.
 *
 * Aufbau bewusst identisch zum LoginScreen - es ist derselbe Moment im
 * Ablauf, nur einmalig. Die Prüfungen hier sind reine Bequemlichkeit; die
 * verbindliche Validierung macht der Server.
 */
export function SetupScreen({ onSetup, defaultUsername, tokenRequired }: SetupScreenProps) {
  const [username, setUsername] = useState(defaultUsername)
  const [password, setPassword] = useState("")
  const [passwordRepeat, setPasswordRepeat] = useState("")
  const [setupToken, setSetupToken] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const tooShort = password.length > 0 && password.length < MIN_PASSWORD_LENGTH
  const mismatch = passwordRepeat.length > 0 && password !== passwordRepeat
  const canSubmit =
    username.trim().length > 0 &&
    password.length >= MIN_PASSWORD_LENGTH &&
    password === passwordRepeat &&
    (!tokenRequired || setupToken.length > 0)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (loading || !canSubmit) return
    setError(null)
    setLoading(true)
    try {
      await onSetup(username.trim(), password, tokenRequired ? setupToken : undefined)
    } catch (err) {
      setError(
        err instanceof Error && err.message && !err.message.startsWith("HTTP error")
          ? err.message
          : "Einrichtung fehlgeschlagen"
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
                Ersteinrichtung
              </p>
            </div>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          <p className="text-sm text-slate-600 dark:text-slate-400">
            Lege das Konto fest, mit dem du dich künftig anmeldest. Empfohlen sind
            mindestens 12 Zeichen.
          </p>

          <div>
            <label
              htmlFor="setup-username"
              className="text-sm font-semibold text-slate-700 dark:text-slate-300 mb-2 block"
            >
              Benutzername
            </label>
            <div className="relative">
              <User className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
              <Input
                id="setup-username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="username"
                className="pl-9"
              />
            </div>
          </div>

          <div>
            <label
              htmlFor="setup-password"
              className="text-sm font-semibold text-slate-700 dark:text-slate-300 mb-2 block"
            >
              Passwort
            </label>
            <div className="relative">
              <Lock className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
              <Input
                id="setup-password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="new-password"
                autoFocus
                className="pl-9"
              />
            </div>
            {tooShort && (
              <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">
                Mindestens {MIN_PASSWORD_LENGTH} Zeichen.
              </p>
            )}
          </div>

          <div>
            <label
              htmlFor="setup-password-repeat"
              className="text-sm font-semibold text-slate-700 dark:text-slate-300 mb-2 block"
            >
              Passwort wiederholen
            </label>
            <div className="relative">
              <Lock className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
              <Input
                id="setup-password-repeat"
                type="password"
                value={passwordRepeat}
                onChange={(e) => setPasswordRepeat(e.target.value)}
                autoComplete="new-password"
                className="pl-9"
              />
            </div>
            {mismatch && (
              <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">
                Die Passwörter stimmen nicht überein.
              </p>
            )}
          </div>

          {tokenRequired && (
            <div>
              <label
                htmlFor="setup-token"
                className="text-sm font-semibold text-slate-700 dark:text-slate-300 mb-2 block"
              >
                Setup-Token
              </label>
              <div className="relative">
                <KeyRound className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
                <Input
                  id="setup-token"
                  type="password"
                  value={setupToken}
                  onChange={(e) => setSetupToken(e.target.value)}
                  autoComplete="off"
                  className="pl-9"
                />
              </div>
              <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">
                Der Server verlangt SSA_SETUP_TOKEN aus seiner Umgebung.
              </p>
            </div>
          )}

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
            disabled={!canSubmit}
          >
            Konto anlegen
          </Button>
        </form>
      </div>
    </div>
  )
}
