import { Badge } from "@/components/ui/badge";

/**
 * Marks a template whose engine cannot run on this backend (a LaTeX template
 * on a host with no pdflatex). Shared by the gallery card and the template
 * detail page so the wording and the explanation cannot drift apart.
 */
export function RequiresTexBadge() {
  return (
    <Badge
      variant="outline"
      className="border-amber-500/40 text-amber-700 dark:text-amber-400"
      title="TeX is not installed where the backend runs. A resume using this template renders through a Typst template instead, and the render says so, until TeX is installed."
    >
      requires TeX
    </Badge>
  );
}
