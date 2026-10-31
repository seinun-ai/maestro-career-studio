"use client";

import { CountryPicker } from "@/components/country-picker";

/** Citizen of names the United Kingdom by the citizenship its forms mean (British citizen, not every British
 *  nationality). */
export const CITIZEN_NAMES: Readonly<Record<string, string>> = { GB: "United Kingdom (British citizen)" };

/** What a citizenship does, said under "Citizen of" wherever it is asked. */
export const CITIZEN_HINT = "Where your citizenship lets you work in a country without a permit, its work-permit answers follow from it.";

/** Citizen of: a country picker valued as ISO codes, the United Kingdom read as British citizen. Profile's
 *  Country answers and Next up ask it, and Setup's answers step. */
export function CitizenshipPicker({
  id,
  label,
  value,
  onChange,
  describedBy,
}: {
  id: string;
  label: string;
  value: readonly string[];
  onChange: (codes: string[]) => void;
  describedBy?: string;
}) {
  return (
    <CountryPicker
      id={id}
      aria-label={label}
      aria-describedby={describedBy}
      names={CITIZEN_NAMES}
      value={value}
      onChange={onChange}
    />
  );
}
