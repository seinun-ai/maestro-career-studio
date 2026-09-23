import type { ReactNode } from "react";

import { focusIfDropped } from "@/lib/focus";

/**
 * Fullscreen document-editor page contract.
 *
 * The page owns viewport height only — no padding, outer border, or page-level
 * title row. The child owns left-pane chrome and renders `EditorShell` as the
 * sole fill child so panes scroll internally instead of growing the page.
 *
 * `tabIndex={-1}`: when a studio remounts its editor (Load latest, Rebuild),
 * focus inside it lands here, the studio's own landmark, rather than on
 * <body>. A container, not a control, so no outline. An arrival does the same:
 * a navigation here (Create on /templates or New base résumé, a gallery card)
 * unmounts what held focus, so a focus left on <body> lands on this landmark.
 * `focusIfDropped` is a module function, so the ref is stable and runs on
 * mount only.
 */
export function FullscreenEditorPage({ children }: { children: ReactNode }) {
  return (
    <main tabIndex={-1} className="flex h-dvh flex-col overflow-hidden outline-none" ref={focusIfDropped}>
      {children}
    </main>
  );
}
