"use client";

import { useMemo, useRef, useState } from "react";
import { Combobox } from "@base-ui/react/combobox";
import { useQuery } from "@tanstack/react-query";
import { CheckIcon, XIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { apiFetch } from "@/lib/api";
import type { FavoredRole, RoleCategory, RoleMatch } from "@/lib/types";

/** A category and the specific roles nested under it, in the shape Base UI's
 *  grouped filtering wants (`items` is the part it filters). */
type RoleGroup = { key: string; label: string; items: FavoredRole[] };

/** MAX_LABEL_CHARS in backend/app/schemas/job_preferences.py, which `/match`
 *  bounds itself by too. Capping the input is what makes that 422 unreachable
 *  rather than merely survivable: an over-long label is REJECTED on save, not
 *  truncated, so the user would lose the entry rather than a few characters. */
export const MAX_ROLE_LABEL_CHARS = 80;

const ROLE_ITEM_CLASS =
  "flex cursor-default items-center justify-between gap-2 rounded-md px-2 py-1.5 text-sm outline-none select-none data-highlighted:bg-accent data-highlighted:text-accent-foreground";

/** The identity the server dedups on: the role key, else the folded label. */
export function roleIdentity(entry: FavoredRole) {
  return entry.role ?? `custom:${entry.label.toLowerCase()}`;
}

/**
 * Map a stored base-resume tag (`role_label` + `role_category`) onto the
 * FavoredRole shape the shared picker speaks. `unknown` with no label is empty.
 */
export function favoredRoleFromTag(
  roleCategory: string,
  roleLabel: string | null | undefined,
  categories?: RoleCategory[],
): FavoredRole | null {
  if (roleLabel) {
    return {
      role: null,
      label: roleLabel,
      // `other` is the unmapped projection, not a confirmed mapping the user
      // chose — keep category null so the chip and identity write match.
      category: roleCategory === "other" ? null : roleCategory,
    };
  }
  if (!roleCategory || roleCategory === "unknown") return null;
  const hit = categories?.find((c) => c.key === roleCategory);
  return {
    role: roleCategory,
    label: hit?.label ?? roleCategory,
    category: null,
  };
}

/**
 * Identity / create payload for a picker value. Catalog picks send the label
 * alone so the server can exact-match nested roles down to their parent;
 * free text carries an optional confirmed mapping.
 */
export function identityFromFavoredRole(entry: FavoredRole | null): {
  role_label: string | null;
  role_category?: string;
} {
  if (!entry) return { role_label: null, role_category: "unknown" };
  if (entry.role === null) {
    return entry.category
      ? { role_label: entry.label, role_category: entry.category }
      : { role_label: entry.label };
  }
  return { role_label: entry.label };
}

/**
 * The "add what I typed" row.
 *
 * Offered whenever the typed text is not ALREADY A CATALOG LABEL — deliberately
 * not "when the filter returned nothing". Two reasons that condition was wrong,
 * both found in the browser:
 *
 *  1. Base UI keeps SELECTED items in the filtered list so they can be toggled
 *     off, so once a single chip existed the list was never empty and the row
 *     never appeared again. Custom roles were addable only as the first entry.
 *  2. It also refused a custom role whose text is a substring of a catalog one
 *     — typing "Analytics" could not be added because "Analytics Engineer"
 *     survived the filter.
 *
 * Showing it alongside partial matches is the ordinary combobox contract: the
 * catalog suggestions and "use my words" are different offers, and the user
 * picks.
 */
function AddCustomRoleItem({
  label,
  alreadyAdded,
  isCatalogLabel,
}: {
  label: string;
  alreadyAdded: boolean;
  isCatalogLabel: boolean;
}) {
  // Offering a chip that already exists would not add a second one: Base UI
  // reads it as selected and the press would REMOVE it.
  if (!label || alreadyAdded || isCatalogLabel) return null;
  const entry: FavoredRole = { role: null, label, category: null };
  return (
    <Combobox.Item value={entry} className={ROLE_ITEM_CLASS}>
      <span className="truncate">
        Add <span className="font-medium">&ldquo;{label}&rdquo;</span>
      </span>
    </Combobox.Item>
  );
}

type RolePickerBase = {
  id?: string;
  className?: string;
  disabled?: boolean;
  placeholder?: string;
  /** When set, skip the internal vocabulary fetch (e.g. a parent already has it). */
  roleCategories?: RoleCategory[];
};

type RolePickerMultipleProps = RolePickerBase & {
  mode: "multiple";
  value: FavoredRole[];
  onValueChange: (next: FavoredRole[]) => void;
};

type RolePickerSingleProps = RolePickerBase & {
  mode: "single";
  value: FavoredRole | null;
  onValueChange: (next: FavoredRole | null) => void;
};

export type RolePickerProps = RolePickerMultipleProps | RolePickerSingleProps;

export function RolePicker(props: RolePickerProps) {
  // Same key as useRoleCategories — one vocabulary fetch shared app-wide.
  const rolesQuery = useQuery({
    queryKey: ["role-categories"],
    queryFn: () => apiFetch<RoleCategory[]>("/api/role-categories"),
    staleTime: 60 * 60 * 1000,
    enabled: props.roleCategories === undefined,
  });
  const roleCategories = props.roleCategories ?? rolesQuery.data;

  const groups = useMemo<RoleGroup[]>(
    () =>
      (roleCategories ?? [])
        // `other` and `unknown` are storage sentinels, not things anyone is
        // targeting — "Count this as Unknown?" is not a question worth asking.
        .filter((category) => !category.reserved)
        .map((category) => ({
          key: category.key,
          label: category.label,
          items: [
            // A category is its own role key server-side (`parent_of` returns
            // itself), so picking the whole group needs no special shape.
            { role: category.key, label: category.label, category: null },
            ...category.roles.map((role) => ({
              role: role.key,
              label: role.label,
              category: null,
            })),
          ],
        })),
    [roleCategories],
  );
  const catalogLabels = useMemo(() => {
    const labels = new Map<string, string>();
    // Reserved categories included: a preference stored before this picker
    // existed can carry `other`, and its chip still has to render.
    for (const category of roleCategories ?? []) {
      labels.set(category.key, category.label);
      for (const role of category.roles) labels.set(role.key, role.label);
    }
    return labels;
  }, [roleCategories]);
  const catalogLabel = (key: string | null) =>
    (key && catalogLabels.get(key)) || key || "";
  // Case-folded catalog labels, for deciding whether typed text is already a
  // real entry. An EXACT match is the only thing that should suppress the
  // "add my words" row — see AddCustomRoleItem for why a filter-emptiness test
  // was wrong in two separate ways.
  const catalogLabelSet = useMemo(
    () => new Set([...catalogLabels.values()].map((l) => l.toLowerCase())),
    [catalogLabels],
  );

  const selected = props.mode === "multiple" ? props.value : props.value ? [props.value] : [];

  const [query, setQuery] = useState("");
  const [suggestion, setSuggestion] = useState<{
    label: string;
    match: RoleMatch;
  } | null>(null);
  const pendingMatch = useRef<string | null>(null);
  // ComboboxRoot.onItemHighlighted: `undefined` means nothing is highlighted
  // (store activeIndex === null). A ref so Enter can read it without a render.
  const hasHighlightRef = useRef(false);
  // The label of the selection committed in THIS event, for single mode.
  // Base UI back-fills the input with the picked item's label
  // (fillInputOnItemPress is in ComboboxRoot's Omit<> list, so it cannot be
  // turned off), and comparing against props.value.label misses the first
  // pick: onInputValueChange fires before React re-renders with the new
  // value, so props.value is STALE during exactly the event that matters —
  // which is how "Data Platform Engineer" ended up as chip AND text.
  const justCommittedRef = useRef<string | null>(null);
  // Base UI scrolls the selected item into view when the popup opens, which
  // presents a mid-list, cut-off view to someone who just clicked to browse.
  const popupRef = useRef<HTMLDivElement | null>(null);
  // The visible chips box, not the collapsed <input>. Without an explicit
  // anchor, @base-ui falls through to the input — which this component
  // shrinks when a value is set in single mode, so the popup paints over
  // the page title in the editor header.
  const chipsRef = useRef<HTMLDivElement | null>(null);

  const requestMatch = (label: string) => {
    pendingMatch.current = label;
    apiFetch<RoleMatch>(
      `/api/role-categories/match?q=${encodeURIComponent(label)}`,
    )
      .then((match) => {
        // "none" is TRUTHY in JavaScript, so this compares against the string.
        if (pendingMatch.current !== label || match.confidence === "none") return;
        setSuggestion({ label, match });
      })
      // Enrichment, never a precondition: a failed or refused match leaves the
      // chip standing and says nothing. An unmapped role is a supported answer,
      // so there is no error here worth interrupting anyone for.
      .catch(() => undefined);
  };

  const commitRoles = (next: FavoredRole[]) => {
    if (props.mode === "multiple") {
      props.onValueChange(next);
    } else {
      props.onValueChange(next[0] ?? null);
      // Single mode renders the selection as a CHIP, so the input must not
      // also carry it — chip + text was the "multiple addition like field"
      // duplication reported from live use. Catalog selections arrive here
      // without passing addCustomLabel, so the clear belongs on the commit —
      // and the ref is what lets onInputValueChange reject the back-fill that
      // Base UI fires BEFORE React re-renders props.value.
      justCommittedRef.current = next[0]?.label ?? null;
      setQuery("");
    }
    // Base UI appends to the end in multiple-selection mode, so this is what
    // the user just picked. The chip is committed FIRST and enriched after: if
    // its existence depended on `/match`, a failed request would swallow their
    // typed text behind a toast.
    const added =
      next.length > selected.length ? next[next.length - 1] : null;
    if (added && added.role === null) {
      setSuggestion(null);
      requestMatch(added.label);
    }
  };

  const addCustomLabel = (label: string) => {
    const entry: FavoredRole = { role: null, label, category: null };
    if (props.mode === "multiple") {
      if (
        selected.some(
          (e) =>
            e.role === null && e.label.toLowerCase() === label.toLowerCase(),
        )
      ) {
        return;
      }
      commitRoles([...selected, entry]);
    } else {
      commitRoles([entry]);
    }
    setQuery("");
  };

  const confirmSuggestion = () => {
    if (!suggestion) return;
    const { label, match } = suggestion;
    setSuggestion(null);
    const mapped: FavoredRole = {
      role: match.role,
      label: catalogLabel(match.role) || label,
      category: match.category,
    };
    if (props.mode === "multiple") {
      const duplicate =
        match.role !== null &&
        selected.some((entry) => entry.role === match.role);
      commitRoles(
        duplicate
          ? selected.filter(
              (entry) => !(entry.role === null && entry.label === label),
            )
          : selected.map((entry) =>
              entry.role === null && entry.label === label ? mapped : entry,
            ),
      );
    } else {
      commitRoles([mapped]);
    }
  };

  // Only while the chip it is about still exists — removing that chip is as
  // good an answer as "Keep unmapped", and leaves nothing to ask about.
  const pendingSuggestion =
    suggestion &&
    selected.some(
      (entry) => entry.role === null && entry.label === suggestion.label,
    )
      ? suggestion
      : null;
  // An `alias` hit returns the user's own words as `label` (only `exact`
  // returns the catalog's) and the server derives the label for any entry
  // carrying a role — so confirming visibly renames the chip. Name it up front
  // rather than letting it change under them after the save.
  const suggestedLabel = pendingSuggestion
    ? catalogLabel(pendingSuggestion.match.role) || pendingSuggestion.label
    : "";

  const typed = query.trim();
  const alreadyAdded = selected.some(
    (entry) =>
      entry.role === null && entry.label.toLowerCase() === typed.toLowerCase(),
  );
  const isCatalogLabel = catalogLabelSet.has(typed.toLowerCase());
  const canAddCustom = Boolean(typed) && !alreadyAdded && !isCatalogLabel;

  const chipsClassName =
    props.className ??
    "border-input focus-within:ring-ring/50 flex min-h-9 flex-wrap items-center gap-1.5 rounded-md border bg-transparent px-2 py-1.5 text-sm focus-within:ring-2";

  const list = (
    <>
      <div ref={chipsRef}>
      <Combobox.Chips className={chipsClassName}>
        {selected.map((entry) => (
          <Combobox.Chip
            key={roleIdentity(entry)}
            className="bg-muted text-foreground/90 inline-flex items-center gap-1 rounded-md px-2 py-0.5"
          >
            {entry.label}
            {/* Only for a custom entry the user has since mapped: without
                it, confirming a category-only suggestion changes nothing
                they can see. A role-bearing chip already says it. */}
            {entry.role === null && entry.category !== null && (
              <span className="text-muted-foreground">
                · {catalogLabel(entry.category)}
              </span>
            )}
            {props.mode === "multiple" ? (
              <Combobox.ChipRemove
                aria-label={`Remove ${entry.label}`}
                className="text-muted-foreground hover:text-foreground relative -mr-0.5 rounded-sm after:absolute after:-inset-2 after:content-['']"
              >
                <XIcon className="size-3" />
              </Combobox.ChipRemove>
            ) : (
              // NOT ChipRemove: Base UI's chips model removal as filtering the
              // multiple-selection ARRAY, so in single mode the press lands in
              // a handler with no array to filter and nothing happens — the
              // "X doesn't delete" report from live use. A plain button wired
              // straight to the value is deterministic in both worlds.
              <button
                type="button"
                aria-label={`Remove ${entry.label}`}
                className="text-muted-foreground hover:text-foreground relative -mr-0.5 rounded-sm after:absolute after:-inset-2 after:content-['']"
                onClick={() => commitRoles([])}
              >
                <XIcon className="size-3" />
              </button>
            )}
          </Combobox.Chip>
        ))}
        <Combobox.Input
          id={props.id}
          disabled={props.disabled}
          maxLength={MAX_ROLE_LABEL_CHARS}
          placeholder={
            props.placeholder ??
            (selected.length === 0 ? "Search roles, or type your own…" : "")
          }
          // min-w-40 keeps a comfortable typing target — except in single mode
          // with a value, where 160px next to a wide chip cannot fit the
          // narrow dialog columns and flex-wrap drops the cursor onto a blank
          // second line. The selection is the content there; the input only
          // needs to exist for replace-by-typing, so it shrinks instead.
          className={
            props.mode === "single" && props.value
              ? "placeholder:text-muted-foreground min-w-0 flex-1 bg-transparent outline-none"
              : "placeholder:text-muted-foreground min-w-40 flex-1 bg-transparent outline-none"
          }
          onKeyDown={(event) => {
            // Backspace-on-empty clears the single selection, matching the
            // chips convention — Base UI's own Backspace handling is also
            // multiple-mode-only, for the same array-shaped reason as above.
            if (
              event.key === "Backspace" &&
              props.mode === "single" &&
              props.value &&
              query === ""
            ) {
              event.preventDefault();
              commitRoles([]);
              return;
            }
            if (event.key !== "Enter") return;
            // Highlighted item wins — Base UI selects it (ComboboxInput reads
            // store.state.activeIndex). We only commit free text when nothing
            // is highlighted (`onItemHighlighted` → undefined).
            if (hasHighlightRef.current) return;
            if (!canAddCustom) return;
            // preventDefault: Base UI closes the popup on Enter-with-no-
            // highlight but deliberately allows form submission; stop that.
            event.preventDefault();
            addCustomLabel(typed);
          }}
        />
      </Combobox.Chips>
      </div>
      <Combobox.Portal>
        <Combobox.Positioner
          anchor={chipsRef}
          sideOffset={4}
          className="isolate z-50"
        >
          <Combobox.Popup
            ref={popupRef}
            className="bg-popover text-popover-foreground ring-foreground/10 max-h-72 w-(--anchor-width) overflow-y-auto overscroll-contain rounded-lg p-1 shadow-md ring-1"
          >
            <Combobox.List>
              <Combobox.Collection>
                {(group: RoleGroup) => (
                  <Combobox.Group
                    key={group.key}
                    items={group.items}
                    className="scroll-my-1"
                  >
                    <Combobox.GroupLabel className="text-muted-foreground px-2 py-1 text-xs">
                      {group.label}
                    </Combobox.GroupLabel>
                    <Combobox.Collection>
                      {(entry: FavoredRole) => (
                        <Combobox.Item
                          key={entry.role}
                          value={entry}
                          className={ROLE_ITEM_CLASS}
                        >
                          <span className="truncate">
                            {/* The first item of every group IS its
                                category. Saying so beats repeating the
                                group label verbatim one line below it. */}
                            {entry.role === group.key
                              ? `Any ${group.label} role`
                              : entry.label}
                          </span>
                          <Combobox.ItemIndicator>
                            <CheckIcon className="size-4 shrink-0" />
                          </Combobox.ItemIndicator>
                        </Combobox.Item>
                      )}
                    </Combobox.Collection>
                  </Combobox.Group>
                )}
              </Combobox.Collection>
              <AddCustomRoleItem
                label={typed}
                alreadyAdded={alreadyAdded}
                isCatalogLabel={isCatalogLabel}
              />
            </Combobox.List>
            {/* Must stay mounted to announce reliably, so the message is
                what is conditional — and the padding rides on the message,
                not the wrapper, or the empty case leaves a blank strip.
                Covers only what the item above cannot: nothing typed and
                no catalog to show. */}
            <Combobox.Empty>
              {typed ? null : (
                <div className="text-muted-foreground px-2 py-1.5 text-sm">
                  No roles to show.
                </div>
              )}
            </Combobox.Empty>
          </Combobox.Popup>
        </Combobox.Positioner>
      </Combobox.Portal>
    </>
  );

  return (
    <div className="grid gap-1.5">
      {props.mode === "multiple" ? (
        <Combobox.Root<FavoredRole, true>
          multiple
          disabled={props.disabled}
          items={groups}
          value={props.value}
          onValueChange={(next) => commitRoles(next ?? [])}
          inputValue={query}
          onInputValueChange={setQuery}
          itemToStringLabel={(entry) => entry.label}
          itemToStringValue={roleIdentity}
          // Values are rebuilt from the catalog on every render, so referential
          // equality would never mark a selected item as selected.
          isItemEqualToValue={(a, b) => roleIdentity(a) === roleIdentity(b)}
          onItemHighlighted={(item) => {
            hasHighlightRef.current = item !== undefined;
          }}
          onOpenChangeComplete={(open) => {
            // Opening scrolled-to-the-last-selection reads as a glitch to
            // someone who clicked to browse: the list starts mid-scroll, cut
            // off. Base UI owns the scroll-into-view, so the reset happens
            // after the open completes.
            if (open) popupRef.current?.scrollTo({ top: 0 });
          }}
        >
          {list}
        </Combobox.Root>
      ) : (
        <Combobox.Root<FavoredRole, false>
          disabled={props.disabled}
          items={groups}
          value={props.value}
          onValueChange={(next) =>
            commitRoles(next ? [next as FavoredRole] : [])
          }
          inputValue={query}
          onInputValueChange={(value) => {
            // Base UI back-fills the input with the selected item's label in
            // single-selection mode. The chip already says it; accepting the
            // back-fill re-creates the chip+text duplication — worse, the
            // echoed text was COUPLED to the selection, so deleting it also
            // deleted the chip. Two rejections: the just-committed ref (the
            // same event; props.value is still stale) and the settled value
            // (re-fills on blur/reopen). Only user typing gets through.
            if (
              value === justCommittedRef.current ||
              (props.value && value === props.value.label)
            ) {
              setQuery("");
              return;
            }
            justCommittedRef.current = null;
            setQuery(value);
          }}
          itemToStringLabel={(entry) => entry.label}
          itemToStringValue={roleIdentity}
          isItemEqualToValue={(a, b) => roleIdentity(a) === roleIdentity(b)}
          onItemHighlighted={(item) => {
            hasHighlightRef.current = item !== undefined;
          }}
          onOpenChangeComplete={(open) => {
            // Opening scrolled-to-the-last-selection reads as a glitch to
            // someone who clicked to browse: the list starts mid-scroll, cut
            // off. Base UI owns the scroll-into-view, so the reset happens
            // after the open completes.
            if (open) popupRef.current?.scrollTo({ top: 0 });
          }}
        >
          {list}
        </Combobox.Root>
      )}
      {pendingSuggestion && (
        <div className="flex flex-wrap items-center gap-2 rounded-md border border-dashed px-2.5 py-2 text-xs">
          <span>
            Count &ldquo;{pendingSuggestion.label}&rdquo; as{" "}
            {catalogLabel(pendingSuggestion.match.category)}?
          </span>
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={confirmSuggestion}
          >
            Yes, use &ldquo;{suggestedLabel}&rdquo;
          </Button>
          {/* Dismissal is an end state, not a deferral: an unmapped role
              still reaches the brief and the agent prompts as words. */}
          <Button
            type="button"
            size="sm"
            variant="ghost"
            onClick={() => setSuggestion(null)}
          >
            Keep unmapped
          </Button>
        </div>
      )}
    </div>
  );
}
