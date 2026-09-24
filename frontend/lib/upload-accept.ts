/**
 * The ONE place the browser is told which files the backend can read.
 *
 * Six file pickers used to carry their own hand-typed `accept` strings —
 * extensions only, no MIME types, and no two lists alike. Extension-only
 * lists are what a picker greys files out on: the OS dialog maps each entry
 * to a system type, and a `.docx` whose registration on that machine is
 * missing or odd (Pages, a stale LaunchServices database, a Word-less Mac)
 * never lights up even though the backend's `attachment_extract` reads it
 * fine. Listing the MIME type beside the extension gives the dialog a second
 * way to recognise the file; the extension stays so a drag-and-drop with no
 * MIME (common for `.tex`/`.md`) still passes `Dropzone`'s client filter.
 *
 * Mirrors `backend/app/services/attachment_extract.py`: every extension here
 * has a branch there. `backend/tests/test_frontend_upload_accept.py` pins the
 * two together and that every picker reads from this module.
 */

export const DOCX_MIME =
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document";

const DOCUMENT_EXTS = [".pdf", ".docx", ".md", ".markdown", ".txt", ".tex"];
const DOCUMENT_MIMES = ["application/pdf", DOCX_MIME, "text/markdown", "text/plain"];
const IMAGE_EXTS = [".png", ".jpg", ".jpeg", ".webp"];
const IMAGE_MIMES = ["image/png", "image/jpeg", "image/webp"];

/** Anything the extractor can turn into text: documents and images (the
 *  vision fallback transcribes a screenshot of a resume). Career KB documents,
 *  quick capture, chat attachments, onboarding documents. */
export const DOCUMENT_ACCEPT = [
  ...DOCUMENT_EXTS,
  ...IMAGE_EXTS,
  ...DOCUMENT_MIMES,
  ...IMAGE_MIMES,
].join(",");

/** A resume file for import: the app's own JSON plus the text documents.
 *  No images — a screenshot is not a resume the parser should mint a base
 *  from. */
export const RESUME_FILE_ACCEPT = [
  ".json",
  ...DOCUMENT_EXTS,
  "application/json",
  ...DOCUMENT_MIMES,
].join(",");

// Each extension's name on screen, in the order a list reads them.
const TYPE_NAMES: readonly (readonly [string, string])[] = [
  [".pdf", "PDF"],
  [".docx", "Word"],
  [".md", "Markdown"],
  [".markdown", "Markdown"],
  [".txt", "text"],
  [".tex", "LaTeX"],
  [".json", "JSON"],
];
const IMAGE_NAMES: readonly (readonly [string, string])[] = [
  [".png", "PNG"],
  [".jpg", "JPG"],
  [".jpeg", "JPG"],
  [".webp", "WebP"],
];

/** "A, B or C". */
function orList(items: string[]): string {
  return items.length < 2 ? (items[0] ?? "") : `${items.slice(0, -1).join(", ")} or ${items.at(-1)}`;
}

/** The file types an `accept` list takes, in words: "PDF, Word, Markdown, text, LaTeX or JSON".
 *  Read from the picker's own list, so a rejection names what THAT picker takes. */
export function acceptedTypesLabel(accept: string): string {
  const entries = new Set(accept.split(",").map((entry) => entry.trim().toLowerCase()));
  const named = (table: typeof TYPE_NAMES) => [
    ...new Set(table.filter(([ext]) => entries.has(ext)).map(([, name]) => name)),
  ];
  const images = named(IMAGE_NAMES);
  const types = [...named(TYPE_NAMES), ...(images.length ? [`an image (${orList(images)})`] : [])];
  return types.length ? orList(types) : "a different file";
}

/**
 * A picker's hint in plain words: the files most people have first ("PDF, Word or text files"), then
 * the rest, named once ("Also Markdown, LaTeX or a Maestro CS JSON file."). `acceptedTypesLabel`
 * stays the rejection's list; this is the hint above the drop zone.
 */
export function acceptedFilesHint(accept: string): string {
  const entries = new Set(accept.split(",").map((entry) => entry.trim().toLowerCase()));
  const common = ([[".pdf", "PDF"], [".docx", "Word"], [".txt", "text"]] as const)
    .filter(([ext]) => entries.has(ext))
    .map(([, name]) => name);
  const image = IMAGE_NAMES.some(([ext]) => entries.has(ext));
  const rest = [
    ...(entries.has(".md") ? ["Markdown"] : []),
    ...(entries.has(".tex") ? ["LaTeX"] : []),
    ...(entries.has(".json") ? ["a Maestro CS JSON file"] : []),
  ];
  const lead = `${orList(common)} files${image ? ", or an image" : ""}.`;
  return rest.length ? `${lead} Also ${orList(rest)}.` : lead;
}
