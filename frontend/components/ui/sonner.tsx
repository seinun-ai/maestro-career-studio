"use client"

import { useTheme } from "next-themes"
import { Toaster as Sonner, type ToasterProps } from "sonner"
import { CircleCheckIcon, InfoIcon, TriangleAlertIcon, OctagonXIcon, Loader2Icon } from "lucide-react"

const Toaster = ({ ...props }: ToasterProps) => {
  const { theme = "system" } = useTheme()

  return (
    <Sonner
      theme={theme as ToasterProps["theme"]}
      className="toaster group"
      icons={{
        success: (
          <CircleCheckIcon className="size-4" />
        ),
        info: (
          <InfoIcon className="size-4" />
        ),
        warning: (
          <TriangleAlertIcon className="size-4" />
        ),
        error: (
          <OctagonXIcon className="size-4" />
        ),
        loading: (
          <Loader2Icon className="size-4 animate-spin" />
        ),
      }}
      style={
        {
          "--normal-bg": "var(--popover)",
          "--normal-text": "var(--popover-foreground)",
          "--normal-border": "var(--border)",
          "--border-radius": "var(--radius-corner-md)",
        } as React.CSSProperties
      }
      toastOptions={{
        classNames: {
          // M3 snackbar elevation. Sonner's own box-shadow is unlayered CSS, which
          // beats `@layer utilities` as well as the specificity of one class, so
          // the level needs `!`. Sonner's keyboard focus indicator is that same
          // box-shadow, so the ring is restated: the important shadow reads
          // --tw-ring-shadow and the two compose.
          toast: "cn-toast shadow-level3! focus-visible:ring-2 focus-visible:ring-ring",
        },
      }}
      {...props}
    />
  )
}

export { Toaster }
