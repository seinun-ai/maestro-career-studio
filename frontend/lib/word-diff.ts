export interface DiffToken {
  kind: "same" | "removed" | "added";
  text: string;
}

/** Word-level LCS diff for short texts (resume bullets / summaries). */
export function wordDiff(oldText: string, newText: string): DiffToken[] {
  const a = oldText.split(/\s+/).filter(Boolean);
  const b = newText.split(/\s+/).filter(Boolean);
  const m = a.length;
  const n = b.length;
  // lcs[i][j] = LCS length of a[i:], b[j:]
  const lcs: number[][] = Array.from({ length: m + 1 }, () =>
    new Array<number>(n + 1).fill(0),
  );
  for (let i = m - 1; i >= 0; i--) {
    for (let j = n - 1; j >= 0; j--) {
      lcs[i][j] =
        a[i] === b[j]
          ? lcs[i + 1][j + 1] + 1
          : Math.max(lcs[i + 1][j], lcs[i][j + 1]);
    }
  }
  const tokens: DiffToken[] = [];
  const push = (kind: DiffToken["kind"], text: string) => {
    const last = tokens[tokens.length - 1];
    if (last && last.kind === kind) last.text += ` ${text}`;
    else tokens.push({ kind, text });
  };
  let i = 0;
  let j = 0;
  while (i < m && j < n) {
    if (a[i] === b[j]) {
      push("same", a[i]);
      i++;
      j++;
    } else if (lcs[i + 1][j] >= lcs[i][j + 1]) {
      push("removed", a[i]);
      i++;
    } else {
      push("added", b[j]);
      j++;
    }
  }
  while (i < m) push("removed", a[i++]);
  while (j < n) push("added", b[j++]);
  return tokens;
}

/** A run of one side's text; `changed` marks what the other side lacks. */
export interface DiffSegment {
  text: string;
  changed: boolean;
}

// Words, single punctuation marks and runs of space, so "Snowflake," keeps "Snowflake" when ", Power BI" is added.
const TOKEN = /[\p{L}\p{N}_]+|\s+|[^\p{L}\p{N}_\s]/gu;
// Past this many LCS cells (two sides of ~500 tokens) the lines are marked whole, not word by word.
const MAX_CELLS = 250_000;

/**
 * A change's two sides as runs whose texts join back to each side exactly, for a diff drawn as two lines
 * (components/resume-editor/hunk-diff.tsx). A space between two changed runs joins them, so a rewritten
 * phrase reads as one mark.
 */
export function lineDiff(oldText: string, newText: string): { before: DiffSegment[]; after: DiffSegment[] } {
  const a = oldText.match(TOKEN) ?? [];
  const b = newText.match(TOKEN) ?? [];
  const m = a.length;
  const n = b.length;
  if (m * n > MAX_CELLS) {
    return { before: tidy(a.map((text) => ({ text, changed: true }))), after: tidy(b.map((text) => ({ text, changed: true }))) };
  }
  const lcs: number[][] = Array.from({ length: m + 1 }, () => new Array<number>(n + 1).fill(0));
  for (let i = m - 1; i >= 0; i--) {
    for (let j = n - 1; j >= 0; j--) {
      lcs[i][j] = a[i] === b[j] ? lcs[i + 1][j + 1] + 1 : Math.max(lcs[i + 1][j], lcs[i][j + 1]);
    }
  }
  const before: DiffSegment[] = [];
  const after: DiffSegment[] = [];
  let i = 0;
  let j = 0;
  while (i < m && j < n) {
    if (a[i] === b[j]) {
      before.push({ text: a[i++], changed: false });
      after.push({ text: b[j++], changed: false });
    } else if (lcs[i + 1][j] >= lcs[i][j + 1]) {
      before.push({ text: a[i++], changed: true });
    } else {
      after.push({ text: b[j++], changed: true });
    }
  }
  while (i < m) before.push({ text: a[i++], changed: true });
  while (j < n) after.push({ text: b[j++], changed: true });
  return { before: tidy(before), after: tidy(after) };
}

function tidy(tokens: DiffSegment[]): DiffSegment[] {
  const marked = merge(
    tokens.map((token, k) =>
      !token.changed && /^\s+$/.test(token.text) && tokens[k - 1]?.changed && tokens[k + 1]?.changed
        ? { ...token, changed: true }
        : token,
    ),
  );
  // A mark ends at its words: the spaces at its edges stay plain.
  return merge(
    marked.flatMap((run) => {
      if (!run.changed) return [run];
      const [, lead, core, trail] = /^(\s*)([\s\S]*?)(\s*)$/.exec(run.text) ?? ["", "", run.text, ""];
      return [
        { text: lead, changed: false },
        { text: core, changed: true },
        { text: trail, changed: false },
      ].filter((piece) => piece.text);
    }),
  );
}

function merge(runs: DiffSegment[]): DiffSegment[] {
  const out: DiffSegment[] = [];
  for (const run of runs) {
    const last = out[out.length - 1];
    if (last && last.changed === run.changed) last.text += run.text;
    else out.push({ ...run });
  }
  return out;
}
