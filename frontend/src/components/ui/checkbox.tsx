import * as React from "react"
import { Check, Minus } from "lucide-react"
import { cn } from "@/lib/cn"

interface CheckboxProps {
  checked: boolean
  onCheckedChange: (checked: boolean) => void
  indeterminate?: boolean
  label?: React.ReactNode
  disabled?: boolean
  className?: string
  "aria-label"?: string
}

/** Checkbox im Stil des UI-Kits (voller Dark-Mode, Touch-Target) */
export function Checkbox({
  checked,
  onCheckedChange,
  indeterminate,
  label,
  disabled,
  className,
  "aria-label": ariaLabel,
}: CheckboxProps) {
  return (
    <label
      className={cn(
        "inline-flex items-center gap-2 select-none",
        disabled ? "cursor-not-allowed opacity-50" : "cursor-pointer",
        className
      )}
    >
      <button
        type="button"
        role="checkbox"
        aria-checked={indeterminate ? "mixed" : checked}
        aria-label={ariaLabel ?? (typeof label === "string" ? label : undefined)}
        disabled={disabled}
        onClick={(e) => {
          e.stopPropagation()
          onCheckedChange(!checked)
        }}
        className={cn(
          "flex h-5 w-5 flex-shrink-0 items-center justify-center rounded border transition-colors",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-1 dark:focus-visible:ring-offset-slate-900",
          checked || indeterminate
            ? "border-primary-500 bg-primary-500 text-white"
            : "border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800"
        )}
      >
        {indeterminate ? (
          <Minus className="h-3.5 w-3.5" />
        ) : checked ? (
          <Check className="h-3.5 w-3.5" />
        ) : null}
      </button>
      {label && (
        <span className="text-sm text-slate-700 dark:text-slate-300">{label}</span>
      )}
    </label>
  )
}
