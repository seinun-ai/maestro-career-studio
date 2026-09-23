/**
 * Where focus goes when the element holding it disappears. DOM only, no React, so `node --test` runs
 * them against a stand-in document (`focus.test.ts`); the hooks in `hooks/use-focus-return.ts` call them.
 */

/** SidebarGutter's id: the skip link's target, the one `tabIndex={-1}` element every route shares. */
const MAIN_CONTENT_ID = "main-content";
export const FIELD =
  'input:not([type="hidden"]):not(:disabled), textarea:not(:disabled), select:not(:disabled)';
export const TABBABLE = `${FIELD}, button:not(:disabled), a[href], [tabindex]:not([tabindex="-1"])`;

/** Focus `target` only when focus has fallen to <body>: never take it from where the user put it. */
export function focusIfDropped(target: HTMLElement | null | undefined): void {
  const active = document.activeElement;
  if (active && active !== document.body) return;
  target?.focus({ preventScroll: true });
}

/**
 * Where focus goes back to if `el` disappears. The ancestors are read NOW, while `el` is attached: a removed
 * subtree has no path back to the document. The answer is `el` while it is still connected, else the nearest
 * `tabIndex={-1}` ancestor still connected (a panel that opted in), else the main area.
 */
export function focusReturnPoint(el: Element | null): () => HTMLElement | null {
  if (!(el instanceof HTMLElement) || el === document.body) return () => null;
  const chain: HTMLElement[] = [];
  for (
    let a = el.parentElement?.closest<HTMLElement>('[tabindex="-1"]');
    a;
    a = a.parentElement?.closest<HTMLElement>('[tabindex="-1"]')
  )
    chain.push(a);
  return () =>
    el.isConnected ? el : (chain.find((a) => a.isConnected) ?? document.getElementById(MAIN_CONTENT_ID));
}

/** The element when it takes focus itself, else its first text field, else its first tabbable. */
export function focusTarget(el: HTMLElement): HTMLElement {
  if (el.matches(TABBABLE)) return el;
  return el.querySelector<HTMLElement>(FIELD) ?? el.querySelector<HTMLElement>(TABBABLE) ?? el;
}

/** A field that can hold a draft only its blur commits: any text input, textarea or contenteditable. */
export function holdsDraft(el: Element | null): el is HTMLElement {
  return (
    el instanceof HTMLInputElement ||
    el instanceof HTMLTextAreaElement ||
    (el instanceof HTMLElement && el.isContentEditable)
  );
}
