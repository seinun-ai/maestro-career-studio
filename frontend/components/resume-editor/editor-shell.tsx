"use client";

import { useEffect, useState, type ReactNode } from "react";
import { ChevronLeft, ChevronRight, SlidersHorizontal } from "lucide-react";

import { Button } from "@/components/ui/button";

const DEFAULT_STORAGE_KEY = "baseResumeEditor";
const DEFAULT_PREVIEW_PCT = 45;
const MIN_PREVIEW_PCT = 25;
const MAX_PREVIEW_PCT = 70;

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
}) {
  const collapsedKey = `${storageKey}.previewCollapsed`;
  const widthKey = `${storageKey}.previewWidthPct`;
  const [collapsed, setCollapsed] = useState(false);
  const [fmtOpen, setFmtOpen] = useState(false);
  const [previewPct, setPreviewPct] = useState(DEFAULT_PREVIEW_PCT);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    const c = window.localStorage.getItem(collapsedKey);
    const w = window.localStorage.getItem(widthKey);
    // eslint-disable-next-line react-hooks/set-state-in-effect -- hydrating from localStorage after mount
    if (c === "1") setCollapsed(true);
    if (w) {
      const n = Number(w);
      if (Number.isFinite(n) && n >= MIN_PREVIEW_PCT && n <= MAX_PREVIEW_PCT) {
        setPreviewPct(n);
      }
    }
    setHydrated(true);
  }, [collapsedKey, widthKey]);

  useEffect(() => {
    if (!hydrated) return;
    window.localStorage.setItem(collapsedKey, collapsed ? "1" : "0");
  }, [collapsed, hydrated, collapsedKey]);

  useEffect(() => {
    if (!hydrated) return;
    window.localStorage.setItem(widthKey, String(previewPct));
  }, [previewPct, hydrated, widthKey]);

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
      <div className="relative flex min-h-0 w-full flex-1">
        <div className={leftClass}>{editor}</div>
        <button
          type="button"
          aria-label="Show PDF preview"
          onClick={() => setCollapsed(false)}
          className="bg-background hover:bg-muted text-muted-foreground hover:text-foreground absolute top-1/2 right-0 z-10 flex h-20 w-7 -translate-y-1/2 items-center justify-center gap-1 rounded-l-md border border-r-0 shadow-md transition-colors"
        >
          <ChevronLeft className="size-4" />
        </button>
      </div>
    );
  }

  return (
    <div className="flex min-h-0 w-full flex-1">
      <div className={leftOpenClass} style={{ width: `${100 - previewPct}%` }}>
        {editor}
      </div>
      <Splitter
        onDrag={(deltaPct) =>
          setPreviewPct((p) =>
            Math.min(MAX_PREVIEW_PCT, Math.max(MIN_PREVIEW_PCT, p - deltaPct)),
          )
        }
      />
      <div
        className="bg-muted/30 relative flex min-h-0 min-w-0 flex-col overflow-hidden border-l"
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
              aria-label="Hide PDF preview"
              onClick={() => setCollapsed(true)}
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
        <div className="min-h-0 flex-1 overflow-hidden">{preview}</div>
      </div>
    </div>
  );
}

function Splitter({ onDrag }: { onDrag: (deltaPct: number) => void }) {
  const start = (e: React.PointerEvent<HTMLDivElement>) => {
    e.preventDefault();
    const viewportW = window.innerWidth;
    let lastX = e.clientX;
    const move = (ev: PointerEvent) => {
      const deltaPx = ev.clientX - lastX;
      lastX = ev.clientX;
      onDrag((deltaPx / viewportW) * 100);
    };
    const up = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  };
  return (
    <div
      role="separator"
      aria-orientation="vertical"
      onPointerDown={start}
      className="hover:bg-primary/20 w-1 shrink-0 cursor-col-resize bg-transparent transition-colors"
    />
  );
}
