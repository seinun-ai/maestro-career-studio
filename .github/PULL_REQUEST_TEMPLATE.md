### Description of Changes
Briefly summarize what this pull request accomplishes and why the changes are needed.

### Related Issues
Closes # (issue number)

### SYSTEM.md & Architectural Compliance
- [ ] I have read `SYSTEM.md` and verified my changes comply with existing architectural invariants.
- [ ] I have updated `SYSTEM.md` to reflect any new endpoints, models, entities, or frontend/backend behaviors introduced in this PR.
- [ ] **Deprecation Ledger (§13):** If this change supersedes existing functionality without deleting it, I have added a tracking row in `SYSTEM.md` Section 13 defining an explicit removal trigger.

### Verification & Testing
Describe how you tested this PR and confirm automated tests pass cleanly:
- [ ] Verified clean test execution against throwaway test DB: `pytest tests/ mcp_server/tests/ -q` (0 failures, no unexpected skips).
- [ ] Verified frontend compile and production bundle build: `cd frontend && npx tsc --noEmit && npm run build`.
- [ ] Ensured NO personal identifiable information (PII) or real API keys are included in code, docs, or test payloads.
