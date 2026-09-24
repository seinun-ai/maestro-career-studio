import assert from "node:assert/strict";
import { test } from "node:test";

import { DOCUMENT_ACCEPT, RESUME_FILE_ACCEPT, acceptedFilesHint, acceptedTypesLabel } from "./upload-accept.ts";

test("a rejected file hears the types its own picker takes", () => {
  // Resume pickers: the app's JSON export and LaTeX sources too, no images.
  assert.equal(acceptedTypesLabel(RESUME_FILE_ACCEPT), "PDF, Word, Markdown, text, LaTeX or JSON");
  // Document pickers: images too (the extractor reads a screenshot).
  assert.equal(
    acceptedTypesLabel(DOCUMENT_ACCEPT),
    "PDF, Word, Markdown, text, LaTeX or an image (PNG, JPG or WebP)",
  );
});

test("a short or unknown list still reads as words", () => {
  assert.equal(acceptedTypesLabel(".pdf"), "PDF");
  assert.equal(acceptedTypesLabel(".PDF, .docx"), "PDF or Word");
  assert.equal(acceptedTypesLabel(".png,image/png"), "an image (PNG)");
  assert.equal(acceptedTypesLabel("application/x-thing"), "a different file");
});

test("a picker's hint leads with the files people have, then names the rest", () => {
  assert.equal(
    acceptedFilesHint(RESUME_FILE_ACCEPT),
    "PDF, Word or text files. Also Markdown, LaTeX or a Maestro CS JSON file.",
  );
  assert.equal(acceptedFilesHint(DOCUMENT_ACCEPT), "PDF, Word or text files, or an image. Also Markdown or LaTeX.");
  assert.equal(acceptedFilesHint(".pdf"), "PDF files.");
});
