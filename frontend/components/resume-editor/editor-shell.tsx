"use client";

import { useId, useRef, useState, type ReactNode } from "react";
import {
  ArrowLeftToLine,
  ArrowRightToLine,
  ChevronLeft,
  ChevronRight,
  History,
  SlidersHorizontal,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { useFocusHandoff, useFocusOnNextCommit } from "@/hooks/use-focus-return";
import {
  parseFlag,
  serializeFlag,
  useLocalStorageState,
} from "@/hooks/use-local-storage-state";
import { clampPreviewPct, PREVIEW_PCT, nextPreviewPct, parsePreviewPct } from "@/lib/studio";
import { cn } from "@/lib/utils";

const DEFAULT_STORAGE_KEY = "baseResumeEditor";

/**
 * The one two-pane editor shell: a left working pane and a resizable,
 * collapsible right preview pane. Serves the base-resume editor, the
 * application studio, and the template editor (which passes
 * `fullHeightLeft` so a full-height editor like Monaco can size itself —
 * per-tab chrome then lives inside `editor`).
 */
export function EditorShell({
  editor,
  preview,
  previewHeader,
  previewTitle,
  formattingPanel,
  fullHeightLeft = false,
  storageKey = DEFAULT_STORAGE_KEY,
  previewStale = false,
}: {
  editor: ReactNode;
  preview: ReactNode;
  previewHeader?: ReactNode;
  /** Preview pane title; defaults to "Preview". */
  previewTitle?: ReactNode;
  formattingPanel?: ReactNode;
  /**
   * Document surfaces (default) get a centered, padded, scrollable left pane.
   * Full-height surfaces (the template editor's Monaco pane) get an unpadded
   * flex column that lets the child own its scrolling.
   */
  fullHeightLeft?: boolean;
  /**
   * Namespace for the persisted collapse/width state. Distinct surfaces (e.g.
   * the base-resume editor vs. the application studio) pass different keys so
   * their divider preferences don't collide in localStorage.
   */
  storageKey?: string;
  /**
   * The form has unsaved edits, so the pages below are the LAST SAVE. The
   * shell marks the preview stale rather than letting an old page pass for
   * the current one (Overleaf's "uncompiled" state).
   */
  previewStale?: boolean;
}) {
  const collapsedKey = `${storageKey}.previewCollapsed`;
  const widthKey = `${storageKey}.previewWidthPct`;
  const [collapsed, setCollapsed] = useLocalStorageState(
    collapsedKey,
    parseFlag,
    serializeFlag,
  );
  const [fmtOpen, setFmtOpen] = useState(false);
  const [storedPct, setStoredPct] = useLocalStorageState(
    widthKey,
    parsePreviewPct,
    String,
  );
  // The width under the pointer. It is rendered, not persisted, so a drag
  // does not write localStorage on every move.
  const [dragPct, setDragPct] = useState<number | null>(null);
  const previewPct = dragPct ?? storedPct;
  const editorPaneId = useId();
  // A remount of the studio around the shell (Load latest, Rebuild, a foreign
  // edit adopted while clean) removes it with focus inside: focus moves to the
  // page's <main>. The two preview toggles live in different branches, so the
  // pressed one unmounts and hands focus to its counterpart.
  const rootRef = useRef<HTMLDivElement>(null);
  useFocusHandoff(rootRef);
  const hideRef = useRef<HTMLButtonElement>(null);
  const showRef = useRef<HTMLButtonElement>(null);
  const focusNext = useFocusOnNextCommit();

  // `min-w-0` on both: a flex item defaults to min-width:auto, so the pane
  // refuses to shrink below its content's min-content width and pushes the
  // shell — and with it the page — wider, which is where the studio's
  // horizontal scrollbar came from.
  const leftClass = fullHeightLeft
    ? "flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden"
    : "mx-auto w-full min-w-0 max-w-5xl flex-1 overflow-y-auto p-6";
  const leftOpenClass = fullHeightLeft
    ? "flex min-h-0 min-w-0 flex-col overflow-hidden"
    : "min-w-0 flex-1 overflow-y-auto p-6";

  if (collapsed) {
    return (
      <div ref={rootRef} className="flex min-h-0 w-full flex-1">
        <div className={leftClass}>{editor}</div>
        {/* In flow, not an overlay: an absolutely-placed tab covered the left
            pane's scrollbar and its right-aligned controls. */}
        <div className="bg-canvas flex w-7 shrink-0 items-center border-l">
          <button
            ref={showRef}
            type="button"
            aria-label="Show PDF preview"
            title="Show PDF preview"
            onClick={() => {
              setCollapsed(false);
              focusNext(hideRef);
            }}
            className="text-muted-foreground hover:bg-muted hover:text-foreground focus-visible:ring-ring flex h-20 w-full items-center justify-center transition-colors outline-none focus-visible:ring-2 focus-visible:ring-inset"
          >
            <ChevronLeft className="size-4" aria-hidden="true" />
          </button>
        </div>
      </div>
    );
  }

  return (
    <div ref={rootRef} className="flex min-h-0 w-full flex-1">
      <div
        id={editorPaneId}
        className={leftOpenClass}
        style={{ width: `${100 - previewPct}%` }}
      >
        {editor}
      </div>
      <Splitter
        editorPct={100 - previewPct}
        controls={editorPaneId}
        onDrag={(editorPct) => setDragPct(clampPreviewPct(100 - editorPct))}
        onDragEnd={(editorPct) => {
          setStoredPct(clampPreviewPct(100 - editorPct));
          setDragPct(null);
        }}
        onReset={() => {
          setStoredPct(PREVIEW_PCT.default);
          setDragPct(null);
        }}
        onKey={(key) => {
          const next = nextPreviewPct(previewPct, key);
          if (next === null) return false;
          setStoredPct(next);
          setDragPct(null);
          return true;
        }}
      />
      <div
        className="bg-canvas relative flex min-h-0 min-w-0 flex-col overflow-hidden border-l"
        style={{ width: `${previewPct}%` }}
      >
        {/* Wraps: this header is inside the preview pane, which the user can
            drag down to 25% of the window. Both studios now hang only the
            formatting panel and two icon buttons off it — the template picker
            and Generate PDF moved out (2026-08-06) — but keep the wrap: it is
            what stopped this row overflowing into a page-wide horizontal
            scrollbar, and the next control added here would bring it back. */}
        <div className="flex flex-wrap items-center justify-between gap-2 border-b px-3 py-2">
          <span className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
            {previewTitle ?? "Preview"}
          </span>
          <div className="flex min-w-0 flex-wrap items-center gap-1">
            {formattingPanel && (
              <Button
                variant="ghost"
                size="sm"
                aria-expanded={fmtOpen}
                onClick={() => setFmtOpen((o) => !o)}
                className="gap-1.5 text-xs font-normal"
              >
                <SlidersHorizontal className="size-3.5 opacity-70" />
                Formatting
              </Button>
            )}
            {previewHeader}
            <Button
              size="icon-sm"
              variant="ghost"
              aria-label="Widen preview"
              title="Widen preview"
              // Pressed until it reaches its limit, it disables itself: a
              // disabled <button> drops focus, so it stays focusable (dimmed
              // on data-disabled, as Save is).
              focusableWhenDisabled
              className="data-disabled:pointer-events-none data-disabled:opacity-50"
              disabled={previewPct >= PREVIEW_PCT.max}
              onClick={() =>
                setStoredPct(nextPreviewPct(previewPct, "ArrowLeft") ?? previewPct)
              }
            >
              <ArrowLeftToLine className="size-4" />
            </Button>
            <Button
              size="icon-sm"
              variant="ghost"
              aria-label="Narrow preview"
              title="Narrow preview"
              // Focusable at its limit, like Widen.
              focusableWhenDisabled
              className="data-disabled:pointer-events-none data-disabled:opacity-50"
              disabled={previewPct <= PREVIEW_PCT.min}
              onClick={() =>
                setStoredPct(nextPreviewPct(previewPct, "ArrowRight") ?? previewPct)
              }
            >
              <ArrowRightToLine className="size-4" />
            </Button>
            <Button
              ref={hideRef}
              size="icon-sm"
              variant="ghost"
              aria-label="Hide PDF preview"
              onClick={() => {
                setCollapsed(true);
                focusNext(showRef);
              }}
            >
              <ChevronRight className="size-4" />
            </Button>
          </div>
        </div>
        {fmtOpen && formattingPanel && (
          <div className="border-b bg-background/60 max-h-[60vh] overflow-y-auto">
            {formattingPanel}
          </div>
        )}
        {previewStale ? (
          // Not a live region: the header's save-status line already
          // announces "Unsaved changes". This is the visual half. The copy
          // does not say "your last save": after a failed render the pages
          // are older than that.
          <div className="flex items-center gap-2 border-b bg-amber-500/10 px-3 py-1.5 text-xs text-amber-800 dark:text-amber-300">
            <History aria-hidden="true" className="size-3.5 shrink-0" />
            {"Preview doesn't include your unsaved edits. Save to update it."}
          </div>
        ) : null}
        {/* Stale dims the page IMAGES only: the render-error banner, the
            page-count pill and the zoom controls stay at full contrast. */}
        <div
          className={cn(
            "min-h-0 flex-1 overflow-hidden [&_img]:transition-opacity [&_img]:duration-200",
            previewStale && "[&_img]:opacity-60",
          )}
        >
          {preview}
        </div>
      </div>
    </div>
  );
}

function Splitter({
  editorPct,
  controls,
  onDrag,
  onDragEnd,
  onReset,
  onKey,
}: {
  /** The editor's share. Fractional while dragging; announced rounded. */
  editorPct: number;
  /** id of the editor pane this divider resizes (APG window splitter). */
  controls: string;
  onDrag: (editorPct: number) => void;
  onDragEnd: (editorPct: number) => void;
  onReset: () => void;
  /** Returns true when it handled the key. */
  onKey: (key: string) => boolean;
}) {
  const drag = useRef<{ left: number; width: number; editorPct: number } | null>(
    null,
  );
  const finish = () => {
    const d = drag.current;
    if (!d) return; // pointerup and lostpointercapture both fire
    drag.current = null;
    document.body.style.cursor = "";
    document.body.style.userSelect = "";
    onDragEnd(d.editorPct);
  };
  return (
    // APG window splitter: focusable, and its value is the primary (editor)
    // pane's share. Pointer-only resizing was the gap Apple's split-view
    // guidance and WCAG 2.1.1 both name. The separator stays self-closing so
    // the keyboard pin can slice its attributes.
    <div
      role="separator"
      aria-orientation="vertical"
      aria-label="Resize preview"
      title="Drag to resize. Double-click to reset."
      aria-controls={controls}
      aria-valuenow={Math.round(editorPct)}
      // The value is the EDITOR's share; say both so "Resize preview" is not
      // read as the preview's width.
      aria-valuetext={`Editor ${Math.round(editorPct)}%, preview ${100 - Math.round(editorPct)}%`}
      aria-valuemin={100 - PREVIEW_PCT.max}
      aria-valuemax={100 - PREVIEW_PCT.min}
      tabIndex={0}
      onPointerDown={(e) => {
        if (e.button !== 0) return;
        e.preventDefault();
        // The shell's box, not the window: with the sidebar pinned a window
        // fraction moved the divider 80% as far as the pointer.
        const shell = e.currentTarget.parentElement!.getBoundingClientRect();
        drag.current = { left: shell.left, width: shell.width, editorPct };
        e.currentTarget.setPointerCapture(e.pointerId);
        document.body.style.cursor = "col-resize";
        document.body.style.userSelect = "none";
      }}
      onPointerMove={(e) => {
        const d = drag.current;
        if (!d) return;
        // Absolute: the divider stays under the pointer and a clamp cannot drift.
        d.editorPct = ((e.clientX - d.left) / d.width) * 100;
        onDrag(d.editorPct);
      }}
      onPointerUp={finish}
      onPointerCancel={finish}
      onLostPointerCapture={finish}
      onDoubleClick={onReset}
      onKeyDown={(e) => {
        // Alt/Cmd+Arrow is the browser's Back/Forward: let it through.
        if (e.altKey || e.ctrlKey || e.metaKey) return;
        if (onKey(e.key)) e.preventDefault();
      }}
      // `relative z-10`: the preview pane is positioned and paints over a
      // static sibling, which hid the right half of the focus ring. The
      // invisible before-element widens the 4px hit target.
      className="hover:bg-primary/20 focus-visible:bg-primary/40 focus-visible:ring-ring relative z-10 w-1 shrink-0 cursor-col-resize touch-none bg-transparent transition-colors outline-none before:absolute before:inset-y-0 before:-inset-x-1.5 before:content-[''] focus-visible:ring-2"
    />
  );
}
