import * as React from "react"
import { cn } from "@/lib/cn"

/* Badge
 *
 * Status ist eine Maschinenangabe — also Mono, Versalien, weites Tracking.
 * Der frühere Dauerpuls auf „läuft" ist raus: eine Fläche, die endlos atmet, während
 * daneben schon ein Fortschrittsbalken läuft, ist zweimal dieselbe Information und
 * einmal zu viel Bewegung. „läuft" trägt jetzt einen ruhigen Akzentpunkt.
 */

export interface BadgeProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: "success" | "warning" | "error" | "running" | "pending" | "default"
}

function Badge({ className, variant = "default", children, ...props }: BadgeProps) {
  const variants = {
    default:
      "bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-300 border-slate-200 dark:border-slate-600",
    success:
      "bg-emerald-50 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300 border-emerald-200 dark:border-emerald-700",
    warning:
      "bg-amber-50 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300 border-amber-200 dark:border-amber-700",
    error:
      "bg-red-50 dark:bg-red-900/30 text-red-700 dark:text-red-300 border-red-200 dark:border-red-700",
    running:
      "bg-primary-50 dark:bg-primary-900/30 text-primary-700 dark:text-primary-300 border-primary-200 dark:border-primary-700",
    pending:
      "bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-400 border-slate-200 dark:border-slate-600",
  }

  return (
    <div
      className={cn(
        "inline-flex items-center gap-1.5 rounded-sm border px-2 py-0.5",
        "font-mono text-[11px] font-medium uppercase tracking-label",
        "overflow-visible min-w-fit flex-shrink-0",
        variants[variant],
        className
      )}
      {...props}
    >
      {variant === "running" && (
        <span
          className="h-1.5 w-1.5 flex-shrink-0 rounded-full bg-primary-500 dark:bg-primary-400"
          aria-hidden="true"
        />
      )}
      {children}
    </div>
  )
}

export { Badge }
