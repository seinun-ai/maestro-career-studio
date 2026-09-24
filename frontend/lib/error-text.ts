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
const MISSING_KEY = /\bno (?:openai |gemini )?api key\b|\b[A-Z]+_API_KEY is required\b/i;
const REFUSED_KEY = /invalid_api_key|incorrect api key|api key not valid|api_key_invalid|error code: 401\b/i;

/** The part of an error a user may read, or undefined. For a load error's `detail`. */
export function errorDetail(err: unknown): string | undefined {
  const message = err instanceof Error ? err.message.trim() : "";
  if (MISSING_KEY.test(message)) return "Add an API key in Settings › AI & models.";
  if (REFUSED_KEY.test(message)) return "Check your API key in Settings › AI & models.";
  return isPlainSentence(message) ? message : undefined;
}

/** "Couldn't save the resume. <detail, or Try again.>" for a toast. */
export function couldnt(what: string, err: unknown): string {
  return `Couldn't ${what}. ${errorDetail(err) ?? "Try again."}`;
}
