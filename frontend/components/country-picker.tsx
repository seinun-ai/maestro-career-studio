"use client";

import { useMemo, useRef, useState } from "react";
import { Combobox } from "@base-ui/react/combobox";
import { useQuery } from "@tanstack/react-query";
import { CheckIcon, XIcon } from "lucide-react";

import { PICKER_ITEM_CLASS, PickerPopup } from "@/components/role-picker";
import { apiFetch } from "@/lib/api";
import { countryCodes, type CountryCodes } from "@/lib/autofill-options";
import type { Country } from "@/lib/types";

/** The country list, fetched once. It lives in backend/app/services/data/countries.yaml and is not
 *  copied here, for the reason `useRoleCategories` gives. */
export function useCountries({ enabled = true }: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: ["countries"],
    queryFn: () => apiFetch<Country[]>("/api/countries"),
    staleTime: 60 * 60 * 1000, // the list changes only on deploy
    enabled,
  });
}

/** The country list as names, aliases and codes to ISO codes (`countryCodes`), or null until it is read. */
export function useCountryCodes(): CountryCodes | null {
  const { data } = useCountries();
  return useMemo(() => (data ? countryCodes(data) : null), [data]);
}

/**
 * A searchable multi-select of countries, valued as ISO codes. `RolePicker`'s multiple mode without
 * its groups and its "add what I typed" row: a country is one of the list's or none.
 *
 * A stored entry that is a country's name, not its code (an older save or a hand edit: "India"), shows
 * as that country, and any change hands back codes in its place; an entry that names no country shows
 * as written.
 */
export function CountryPicker(props: {
  value: readonly string[];
  onChange: (codes: string[]) => void;
  /** A country's own words here, by code, in place of its name (Citizen of: "United Kingdom (British
   *  citizen)"). */
  names?: Readonly<Record<string, string>>;
  id?: string;
  /** The input's name. Base UI's input takes none from context here (conventions: Naming a control). */
  "aria-label": string;
  "aria-describedby"?: string;
  disabled?: boolean;
  /** While a change saves: nothing commits, but unlike `disabled` the input keeps focus. */
  readOnly?: boolean;
}) {
  const { data } = useCountries();
  const { names } = props;
  // The file is in code order; a reader looks a country up by its name.
  const countries = useMemo(
    () =>
      (data ?? [])
        .map((c) => ({ code: c.code, name: names?.[c.code] ?? c.name }))
        .sort((a, b) => a.name.localeCompare(b.name)),
    [data, names],
  );
  const byCode = useMemo(() => new Map(countries.map((c) => [c.code, c])), [countries]);
  const byName = useMemo(
    () => new Map((data ?? []).map((c) => [c.name.toLowerCase(), byCode.get(c.code) ?? c])),
    [data, byCode],
  );
  // A code the list lacks (or before it loads) still shows, as itself; so does a name it does not know.
  // Each country once: "IN" and "India" are one.
  const selected = [
    ...new Map(
      props.value.map((entry) => {
        const country = byCode.get(entry.toUpperCase()) ?? byName.get(entry.toLowerCase()) ?? { code: entry, name: entry };
        return [country.code, country] as const;
      }),
    ).values(),
  ];

  const [query, setQuery] = useState("");
  const popupRef = useRef<HTMLDivElement | null>(null);
  // Anchor the popup to the chips box, not the input, which wraps under the chips.
  const chipsRef = useRef<HTMLDivElement | null>(null);

  return (
    <Combobox.Root<Country, true>
      multiple
      disabled={props.disabled}
      readOnly={props.readOnly}
      items={countries}
      value={selected}
      onValueChange={(next) => props.onChange((next ?? []).map((c) => c.code))}
      inputValue={query}
      onInputValueChange={setQuery}
      itemToStringLabel={(c) => c.name}
      itemToStringValue={(c) => c.code}
      // Values are rebuilt on every render, so referential equality would never match.
      isItemEqualToValue={(a, b) => a.code === b.code}
      onOpenChangeComplete={(open) => {
        // Base UI scrolls to the last selection on open; a reader who clicked to browse starts at the top.
        if (open) popupRef.current?.scrollTo({ top: 0 });
      }}
    >
      <div ref={chipsRef}>
        <Combobox.Chips className="border-input focus-within:ring-ring flex min-h-9 flex-wrap items-center gap-1.5 rounded-corner-sm border bg-transparent px-2 py-1.5 text-body-medium focus-within:ring-2">
          {selected.map((country) => (
            <Combobox.Chip
              key={country.code}
              className="bg-muted text-foreground/90 inline-flex h-5 max-h-full items-center gap-1 rounded-full px-1.5 leading-none"
            >
              {country.name}
              <Combobox.ChipRemove
                aria-label={`Remove ${country.name}`}
                className="text-muted-foreground hover:text-foreground relative -mr-0.5 rounded-full after:absolute after:-inset-2 after:content-['']"
              >
                <XIcon className="size-3" />
              </Combobox.ChipRemove>
            </Combobox.Chip>
          ))}
          <Combobox.Input
            id={props.id}
            aria-label={props["aria-label"]}
            aria-describedby={props["aria-describedby"]}
            disabled={props.disabled}
            size={1}
            className="min-w-24 flex-1 bg-transparent outline-none"
            onKeyDown={(event) => {
              // Base UI clears the value on Escape while the list is closed and swallows the key, so
              // an Esc meant for the enclosing dialog would save no countries at all. Escape only
              // closes; a country is removed by its X or Backspace.
              if (
                event.key === "Escape" &&
                event.currentTarget.getAttribute("aria-expanded") !== "true"
              ) {
                event.preventBaseUIHandler();
              }
            }}
          />
        </Combobox.Chips>
      </div>
      <PickerPopup anchor={chipsRef} popupRef={popupRef}>
        <Combobox.List>
          {(country: Country) => (
            <Combobox.Item key={country.code} value={country} className={PICKER_ITEM_CLASS}>
              <span className="truncate">{country.name}</span>
              <Combobox.ItemIndicator>
                <CheckIcon className="size-4 shrink-0" />
              </Combobox.ItemIndicator>
            </Combobox.Item>
          )}
        </Combobox.List>
        {/* Stays mounted to announce reliably, so the message is what is conditional. */}
        <Combobox.Empty>
          <div className="text-muted-foreground px-2 py-1.5 text-body-medium">
            {query.trim() ? "No country matches." : "No countries to show."}
          </div>
        </Combobox.Empty>
      </PickerPopup>
    </Combobox.Root>
  );
}
