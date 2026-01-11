import * as React from "react"
import { cn } from "@/lib/cn"

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "default" | "primary" | "secondary" | "ghost" | "destructive"
  size?: "sm" | "md" | "lg"
  isLoading?: boolean
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = "default", size = "md", isLoading, children, disabled, ...props }, ref) => {
    const baseStyles = "inline-flex items-center justify-center rounded-md font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-1 disabled:opacity-50 disabled:pointer-events-none"
    
    const variants = {
      default: "bg-slate-900 dark:bg-slate-50 text-slate-50 dark:text-slate-900 hover:bg-slate-800 dark:hover:bg-slate-100 active:bg-slate-900 dark:active:bg-slate-200",
      primary: "bg-primary-500 text-white hover:bg-primary-600 active:bg-primary-700",
      secondary: "bg-slate-100 dark:bg-slate-700 text-slate-900 dark:text-slate-50 hover:bg-slate-200 dark:hover:bg-slate-600 active:bg-slate-300 dark:active:bg-slate-500",
      ghost: "hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-700 dark:text-slate-300 active:bg-slate-200 dark:active:bg-slate-700",
      destructive: "bg-red-600 text-white hover:bg-red-700 active:bg-red-800",
    }
    
    const sizes = {
      sm: "h-10 min-h-[40px] px-3 text-xs",
      md: "h-10 min-h-[40px] px-4 text-sm",
      lg: "h-11 min-h-[44px] px-8 text-base",
    }
    
    return (
      <button
        className={cn(baseStyles, variants[variant], sizes[size], className)}
        ref={ref}
        disabled={disabled || isLoading}
        {...props}
      >
        {isLoading && (
          <svg className="mr-2 h-4 w-4 animate-spin" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
          </svg>
        )}
        {children}
      </button>
    )
  }
)
Button.displayName = "Button"

export { Button }
