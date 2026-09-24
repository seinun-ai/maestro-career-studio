/**
 * The words for a failure (docs/frontend-conventions.md, Microcopy rules,
 * *Errors*): what failed, then what to do. A thrown message is shown only when
 * it is a plain sentence written for the user: the server's plain details
 * (appendix D9 rewrites every one a user can reach), the sentences lib/api.ts
 * writes for a network failure or a rejected form, and the app's own
 * `throw new Error("Choose a file first.")`. JSON, schema paths, status codes,
 * lowercase developer text and stack words never are. Pure (no imports), so
 * lib/error-text.test.ts runs it under `node --test`; pinned by
 * test_frontend_error_words.py.
 */

/** Starts with a capital, ends with a stop, and holds nothing that looks like code. */
export function isPlainSentence(text: string): boolean {
  const t = text.trim();
  return t.length > 0 && t.length <= 240 && /^[A-Z][^{}[\]<>_`|\\]*[.!?]$/.test(t);
}

// The server's API key failures (backend/app/services/llm.py), which name an
// environment variable or quote a provider's 401, so no plain-sentence check
// lets them through; every caller then said only "Try again", which never helps.
// REFUSED_KEY also covers the server's own sentences for a refused key: today's
// "<Provider> refused your API key. …" (`_no_answer`) and the older "The AI model
// didn't answer (your key was refused). …". Both are exported as the one source the
// Companion's copy is pinned equal to (backend/tests/test_frontend_settings_assistant_words.py).
export const MISSING_KEY = /\bno (?:openai |gemini )?api key\b|\b[A-Z]+_API_KEY is required\b/i;
export const REFUSED_KEY =
  /invalid_api_key|incorrect api key|api key not valid|api_key_invalid|error code: 401\b|your key was refused|refused your api key/i;
// Who refused it, for the sentence: each provider's own words for a refused key.
const GEMINI_WORDS = /gemini|api key not valid|api_key_invalid/i;
const OPENAI_WORDS = /openai|invalid_api_key|incorrect api key/i;

function refusedKey(message: string): string | undefined {
  if (!REFUSED_KEY.test(message)) return undefined;
  // The server already said who, in a sentence ("OpenAI refused your API key. Check it in …").
  if (/refused your api key/i.test(message) && isPlainSentence(message)) return message;
  const who = GEMINI_WORDS.test(message) ? "Gemini" : OPENAI_WORDS.test(message) ? "OpenAI" : "The AI provider";
  return `${who} refused your API key. Check it in Settings › AI & models.`;
}

/** The part of an error a user may read, or undefined. For a toast (`couldnt`). */
export function errorDetail(err: unknown): string | undefined {
  const message = err instanceof Error ? err.message.trim() : "";
  if (MISSING_KEY.test(message)) return "Add an API key in Settings › AI & models.";
  return refusedKey(message) ?? (isPlainSentence(message) ? message : undefined);
}

// lib/api.ts's words for the generic failure: true of every status, so a load error says more.
const GENERIC = "Something went wrong. Try again.";
const OUR_SIDE = "Something went wrong on our side. Try again.";

/** An ApiError's status and body (lib/api.ts), read by shape: this file imports nothing. */
function statusOf(err: unknown): { status?: number; body?: unknown } {
  if (typeof err !== "object" || err === null) return {};
  const { status, body } = err as { status?: unknown; body?: unknown };
  return { status: typeof status === "number" ? status : undefined, body };
}

/** A 422 on a read is a link whose id is malformed: FastAPI names a `path` field. */
function isPathError(body: unknown): boolean {
  const detail = (body as { detail?: unknown } | null)?.detail;
  return Array.isArray(detail) && detail.some((d) => (d as { loc?: unknown[] })?.loc?.[0] === "path");
}

/**
 * The sentence under a load error: why it failed, then what to do. Only a failure to reach the app
 * (lib/api.ts, or the proxy's 502) says to check that it's running; a running app answered, so a 404
 * is a deleted `thing` ("job", "application"), a malformed id is a wrong link, and a 5xx is ours.
 * Without a `thing` (a list), a 404 or 422 is not the user's doing either.
 */
export function loadErrorDetail(err: unknown, thing?: string): string {
  const { status, body } = statusOf(err);
  if (thing && status === 404) return `This ${thing} may have been deleted.`;
  if (thing && status === 422 && isPathError(body)) {
    return `This link doesn't point to ${/^[aeiou]/i.test(thing) ? "an" : "a"} ${thing}.`;
  }
  const detail = errorDetail(err);
  if (detail && detail !== GENERIC && !(status === 404 || status === 422)) return detail;
  return OUR_SIDE;
}

/** "Couldn't save the resume. <detail, or Try again.>" for a toast. */
export function couldnt(what: string, err: unknown): string {
  return `Couldn't ${what}. ${errorDetail(err) ?? "Try again."}`;
}
