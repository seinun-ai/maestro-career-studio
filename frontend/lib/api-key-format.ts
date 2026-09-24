/**
 * A typed API key's one check before it is saved: the shape each provider issues. Saving never
 * calls the provider, so a key in the right shape is "checked on first use", never "working".
 * Pure, so lib/api-key-format.test.ts runs it under `node --test`; pinned by
 * test_frontend_settings_assistant_words.py.
 */

export type KeyProvider = "openai" | "gemini";

const SHAPE: Record<KeyProvider, { prefix: string; named: string }> = {
  openai: { prefix: "sk-", named: "An OpenAI" },
  gemini: { prefix: "AIza", named: "A Gemini" },
};

/** Why this key can't be right, or undefined. An empty field removes the key; a custom AI server's
 *  key (sent as the OpenAI key) has whatever shape that server gives it. */
export function keyFormatProblem(
  provider: KeyProvider,
  key: string,
  customServer: boolean,
): string | undefined {
  const typed = key.trim();
  if (!typed || (provider === "openai" && customServer)) return undefined;
  const { prefix, named } = SHAPE[provider];
  return typed.startsWith(prefix)
    ? undefined
    : `${named} API key starts with ${prefix}. Check that you copied the whole key.`;
}

/** The toast after Save: what changed, and that a new key is checked on first use. */
export function keysSavedText(patch: { openai_api_key?: string | null; gemini_api_key?: string | null }): string {
  const sent = [patch.openai_api_key, patch.gemini_api_key].filter((k) => k !== undefined);
  const added = sent.filter((k) => k).length;
  if (added === 0) return sent.length > 1 ? "API keys removed." : "API key removed.";
  return added > 1
    ? "API keys saved. We'll check them on first use."
    : "API key saved. We'll check it on first use.";
}
