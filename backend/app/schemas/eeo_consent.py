"""Backend-owned standing consent for deterministic EEO autofill.

Metadata only — never stores EEO answer values. Answers live in the autofill
profile; this record only authorizes the extension/tool-side exact-match path.
"""

from pydantic import BaseModel, Field

CURRENT_POLICY_VERSION = "1"


class EeoConsent(BaseModel):
    """One consent record, TWO independent permissions.

    They travel together because they are one thing to the user — "what may
    this extension answer on my behalf" — and they are stored apart because
    they are not one decision. `enabled` authorizes disclosing protected
    characteristics; `consent_forms` authorizes ticking an application's own
    agreement boxes. Folding them into a single flag would make opting into
    EEO fill silently also opt into agreeing to terms, which is not a trade
    anyone chose.

    Metadata only, both of them. No answer value is ever stored here.
    """

    model_config = {"extra": "forbid"}

    enabled: bool = False
    # Ticking "Yes, I have read and consent to the terms and conditions" and
    # its family — acknowledgements, attestations, arbitration and waiver
    # boxes. OFF by default, and it stays a standing consent rather than a
    # per-form question because that is what the user gives once, on purpose.
    #
    # What it does NOT unlock, at any setting: signature and initials fields,
    # passwords, and government identifiers (SSN, passport, licence numbers).
    # A signature is a distinct act rather than an agreement, and the other two
    # are credentials, not consent — nothing in a profile authorizes typing
    # them into a page.
    consent_forms: bool = False
    acknowledged_at: str | None = None
    policy_version: str = Field(default=CURRENT_POLICY_VERSION)
