/**
 * Plain words for a typed resume edit ("Rewrite bullet 2 of Data Scientist at
 * Acme"), never the op (`replace_bullet · experience[0].bullets[1]`). Chat's
 * suggestion card and the studio's Ask for changes sheet both list ops with it.
 *
 * Pure, so `node --test` runs it (lib/describe-edit.test.ts). The vocabulary is
 * backend/app/schemas/resume_edit.py; test_frontend_plain_words.py fails when a
 * kind there has no `case` here.
 *
 * Ops apply IN ORDER (resume_edit.apply_edits), so op 2's indices point into
 * the document op 1 left behind. `describeEdits` keeps working copies of the
 * arrays an op can shift. It never guesses: with no document, or an index the
 * document does not have, the words name the section and not the entry.
 */

type Section = "experience" | "projects" | "education";

const SECTION_WORD: Record<Section, string> = {
  experience: "Experience",
  projects: "Projects",
  education: "Education",
};

const PREVIEW_CHARS = 90;

export type EditOp = Record<string, unknown>;

/** The document the ops apply to. Loose on purpose: an application's
 *  customized_json is untyped, and a malformed field must not throw. */
export interface ResumeLike {
  experience?: unknown;
  projects?: unknown;
  education?: unknown;
  skills?: unknown;
  extra_sections?: unknown;
}

export interface EditWords {
  /** What happens, and to which part: "Remove Analyst at Foo". */
  action: string;
  /** The new (or removed) text, shortened; null when there is none. */
  detail: string | null;
}

function text(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function short(value: unknown): string | null {
  const joined = Array.isArray(value)
    ? value.map(text).filter((t): t is string => t !== null).join(", ")
    : text(value);
  if (!joined) return null;
  return joined.length > PREVIEW_CHARS ? `${joined.slice(0, PREVIEW_CHARS)}…` : joined;
}

function position(value: unknown): number | null {
  return typeof value === "number" && Number.isInteger(value) && value >= 0 ? value : null;
}

function field(obj: unknown, key: string): unknown {
  return obj && typeof obj === "object" ? (obj as Record<string, unknown>)[key] : undefined;
}

function isSection(value: unknown): value is Section {
  return value === "experience" || value === "projects" || value === "education";
}

function pair(first: unknown, second: unknown): string | null {
  const a = text(first);
  const b = text(second);
  return a && b ? `${a} at ${b}` : (a ?? b);
}

/** How a person names an entry: "Data Scientist at Acme", "Churn model". */
export function entryName(section: Section, entry: unknown): string | null {
  if (section === "experience") return pair(field(entry, "role"), field(entry, "company"));
  if (section === "projects") return text(field(entry, "name"));
  return pair(field(entry, "degree"), field(entry, "institution"));
}

/** Working copies of every array an op can shift or rename. */
interface Shadow {
  known: boolean;
  entries: Record<Section, unknown[]>;
  extras: unknown[];
  skills: unknown[];
}

function shadowOf(doc: ResumeLike | null | undefined): Shadow {
  const list = (value: unknown) => (Array.isArray(value) ? [...value] : []);
  return {
    known: doc != null,
    entries: {
      experience: list(doc?.experience),
      projects: list(doc?.projects),
      education: list(doc?.education),
    },
    extras: list(doc?.extra_sections),
    skills: list(doc?.skills),
  };
}

function bulletsOf(entry: unknown): unknown[] {
  const bullets = field(entry, "bullets");
  return Array.isArray(bullets) ? bullets : [];
}

function sameKey(a: unknown, b: unknown): boolean {
  const x = text(a);
  const y = text(b);
  return x !== null && y !== null && x.toLowerCase() === y.toLowerCase();
}

function extraIndex(s: Shadow, key: unknown): number {
  return s.extras.findIndex((section) => sameKey(field(section, "key"), key));
}

function skillGroup(s: Shadow, category: unknown): unknown {
  return s.skills.find((group) => sameKey(field(group, "category"), category));
}

function describeOne(op: EditOp, s: Shadow): EditWords {
  const section = isSection(op.section) ? op.section : null;
  const sectionWord = section ? SECTION_WORD[section] : "the resume";
  const index = position(op.index);
  const entry = section && index !== null ? s.entries[section][index] : undefined;
  const name = section ? entryName(section, entry) : null;
  // Hidden rows are in the data but not on the PDF: say so, or "Remove
  // Analyst at Foo" reads like a mistake.
  const hidden = field(entry, "enabled") === false;
  const target = name ? `${name}${hidden ? " (hidden)" : ""}` : null;
  const bulletNo = position(op.bullet_index);
  // An ordinal only for a bullet the entry has: the dry run proved it at
  // propose time, but the document may have moved since.
  const bulletText = bulletNo !== null ? bulletsOf(entry)[bulletNo] : undefined;
  const bullet =
    target && bulletNo !== null && bulletText !== undefined
      ? `bullet ${bulletNo + 1} of ${target}`
      : null;
  const extraAt = extraIndex(s, op.section_key);
  const extraTitle =
    text(field(s.extras[extraAt], "title")) ?? text(field(op.value, "title"));
  const extra = extraTitle ? `the ${extraTitle} section` : "another section";

  switch (op.kind) {
    case "replace_summary": {
      const detail = short(op.value);
      return detail
        ? { action: "Rewrite the summary", detail }
        : { action: "Remove the summary", detail: null };
    }
    case "toggle_entry":
      return op.enabled === false
        ? { action: `Hide ${name ?? `an item in ${sectionWord}`} from the PDF`, detail: null }
        : { action: `Show ${name ?? `an item in ${sectionWord}`} on the PDF`, detail: null };
    case "replace_bullet":
      return {
        action: bullet ? `Rewrite ${bullet}` : `Rewrite a bullet in ${sectionWord}`,
        detail: short(op.value),
      };
    case "add_bullet":
      return {
        action: target ? `Add a bullet to ${target}` : `Add a bullet in ${sectionWord}`,
        detail: short(op.text),
      };
    case "remove_bullet":
      return {
        action: bullet ? `Remove ${bullet}` : `Remove a bullet in ${sectionWord}`,
        detail: short(bulletText),
      };
    case "add_entry": {
      const added = section ? entryName(section, op.value) : null;
      return {
        action: added ? `Add ${added} to ${sectionWord}` : `Add an item to ${sectionWord}`,
        detail: null,
      };
    }
    case "replace_entry":
      return { action: target ? `Edit ${target}` : `Edit an item in ${sectionWord}`, detail: null };
    case "remove_entry":
      return { action: target ? `Remove ${target}` : `Remove an item from ${sectionWord}`, detail: null };
    case "replace_skills_group": {
      const category = text(field(skillGroup(s, op.category), "category")) ?? text(op.category);
      return {
        action: category ? `Replace the ${category} skills` : "Replace a skill group",
        detail: short(op.items),
      };
    }
    case "add_skill_item": {
      const item = text(op.item) ?? "a skill";
      const group = skillGroup(s, op.category);
      const category = text(field(group, "category")) ?? text(op.category);
      if (!category) return { action: `Add ${item} to the skills`, detail: null };
      // "New" only when the document is known to lack the group.
      return s.known && group === undefined
        ? { action: `Add ${item} to a new ${category} skill group`, detail: null }
        : { action: `Add ${item} to the ${category} skills`, detail: null };
    }
    case "replace_contact":
      return { action: "Update the contact details", detail: null };
    case "replace_certifications": {
      const detail = short(op.items);
      return detail
        ? { action: "Replace the certifications", detail }
        : { action: "Remove all certifications", detail: null };
    }
    case "add_extra_section": {
      const title = text(field(op.value, "title"));
      return { action: title ? `Add the ${title} section` : "Add another section", detail: null };
    }
    case "replace_extra_section":
      return { action: `Rewrite ${extra}`, detail: null };
    case "remove_extra_section":
      return { action: `Remove ${extra}`, detail: null };
    case "move_extra_section": {
      const to = position(op.to_index);
      const last = s.extras.length - 1;
      const where =
        extraAt < 0 || to === null || to === extraAt
          ? ""
          : to === 0
            ? " to the top"
            : to === last
              ? " to the bottom"
              : to < extraAt
                ? " up"
                : " down";
      return { action: `Move ${extra}${where}`, detail: null };
    }
    default:
      // A kind this file does not know yet: plain words, never the key.
      return { action: section ? `Change ${sectionWord}` : "Change the resume", detail: null };
  }
}

/** Mirror the op's effect on the working copies, so the next op's indices
 *  land where the backend's will. Copy on write: `doc` is the query cache. */
function advance(op: EditOp, s: Shadow): void {
  const section = isSection(op.section) ? op.section : null;
  const index = position(op.index);
  const list = section ? s.entries[section] : null;
  const entry = list && index !== null ? list[index] : undefined;
  const withBullets = (bullets: unknown[]) => ({ ...(entry as object), bullets });
  switch (op.kind) {
    case "add_entry":
      list?.push(op.value);
      return;
    case "replace_entry":
      if (list && index !== null && index < list.length) list[index] = op.value;
      return;
    case "remove_entry":
      if (list && index !== null && index < list.length) list.splice(index, 1);
      return;
    case "toggle_entry":
      if (list && index !== null && entry !== undefined)
        list[index] = { ...(entry as object), enabled: op.enabled };
      return;
    case "add_bullet":
      if (list && index !== null && entry !== undefined)
        list[index] = withBullets([...bulletsOf(entry), op.text]);
      return;
    case "replace_bullet":
    case "remove_bullet": {
      const b = position(op.bullet_index);
      if (!list || index === null || entry === undefined || b === null) return;
      const bullets = [...bulletsOf(entry)];
      if (op.kind === "remove_bullet") bullets.splice(b, 1);
      else bullets[b] = op.value;
      list[index] = withBullets(bullets);
      return;
    }
    case "add_skill_item":
      if (skillGroup(s, op.category) === undefined)
        s.skills.push({ category: op.category, items: [op.item] });
      return;
    case "add_extra_section":
      s.extras.push(op.value);
      return;
    case "replace_extra_section": {
      const at = extraIndex(s, op.section_key);
      if (at >= 0) s.extras[at] = op.value;
      return;
    }
    case "remove_extra_section": {
      const at = extraIndex(s, op.section_key);
      if (at >= 0) s.extras.splice(at, 1);
      return;
    }
    case "move_extra_section": {
      const at = extraIndex(s, op.section_key);
      const to = position(op.to_index);
      if (at >= 0 && to !== null) s.extras.splice(to, 0, ...s.extras.splice(at, 1));
      return;
    }
  }
}

/** One line of words per op, in order. Pass the document the ops will apply
 *  to (the server copy, not an unsaved form), or nothing for words without
 *  entry names: a resolved card's ops no longer match the current document. */
export function describeEdits(
  ops: readonly EditOp[],
  doc?: ResumeLike | null,
): EditWords[] {
  const shadow = shadowOf(doc);
  return ops.map((op) => {
    const words = describeOne(op, shadow);
    advance(op, shadow);
    return words;
  });
}

// Where a check failed, in the user's words. The studios' Save and the code
// view check the resume against its schema; a raw path (`experience.2.bullets.0`)
// never reaches the screen, it reads as a place.
const PATH_SECTION: Record<string, string> = {
  contact: "Contact",
  summary: "Summary",
  skills: "Skills",
  experience: "Experience",
  projects: "Projects",
  education: "Education",
  certifications: "Certifications",
  extra_sections: "Other sections",
};

// What a numbered row is called inside its list.
const ROW_NOUN: Record<string, string> = {
  bullets: "bullet",
  skills: "group",
  items: "skill",
  certifications: "certification",
  coursework: "course",
  extra_sections: "section",
};

// Lists whose name the row's noun already says ("bullet 2", not "bullets, bullet 2").
const SILENT_LISTS = new Set(["bullets", "items", "entries", "coursework"]);

// A field by the label its editor shows (contact-form, the experience,
// project, education, skills and other-sections editors): "School", never
// "institution". `test_frontend_resume_review.py` holds each word to a label on
// screen.
const FIELD_WORDS: Record<string, string> = {
  name: "Name",
  email: "Email",
  phone: "Phone",
  location: "Location",
  linkedin: "LinkedIn",
  github: "GitHub",
  website: "Website",
  company: "Company",
  role: "Role",
  start_date: "Start date",
  end_date: "End date",
  institution: "School",
  degree: "Degree",
  field: "Field of study",
  graduation_date: "Graduation date",
  gpa: "GPA",
  tech: "Tools used",
  link: "Link",
  date: "Date",
  category: "Group name",
  heading: "Heading",
  subheading: "Subheading",
  title: "Section name",
  type: "Layout",
};

/** One failed field as words: `["experience", 2, "bullets", 0]` reads
 *  "Experience, item 3, bullet 1". Never prints a key, a dot or an index from 0. */
export function describeFieldPath(path: readonly PropertyKey[]): string {
  const words: string[] = [];
  let parent = "";
  for (const seg of path) {
    if (typeof seg === "number") {
      words.push(`${ROW_NOUN[parent] ?? "item"} ${seg + 1}`);
    } else if (typeof seg === "string") {
      if (words.length === 0) words.push(PATH_SECTION[seg] ?? seg.replace(/_/g, " "));
      else if (!SILENT_LISTS.has(seg)) words.push(FIELD_WORDS[seg] ?? seg.replace(/_/g, " "));
      parent = seg;
    }
  }
  const joined = words.join(", ");
  return joined ? joined.charAt(0).toUpperCase() + joined.slice(1) : "The resume";
}

/** "Some fields need fixing: Experience, item 3, bullet 1." for a failed
 *  save: the places, deduplicated, at most three. */
export function fieldsNeedFixing(paths: readonly (readonly PropertyKey[])[]): string {
  const places = [...new Set(paths.map(describeFieldPath))];
  const shown = places.slice(0, 3).join(". ");
  const more = places.length > 3 ? `. And ${places.length - 3} more` : "";
  return `Some fields need fixing: ${shown}${more}.`;
}

/** A schema check's failure, as the code view reports it: the place, then what is wrong with it. */
type SchemaIssue = {
  readonly path: readonly PropertyKey[];
  readonly code: string;
  readonly message: string;
  readonly expected?: unknown;
  readonly origin?: unknown;
};

const EXPECTED_WORDS: Record<string, string> = {
  string: "must be text",
  number: "must be a number",
  boolean: "must be true or false",
  array: "must be a list",
  object: "must be a group of fields",
};

// The schema's own messages are sentences for the user ("Enter your name");
// the library's defaults ("Invalid input: expected string, received number")
// are not, and are replaced by words.
const LIBRARY_MESSAGE = /^(Invalid|Too (small|big)|Expected)/;

function issueWords(issue: SchemaIssue): string {
  const place = describeFieldPath(issue.path);
  // The lines are joined with ". ", so a message that is already a sentence drops its own stop.
  if (!LIBRARY_MESSAGE.test(issue.message)) return `${place}: ${issue.message.replace(/\.$/, "")}`;
  if (issue.code === "invalid_type") {
    if (/received undefined$/.test(issue.message)) return `${place} is missing`;
    return `${place} ${EXPECTED_WORDS[String(issue.expected)] ?? "has the wrong kind of value"}`;
  }
  if (issue.code === "too_small" && issue.origin === "string") return `${place} can't be empty`;
  if (issue.code === "invalid_union" || issue.code === "invalid_value") {
    return `${place} isn't one of the allowed choices`;
  }
  return `${place} isn't valid`;
}

/** "Couldn't apply: Contact, Email must be text. Fix it and choose Apply again." At most three places. */
export function schemaIssuesWords(issues: readonly SchemaIssue[]): string {
  const lines = [...new Set(issues.map(issueWords))];
  const shown = lines.slice(0, 3).join(". ");
  const more = lines.length > 3 ? `. And ${lines.length - 3} more` : "";
  return `Couldn't apply: ${shown}${more}. Fix ${lines.length === 1 ? "it" : "them"} and choose Apply again.`;
}

/**
 * Code the parser can't read, by its line: "Couldn't read the code at line 3. Check for a missing comma or
 * quote." Chrome says "(line 3 column 2)", older engines only "at position 11", Safari neither.
 */
export function jsonErrorWords(text: string, thrown: unknown): string {
  // Only the line number is read from the parser's words; they never reach the screen.
  const parser = thrown instanceof Error ? thrown.message : "";
  const said = /line (\d+)/.exec(parser);
  const at = /position (\d+)/.exec(parser);
  const line = said ? Number(said[1]) : at ? text.slice(0, Number(at[1])).split("\n").length : null;
  return `Couldn't read the code${line ? ` at line ${line}` : ""}. Check for a missing comma or quote.`;
}

// A version change's section, as the server stores it (`resume_versions.diff_versions`).
const CHANGE_SECTION: Record<string, string> = { ...PATH_SECTION, extra: "Other sections", resume: "Resume" };

/** One change in Version history: its section in words, and its label only when it adds something. */
export function diffChangeWords(change: { section: string; label: string }): { section: string; label: string | null } {
  const section = CHANGE_SECTION[change.section] ?? change.section.replace(/_/g, " ");
  const same = change.label.trim().toLowerCase() === section.toLowerCase();
  return { section, label: same ? null : change.label };
}

/**
 * A version's stored one-line summary ("Updated summary · Summary; Added experience · Acme") in words:
 * sections named as on screen, a label that repeats its section dropped ("Updated Summary"). Anything else
 * the server wrote passes through: old summaries keep their words.
 */
export function versionSummaryWords(summary: string): string {
  return summary
    .split("; ")
    .map((part) => {
      const hit = /^(Added|Removed|Updated) (\S+) · (.+)$/.exec(part);
      if (!hit) return part;
      // "Added resume · Initial version" is the first version: its label says it.
      if (hit[2] === "resume") return hit[3];
      const { section, label } = diffChangeWords({ section: hit[2], label: hit[3] });
      return label ? `${hit[1]} ${section} · ${label}` : `${hit[1]} ${section}`;
    })
    .join("; ");
}
