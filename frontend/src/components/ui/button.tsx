import * as React from "react"
import { cn } from "@/lib/cn"

/* Button · Zustände: default · hover · focus-visible · active · disabled · loading
 *
 * Systemstimme: 6 px Radius statt Pille, EIN gefüllter Akzentbutton, alles andere
 * typografisch oder als Hairline-Umriss. Weiß auf accent-500 trägt 5.54:1.
 */

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "default" | "primary" | "secondary" | "ghost" | "destructive"
  size?: "sm" | "md" | "lg"
  isLoading?: boolean
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  (
    {
      className,
      variant = "default",
      size = "md",
      isLoading,
      children,
      disabled,
      type,
      ...props
    },
    ref
  ) => {
    /* Spinner erst nach 150 ms zeigen. Eine Aktion, die in 40 ms zurückkommt,
       soll nicht kurz aufblitzen — das liest sich als Ruckler, nicht als Ladevorgang. */
    const [showSpinner, setShowSpinner] = React.useState(false)
    React.useEffect(() => {
      if (!isLoading) {
        setShowSpinner(false)
        return
      }
      const t = setTimeout(() => setShowSpinner(true), 150)
      return () => clearTimeout(t)
    }, [isLoading])

    const baseStyles = cn(
      "inline-flex items-center justify-center rounded-md font-medium whitespace-nowrap",
      // Nur die Eigenschaften, die sich wirklich ändern dürfen. Kein transition-all —
      // sonst wandert auch der Fokusring durch eine Animation.
      "transition-[background-color,border-color,color] duration-instant ease-out",
      "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:ring-offset-white dark:focus-visible:ring-offset-slate-900",
      "disabled:opacity-45 disabled:pointer-events-none"
    )

    const variants = {
      default:
        "border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-50 hover:border-slate-400 dark:hover:border-slate-500 hover:bg-slate-50 dark:hover:bg-slate-700 active:bg-slate-100 dark:active:bg-slate-600",
      primary:
        "bg-primary-500 text-white hover:bg-primary-600 active:bg-primary-700",
      secondary:
        "bg-slate-100 dark:bg-slate-700 text-slate-900 dark:text-slate-50 hover:bg-slate-200 dark:hover:bg-slate-600 active:bg-slate-300 dark:active:bg-slate-500",
      ghost:
        "text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700 hover:text-slate-900 dark:hover:text-slate-50 active:bg-slate-200 dark:active:bg-slate-600",
      destructive:
        "bg-red-600 text-white hover:bg-red-700 active:bg-red-800",
    }

    /* Echte Stufen. Vorher waren sm und md beide h-10 — eine Skala mit zwei Namen
       für eine Höhe ist keine Skala. Grobe Zeiger heben alles auf 44 px (index.css). */
    const sizes = {
      sm: "h-8 px-2.5 text-xs gap-1.5",
      md: "h-9 px-3.5 text-sm gap-2",
      lg: "h-11 px-6 text-base gap-2",
    }

    return (
      <button
        // Ohne type wird jeder Button in einem <form> still zum Submit-Button.
        type={type ?? "button"}
        className={cn(baseStyles, variants[variant], sizes[size], className)}
        ref={ref}
        disabled={disabled || isLoading}
        data-state={isLoading ? "loading" : undefined}
        {...props}
      >
        {showSpinner && (
          <svg
            className="h-3.5 w-3.5 animate-spin"
            aria-hidden="true"
            xmlns="http://www.w3.org/2000/svg"
            fill="none"
            viewBox="0 0 24 24"
          >
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path
              className="opacity-75"
              fill="currentColor"
              d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
            />
          </svg>
        )}
        {children}
      </button>
    )
  }
)
Button.displayName = "Button"

export { Button }
