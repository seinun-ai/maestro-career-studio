import assert from "node:assert/strict";
import { test } from "node:test";

import {
  documentAddedWords,
  documentReadAgainWords,
  documentStatusLabel,
  draftsFromDocument,
} from "./document-words.ts";

test("a document read whose bullets couldn't be suggested says so, and a file never read says that", () => {
  const mintFailed = { ingest_status: "failed", has_text: true };
  const unreadable = { ingest_status: "failed", has_text: false };
  assert.equal(documentStatusLabel(mintFailed), "Couldn't suggest bullets");
  assert.equal(documentStatusLabel(unreadable), "Couldn't read");
  assert.equal(documentAddedWords(mintFailed, 0), "Document added. Couldn't suggest bullets from it. Try Read again.");
  assert.equal(documentAddedWords(unreadable, 0), "Document added, but no text could be read from it.");
  assert.equal(documentReadAgainWords(mintFailed, 0), "Couldn't suggest bullets from it. Try Read again.");
});

test("a read document claims only the bullets it made", () => {
  const minted = { ingest_status: "minted", has_text: true };
  assert.equal(documentStatusLabel(minted), "Done");
  assert.equal(documentAddedWords(minted, 0), "Document added. It had no new bullets to suggest.");
  assert.equal(documentAddedWords(minted, 1), "Document added. 1 new bullet is ready to review.");
  assert.equal(documentAddedWords(minted, 3), "Document added. 3 new bullets are ready to review.");
  assert.equal(documentReadAgainWords(minted, 0), "Read again. No new bullets to suggest.");
  assert.equal(documentReadAgainWords(minted, 2), "Read again. 2 new bullets are ready to review.");
});

test("drafts are counted from the one document", () => {
  const points = [
    { state: "draft", source_document_id: "d1" },
    { state: "approved", source_document_id: "d1" },
    { state: "draft", source_document_id: "d2" },
    { state: "draft", source_document_id: null },
  ];
  assert.equal(draftsFromDocument(points, "d1"), 1);
  assert.equal(draftsFromDocument(undefined, "d1"), 0);
});
