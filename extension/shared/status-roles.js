/* Maestro CS Companion — an application status's word and colour role.
 *
 * ONE table, the same words and roles as the web app's status chip
 * (frontend/components/status-chip.tsx, STATUS_STYLES), across the extension boundary where no import reaches:
 * one meaning per colour in both apps. `backend/tests/test_extension_status_roles.py` fails if the two drift.
 * A role is a colour family (panel.css `.chip.role-<name>`); the key is what the backend stores, never what the
 * user reads. Loaded by the panel document only (panel.html); panel.js throws at boot naming this file when
 * it did not publish.
 */
(() => {
  const ns = (window.careerStudioCompanion ??= {});

  ns.statusRoles = {
    draft: { label: "Draft", role: "muted" },
    applied: { label: "Applied", role: "primary" },
    interviewing: { label: "Interviewing", role: "warning" },
    offered: { label: "Offer", role: "tertiary" },
    accepted: { label: "Offer accepted", role: "success" },
    rejected: { label: "Rejected", role: "error" },
    withdrawn: { label: "Withdrawn", role: "muted" },
  };
})();
