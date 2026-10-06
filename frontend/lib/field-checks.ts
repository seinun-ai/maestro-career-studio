// Warnings for values the Companion types into real application forms (visual-language plan, Task 12).
// A warning never blocks a save: it says what looks off. Empty is not a warning; required-ness is the
// form's own business.

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;

export function emailWarning(value: string): string | null {
  const v = value.trim();
  if (!v || EMAIL.test(v)) return null;
  return "This doesn't look like an email address. Check it before a form uses it.";
}

export function phoneWarning(value: string): string | null {
  const digits = value.replace(/\D/g, "");
  if (!value.trim() || digits.length >= 7) return null;
  return "A phone number usually has at least 7 digits.";
}

export function linkWarning(value: string): string | null {
  const v = value.trim();
  if (!v) return null;
  if (/\s/.test(v) || !/\.[a-z]{2,}/i.test(v)) return "This doesn't look like a web address.";
  return null;
}
