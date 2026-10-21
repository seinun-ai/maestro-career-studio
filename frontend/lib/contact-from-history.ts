/**
 * "Fill from career history": which contact answers your career history's contact block gives
 * (`GET /api/kb/profile`), shared by Profile's Contact tile and Setup's form answers. Pure, so `node --test`
 * loads it (lib/contact-from-history.test.ts): it imports only types. It fills blanks only, never an
 * answer you gave.
 */
import type { KBProfileOut } from "./types";

type Contact = KBProfileOut["contact"] | undefined;

type ContactLocation = {
  city: string;
  state: string;
  country?: string;
};

const PLACE_SEGMENT = /^[\p{L}][\p{L}\p{M} .'-]*$/u;
const STATE_ABBREVIATION = /^[A-Za-z]{2}$/;

/** "Austin, TX" or "Austin, TX, USA" as city, state and country; anything else is not read (null). */
export function parseContactLocation(location: string | null | undefined): ContactLocation | null {
  if (typeof location !== "string") return null;

  const parts = location.split(",").map((part) => part.trim());
  if (parts.length !== 2 && parts.length !== 3) return null;

  const [city, state, country] = parts;
  if (
    !city ||
    !state ||
    !PLACE_SEGMENT.test(city) ||
    !STATE_ABBREVIATION.test(state) ||
    (parts.length === 3 && (!country || !PLACE_SEGMENT.test(country)))
  ) {
    return null;
  }

  return {
    city,
    state,
    ...(country ? { country } : {}),
  };
}

/** The personal-details answers the contact block holds, as [key, value] pairs (blank ones left out). */
export function resumeContactCandidates(contact: Contact): Array<[key: string, value: string]> {
  const name = contact?.name?.trim() ?? "";
  const [firstName = "", ...lastNameParts] = name ? name.split(/\s+/) : [];
  const location = parseContactLocation(contact?.location);
  const candidates: Array<[string, string | null | undefined]> = [
    ["first_name", firstName],
    ["last_name", lastNameParts.join(" ")],
    ["email", contact?.email],
    ["phone", contact?.phone],
    ["linkedin", contact?.linkedin],
    ["github", contact?.github],
    ["website", contact?.website],
    ["city", location?.city],
    ["state", location?.state],
    ["country", location?.country],
  ];

  return candidates.flatMap(([key, value]) => {
    const normalized = value?.trim();
    return normalized ? [[key, normalized]] : [];
  });
}

export function hasFillableContactDetails(contact: Contact): boolean {
  return resumeContactCandidates(contact).length > 0;
}

/** What a fill adds to `personal`: each answer the contact block has whose field is still blank. */
export function contactAdditions(personal: Record<string, unknown>, contact: Contact): Record<string, string> {
  return Object.fromEntries(
    resumeContactCandidates(contact).flatMap(([key, value]) => {
      const current = personal[key];
      return typeof current !== "string" || !current.trim() ? [[key, value]] : [];
    }),
  );
}
