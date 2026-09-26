"""Backend-owned standing consent for deterministic EEO autofill.

Metadata only — never stores EEO answer values. Answers live in the autofill
profile; this record only authorizes the extension/tool-side exact-match path.
"""

from pydantic import BaseModel, Field

CURRENT_POLICY_VERSION = "2"
# The first policy whose wording covers what `consent_forms` unlocks today.
# Policy 1 described "the application's own agreement boxes"; policy 2 covers
# every field (signatures, initials, typed-name attestations, salary, IDs), so
# an agreement given under policy 1 does not carry over. `enabled` has no such
# floor: policy 2 changed nothing the diversity opt-in covers.
CONSENT_FORMS_MIN_POLICY_VERSION = "2"


def policy_at_least(version: object, minimum: str) -> bool:
    """Whether `version` is `minimum` or later. Fails CLOSED: a version that
    is not a whole number (empty, missing, "1.5", anything hand-edited) is
    older than every policy."""
    if not isinstance(version, str) or not version.isdigit():
        return False
    return int(version) >= int(minimum)


class EeoConsent(BaseModel):
    """One consent record, TWO independent permissions.

    They travel together because they are one thing to the user — "what may
    this extension answer on my behalf" — and they are stored apart because
    they are not one decision. `enabled` authorizes disclosing protected
    characteristics; `consent_forms` lifts the extension's label policy, so it
    may fill an application's own agreement boxes and every other field it
    refuses without it. Folding them into a single flag would make opting into
    EEO fill silently also opt into agreeing to terms, which is not a trade
    anyone chose.

    Metadata only, both of them. No answer value is ever stored here.
    """

    model_config = {"extra": "forbid"}

    enabled: bool = False
    # With it ON, the extension's label policy (extension/shared/policy.js)
    # refuses nothing: "Yes, I have read and consent to the terms and
    # conditions" and its family, and also signatures, initials, typed-name
    # attestations and salary history. OFF by default, and a standing consent
    # rather than a per-form question because that is what the user gives
    # once, on purpose. At every setting the extension never clicks Next or
    # Submit — those stay the user's.
    consent_forms: bool = False
    # Server-derived, never an input: True when the stored record says
    # `consent_forms` under a policy older than CONSENT_FORMS_MIN_POLICY_VERSION.
    # Such a record is SERVED with `consent_forms` false (the permission is not
    # granted anywhere) and this true, so the web app can say why the switch is
    # off. `acknowledged_at` / `policy_version` are shared by both permissions;
    # a yes to either restamps them with the current policy.
    consent_forms_lapsed: bool = False
    acknowledged_at: str | None = None
    policy_version: str = Field(default=CURRENT_POLICY_VERSION)
