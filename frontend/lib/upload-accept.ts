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

/** The human-readable half of an accept list: its extensions, without the
 *  MIME types, for hints and rejection messages. */
export function acceptExtensions(accept: string): string[] {
  return accept
    .split(",")
    .map((entry) => entry.trim())
    .filter((entry) => entry.startsWith("."));
}
