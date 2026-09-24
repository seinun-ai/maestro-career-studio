/**
 * A career history document in words: what reading it did. Pure, so `node --test` runs it
 * (`document-words.test.ts`). The status is stored `extracted | minted | failed`; `failed` covers a file
 * with no readable text AND a file read whose bullets couldn't be suggested (no model key, a model error),
 * which `has_text` tells apart.
 */
import type { KBDocumentOut } from "./types";

type DocumentState = Pick<KBDocumentOut, "ingest_status" | "has_text">;

const bullets = (n: number) => `${n} new ${n === 1 ? "bullet" : "bullets"}`;

/** The status chip. A document read with no new bullets is "Done": it claims none. */
export function documentStatusLabel(doc: DocumentState): string {
  if (doc.ingest_status === "minted") return "Done";
  if (doc.ingest_status === "extracted") return "Read, no bullets";
  if (doc.ingest_status === "failed") return doc.has_text ? "Couldn't suggest bullets" : "Couldn't read";
  return "Reading";
}

/** The toast after an upload. `drafted` is the draft bullets made from this document. */
export function documentAddedWords(doc: DocumentState, drafted: number): string {
  if (doc.ingest_status === "minted") {
    return drafted > 0
      ? `Document added. ${bullets(drafted)} ${drafted === 1 ? "is" : "are"} ready to review.`
      : "Document added. It had no new bullets to suggest.";
  }
  if (doc.ingest_status === "failed") {
    return doc.has_text
      ? "Document added. Couldn't suggest bullets from it. Try Read again."
      : "Document added, but no text could be read from it.";
  }
  return "Document added";
}

/** The toast after Read again. `drafted` is the draft bullets this read added. */
export function documentReadAgainWords(doc: DocumentState, drafted: number): string {
  if (doc.ingest_status === "minted") {
    return drafted > 0
      ? `Read again. ${bullets(drafted)} ${drafted === 1 ? "is" : "are"} ready to review.`
      : "Read again. No new bullets to suggest.";
  }
  if (doc.ingest_status === "failed") {
    return doc.has_text
      ? "Couldn't suggest bullets from it. Try Read again."
      : "No text could be read from this document.";
  }
  return "Read again";
}

/** Draft bullets made from one document, in an item's bullets. */
export function draftsFromDocument(
  points: readonly { state: string; source_document_id?: string | null }[] | undefined,
  documentId: string,
): number {
  return (points ?? []).filter((p) => p.state === "draft" && p.source_document_id === documentId).length;
}
