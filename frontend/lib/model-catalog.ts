/**
 * How a model list row reads (components/settings/model-catalog-panel.tsx). No imports:
 * `node --test` loads it (model-catalog.test.ts). The API sends keys (`openai`, `seed`); the
 * screen shows words.
 */
const PROVIDER_LABELS: Record<string, string> = { openai: "OpenAI", gemini: "Gemini" };

export function providerLabel(provider: string): string {
  return PROVIDER_LABELS[provider] ?? provider;
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
