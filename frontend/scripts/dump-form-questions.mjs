// Writes today's hand-written question set to the backend's golden fixture (Task 1.3 compares the
// served set to it). Run once from frontend/: node scripts/dump-form-questions.mjs
import { writeFileSync } from "node:fs";

import { GROUPS, workPermitFields } from "../lib/autofill-options.ts";

const out = {
  groups: GROUPS,
  permits: {
    us_visa: workPermitFields("us_visa"),
    uk: workPermitFields("uk"),
    generic: workPermitFields("generic"),
  },
};
writeFileSync("../backend/tests/fixtures/form_questions_today.json", JSON.stringify(out, null, 2) + "\n");
