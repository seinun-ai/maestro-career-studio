import type { ReactNode } from "react";

/**
 * Fullscreen document-editor page contract.
 *
 * The page owns viewport height only — no padding, outer border, or page-level
 * title row. The child owns left-pane chrome and renders `EditorShell` as the
 * sole fill child so panes scroll internally instead of growing the page.
 */
export function FullscreenEditorPage({ children }: { children: ReactNode }) {
  return (
    <main className="flex h-dvh flex-col overflow-hidden">{children}</main>
  );
}
