"""Task 10 pins: opt-in full automation and a write-only job-site password.

Source pins follow test_frontend_automations.py: browser review is separate.
Credentials must never enter query/mutation caches or be populated from a GET.
"""

from pathlib import Path
import re

import pytest

from tests.node_ts import ts_map

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
_CARD = _FRONTEND / "components/settings/full-automation-section.tsx"


@pytest.fixture
def source():
    # Missing implementation fails the assertions, rather than collection.
    return _CARD.read_text() if _CARD.exists() else ""


def test_full_automation_is_mounted_after_the_connected_agents_card():
    page = (_FRONTEND / "app/settings/page.tsx").read_text()
    assert "<FullAutomationSection />" in page
    assert page.index("<ConnectedAgentsCard />") < page.index("<FullAutomationSection />")
    assert page.index("<FullAutomationSection />") < page.index("<McpWorkflowSection />")
    tabs = (_FRONTEND / "lib/settings-tabs.ts").read_text()
    assert 'anchors: ["connected-agents", "full-automation",' in tabs


def test_the_card_explains_what_the_switch_allows(source):
    assert 'id="full-automation"' in source
    assert 'title="Full automation"' in source
    assert (
        "When this is on, your connected agent submits a queued job without asking when "
        "its final review shows nothing to check. It asks you about the rest."
    ) in source
    assert 'label="Submit clean applications without asking"' in source
    assert "<Switch" in source


def test_only_turning_on_requires_the_standing_consent_dialog(source):
    assert "useConfirm" in source
    assert 'title: "Turn on full automation?"' in source
    assert 'confirmLabel: "Turn on"' in source
    assert 'cancelLabel: "Cancel"' in source
    assert "consent: true" in source
    assert "if (enabled && !(await confirm(" in source
    assert (
        "Your agent will submit queued jobs whose final review is clean, without asking "
        "each time. The daily limit still applies. You can turn this off at any time."
    ) in source


def test_the_switch_preserves_the_latest_whole_settings_value(source):
    assert '"/api/settings/full-automation"' in source
    assert 'method: "PUT"' in source
    assert "body: JSON.stringify({ value: enabled })" in source
    assert 'scope: { id: "settings-auto-apply" }' in source
    assert "AUTOMATIONS_KEY" in source  # refresh the Apply prompt after a toggle
    assert "void qc.invalidateQueries({ queryKey: AUTOMATIONS_KEY })" in source
    assert "useSingleFlight" in source


def test_login_is_shown_only_while_on_and_uses_the_committed_routes(source):
    assert "initial.full_automation && <JobSiteLoginSection />" in source
    assert "hidden={!enabled}" not in source
    assert "Job-site login" in source
    assert '"/api/settings/job-site-login"' in source
    assert 'method: "DELETE"' in source
    assert "Used only for job-site accounts. Your agent gets it while full automation is on, " in source
    assert "so it passes through your agent's AI provider. Use it for nothing else." in source


def test_password_input_is_new_local_input_and_has_an_accessible_hint(source):
    assert 'type="email"' in source
    assert 'type="password"' in source
    assert 'autoComplete="new-password"' in source
    assert "placeholder=" not in source


def test_password_hint_is_accessible_and_names_the_bounds(source):
    assert "A password is saved. Type a new one to replace it." in source
    assert "At least 8 characters." in source
    assert "aria-describedby={hintId}" in source
    assert 'minLength={8}' in source and 'maxLength={200}' in source


def test_password_input_uses_only_local_input(source):
    assert 'value={newPassword}' in source
    assert not re.search(r"value=\{[^}]*\b(?:data|initial|status)\.password\b", source)


def test_login_edits_warn_before_leaving_and_stay_locked_during_a_write(source):
    assert "useLeaveGuard(dirty || busy)" in source
    assert "readOnly={busy}" in source
    assert "disabled={!dirty || busy}" in source
    assert "onSubmit=" in source
    assert "inFlight.current" in source


def test_password_is_omitted_unless_typed_and_cleared_after_save_or_clear(source):
    assert '...(newPassword ? { password: newPassword } : {})' in source
    assert 'setNewPassword("")' in source
    assert "loginStatus(result)" in source
    assert "return { email, password_set };" in source
    login_write = source[source.index("function useJobSiteLoginEditor("):]
    # react-query's mutation variables would retain the password after Save.
    assert "useMutation(" not in login_write
    assert "mutate(" not in login_write
    for sink in ("console.", "localStorage", "sessionStorage", "JSON.stringify(result)"):
        assert sink not in source


def test_clear_requires_a_destructive_confirmation(source):
    assert 'title: "Clear job-site login?"' in source
    assert 'confirmLabel: "Clear"' in source
    assert "destructive: true" in source
    assert "await editor.clear()" in source


def test_switch_updates_can_be_turned_off_while_on_another_settings_tab():
    page = (_FRONTEND / "app/automations/page.tsx").read_text()
    assert "staleTime: Infinity" not in page
    assert "The catalog reads shipped files and the full-automation setting." in page


def test_auto_apply_setting_writes_share_one_serial_queue(source):
    limits = (_FRONTEND / "components/settings/auto-apply-section.tsx").read_text()
    for card in (source, limits):
        assert 'scope: { id: "settings-auto-apply" }' in card


def test_off_discards_login_drafts_and_their_leave_guard(source):
    assert "initial.full_automation && <JobSiteLoginSection />" in source
    assert "hidden={!enabled}" not in source
    login = source[source.index("function JobSiteLoginSection("):]
    assert "function JobSiteLoginSection()" in login
    assert "enabled," not in login


def test_login_actions_dim_and_block_pointer_input_when_disabled(source):
    actions = source[source.index("function JobSiteLoginActions("):]
    disabled_style = 'className="data-disabled:pointer-events-none data-disabled:opacity-50"'
    assert actions.count(disabled_style) == 2


def test_login_email_column_aligns_with_the_password_field(source):
    assert 'className="grid content-end gap-1.5"' in source


def test_failed_login_loads_offer_retry_before_the_loading_state(source):
    error = source.index("isLoadFailure(login) && !login.data ? (")
    assert error < source.index("<Skeleton", error)
    assert "<LoadErrorState" in source
    assert "onRetry={() => void login.refetch()}" in source
    assert "query={query}" in source  # the switch uses SettingCard's shared gate


def test_the_web_login_response_type_carries_no_password():
    types = (_FRONTEND / "lib/types.ts").read_text()
    match = re.search(r"export interface JobSiteLoginStatus \{([^}]*)\}", types)
    assert match is not None
    assert "email: string | null;" in match[1]
    assert "password_set: boolean;" in match[1]
    assert not re.search(r"\bpassword\s*:", match[1])


@pytest.mark.parametrize(
    "case",
    [
        ("ada@example.com", "", {"email": "ada@example.com"}),
        ("ada@example.com", "new-job-password", {"email": "ada@example.com", "password": "new-job-password"}),
        ("ada@example.com", "        ", {"email": "ada@example.com", "password": "        "}),
    ],
)
def test_login_payload_omits_only_an_empty_password(source, tmp_path, case):
    email, password, want = case
    match = re.search(r"\nfunction jobSiteLoginPayload\(.*?\n\}", source, re.S)
    assert match is not None
    module = tmp_path / "login-payload.ts"
    module.write_text(match[0] + "\nexport const probe = ([email, password]) => jobSiteLoginPayload(email, password);\n")
    assert ts_map(str(module), "probe", [[email, password]]) == [want]


def test_even_an_unexpected_response_password_is_removed_before_caching(source, tmp_path):
    match = re.search(r"\nfunction loginStatus\(.*?\n\}", source, re.S)
    assert match is not None
    types = (_FRONTEND / "lib/types.ts").read_text()
    status_type = re.search(r"export interface JobSiteLoginStatus \{[^}]*\}", types)
    assert status_type is not None
    module = tmp_path / "login-status.ts"
    module.write_text(status_type[0] + match[0] + "\nexport const probe = loginStatus;\n")
    assert ts_map(str(module), "probe", [{
        "email": "ada@example.com", "password_set": True, "password": "unexpected-secret",
    }]) == [{"email": "ada@example.com", "password_set": True}]
