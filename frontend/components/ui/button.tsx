import { Button as ButtonPrimitive } from "@base-ui/react/button"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "@/lib/utils"

const buttonVariants = cva(
  "group/button inline-flex shrink-0 cursor-pointer items-center justify-center rounded-lg border border-transparent bg-clip-padding text-sm font-medium whitespace-nowrap [transition:transform_140ms_var(--ease-out-strong),background-color_160ms_ease,color_160ms_ease,box-shadow_160ms_ease,border-color_160ms_ease,opacity_160ms_ease] outline-none select-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 active:not-aria-[haspopup]:scale-[0.97] active:not-disabled:[transition-duration:60ms] disabled:pointer-events-none disabled:opacity-50 aria-invalid:border-destructive aria-invalid:ring-3 aria-invalid:ring-destructive/20 dark:aria-invalid:border-destructive/50 dark:aria-invalid:ring-destructive/40 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
  {
    variants: {
      variant: {
        // Not `[a]:hover:` — that compiles to an `:is(a)` gate, so the hover
        // only fired when the Button rendered as a link. Base UI renders a
        // <button>, which left the one high-emphasis control in the app with no
        // hover feedback at all. (The gate is correct in badge.tsx, where it
        // came from: a Badge is usually not interactive.)
        default: "bg-primary text-primary-foreground hover:bg-primary/90",
        // M3's filled-tonal: SECONDARY container, M3's role for "recessive
        // components like tonal buttons". It was `bg-primary/10 text-primary`,
        // which failed AA (3.8-4.3:1) in light mode; the role pair is pinned
        // at >= 4.5:1 by backend/tests/test_frontend_color_roles.py.
        tonal:
          "bg-secondary-container text-on-secondary-container hover:bg-secondary-container-hover",
        // M3 extended FAB: the ONE create action on a screen (the sidebar's
        // Add job). Primary container is M3's default FAB colour. A
        // FAB in a rail rests flat and hover raises it one level; a resting
        // shadow read as permanently hovered.
        fab: "bg-primary-container text-on-primary-container hover:bg-primary-container-hover hover:shadow-sm",
        // `dark:border-input` outranks the base `focus-visible:border-ring`, so
        // dark mode showed only the ring/50 halo (~2.2:1, under WCAG 1.4.11's
        // 3:1). The dark focus border is set back to the solid ring here.
        outline:
          "border-border bg-background hover:bg-muted hover:text-foreground aria-expanded:bg-muted aria-expanded:text-foreground dark:border-input dark:bg-input/30 dark:hover:bg-input/50 dark:focus-visible:border-ring",
        secondary:
          "bg-secondary text-secondary-foreground hover:bg-secondary/80 aria-expanded:bg-secondary aria-expanded:text-secondary-foreground",
        ghost:
          "hover:bg-muted hover:text-foreground aria-expanded:bg-muted aria-expanded:text-foreground dark:hover:bg-muted/50",
        destructive:
          "bg-destructive/10 text-destructive hover:bg-destructive/20 focus-visible:border-destructive focus-visible:ring-destructive/20 dark:bg-destructive/20 dark:hover:bg-destructive/30 dark:focus-visible:ring-destructive/40",
        link: "text-primary underline-offset-4 hover:underline",
      },
      size: {
        default:
          "h-8 gap-1.5 px-2.5 has-data-[icon=inline-end]:pr-2 has-data-[icon=inline-start]:pl-2",
        xs: "h-6 gap-1 rounded-[min(var(--radius-md),10px)] px-2 text-xs in-data-[slot=button-group]:rounded-lg has-data-[icon=inline-end]:pr-1.5 has-data-[icon=inline-start]:pl-1.5 [&_svg:not([class*='size-'])]:size-3",
        sm: "h-7 gap-1 rounded-[min(var(--radius-md),12px)] px-2.5 text-[0.8rem] in-data-[slot=button-group]:rounded-lg has-data-[icon=inline-end]:pr-1.5 has-data-[icon=inline-start]:pl-1.5 [&_svg:not([class*='size-'])]:size-3.5",
        lg: "h-9 gap-1.5 px-2.5 has-data-[icon=inline-end]:pr-2 has-data-[icon=inline-start]:pl-2",
        icon: "size-8 pointer-coarse:min-h-11 pointer-coarse:min-w-11",
        "icon-xs":
          "size-6 rounded-[min(var(--radius-md),10px)] in-data-[slot=button-group]:rounded-lg pointer-coarse:min-h-11 pointer-coarse:min-w-11 [&_svg:not([class*='size-'])]:size-3",
        "icon-sm":
          "size-7 rounded-[min(var(--radius-md),12px)] in-data-[slot=button-group]:rounded-lg pointer-coarse:min-h-11 pointer-coarse:min-w-11",
        "icon-lg": "size-9 pointer-coarse:min-h-11 pointer-coarse:min-w-11",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

function Button({
  className,
  variant = "default",
  size = "default",
  ...props
}: ButtonPrimitive.Props & VariantProps<typeof buttonVariants>) {
  return (
    <ButtonPrimitive
      data-slot="button"
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  )
}

export { Button, buttonVariants }
