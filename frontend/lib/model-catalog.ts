/**
 * How the model cards read (components/settings/models-section.tsx, model-catalog-panel.tsx,
 * llm-endpoint.tsx). No imports: `node --test` loads it (model-catalog.test.ts). The API sends keys
 * (`openai`, `seed`); the screen shows words.
 */

// A Map, not an object: `{...}[provider]` answered "constructor" with a function.
const PROVIDER_LABELS = new Map([
  ["openai", "OpenAI"],
  ["gemini", "Gemini"],
]);

/** `open_router` → "Open Router": an unknown key still reads as a word. */
function titleCase(key: string): string {
  return key
    .split(/[\s_-]+/)
    .filter(Boolean)
    .map((word) => word[0].toUpperCase() + word.slice(1))
    .join(" ");
}

export function providerLabel(provider: string): string {
  return PROVIDER_LABELS.get(provider) ?? titleCase(provider);
}

/** `source` is absent on older payloads, which means a seed. */
export function sourceLabel(source: "seed" | "extra" | "configured" | undefined): string {
  if (source === "extra") return "Added";
  if (source === "configured") return "In use";
  return "Built-in";
}

/** The id is worth showing only when the name is not already it (a found OpenAI model is named by its id). */
export function showsModelId(option: { id: string; label: string }): boolean {
  return option.label.trim() !== option.id;
}

/** A model's name for a sentence or an accessible name; the id when the list lacks it. */
export function modelName(options: readonly { id: string; label: string }[], id: string): string {
  return options.find((option) => option.id === id)?.label ?? id;
}

/** This machine, as the browser or the backend container names it. `URL` keeps IPv6 in brackets. */
const LOCAL_HOSTS = new Set(["localhost", "127.0.0.1", "[::1]", "host.docker.internal"]);

/** True when the endpoint is neither empty nor a local address.
 *
 * Whatever is configured here receives the stored API key AND the prompt bodies (resume text, job
 * descriptions), because the OpenAI client is constructed with both. That is fine for a local
 * model server and worth one sentence of warning for anything else: the field accepts any host on
 * purpose, so the check is advisory, not a block. */
export function isRemoteEndpoint(raw: string): boolean {
  const value = raw.trim();
  if (!value) return false;
  try {
    const host = new URL(value).hostname;
    return !(LOCAL_HOSTS.has(host) || host.endsWith(".local"));
  } catch {
    return false; // not a parseable URL yet: the backend rejects it on save
  }
}
