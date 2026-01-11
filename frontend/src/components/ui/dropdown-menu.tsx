import * as React from "react"
import { createPortal } from "react-dom"
import { cn } from "@/lib/cn"

interface DropdownMenuProps {
  trigger: React.ReactNode
  children: React.ReactNode
  align?: "start" | "end"
}

// Context für Dropdown-Menü-Funktionen
const DropdownMenuContext = React.createContext<{
  setOpen: (open: boolean) => void
} | null>(null)

export function DropdownMenu({ trigger, children, align = "end" }: DropdownMenuProps) {
  const [open, setOpen] = React.useState(false)
  const [position, setPosition] = React.useState({ top: 0, left: 0 })
  const triggerRef = React.useRef<HTMLDivElement>(null)
  const menuRef = React.useRef<HTMLDivElement>(null)

  // Calculate position for fixed positioning
  React.useEffect(() => {
    if (open && triggerRef.current) {
      const rect = triggerRef.current.getBoundingClientRect()
      const viewportHeight = window.innerHeight
      
      // Estimate menu height (approximate, will be adjusted after render)
      const estimatedMenuHeight = 200
      const spaceBelow = viewportHeight - rect.bottom
      const spaceAbove = rect.top
      
      // Open upward if not enough space below but enough space above
      const shouldOpenUpward = spaceBelow < estimatedMenuHeight && spaceAbove > spaceBelow
      
      // For fixed positioning, use getBoundingClientRect directly (no scroll offset needed)
      // When opening upward, position menu above the trigger
      let topPosition: number
      if (shouldOpenUpward) {
        topPosition = Math.max(4, rect.top - estimatedMenuHeight - 4)
      } else {
        topPosition = rect.bottom + 4
        // Ensure menu doesn't go below viewport
        if (topPosition + estimatedMenuHeight > viewportHeight) {
          topPosition = Math.max(4, viewportHeight - estimatedMenuHeight - 4)
        }
      }
      
      setPosition({
        top: topPosition,
        left: align === "end" ? rect.right : rect.left,
      })
    }
  }, [open, align])

  React.useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (
        triggerRef.current &&
        menuRef.current &&
        !triggerRef.current.contains(event.target as Node) &&
        !menuRef.current.contains(event.target as Node)
      ) {
        setOpen(false)
      }
    }

    if (open) {
      // Use capture phase to catch clicks before they bubble
      document.addEventListener("mousedown", handleClickOutside, true)
      return () => document.removeEventListener("mousedown", handleClickOutside, true)
    }
  }, [open])

  // Handle keyboard navigation
  React.useEffect(() => {
    if (!open) return

    function handleEscape(e: KeyboardEvent) {
      if (e.key === "Escape") {
        setOpen(false)
      }
    }

    document.addEventListener("keydown", handleEscape)
    return () => document.removeEventListener("keydown", handleEscape)
  }, [open])

  return (
    <>
      <div className="relative inline-block" ref={triggerRef}>
        <div
          onClick={() => setOpen(!open)}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault()
              setOpen(!open)
            }
          }}
        >
          {trigger}
        </div>
      </div>
      {open &&
        createPortal(
          <DropdownMenuContext.Provider value={{ setOpen }}>
            <div
              ref={menuRef}
              className={cn(
                "fixed z-[100] min-w-[10rem] overflow-hidden rounded-md border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 shadow-xl",
                align === "end" ? "right-auto" : "left-auto"
              )}
              style={{
                top: `${position.top}px`,
                left: `${position.left}px`,
                ...(align === "end" && { transform: "translateX(-100%)" }),
              }}
              role="menu"
            >
              {children}
            </div>
          </DropdownMenuContext.Provider>,
          document.body
        )}
    </>
  )
}

export function DropdownMenuItem({
  children,
  onClick,
  className,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  const context = React.useContext(DropdownMenuContext)

  const handleClick = (e: React.MouseEvent<HTMLButtonElement>) => {
    // Schließe das Menü, wenn ein Item geklickt wird
    if (context) {
      context.setOpen(false)
    }
    // Rufe den ursprünglichen onClick-Handler auf
    onClick?.(e)
  }

  return (
    <button
      className={cn(
        "w-full px-3 py-2 text-left text-sm text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700 focus:bg-slate-100 dark:focus:bg-slate-700 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-inset transition-colors min-h-[2.5rem]",
        className
      )}
      onClick={handleClick}
      {...props}
    >
      {children}
    </button>
  )
}
