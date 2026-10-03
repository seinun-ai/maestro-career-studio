import { cn } from "@/lib/utils"

function Skeleton({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="skeleton"
      className={cn("animate-shimmer rounded-corner-sm bg-muted", className)}
      {...props}
    />
  )
}

export { Skeleton }
