/**
 * How the model cards read (components/settings/models-section.tsx, model-catalog-panel.tsx,
 * llm-endpoint.tsx). No imports: `node --test` loads it (model-catalog.test.ts). The API sends keys
 * (`openai`, `seed`); the screen shows words.
 */

// A Map, not an object: `{...}[provider]` answered "constructor" with a function.
const PROVIDER_LABELS = new Map([
  ["openai", "OpenAI"],
  ["anthropic", "Claude"],
  ["gemini", "Gemini"],
  ["openrouter", "OpenRouter"],
]);

/** Every provider the app can call, in the order the screen lists them. */
export const PROVIDERS = ["openai", "anthropic", "gemini", "openrouter"] as const;
export type Provider = (typeof PROVIDERS)[number];

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

/** Letters and digits only, lower-cased: "GPT-5.6 Luna" and "gpt-5.6-luna" read the same. */
function comparable(text: string): string {
  return text.toLowerCase().replace(/[^a-z0-9]/g, "");
}

const PROVIDER_WORDS = new Set(["openai", "gemini", "google", "anthropic", "claude", "openrouter"]);

/** The id is worth showing only when it says something the name does not: not when it is the name
 *  (a found OpenAI model is named by its id), nor the name without its provider ("OpenAI GPT-5.6 Luna",
 *  `gpt-5.6-luna`). */
export function showsModelId(option: { id: string; label: string }): boolean {
  const name = comparable(option.label);
  const id = comparable(option.id);
  if (name === id) return false;
  return !(name.endsWith(id) && PROVIDER_WORDS.has(name.slice(0, name.length - id.length)));
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

/** The slice of the settings payload `keyWarning` reads (lib/types.ts OpenAIInfo). */
export interface KeyState {
  api_key_configured: boolean;
  gemini_api_key_configured: boolean;
  anthropic_api_key_configured: boolean;
  openrouter_api_key_configured: boolean;
  custom_endpoint: boolean;
  model_options: { id: string; provider: string }[];
}

export const CONFIGURED: Record<
  Provider,
  "api_key_configured" | "anthropic_api_key_configured" | "gemini_api_key_configured" | "openrouter_api_key_configured"
> = {
  openai: "api_key_configured",
  anthropic: "anthropic_api_key_configured",
  gemini: "gemini_api_key_configured",
  openrouter: "openrouter_api_key_configured",
};

/** Set when the role's model runs on a provider with no saved key. A custom AI server takes the
 *  OpenAI key's place, so it silences the OpenAI warning only. A model the list lacks says nothing. */
export function keyWarning(roleLabel: string, model: string, state: KeyState): string | undefined {
  const provider = state.model_options.find((o) => o.id === model)?.provider;
  if (!provider || !(PROVIDERS as readonly string[]).includes(provider)) return undefined;
  const known = provider as Provider;
  if (state[CONFIGURED[known]] === true) return undefined;
  if (known === "openai" && state.custom_endpoint) return undefined;
  const name = providerLabel(known);
  return `${roleLabel} uses ${name}, but no ${name} key is saved.`;
}

/** The three everyday jobs as Settings › Basics names them: the role that does each, what its model
 *  must pass for it (the capability test's legs: CapabilityReport in lib/types.ts), and the words for
 *  a pass and a fail. The Reasoning model is not one: it runs only when the Companion is stuck. */
export const EVERYDAY_JOBS = [
  { role: "fast_model", words: "Reads jobs and documents", needs: ["json"], can: "reads jobs", cannot: "read jobs" },
  { role: "smart_model", words: "Tailors and writes", needs: ["text", "json"], can: "writes", cannot: "write" },
  { role: "chat_model", words: "Runs the Assistant", needs: ["tools"], can: "runs the Assistant", cannot: "run the Assistant" },
] as const;

type Capability = "text" | "json" | "tools";

/** The slice of the settings payload the AI model card reads (lib/types.ts OpenAIInfo). */
export interface EverydayState extends KeyState {
  fast_model: string;
  smart_model: string;
  chat_model: string;
  capabilities: Record<string, Partial<Record<Capability, boolean>>>;
}

/** Where the everyday jobs run, in the screen's provider order: a provider's name, or "your own AI
 *  server" for a model a custom server takes (an OpenAI-style model, or one the list lacks). */
export function runsOn(state: EverydayState): string[] {
  const where = new Set<string>();
  for (const job of EVERYDAY_JOBS) {
    const provider = state.model_options.find((o) => o.id === state[job.role])?.provider;
    if (state.custom_endpoint && (provider === undefined || provider === "openai")) where.add("custom");
    else if (provider) where.add(provider);
  }
  const order = [...PROVIDERS, "custom"] as readonly string[];
  return [...where]
    .sort((a, b) => order.indexOf(a) - order.indexOf(b))
    .map((p) => (p === "custom" ? "your own AI server" : providerLabel(p)));
}

/** The providers whose keys the everyday jobs use (a custom server's models use none of these). */
export function keysInUse(state: EverydayState): Provider[] {
  return PROVIDERS.filter((p) =>
    EVERYDAY_JOBS.some((job) => {
      const provider = state.model_options.find((o) => o.id === state[job.role])?.provider;
      return provider === p && !(p === "openai" && state.custom_endpoint);
    }),
  );
}

export type EverydayStatus =
  | { kind: "no-key"; words: string }
  | { kind: "untested"; words: string }
  | { kind: "cannot"; words: string }
  | { kind: "works"; words: string };

/** One status for the everyday jobs, worst first: a missing key, then a model never tested, then a
 *  job its model failed, else Works. Read from the saved test results only; nothing is guessed. */
export function everydayStatus(state: EverydayState): EverydayStatus {
  for (const job of EVERYDAY_JOBS) {
    const warning = keyWarning("", state[job.role], state);
    if (warning) {
      const provider = state.model_options.find((o) => o.id === state[job.role])?.provider ?? "";
      return { kind: "no-key", words: `Add your ${providerLabel(provider)} key` };
    }
  }
  if (EVERYDAY_JOBS.some((job) => !state.capabilities[state[job.role]])) {
    return { kind: "untested", words: "Not tested" };
  }
  const failed = EVERYDAY_JOBS.find((job) =>
    job.needs.some((need: Capability) => state.capabilities[state[job.role]][need] !== true),
  );
  if (failed) return { kind: "cannot", words: `Can't ${failed.cannot}` };
  return { kind: "works", words: "Works" };
}

/** What the everyday jobs' tested models can do, as the card's short line ("reads jobs · writes"). */
export function everydayCan(state: EverydayState): string[] {
  return EVERYDAY_JOBS.filter((job) => {
    const report = state.capabilities[state[job.role]];
    return report !== undefined && job.needs.every((need: Capability) => report[need] === true);
  }).map((job) => job.can);
}
