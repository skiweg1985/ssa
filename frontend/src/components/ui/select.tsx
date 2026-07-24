import * as React from "react"
import { createPortal } from "react-dom"
import { Check, ChevronDown } from "lucide-react"
import { cn } from "@/lib/cn"

export interface SelectOption {
  value: string
  label: string
  description?: string
}

interface SelectProps {
  value: string | null
  onValueChange: (value: string) => void
  options: SelectOption[]
  placeholder?: string
  disabled?: boolean
  className?: string
}

/**
 * Einfaches Select im Stil des UI-Kits (Portal-basiert wie DropdownMenu,
 * z-Index über den Dialogen, damit es in Modals nutzbar ist).
 */
export function Select({
  value,
  onValueChange,
  options,
  placeholder = "Auswählen…",
  disabled,
  className,
}: SelectProps) {
  const [open, setOpen] = React.useState(false)
  const [position, setPosition] = React.useState({ top: 0, left: 0, width: 0 })
  const triggerRef = React.useRef<HTMLButtonElement>(null)
  const menuRef = React.useRef<HTMLDivElement>(null)

  const selected = options.find((o) => o.value === value) ?? null

  React.useEffect(() => {
    if (open && triggerRef.current) {
      const rect = triggerRef.current.getBoundingClientRect()
      const viewportHeight = window.innerHeight
      const estimatedHeight = Math.min(options.length * 40 + 8, 240)
      const spaceBelow = viewportHeight - rect.bottom
      const openUpward = spaceBelow < estimatedHeight && rect.top > spaceBelow
      setPosition({
        top: openUpward
          ? Math.max(4, rect.top - estimatedHeight - 4)
          : rect.bottom + 4,
        left: rect.left,
        width: rect.width,
      })
    }
  }, [open, options.length])

  React.useEffect(() => {
    if (!open) return
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
    function handleEscape(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false)
    }
    document.addEventListener("mousedown", handleClickOutside, true)
    document.addEventListener("keydown", handleEscape)
    return () => {
      document.removeEventListener("mousedown", handleClickOutside, true)
      document.removeEventListener("keydown", handleEscape)
    }
  }, [open])

  return (
    <>
      <button
        type="button"
        ref={triggerRef}
        disabled={disabled}
        onClick={() => setOpen(!open)}
        className={cn(
          "flex h-9 w-full items-center justify-between rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 px-3 py-1 text-sm text-slate-900 dark:text-slate-100 shadow-sm transition-colors",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500",
          "disabled:cursor-not-allowed disabled:opacity-50",
          !selected && "text-slate-400 dark:text-slate-500",
          className
        )}
        aria-haspopup="listbox"
        aria-expanded={open}
      >
        <span className="truncate">{selected ? selected.label : placeholder}</span>
        <ChevronDown className="h-4 w-4 flex-shrink-0 text-slate-400" />
      </button>
      {open &&
        createPortal(
          <div
            ref={menuRef}
            role="listbox"
            className="fixed z-[1100] max-h-60 overflow-y-auto rounded-md border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 py-1 shadow-xl"
            style={{
              top: `${position.top}px`,
              left: `${position.left}px`,
              minWidth: `${position.width}px`,
            }}
          >
            {options.length === 0 && (
              <div className="px-3 py-2 text-sm text-slate-400 dark:text-slate-500">
                Keine Einträge
              </div>
            )}
            {options.map((option) => (
              <button
                key={option.value}
                type="button"
                role="option"
                aria-selected={option.value === value}
                onClick={() => {
                  onValueChange(option.value)
                  setOpen(false)
                }}
                className={cn(
                  "flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-sm text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700 focus:bg-slate-100 dark:focus:bg-slate-700 focus:outline-none transition-colors min-h-[2.5rem]",
                  option.value === value && "font-medium text-slate-900 dark:text-slate-50"
                )}
              >
                <span className="min-w-0">
                  <span className="block truncate">{option.label}</span>
                  {option.description && (
                    <span className="block truncate text-xs text-slate-400 dark:text-slate-500">
                      {option.description}
                    </span>
                  )}
                </span>
                {option.value === value && (
                  <Check className="h-4 w-4 flex-shrink-0 text-primary-500" />
                )}
              </button>
            ))}
          </div>,
          document.body
        )}
    </>
  )
}
