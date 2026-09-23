"use client";

import {
  createContext,
  useCallback,
  useContext,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { focusIfDropped, focusReturnPoint } from "@/hooks/use-focus-return";

export interface ConfirmOptions {
  title: string;
  description?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  destructive?: boolean;
  /**
   * Where focus goes on close, when not the element that opened the confirm
   * (a menu item is gone by then). Null falls through to the default below.
   */
  returnFocus?: () => HTMLElement | null;
}

type ConfirmFn = (opts: ConfirmOptions) => Promise<boolean>;

/**
 * `finalFocus` for a return target. Base UI focuses a container's first
 * tabbable child rather than the container, so a `tabIndex={-1}` landmark
 * (the studio's <main> after Load latest) is focused here once the dialog has
 * gone, and only if focus fell to <body>. Nothing to name: Base UI's default.
 */
function returnTo(target: HTMLElement | null): HTMLElement | boolean {
  if (!target) return true;
  if (target.tabIndex >= 0) return target;
  queueMicrotask(() => focusIfDropped(target));
  return false;
}

const ConfirmContext = createContext<ConfirmFn | null>(null);

export function useConfirm(): ConfirmFn {
  const ctx = useContext(ConfirmContext);
  if (!ctx) {
    throw new Error("useConfirm must be used inside <ConfirmDialogProvider>");
  }
  return ctx;
}

export function ConfirmDialogProvider({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const [opts, setOpts] = useState<ConfirmOptions | null>(null);
  const resolverRef = useRef<((value: boolean) => void) | null>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);
  const confirmRef = useRef<HTMLButtonElement>(null);
  // Taken when the confirm OPENS: a confirmed action can remove its own opener
  // (Load latest remounts the editor), and Base UI's default then finds nothing
  // to return to and focus falls to <body>. This is the opener while it is
  // still connected, else the nearest `tabIndex={-1}` ancestor that survived.
  const returnPoint = useRef<() => HTMLElement | null>(() => null);

  const confirm = useCallback<ConfirmFn>((options) => {
    returnPoint.current = focusReturnPoint(document.activeElement);
    setOpts(options);
    setOpen(true);
    return new Promise<boolean>((resolve) => {
      resolverRef.current = resolve;
    });
  }, []);

  const finish = (value: boolean) => {
    setOpen(false);
    resolverRef.current?.(value);
    resolverRef.current = null;
  };

  return (
    <ConfirmContext.Provider value={confirm}>
      {children}
      <Dialog
        open={open}
        onOpenChange={(next) => {
          if (!next) finish(false);
          setOpen(next);
        }}
      >
        {/* initialFocus, not autoFocus: Base UI's Popup owns initial focus, so
            React's autoFocus prop never applied here. Opened from a dropdown
            menu, the menu's own focus restore won the race and focus stayed
            OUTSIDE the modal entirely — a keyboard user had to tab in from the
            top of the page. Naming the element makes it deterministic, and a
            destructive confirm lands on Cancel: the key that opened the dialog
            is the same one a reflex press sends, and these deletes are
            irreversible. */}
        <DialogContent
          showCloseButton={false}
          className="sm:max-w-md"
          initialFocus={opts?.destructive ? cancelRef : confirmRef}
          finalFocus={() => returnTo(opts?.returnFocus?.() ?? returnPoint.current())}
        >
          <DialogHeader>
            <DialogTitle>{opts?.title ?? ""}</DialogTitle>
            {opts?.description && (
              <DialogDescription>{opts.description}</DialogDescription>
            )}
          </DialogHeader>
          <DialogFooter>
            <Button
              ref={cancelRef}
              variant="outline"
              onClick={() => finish(false)}
            >
              {opts?.cancelLabel ?? "Cancel"}
            </Button>
            <Button
              ref={confirmRef}
              variant={opts?.destructive ? "destructive" : "default"}
              onClick={() => finish(true)}
            >
              {opts?.confirmLabel ?? "Confirm"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </ConfirmContext.Provider>
  );
}
