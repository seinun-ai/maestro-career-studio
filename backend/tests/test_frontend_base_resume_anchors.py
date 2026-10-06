"""Pins: a base resume's Target (docs/plans/2026-10-05-base-resume-anchors-design.md, Frontend).

The studio's ⋯ opens one dialog, **Target**, holding the resume's countries, role, company and focus.
Countries decide which jobs the resume is scored for; the other three steer the AI. Gallery and score
cards show what is set as small pills, and the Score tab says when resumes for other countries were
left out, with a button that scores them anyway. "Anchor" is the code's word and never reaches the
screen. Node tests cover the two sentences in lib/ats-words.ts; they are not in CI, so the words are
pinned here too.
"""

from __future__ import annotations

import re
from pathlib import Path

from tests.node_ts import run_node_test

_ROOT = Path(__file__).resolve().parents[2]
_FRONTEND = _ROOT / "frontend"


def _read(rel: str) -> str:
    return (_FRONTEND / rel).read_text(encoding="utf-8")


def _squash(src: str) -> str:
    return " ".join(src.split())


def _between(src: str, start: str, end: str) -> str:
    at = src.index(start)
    return src[at : src.index(end, at + len(start))]


def _element(src: str, at: int) -> str:
    """A self-closing element that starts at `at`, through its `/>`."""
    return src[at : src.index("/>", at) + 2]


_DIALOG_FILE = _read("components/role-category-picker.tsx")
_PICKER = _read("components/country-picker.tsx")
_PILLS = _read("components/base-resumes/anchor-pills.tsx")
_GALLERY = _read("components/base-resumes/base-resume-gallery.tsx")
_STUDIO = _read("components/resume-editor/editor-body.tsx")
_PANEL = _read("components/ats-score-panel.tsx")
_WORDS = _read("lib/ats-words.ts")
_API = _read("lib/api.ts")
_TYPES = _read("lib/types.ts")


def _dialog() -> str:
    return _DIALOG_FILE[_DIALOG_FILE.index("export function TargetDialog(") :]


# ── The Target dialog ──────────────────────────────────────────────────────


def test_the_dialog_is_called_target_and_lists_four_fields_in_order():
    dialog = _dialog()
    assert "<DialogTitle>Target</DialogTitle>" in dialog
    assert "RoleCategoryDialog" not in _DIALOG_FILE + _STUDIO
    labels = [dialog.index(f'label="{name}"') for name in ("Countries", "Role", "Company", "Focus")]
    assert labels == sorted(labels)


def test_the_dialog_says_what_the_fields_are_for():
    dialog = _squash(_dialog())
    assert (
        "<DialogDescription> Used when tailoring or asking for changes. "
        "Saving here does not change the resume. </DialogDescription>"
    ) in dialog
    assert 'hint="Only scored for jobs in these countries. Leave empty to use anywhere."' in dialog
    assert 'hint="Such as payments platforms."' in dialog


def test_a_hint_sits_between_its_label_and_its_control_and_is_wired():
    """Conventions, Form conventions: below the control a hint is read only after typing."""
    field = _between(_DIALOG_FILE, "function AnchorField(", "\n}\n")
    label, hint, control = (field.index(s) for s in ("<Label htmlFor={id}>", "<p id={hintId}", "{children("))
    assert label < hint < control
    assert "hint ? hintId : undefined" in field


def test_company_and_focus_are_plain_capped_fields_with_no_placeholder():
    text = _between(_DIALOG_FILE, "function AnchorTextField(", "\n}\n")
    tag = _element(text, text.index("<Input"))
    assert "placeholder" not in tag
    assert "maxLength={MAX_ROLE_LABEL_CHARS}" in tag
    assert "aria-describedby={describedBy}" in tag
    assert "readOnly={save.isPending}" in tag
    # Commit on blur, and only a changed value.
    assert "onBlur={commit}" in tag
    assert 'if (next === (value ?? "")) return;' in text


def test_every_patch_sends_only_the_key_it_changed():
    hook = _between(_DIALOG_FILE, "function useAnchorSave<", "\n}\n")
    assert "body: JSON.stringify({ [field]: value })," in hook
    assert "qc.setQueryData([\"base-resumes\", slug], updated);" in hook
    assert "qc.invalidateQueries({ queryKey: [\"base-resumes\"] });" in hook
    assert "onError: (err: Error) => toast.error(couldnt(`save the ${FIELD_WORDS[field]}`, err))," in hook


def test_countries_save_on_change_and_the_picker_is_named_and_read_only_while_it_saves():
    dialog = _dialog()
    tag = _squash(_element(dialog, dialog.index("<CountryPicker")))
    for attr in ('aria-label="Countries"', "aria-describedby={describedBy}", "readOnly={saveCountries.isPending}",
                 "onChange={(codes) => saveCountries.mutate(codes)}"):
        assert attr in tag, attr


def test_closing_with_escape_commits_a_typed_value_first():
    """Esc unmounts the fields without a blur, which used to drop the typed company or focus."""
    dialog = _squash(_dialog())
    assert "if (!next && active instanceof HTMLElement && bodyRef.current?.contains(active)) active.blur();" in dialog
    assert "<DialogContent finalFocus={finalFocus}>" in dialog


def test_the_role_field_keeps_its_picker_and_its_visible_label():
    dialog = _squash(_dialog())
    assert '<RoleCategoryPicker id={id} aria-label="Role"' in dialog
    # The picker's own default name stays for the callers with no visible label.
    assert '"aria-label": ariaLabel = "Target role",' in _DIALOG_FILE


def test_the_studio_menu_opens_target():
    assert "export function targetMenuLabel(" in _DIALOG_FILE
    label = _between(_DIALOG_FILE, "export function targetMenuLabel(", "\n}\n")
    assert 'return `Target: ${displayRoleTag(roleCategory, label, options)}`;' in label
    assert 'return "Target";' in label
    item = _squash(_between(_STUDIO, "<DropdownMenuItem onClick={() => setTargetOpen(true)}>", "</DropdownMenuItem>"))
    assert "{targetMenuLabel(" in item
    dialog = _squash(_between(_STUDIO, "<TargetDialog", "/>"))
    # `(live ?? initial)`, not `live?.company ?? initial.company`: a cleared company is null, and the
    # fallback would show the value from before the clear.
    for prop in ("countries={(live ?? initial).countries}", "company={(live ?? initial).company}",
                 "focus={(live ?? initial).focus}", "finalFocus={overflowRef}"):
        assert prop in dialog, prop


# ── The country picker ─────────────────────────────────────────────────────


def test_the_country_picker_reads_the_list_once_and_names_its_input():
    hook = _between(_PICKER, "export function useCountries(", "\n}\n")
    assert 'queryKey: ["countries"],' in hook
    assert 'apiFetch<Country[]>("/api/countries")' in hook
    assert "staleTime: 60 * 60 * 1000," in hook
    assert re.search(r"<Combobox\.Input\s+id=\{props\.id\}\s+aria-label=\{props\[\"aria-label\"\]\}", _PICKER)
    assert "placeholder" not in _PICKER
    assert "readOnly={props.readOnly}" in _squash(_PICKER[_PICKER.index("<Combobox.Root") : _PICKER.index("<div ref={chipsRef}>")])


def test_escape_on_a_closed_country_list_never_clears_the_countries():
    """Base UI clears the value on Escape with the list closed: Esc meant for the dialog PATCHed []."""
    keys = _squash(_PICKER[_PICKER.index("onKeyDown={(event) => {") :])
    assert (
        'if ( event.key === "Escape" && event.currentTarget.getAttribute("aria-expanded") !== "true" ) '
        "{ event.preventBaseUIHandler(); }"
    ) in keys


# ── Pills ──────────────────────────────────────────────────────────────────


def test_pills_show_what_is_set_and_nothing_when_nothing_is():
    pills = _PILLS
    assert 'variant="secondary"' in pills
    assert "if (resume.countries.length === 0 && texts.length === 0) return null;" in pills
    assert 'roleSet ? displayRoleTag(resume.role_category, resume.role_label, options) : null,' in pills
    # A country is its code, with its name for the pointer and the screen reader.
    assert "title={countryName(code)}" in pills
    assert '<span className="sr-only">{countryName(code)}</span>' in pills
    # User text is capped and truncates, its whole value in `title`.
    assert "truncate" in pills and "max-w-48" in pills


def test_the_gallery_and_the_score_cards_show_the_pills():
    assert "<AnchorPills resume={resume} />" in _GALLERY
    # The unset role stays the gallery's one invitation; a set role is a pill.
    assert "Role not set" in _GALLERY and "Role not set" not in _PILLS
    card = _between(_PANEL, "function AtsScoreCard(", "export function AtsScorePanel(")
    assert "{resume && <AnchorPills resume={resume} />}" in card
    assert card.index("<CardTitle") < card.index("<AnchorPills")


# ── The Score tab ──────────────────────────────────────────────────────────


def test_the_score_list_key_carries_the_country_flag_and_prefix_invalidations_still_reach_it():
    assert 'queryKey: ["ats-scores", jobId, { includeOtherCountries }],' in _PANEL
    assert "queryFn: () => listAtsScores(jobId, { includeOtherCountries })," in _PANEL
    assert 'queryKey: ["ats-scores", jobId, "candidates"],' in _PANEL
    assert "queryFn: () => getAtsCandidates(jobId)," in _PANEL
    # A run invalidates the PREFIX, which covers both keys.
    assert 'onSuccess: () => qc.invalidateQueries({ queryKey: ["ats-scores", jobId] }),' in _PANEL
    # Switching the view keeps the cards on screen until the new list lands.
    assert "placeholderData: keepPreviousData," in _PANEL
    for rel in ("components/ats-compare-panel.tsx", "components/resume-editor/tailored-resume-studio.tsx",
                "app/jobs/[id]/tailor/[sessionId]/page.tsx"):
        assert 'qc.invalidateQueries({ queryKey: ["ats-scores", jobId] });' in _read(rel), rel


def test_the_api_forwards_the_country_flag():
    assert "include_other_countries: Boolean(opts.includeOtherCountries)," in _API
    assert "&include_other_countries=${Boolean(opts.includeOtherCountries)}" in _API
    assert "export function getAtsCandidates(jobId: UUID)" in _API
    assert "/api/ats-scores/candidates?job_id=${encodeURIComponent(jobId)}" in _API
    candidates = _between(_TYPES, "export interface AtsCandidates {", "}")
    for field in ("job_country: string | null;", "fallback: boolean;", "skipped: string[];"):
        assert field in candidates, field
    summary = _between(_TYPES, "export interface BaseResumeSummary {", "\n}")
    for field in ("countries: string[];", "company: string | null;", "focus: string | null;"):
        assert field in summary, field


def test_skipped_resumes_are_one_line_with_a_button_that_scores_them_anyway():
    panel = _squash(_PANEL)
    assert '<p className="text-body-small text-muted-foreground"> {skippedCountriesLine(skipped.length, countryName(jobCountry))}{" "} <Button' in panel
    button = _squash(_between(_PANEL, "{skippedCountriesLine(", "</Button>"))
    assert "onClick={scoreOtherCountries}" in button
    assert "focusableWhenDisabled" in button and "disabled={run.isPending}" in button
    assert button.endswith("Score them anyway")
    handler = _squash(_between(_PANEL, "const scoreOtherCountries = () => {", "\n  };"))
    assert "setIncludeOtherCountries(true);" in handler
    assert "focusNext(updateRef);" in handler
    assert "runOnce(true);" in handler
    # The run posts the flag; Update scores in that view keeps it.
    assert "runAtsScores(jobId, { includeOtherCountries: all === true || includeOtherCountries })" in panel
    # Once scored anyway, the line would be untrue.
    assert "const skipped = includeOtherCountries ? [] : (candidates.data?.skipped ?? []);" in panel


def test_no_resume_for_the_country_is_said_when_scoring_fell_back():
    panel = _squash(_PANEL)
    assert "{jobCountry && candidates.data?.fallback && (" in panel
    assert "{noResumeForCountry(countryName(jobCountry))}" in panel


def test_the_sentences_read_as_the_design_says():
    assert "`${n} resumes for other countries weren't scored for this ${country} job.`" in _WORDS
    assert "`1 resume for another country wasn't scored for this ${country} job.`" in _WORDS
    assert "`None of your resumes is set for ${country}.`" in _WORDS


def test_the_sentence_helpers_pass_their_node_tests():
    result = run_node_test("lib/ats-words.test.ts")
    assert result.returncode == 0, result.stdout + result.stderr


# ── Words ──────────────────────────────────────────────────────────────────


def test_anchor_is_never_on_screen():
    from tests.test_frontend_vocabulary import ui_strings

    shown = [f"{rel}:{line}: {text}" for rel, line, text in ui_strings() if re.search(r"\banchors?\b", text, re.I)]
    assert shown == [], shown


def test_target_is_a_canonical_term():
    conventions = " ".join((_ROOT / "docs/frontend-conventions.md").read_text(encoding="utf-8").split())
    assert (
        "**Target** (the base resume's dialog for countries, role, company and focus; "
        "anchors is the agent and code word, never on screen)"
    ) in conventions
