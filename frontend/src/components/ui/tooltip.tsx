import * as React from "react"
import { createPortal } from "react-dom"
import { cn } from "@/lib/cn"

interface TooltipProps {
  content: string
  children: React.ReactNode
  side?: "top" | "bottom" | "left" | "right"
  fullWidth?: boolean
}

export function Tooltip({ content, children, side = "top", fullWidth = false }: TooltipProps) {
  const [isVisible, setIsVisible] = React.useState(false)
  const [isFocused, setIsFocused] = React.useState(false)
  const [position, setPosition] = React.useState({ top: 0, left: 0 })
  const triggerRef = React.useRef<HTMLDivElement>(null)
  const showTooltip = isVisible || isFocused

  // Calculate position for fixed positioning
  React.useEffect(() => {
    if (showTooltip && triggerRef.current) {
      const rect = triggerRef.current.getBoundingClientRect()
      const tooltipOffset = 8

      switch (side) {
        case "top":
          setPosition({
            top: rect.top + window.scrollY - tooltipOffset,
            left: rect.left + window.scrollX + rect.width / 2,
          })
          break
        case "bottom":
          setPosition({
            top: rect.bottom + window.scrollY + tooltipOffset,
            left: rect.left + window.scrollX + rect.width / 2,
          })
          break
        case "left":
          setPosition({
            top: rect.top + window.scrollY + rect.height / 2,
            left: rect.left + window.scrollX - tooltipOffset,
          })
          break
        case "right":
          setPosition({
            top: rect.top + window.scrollY + rect.height / 2,
            left: rect.right + window.scrollX + tooltipOffset,
          })
          break
      }
    }
  }, [showTooltip, side])

  return (
    <>
      <div
        ref={triggerRef}
        className={cn("relative", fullWidth ? "block w-full" : "inline-block")}
        onMouseEnter={() => setIsVisible(true)}
        onMouseLeave={() => setIsVisible(false)}
        onFocus={() => setIsFocused(true)}
        onBlur={() => setIsFocused(false)}
      >
        {children}
      </div>
      {showTooltip &&
        createPortal(
          <div
            className={cn(
              "fixed z-[100] whitespace-pre-line rounded-md bg-slate-900 px-3 py-2 text-xs text-white shadow-xl min-w-[200px] max-w-[400px] pointer-events-none",
              side === "top" && "-translate-y-full -translate-x-1/2",
              side === "bottom" && "-translate-x-1/2",
              side === "left" && "-translate-x-full -translate-y-1/2",
              side === "right" && "-translate-y-1/2"
            )}
            style={{
              top: `${position.top}px`,
              left: `${position.left}px`,
            }}
            role="tooltip"
          >
            {content}
            <div
              className={cn(
                "absolute h-0 w-0 border-4 border-transparent",
                side === "top" && "top-full left-1/2 -translate-x-1/2 border-t-slate-900",
                side === "bottom" && "bottom-full left-1/2 -translate-x-1/2 border-b-slate-900",
                side === "left" && "left-full top-1/2 -translate-y-1/2 border-l-slate-900",
                side === "right" && "right-full top-1/2 -translate-y-1/2 border-r-slate-900"
              )}
            />
          </div>,
          document.body
        )}
    </>
  )
}
