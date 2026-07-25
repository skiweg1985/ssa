import { useCallback, useEffect, useRef, useState } from "react"

/**
 * Kopiert Text in die Zwischenablage und merkt sich, welcher Block zuletzt
 * kopiert wurde — für die "Kopiert!"-Quittung am jeweiligen Button.
 *
 * Schlüssel statt Index, damit gefilterte Listen (z.B. pro Tab) nicht
 * versehentlich die Quittung eines anderen Blocks anzeigen.
 */
interface UseCopyToClipboardOptions {
  /** Wie lange die "Kopiert!"-Quittung stehen bleibt */
  resetAfterMs?: number
  /**
   * Wird aufgerufen, wenn das Kopieren fehlschlägt. Ohne Callback landet der
   * Fehler nur in der Konsole — für unkritische Blöcke wie cURL-Befehle
   * ausreichend, die der Nutzer auch markieren kann.
   */
  onError?: (error: unknown) => void
}

export function useCopyToClipboard({
  resetAfterMs = 2000,
  onError,
}: UseCopyToClipboardOptions = {}) {
  const [copiedKey, setCopiedKey] = useState<string | null>(null)
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Timer aufräumen, damit ein setState nach dem Unmount ausbleibt
  useEffect(() => {
    return () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current)
    }
  }, [])

  const markCopied = useCallback(
    (key: string) => {
      setCopiedKey(key)
      if (timeoutRef.current) clearTimeout(timeoutRef.current)
      timeoutRef.current = setTimeout(() => setCopiedKey(null), resetAfterMs)
    },
    [resetAfterMs]
  )

  const copy = useCallback(
    async (text: string, key: string) => {
      try {
        // Moderne Clipboard API (benötigt HTTPS oder localhost)
        if (navigator.clipboard && navigator.clipboard.writeText) {
          await navigator.clipboard.writeText(text)
          markCopied(key)
          return
        }

        // Fallback für HTTP-Zugriff ohne localhost: execCommand
        const textArea = document.createElement("textarea")
        textArea.value = text
        textArea.style.position = "fixed"
        textArea.style.left = "-999999px"
        textArea.style.top = "-999999px"
        document.body.appendChild(textArea)
        textArea.focus()
        textArea.select()

        const successful = document.execCommand("copy")
        document.body.removeChild(textArea)

        if (successful) {
          markCopied(key)
        } else {
          console.error("Kopieren fehlgeschlagen")
          onError?.(new Error("Kopieren fehlgeschlagen"))
        }
      } catch (err) {
        console.error("Fehler beim Kopieren:", err)
        onError?.(err)
      }
    },
    [markCopied, onError]
  )

  return { copiedKey, copy }
}
