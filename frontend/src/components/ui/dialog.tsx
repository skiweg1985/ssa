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
        className="fixed inset-0 z-[1000] flex items-center justify-center p-4 bg-black/50 animate-in fade-in"
        onClick={() => onOpenChange(false)}
      >
        <div
          className="relative z-[1000] w-full max-w-4xl max-h-[90vh] bg-white rounded-xl shadow-2xl flex flex-col overflow-hidden animate-in slide-in-from-bottom-4"
          onClick={(e) => e.stopPropagation()}
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
      "flex flex-col space-y-1.5 text-center sm:text-left",
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
    <div ref={ref} className={cn("flex-1 overflow-y-auto p-6", className)} {...props}>
      {children}
    </div>
  )
)
DialogContent.displayName = "DialogContent"

const DialogFooter = ({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) => (
  <div
    className={cn(
      "flex flex-col-reverse sm:flex-row sm:justify-end sm:space-x-2 border-t border-slate-200 px-6 py-4 bg-slate-50",
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
          "absolute right-4 top-4 rounded-sm opacity-70 ring-offset-white transition-opacity hover:opacity-100 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2",
          className
        )}
        onClick={handleClick}
        {...props}
      >
        {children || <X className="h-4 w-4" />}
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
