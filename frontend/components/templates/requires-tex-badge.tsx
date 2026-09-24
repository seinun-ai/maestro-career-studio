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
      // pdf_render.resolve_render_template: the first ready template that
      // doesn't need TeX stands in; with none, there is no PDF.
      title="This template needs TeX, which isn't installed on this computer. Until it is, resumes that use it are made with another ready template that doesn't need TeX."
    >
      Needs setup
    </Badge>
  );
}
