/**
 * Words for a snake_case key when no label is at hand: a role category before
 * `/api/role-categories` answers (or after it fails), or a base resume's slug.
 * Pure, so `node --test` runs it (lib/humanize-slug.test.ts).
 *
 * Title case gets acronyms wrong ("Ai Ml Engineer", "Mlops Engineer"), so the
 * tokens the role catalog spells differently are listed here. The catalog in
 * backend/app/services/ats/data/role_categories.yaml stays the only list of
 * roles; this is only their casing, and `test_frontend_analytics.py` fails when
 * the catalog gains a token this map does not case.
 */
const TOKEN_CASE: Record<string, string> = {
  ai: "AI",
  bi: "BI",
  devrel: "DevRel",
  it: "IT",
  ml: "ML",
  mlops: "MLOps",
  qa: "QA",
  ui: "UI",
  ux: "UX",
};

/** Adjacent tokens written as one slash pair ("AI/ML Engineer"). */
const SLASH_PAIRS = new Set(["ai_ml", "ui_ux"]);

export function humanizeSlug(key: string | null | undefined): string {
  const tokens = (key ?? "").split("_").filter(Boolean);
  const words: string[] = [];
  tokens.forEach((token, i) => {
    const word = TOKEN_CASE[token] ?? token.charAt(0).toUpperCase() + token.slice(1);
    if (i > 0 && SLASH_PAIRS.has(`${tokens[i - 1]}_${token}`)) {
      words[words.length - 1] += `/${word}`;
    } else {
      words.push(word);
    }
  });
  // Never blank: a chart label or filter option with no text is worse than this.
  return words.join(" ") || "Unknown";
}
