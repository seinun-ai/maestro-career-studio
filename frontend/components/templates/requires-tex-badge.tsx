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
      title="This template needs extra software that isn't installed. Resumes using it use a similar template for now."
    >
      Needs setup
    </Badge>
  );
}
