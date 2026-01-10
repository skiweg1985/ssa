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
    success: "bg-green-50 border-green-200 text-green-800",
    error: "bg-red-50 border-red-200 text-red-800",
    warning: "bg-yellow-50 border-yellow-200 text-yellow-800",
    info: "bg-blue-50 border-blue-200 text-blue-800",
  }

  return (
    <div
      className={cn(
        "bg-white border-l-4 rounded-lg shadow-lg p-4 min-w-[300px] animate-in slide-in-from-right",
        typeStyles[toast.type]
      )}
    >
      <div className="flex justify-between items-start mb-2">
        <span className="font-semibold">{toast.title}</span>
        <button
          className="text-slate-400 hover:text-slate-600 focus:outline-none focus:ring-2 focus:ring-primary-500 rounded"
          onClick={() => onRemove(toast.id)}
          aria-label="Toast schließen"
        >
          <X className="h-4 w-4" />
        </button>
      </div>
      <div className="text-sm">{toast.message}</div>
    </div>
  )
}
