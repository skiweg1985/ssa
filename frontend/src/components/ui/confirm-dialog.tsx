import * as React from "react"
import { AlertTriangle } from "lucide-react"
import { Dialog, DialogHeader, DialogTitle, DialogContent, DialogFooter } from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"

/* Bestätigungsdialog · Zustände: default · hover · focus-visible · active · disabled · loading
 *
 * Ersetzt window.confirm(). Der native Dialog war ungestylt, blockierend, nicht
 * fokusverwaltet und ließ sich nicht beschriften — bei „Job UND Verlauf löschen"
 * standen OK und Abbrechen für zwei Dinge, die man nicht verwechseln darf.
 *
 * Zwei Stufen:
 *   confirmLabel allein            → ein bewusster Klick.
 *   zusätzlich requireTyping="Name" → der Name muss getippt werden. Für alles,
 *                                     was Daten unwiederbringlich mitnimmt.
 */

export interface ConfirmDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  /** Was passiert, in einem Satz. Keine Frage — die Frage ist der Knopf. */
  description: React.ReactNode
  /** Was verloren geht. Erscheint als Warnblock. */
  consequence?: React.ReactNode
  confirmLabel: string
  cancelLabel?: string
  /** Ist der Wert gesetzt, muss er exakt getippt werden, bevor bestätigt werden kann. */
  requireTyping?: string
  onConfirm: () => void | Promise<void>
}

export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  consequence,
  confirmLabel,
  cancelLabel = "Abbrechen",
  requireTyping,
  onConfirm,
}: ConfirmDialogProps) {
  const [typed, setTyped] = React.useState("")
  const [busy, setBusy] = React.useState(false)

  React.useEffect(() => {
    if (open) {
      setTyped("")
      setBusy(false)
    }
  }, [open])

  const armed = !requireTyping || typed.trim() === requireTyping

  async function handleConfirm() {
    if (!armed || busy) return
    setBusy(true)
    try {
      await onConfirm()
      onOpenChange(false)
    } finally {
      setBusy(false)
    }
  }

  if (!open) return null

  return (
    <Dialog open={open} onOpenChange={onOpenChange} maxWidth="md">
      <DialogHeader>
        <DialogTitle className="flex items-center gap-2">
          <AlertTriangle className="h-4 w-4 flex-shrink-0 text-amber-600 dark:text-amber-400" aria-hidden="true" />
          <span className="truncate">{title}</span>
        </DialogTitle>
      </DialogHeader>

      <DialogContent>
        <div className="space-y-4">
          <p className="text-sm text-slate-600 dark:text-slate-300">{description}</p>

          {consequence && (
            <div className="rounded-md border border-amber-200 dark:border-amber-700 bg-amber-50 dark:bg-amber-900/30 px-3 py-2.5 text-sm text-amber-800 dark:text-amber-200">
              {consequence}
            </div>
          )}

          {requireTyping && (
            <div>
              <label
                htmlFor="confirm-typed-name"
                className="mb-2 block text-sm text-slate-600 dark:text-slate-300"
              >
                Zum Bestätigen{" "}
                <code className="rounded-sm bg-slate-100 dark:bg-slate-700 px-1.5 py-0.5 font-mono text-xs text-slate-900 dark:text-slate-50">
                  {requireTyping}
                </code>{" "}
                eingeben:
              </label>
              <Input
                id="confirm-typed-name"
                value={typed}
                onChange={(e) => setTyped(e.target.value)}
                autoComplete="off"
                autoFocus
                spellCheck={false}
                className="font-mono"
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault()
                    void handleConfirm()
                  }
                }}
              />
            </div>
          )}
        </div>
      </DialogContent>

      <DialogFooter>
        <Button variant="ghost" onClick={() => onOpenChange(false)} disabled={busy}>
          {cancelLabel}
        </Button>
        <Button variant="destructive" onClick={handleConfirm} disabled={!armed} isLoading={busy}>
          {confirmLabel}
        </Button>
      </DialogFooter>
    </Dialog>
  )
}
