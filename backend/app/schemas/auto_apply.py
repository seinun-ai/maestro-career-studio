"""Auto-apply lane knobs. Consumed by the proposals router (cooldown/dedup,
submission caps, expiry) and read by hunting playbooks via GET
/api/settings/auto-apply (per-run caps are enforced agent-side)."""
from pydantic import BaseModel, Field


class AutoApplySettings(BaseModel):
    model_config = {"extra": "forbid"}

    max_proposals_per_run: int = Field(default=10, ge=1)
    max_submissions_per_day: int = Field(default=10, ge=1)
    # DEPRECATED 2026-08-01: declines are posting-scoped (design G3); no code
    # reads this. Kept so existing auto_apply.json files still validate
    # (extra="forbid" would otherwise reset a hand-edited file to defaults).
    cooldown_days: int = Field(default=30, ge=0)
    company_blocklist: list[str] = Field(default_factory=list)
    proposal_expiry_days: int = Field(default=7, ge=1)
    auto_pick_margin: float = Field(default=5.0, ge=0)
    auto_pick_floor: float = Field(default=60.0, ge=0, le=100)
