import * as React from "react"
import { X } from "lucide-react"
import { cn } from "@/lib/cn"

export type ToastType = "success" | "error" | "warning" | "info"

interface Toast {
  id: string
  title: string
  message: string
  type: ToastType
}

interface ToastContextValue {
  toasts: Toast[]
  showToast: (title: string, message: string, type?: ToastType) => void
}

const ToastContext = React.createContext<ToastContextValue | undefined>(undefined)

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = React.useState<Toast[]>([])

  const showToast = React.useCallback(
    (title: string, message: string, type: ToastType = "info") => {
      const id = Math.random().toString(36).substring(7)
      const newToast: Toast = { id, title, message, type }
      setToasts((prev) => [...prev, newToast])

      setTimeout(() => {
        setToasts((prev) => prev.filter((t) => t.id !== id))
      }, 5000)
    },
    []
  )

  const removeToast = (id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
  }

  return (
    <ToastContext.Provider value={{ toasts, showToast }}>
      {children}
      {/* Fest in der Ecke gestapelt: ein neuer Toast schiebt keinen bestehenden
          und verschiebt nichts im Dokument. */}
      <div
        className="fixed top-4 right-4 left-4 sm:left-auto z-toast flex flex-col gap-2 pointer-events-none"
        role="status"
        aria-live="polite"
        aria-atomic="false"
      >
        {toasts.map((toast) => (
          <ToastItem key={toast.id} toast={toast} onRemove={removeToast} />
        ))}
      </div>
    </ToastContext.Provider>
  )
}

// Provider und zugehoeriger Hook gehoeren bewusst in dieselbe Datei.
// Die Regel betrifft nur Fast Refresh im Dev, nicht die Korrektheit.
// eslint-disable-next-line react-refresh/only-export-components
export function useToast() {
  const context = React.useContext(ToastContext)
  if (!context) {
    throw new Error("useToast must be used within ToastProvider")
  }
  return context
}

function ToastItem({
  toast,
  onRemove,
}: {
  toast: Toast
  onRemove: (id: string) => void
}) {
  /* Der Status sitzt in einem kleinen Punkt, nicht in einem 4 px dicken Seitenstreifen.
     Der Streifen war die auffälligste Kartenform der Vorlage — und die eine, die
     jedes generierte Dashboard trägt. */
  const dotStyles = {
    success: "bg-emerald-600 dark:bg-emerald-400",
    error: "bg-red-600 dark:bg-red-400",
    warning: "bg-amber-600 dark:bg-amber-400",
    info: "bg-primary-500 dark:bg-primary-400",
  }

  return (
    <div
      className={cn(
        "pointer-events-auto flex gap-3 rounded-md border border-slate-200 dark:border-slate-700",
        "bg-white dark:bg-slate-800 p-3.5 shadow-lg sm:min-w-[320px] sm:max-w-sm",
        "animate-in slide-in-from-right"
      )}
    >
      <span
        className={cn("mt-1.5 h-2 w-2 flex-shrink-0 rounded-full", dotStyles[toast.type])}
        aria-hidden="true"
      />
      <div className="min-w-0 flex-1">
        <div className="font-display text-sm font-semibold tracking-display text-slate-900 dark:text-slate-50">
          {toast.title}
        </div>
        <div className="mt-0.5 text-sm text-slate-600 dark:text-slate-300 break-words">
          {toast.message}
        </div>
      </div>
      <button
        type="button"
        className="-mr-1 -mt-1 h-7 w-7 flex-shrink-0 rounded-sm flex items-center justify-center text-slate-400 dark:text-slate-500 hover:text-slate-900 dark:hover:text-slate-50 hover:bg-slate-100 dark:hover:bg-slate-700 transition-[color,background-color] duration-instant ease-out focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
        onClick={() => onRemove(toast.id)}
        aria-label="Meldung schließen"
      >
        <X className="h-4 w-4" aria-hidden="true" />
      </button>
    </div>
  )
}
