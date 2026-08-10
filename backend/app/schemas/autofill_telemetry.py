"""Frozen POST-batch contract for extension autofill telemetry.

FROZEN means the extension side, not just this file. The browser extension is
installed out-of-band and updates on its own schedule, so every field name and
type here is a live compatibility surface with panels already in the wild.
Additive changes only: because the endpoint rejects unknown keys (below), a
rename does not degrade gracefully — it 422s every batch from every client that
has not updated, and telemetry stops silently.

extra="forbid" on BOTH models is the privacy backstop: any unexpected key (a
typed value, an AI answer) 422s instead of being stored.

Length caps below are the input-size hardening: labels, hosts, option texts and
the batch/option list sizes are bounded so a hostile or buggy client cannot
push unbounded strings/rows through the endpoint. Oversize input 422s (it is
NOT silently truncated); post_telemetry additionally strips+caps host and
option texts as a belt over these constraints."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_LABEL = 200
MAX_HOST = 255
MAX_OPTION_TEXT = 200
MAX_OPTIONS = 30
MAX_OBSERVATIONS = 200

ObservationOutcome = Literal[
    "filled",
    "corrected",
    # The write landed but the site reformatted it ("5551234567" →
    # "(555) 123-4567"). A success: the field is non-empty and normalizes to
    # what we wrote. Split out of not_stuck once the readback started requiring
    # the value to survive two animation frames, which made every formatting
    # site look like a mechanical failure.
    "filled_normalized",
    "no_rule",
    # A rule matched the label but no authorized source held an answer. Distinct
    # from `no_rule` (nothing matched) on purpose: this one is fixed by filling
    # in the profile, that one by writing a rule. Collapsing them hid which.
    "missing_source",
    # Recognised and deliberately not written (signature, consent, attestation,
    # credential). Correct behaviour, never a failure. Declared ahead of the
    # writer that will emit it: this contract is frozen and extensions update
    # out-of-band, so one edit panels can rely on beats two.
    "policy_blocked",
    # An EEO field seen while the EEO opt-in was off. Emitted by the extension
    # since that opt-in landed; missing here, so — extra="forbid" being what it
    # is — a single one of these 422'd the whole batch and sendTelemetry
    # swallowed the error. The opt-in is off by default, so in practice any
    # page with an EEO section reported nothing at all.
    "eeo_disabled",
    "skip_rule",
    "skipped_checkbox",
    "combobox_snap_failed",
    "not_stuck",
    "hidden",
    "ai_answered",
    "ai_no_stick",
    "ai_unanswered",
    # The reply came back but could not be matched to the questions: the model
    # answered N questions in one un-numbered blob, and services/qa.py
    # `_split_numbered_answers` returned a 1-element list. Nothing was written.
    #
    # Neutral by omission from both sets, and that is the point of it existing.
    # The extension's only alternative was to report the unmatched questions
    # `ai_unanswered`, which IS a FAILURE outcome — so one unsplittable reply
    # charged up to eight rule failures and moved a per-kind rate the summary
    # module declares frozen. The fill path did nothing wrong; it declined.
    "ai_unaligned",
    # The applied-detection prompt, whose EMITTER WAS RETIRED 2026-07-28 (the
    # extension no longer watches for a submitted application). The pair stays
    # for the reason at the top of this file: this contract is additive-only —
    # an extension installed out-of-band may still send them, stored rows carry
    # them, and a value this Literal does not know 422s a whole batch silently.
    # Both remain in autofill_telemetry.NEUTRAL_OUTCOMES by derivation, so old
    # rows still move no fill-success rate on the Analytics coverage card.
    "applied_detected",
    "applied_dismissed",
]

# The kind of THING an observation is about. Six form controls plus one value
# that is not a control at all.
#
# `signal` was the applied-detection watcher's (emitter retired 2026-07-28;
# the kind stays for the same additive-only reason as the outcome pair above):
# the row it produced is one page
# event per host, not a field the rules could ever fill. It is declared here
# rather than smuggled in as `text` because every consumer of this table reads
# `kind` as "which control shape" — `by_kind` publishes a per-kind fill success
# rate, `totals` counts signatures and hosts as coverage, and the novelty mark
# on each row feeds the "coverage saturated, you can turn it off"
# recommendation. A detection event answering to `text` would move all three
# while saying nothing about any form.
#
# Non-form kinds are excluded from the coverage summary by
# `autofill_telemetry.NON_FORM_KINDS`; adding another one means adding it there
# too, and the partition test in test_autofill_telemetry_summary.py is what
# says so out loud.
ObservationKind = Literal[
    "text", "textarea", "select", "radio", "checkbox", "combobox", "signal"
]


class TelemetryObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = Field(max_length=MAX_LABEL)
    kind: ObservationKind
    host: str = Field(max_length=MAX_HOST)
    outcome: ObservationOutcome
    rule_id: str | None = None
    options: list[str] | None = Field(default=None, max_length=MAX_OPTIONS)

    @field_validator("options")
    @classmethod
    def _reject_oversize_option_texts(
        cls, value: list[str] | None
    ) -> list[str] | None:
        # Oversize option text 422s here rather than being stored capped.
        if value is not None:
            for option in value:
                if len(option) > MAX_OPTION_TEXT:
                    raise ValueError(
                        f"option text exceeds {MAX_OPTION_TEXT} characters"
                    )
        return value


class TelemetryBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_host: str = Field(max_length=MAX_HOST)
    action: Literal["profile_fill", "ai_fill", "applied_detection"]
    observations: list[TelemetryObservation] = Field(max_length=MAX_OBSERVATIONS)
