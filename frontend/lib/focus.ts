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

/**
 * Where focus goes when a list item disappears: the next item's first field or tabbable while it is still there,
 * else the previous one's, else the list's nearest `tabIndex={-1}` ancestor (else the main area). The siblings
 * and the landmark are read NOW, while the item is attached; the item itself is never the answer, because a
 * caller can ask while the item is still on its way out.
 */
export function focusSuccessor(item: Element | null | undefined): () => HTMLElement | null {
  const siblings = [item?.nextElementSibling, item?.previousElementSibling];
  const landmark = focusReturnPoint(
    item?.parentElement?.closest<HTMLElement>('[tabindex="-1"]') ?? document.getElementById(MAIN_CONTENT_ID),
  );
  return () => {
    const sibling = siblings.find((s): s is HTMLElement => s instanceof HTMLElement && s.isConnected);
    return sibling ? focusTarget(sibling) : landmark();
  };
}

/**
 * A Base UI `finalFocus` value for a return target. Base UI focuses a container's first tabbable child rather
 * than the container, so a `tabIndex={-1}` landmark (the studio's <main> after Load latest) is focused here once
 * the popup has gone, and only if focus fell to <body>. No target: Base UI's default.
 *
 * Base UI timing this depends on (1.4.1, `FloatingFocusManager`): a function `finalFocus` is read when the popup
 * UNMOUNTS, not when it opens, and Base UI's own return runs in a microtask queued after that read, so the
 * microtask here runs first and a `false` leaves it nothing to do. After a Base UI upgrade, re-check in the
 * browser: Load latest lands on the studio's <main>, Rebuild's Cancel on ⋯, a referral's Delete confirm on
 * Delete, archiving the last base résumé on the list.
 */
export function finalFocusOn(target: HTMLElement | null): HTMLElement | boolean {
  if (!target) return true;
  if (target.tabIndex >= 0) return target;
  queueMicrotask(() => focusIfDropped(target));
  return false;
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
