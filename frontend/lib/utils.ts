import { clsx, type ClassValue } from "clsx"
import { extendTailwindMerge } from "tailwind-merge"

// tailwind-merge only knows Tailwind's stock names. A token added to the
// @theme block in app/globals.css is registered here too, or cn() misfiles
// it: an unknown text-* is taken for a COLOUR and dropped beside
// text-muted-foreground, an unknown shadow-* for a shadow colour, and an
// unknown rounded-* or ease-* is never merged against its stock sibling.
// backend/tests/test_frontend_design_tokens.py keeps the two lists equal.
const twMerge = extendTailwindMerge({
  extend: {
    theme: {
      text: [
        "display-large",
        "display-medium",
        "display-small",
        "headline-large",
        "headline-medium",
        "headline-small",
        "title-large",
        "title-medium",
        "title-small",
        "body-large",
        "body-medium",
        "body-small",
        "label-large",
        "label-medium",
        "label-small",
      ],
      radius: ["corner-xs", "corner-sm", "corner-md", "corner-lg", "corner-xl"],
      shadow: ["level1", "level2", "level3"],
      ease: ["standard", "emphasized-decelerate", "emphasized-accelerate"],
    },
  },
})

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function move<T>(arr: T[], from: number, to: number): T[] {
  if (to < 0 || to >= arr.length) return arr;
  const next = [...arr];
  const [item] = next.splice(from, 1);
  next.splice(to, 0, item);
  return next;
}
