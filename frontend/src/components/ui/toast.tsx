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
      <div className="fixed top-4 right-4 z-50 flex flex-col gap-2">
        {toasts.map((toast) => (
          <ToastItem key={toast.id} toast={toast} onRemove={removeToast} />
        ))}
      </div>
    </ToastContext.Provider>
  )
}

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
  const typeStyles = {
    success: "bg-green-50 dark:bg-green-900/90 border-green-200 dark:border-green-700 text-green-800 dark:text-green-200",
    error: "bg-red-50 dark:bg-red-900/90 border-red-200 dark:border-red-700 text-red-800 dark:text-red-200",
    warning: "bg-yellow-50 dark:bg-yellow-900/90 border-yellow-200 dark:border-yellow-700 text-yellow-800 dark:text-yellow-200",
    info: "bg-blue-50 dark:bg-blue-900/90 border-blue-200 dark:border-blue-700 text-blue-800 dark:text-blue-200",
  }

  return (
    <div
      className={cn(
        "bg-white dark:bg-slate-800 border-l-4 rounded-lg shadow-lg p-4 min-w-[300px] animate-in slide-in-from-right backdrop-blur-sm",
        typeStyles[toast.type]
      )}
    >
      <div className="flex justify-between items-start mb-2">
        <span className="font-semibold">{toast.title}</span>
        <button
          className="text-slate-400 dark:text-slate-500 hover:text-slate-600 dark:hover:text-slate-300 focus:outline-none focus:ring-2 focus:ring-primary-500 rounded"
          onClick={() => onRemove(toast.id)}
          aria-label="Toast schließen"
        >
          <X className="h-4 w-4" />
        </button>
      </div>
      <div className="text-sm text-slate-700 dark:text-slate-300">{toast.message}</div>
    </div>
  )
}
