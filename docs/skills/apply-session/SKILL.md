---
name: apply-session
description: Use to work through the user's accepted Maestro CS application queue with a browser — tailor where needed, fill each application, and submit once the user says yes. Autonomous apart from that yes.
---

# Apply session

Work the accepted queue end to end without stopping for routine questions. You
need Maestro CS over MCP and a browser tool (Playwright MCP with headed Chrome,
or Claude in Chrome).

**Ask the user for only two things:** information that isn't anywhere in the
app, and one explicit yes per application before the final submit. Decide
everything else yourself.

1. **Queue.** `list_proposals(status="accepted")` and work it in order, one
   application at a time, in this session. Say which one you are starting.
2. **Prepare.** Tailor or render only when the linked application or its PDF is
   missing or stale — a current draft, including one the user tailored, stays
   as is. Stage the PDF with `prepare_application_pdf_upload` and upload the
   path it returns.
3. **Fill.** Answer from the user's profile, Career KB and saved Q&A
   (`get_autofill_profile`, `list_qa_entries`). Read back what each field saved.
   Signatures, logins, CAPTCHAs and legal attestations are the user's to do in
   the browser.
4. **Blocked?** Don't stall the run: `report_failure` with the reason (or decline
   the posting if it is gone) and move on to the next one.
5. **Submit.** Call `get_final_review`, attach a screenshot of the filled form
   as `final_review` evidence, and show the user one short summary (company,
   role, PDF, key answers, and any duplicate warning). Only after their yes for
   *this* application: `record_consent`, click submit once, attach the
   confirmation as `submission_receipt`, and `mark_submitted`. If you can't tell
   whether it went through, say so and never click again.
6. **Digest.** End with submitted / needs the user / declined / still queued.

The Maestro CS tools' own descriptions carry the rest (states, evidence,
duplicates) — follow them rather than working around a refusal. If the
`agent-apply-execution` skill is installed, use it for detailed browser
technique.
