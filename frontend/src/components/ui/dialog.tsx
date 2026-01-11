import * as React from "react"
import { X } from "lucide-react"
import { cn } from "@/lib/cn"

interface DialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  children: React.ReactNode
}

interface DialogContentProps extends React.HTMLAttributes<HTMLDivElement> {
  children: React.ReactNode
}

// Context für Dialog-Funktionen
const DialogContext = React.createContext<{
  onOpenChange: (open: boolean) => void
} | null>(null)

const Dialog = ({ open, onOpenChange, children }: DialogProps) => {
  // Esc-Taste Handler
  React.useEffect(() => {
    if (!open) return

    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onOpenChange(false)
      }
    }

    document.addEventListener("keydown", handleEscape)
    return () => {
      document.removeEventListener("keydown", handleEscape)
    }
  }, [open, onOpenChange])

  React.useEffect(() => {
    if (open) {
      document.body.style.overflow = 'hidden'
    } else {
      document.body.style.overflow = ''
    }
    return () => {
      document.body.style.overflow = ''
    }
  }, [open])

  if (!open) return null

  return (
    <DialogContext.Provider value={{ onOpenChange }}>
      <div
        className="fixed inset-0 z-[1000] flex items-end sm:items-center justify-center p-0 sm:p-4 bg-black/50 animate-in fade-in"
        style={{
          // Für iOS Safari: Berücksichtige safe-area-insets im Overlay
          paddingTop: 'env(safe-area-inset-top)',
          paddingBottom: 'env(safe-area-inset-bottom)',
          paddingLeft: 'env(safe-area-inset-left)',
          paddingRight: 'env(safe-area-inset-right)',
        }}
        onClick={() => onOpenChange(false)}
      >
        <div
          className="relative z-[1000] w-full h-[85vh] sm:h-auto sm:max-h-[90vh] sm:max-w-4xl bg-white dark:bg-slate-900 rounded-t-xl sm:rounded-xl shadow-2xl flex flex-col overflow-hidden animate-in slide-in-from-bottom-4"
          onClick={(e) => e.stopPropagation()}
          style={{
            // Für iOS Safari: verwende dvh (dynamic viewport height) wenn verfügbar, fallback zu vh
            // Berücksichtige safe-area-insets für die Höhe (Overlay hat bereits Padding)
            maxHeight: 'min(85dvh, 85vh)',
          }}
        >
          {children}
        </div>
      </div>
    </DialogContext.Provider>
  )
}

const DialogHeader = ({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) => (
  <div
    className={cn(
      "flex flex-col space-y-1.5 text-center sm:text-left flex-shrink-0 relative",
      className
    )}
    {...props}
  />
)
DialogHeader.displayName = "DialogHeader"

const DialogTitle = React.forwardRef<
  HTMLHeadingElement,
  React.HTMLAttributes<HTMLHeadingElement>
>(({ className, ...props }, ref) => (
  <h2
    ref={ref}
    className={cn(
      "text-xl font-semibold leading-none tracking-tight",
      className
    )}
    {...props}
  />
))
DialogTitle.displayName = "DialogTitle"

const DialogDescription = React.forwardRef<
  HTMLParagraphElement,
  React.HTMLAttributes<HTMLParagraphElement>
>(({ className, ...props }, ref) => (
  <p
    ref={ref}
    className={cn("text-sm text-slate-500", className)}
    {...props}
  />
))
DialogDescription.displayName = "DialogDescription"

const DialogContent = React.forwardRef<HTMLDivElement, DialogContentProps>(
  ({ className, children, ...props }, ref) => (
    <div 
      ref={ref} 
      className={cn("flex-1 overflow-y-auto overflow-x-hidden p-6 min-h-0", className)} 
      style={{
        // Für iOS Safari: verbessere Scrolling
        WebkitOverflowScrolling: 'touch',
        overscrollBehavior: 'contain',
      }}
      {...props}
    >
      {children}
    </div>
  )
)
DialogContent.displayName = "DialogContent"

const DialogFooter = ({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) => (
  <div
    className={cn(
      "flex flex-col-reverse sm:flex-row sm:justify-end sm:space-x-2 border-t border-slate-200 px-6 py-4 bg-slate-50 flex-shrink-0",
      className
    )}
    {...props}
  />
)
DialogFooter.displayName = "DialogFooter"

interface DialogCloseProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  children?: React.ReactNode
}

const DialogClose = React.forwardRef<HTMLButtonElement, DialogCloseProps>(
  ({ className, children, onClick, ...props }, ref) => {
    const context = React.useContext(DialogContext)
    
    const handleClick = (e: React.MouseEvent<HTMLButtonElement>) => {
      if (context) {
        context.onOpenChange(false)
      }
      onClick?.(e)
    }

    return (
      <button
        ref={ref}
        type="button"
        className={cn(
          "absolute right-4 top-4 z-10 rounded-sm opacity-70 ring-offset-white transition-opacity hover:opacity-100 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2 touch-manipulation",
          "min-w-[44px] min-h-[44px] flex items-center justify-center", // Mindestgröße für Touch-Targets
          className
        )}
        onClick={handleClick}
        {...props}
      >
        {children || <X className="h-5 w-5" />}
        <span className="sr-only">Close</span>
      </button>
    )
  }
)
DialogClose.displayName = "DialogClose"

export {
  Dialog,
  DialogHeader,
  DialogFooter,
  DialogTitle,
  DialogDescription,
  DialogContent,
  DialogClose,
}
