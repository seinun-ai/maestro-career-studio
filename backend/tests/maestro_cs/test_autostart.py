"""`maestro autostart on|off|status`: rendering is pure, every system call goes through a runner.

Nothing here runs launchctl, systemctl, loginctl or schtasks, and nothing writes outside tmp_path.
"""
import plistlib
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path, PurePosixPath

import pytest

from maestro_cs import autostart, cli, control
from maestro_cs.autostart import (
    LABEL,
    TASK_NAME,
    UNIT_NAME,
    Autostart,
    render_plist,
    render_schtasks_create,
    render_task_xml,
    render_unit,
)
from maestro_cs.control import ControlError

OFF_STOPPED = (
    "Autostart is off. Maestro no longer starts at login and has stopped; "
    "run `maestro start` to use it now."
)
NS = "{http://schemas.microsoft.com/windows/2004/02/mit/task}"

SHIM = "/Users/ann/.local/share/uv/tools/maestro-career-studio/bin/maestro"
SHIM_SPACES = "/Users/ann lee/.local/share/uv/tools/maestro-career-studio/bin/maestro"
HOME = "/Users/ann/Library/Application Support/Maestro Career Studio"
PYTHONW = r"C:\Users\ann\AppData\Roaming\uv\tools\maestro-career-studio\Scripts\pythonw.exe"
PYTHONW_SPACES = r"C:\Users\Ann Lee\AppData\Roaming\uv\tools\maestro-career-studio\Scripts\pythonw.exe"


# --- pure rendering ------------------------------------------------------------------------

def test_plist_has_the_documented_keys():
    data = plistlib.loads(render_plist(SHIM, PurePosixPath(HOME), custom_home=False))
    assert data == {
        "Label": LABEL,
        "ProgramArguments": [SHIM, "run"],
        "RunAtLoad": True,
        "KeepAlive": {"SuccessfulExit": False},
        "ProcessType": "Interactive",
        "StandardOutPath": f"{HOME}/logs/launchd.log",
        "StandardErrorPath": f"{HOME}/logs/launchd.log",
    }
    assert LABEL == "io.github.seinun-ai.maestro-career-studio"


def test_plist_carries_maestro_home_only_when_the_user_set_one():
    data = plistlib.loads(render_plist(SHIM_SPACES, PurePosixPath("/data/mine"), custom_home=True))
    assert data["EnvironmentVariables"] == {"MAESTRO_HOME": "/data/mine"}
    assert data["ProgramArguments"][0] == SHIM_SPACES  # a path with spaces is one argv entry


@pytest.mark.skipif(shutil.which("plutil") is None, reason="plutil is macOS only")
def test_rendered_plist_passes_plutil_lint(tmp_path):
    target = tmp_path / "x.plist"
    target.write_bytes(render_plist(SHIM_SPACES, Path(HOME), custom_home=True))
    done = subprocess.run(["plutil", "-lint", str(target)], capture_output=True, text=True)
    assert done.returncode == 0, done.stdout + done.stderr


def test_unit_text_is_exact():
    text = render_unit(SHIM, PurePosixPath("/home/ann/.local/share/maestro-career-studio"))
    assert text == (
        "[Unit]\n"
        "Description=Maestro Career Studio\n"
        "\n"
        "[Service]\n"
        f"ExecStart={SHIM} run\n"
        "Restart=on-failure\n"
        "RestartSec=5\n"
        "Environment=MAESTRO_HOME=/home/ann/.local/share/maestro-career-studio\n"
        "\n"
        "[Install]\n"
        "WantedBy=default.target\n"
    )


def test_unit_quotes_paths_and_escapes_specifiers():
    text = render_unit('/home/ann lee/100%/$bin/maestro', PurePosixPath("/srv/my data"))
    assert 'ExecStart="/home/ann lee/100%%/$$bin/maestro" run\n' in text
    assert 'Environment="MAESTRO_HOME=/srv/my data"\n' in text


def test_task_xml_has_every_documented_element():
    text = render_task_xml(PYTHONW, r"LAPTOP\ann")
    assert text.startswith('<?xml version="1.0" encoding="UTF-16"?>')
    root = ET.fromstring(text.split("?>", 1)[1])
    assert root.tag == NS + "Task" and root.get("version") == "1.2"

    def find(path):
        node = root.find("/".join(NS + part for part in path.split("/")))
        assert node is not None, path
        return node.text

    assert find("RegistrationInfo/Description")
    assert find("Triggers/LogonTrigger/UserId") == r"LAPTOP\ann"
    assert find("Principals/Principal/UserId") == r"LAPTOP\ann"
    assert find("Principals/Principal/LogonType") == "InteractiveToken"
    assert find("Principals/Principal/RunLevel") == "LeastPrivilege"
    assert find("Settings/DisallowStartIfOnBatteries") == "false"
    assert find("Settings/StopIfGoingOnBatteries") == "false"
    assert find("Settings/ExecutionTimeLimit") == "PT0S"
    assert find("Settings/MultipleInstancesPolicy") == "IgnoreNew"
    assert find("Settings/Enabled") == "true"
    assert find("Settings/Hidden") == "false"
    assert find("Actions/Exec/Command") == PYTHONW
    assert find("Actions/Exec/Arguments") == "-m maestro_cs start --no-browser"
    assert "/SC" not in text  # one trigger, one user: not "any user's logon"


def test_task_xml_escapes_a_path_with_spaces_and_markup_characters():
    nasty = r"C:\Users\Ann & Bob <Lee>\AppData\Scripts\pythonw.exe"
    text = render_task_xml(nasty, r"DOM\a&b")
    assert "Ann &amp; Bob &lt;Lee&gt;" in text
    root = ET.fromstring(text.split("?>", 1)[1])
    assert root.find(f"{NS}Actions/{NS}Exec/{NS}Command").text == nasty
    assert root.find(f"{NS}Triggers/{NS}LogonTrigger/{NS}UserId").text == r"DOM\a&b"


def test_schtasks_create_reads_the_xml_file():
    assert render_schtasks_create("x.xml") == [
        "schtasks", "/Create", "/TN", "Maestro Career Studio", "/XML", "x.xml", "/F",
    ]
    assert TASK_NAME == "Maestro Career Studio"


# --- the fake system -----------------------------------------------------------------------

class Runner:
    """Records argv lists; `plan` maps a joined-argv prefix to a (returncode, text) answer."""

    def __init__(self, plan=None, missing=()):
        self.calls: list[list[str]] = []
        self.plan = plan or {}
        self.missing = set(missing)
        self.after = None

    def __call__(self, argv):
        argv = list(argv)
        self.calls.append(argv)
        if argv[0] in self.missing:
            raise FileNotFoundError(argv[0])
        if self.after:
            self.after(argv)
        for prefix, (code, text) in self.plan.items():
            if " ".join(argv).startswith(prefix):
                return subprocess.CompletedProcess(argv, code, stdout=text, stderr=text)
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    def verbs(self):
        return [" ".join(c[:3]) for c in self.calls]


def make(tmp_path, platform, runner=None, *, environ=None, **kw):
    said: list[str] = []
    obj = Autostart(
        tmp_path / "data",
        environ if environ is not None else {},
        platform=platform,
        user_home=tmp_path / "user",
        runner=runner or Runner(),
        say=said.append,
        shim=kw.pop("shim", SHIM),
        python=kw.pop("python", PYTHONW),
        which=kw.pop("which", lambda name: f"/usr/bin/{name}"),
        uid=501,
        user="ann",
        **kw,
    )
    return obj, said


def plist_file(tmp_path):
    return tmp_path / "user" / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def unit_file(tmp_path):
    return tmp_path / "user" / ".config" / "systemd" / "user" / UNIT_NAME


# --- macOS ---------------------------------------------------------------------------------

@pytest.mark.skipif(sys.platform == "win32", reason="Windows does not implement POSIX file modes")
def test_mac_on_writes_a_0644_plist_and_bootstraps_it(tmp_path):
    runner = Runner()
    auto, said = make(tmp_path, "darwin", runner)
    assert auto.handle("on") == 0
    target = plist_file(tmp_path)
    assert plistlib.loads(target.read_bytes())["ProgramArguments"] == [SHIM, "run"]
    assert target.stat().st_mode & 0o777 == 0o644
    # A best-effort bootout first: the job may be loaded although its plist is gone.
    assert runner.calls == [["launchctl", "bootout", f"gui/501/{LABEL}"],
                            ["launchctl", "bootstrap", "gui/501", str(target)]]
    assert said == ["Autostart is on. Maestro will start when you log in; it is starting now."]
    assert (tmp_path / "data" / "logs").is_dir()  # launchd will not create the log folder


def test_mac_on_twice_does_not_touch_launchd_again(tmp_path):
    runner = Runner()
    auto, said = make(tmp_path, "darwin", runner)
    auto.handle("on")
    runner.calls.clear()
    assert auto.handle("on") == 0
    assert runner.calls == []
    assert said[-1] == "Autostart is already on."


def test_mac_on_after_a_reinstall_replaces_the_loaded_job(tmp_path):
    runner = Runner()
    make(tmp_path, "darwin", runner, shim="/old/bin/maestro")[0].handle("on")
    runner.calls.clear()
    auto, _ = make(tmp_path, "darwin", runner)
    auto.handle("on")
    assert runner.verbs() == ["launchctl bootout gui/501/" + LABEL, "launchctl bootstrap gui/501"]
    assert plistlib.loads(plist_file(tmp_path).read_bytes())["ProgramArguments"][0] == SHIM


def test_mac_bootstrap_failure_leaves_nothing_behind(tmp_path):
    runner = Runner({"launchctl bootstrap": (5, "Bootstrap failed: 5: Input/output error\n")})
    auto, _ = make(tmp_path, "darwin", runner)
    with pytest.raises(ControlError, match="Input/output error"):
        auto.handle("on")
    assert not plist_file(tmp_path).exists()


def test_mac_off_boots_out_then_deletes_the_plist(tmp_path):
    runner = Runner()
    auto, said = make(tmp_path, "darwin", runner)
    auto.handle("on")
    runner.calls.clear()
    assert auto.handle("off") == 0
    assert runner.calls == [["launchctl", "bootout", f"gui/501/{LABEL}"]]
    assert not plist_file(tmp_path).exists()
    assert said[-1] == OFF_STOPPED


def test_mac_off_when_the_job_was_not_loaded_still_removes_the_file(tmp_path):
    runner = Runner()
    auto, said = make(tmp_path, "darwin", runner)
    auto.handle("on")
    runner.plan = {"launchctl bootout": (3, "Boot-out failed: 3: No such process\n")}
    assert auto.handle("off") == 0
    assert not plist_file(tmp_path).exists()
    assert said[-1] == "Autostart is off. Maestro no longer starts at login."


def test_mac_off_when_already_off_only_probes_launchd(tmp_path):
    runner = Runner({"launchctl bootout": (3, "Boot-out failed: 3: No such process\n")})
    auto, said = make(tmp_path, "darwin", runner)
    assert auto.handle("off") == 0
    assert runner.calls == [["launchctl", "bootout", f"gui/501/{LABEL}"]]
    assert said == ["Autostart is already off."]


def test_mac_off_stops_a_loaded_job_whose_plist_is_gone(tmp_path):
    runner = Runner()
    auto, said = make(tmp_path, "darwin", runner)
    assert auto.handle("off") == 0
    assert said == [OFF_STOPPED]


def test_mac_on_boots_out_a_loaded_job_with_no_plist_before_bootstrapping(tmp_path):
    runner = Runner({"launchctl bootout": (0, "")})
    auto, _ = make(tmp_path, "darwin", runner)
    auto.handle("on")
    assert runner.verbs() == [f"launchctl bootout gui/501/{LABEL}", "launchctl bootstrap gui/501"]


def test_mac_a_symlinked_plist_stays_a_link(tmp_path):
    real = tmp_path / "dotfiles" / "agent.plist"
    real.parent.mkdir()
    real.write_text("old")
    link = plist_file(tmp_path)
    link.parent.mkdir(parents=True)
    link.symlink_to(real)
    auto, _ = make(tmp_path, "darwin")
    auto.handle("on")
    assert link.is_symlink() and plistlib.loads(real.read_bytes())["Label"] == LABEL


def test_a_run_next_to_a_live_supervisor_exits_zero_so_bootstrap_is_harmless(tmp_path, monkeypatch, capsys):
    # launchd's KeepAlive only restarts after a non-zero exit; `maestro run` beside a live
    # supervisor exits 0, so bootstrapping while Maestro already runs does not loop.
    assert plistlib.loads(render_plist(SHIM, Path(HOME), False))["KeepAlive"] == {"SuccessfulExit": False}
    monkeypatch.setattr(control, "running_supervisor", lambda ctx: object())
    ctx = control.load_context({"MAESTRO_HOME": str(tmp_path / "home")})
    assert control.run(ctx) == 0
    assert "already running" in capsys.readouterr().out


def test_a_busy_port_at_login_exits_zero_so_the_supervisor_units_do_not_loop(tmp_path, monkeypatch, capsys):
    # Docker (or anything) holding 8001/3000 at login: launchd restarts a non-zero `run` every
    # ~10 s and systemd until StartLimitBurst; a clean exit 0 ends it, and the user is told why.
    assert plistlib.loads(render_plist(SHIM, Path(HOME), False))["KeepAlive"] == {"SuccessfulExit": False}
    unit = render_unit(SHIM, Path("/home/ann/.local/share/maestro-career-studio"))
    assert "Restart=on-failure" in unit and f"ExecStart={SHIM} run" in unit
    monkeypatch.setattr(control, "web_bundle_missing", lambda environ: False)
    monkeypatch.setattr(control, "port_free", lambda port, host="127.0.0.1": False)
    monkeypatch.setattr(control, "http_get_json", lambda url, timeout=2.0: {"version": "0.8.0"})
    ctx = control.load_context({"MAESTRO_HOME": str(tmp_path / "home")})
    assert control.run(ctx) == 0
    assert "Another Maestro (version 0.8.0) is already running" in capsys.readouterr().out


def test_windows_autostart_runs_start_which_refuses_a_busy_port_with_a_sentence(tmp_path, monkeypatch, capsys):
    # The Windows task has no restart setting and runs `start`; `start` raises ControlError, which
    # the CLI turns into one stderr sentence and exit 1 (never a traceback).
    xml = render_task_xml(PYTHONW, "ann")
    assert "RestartOnFailure" not in xml and "-m maestro_cs start --no-browser" in xml
    monkeypatch.setattr(control, "web_bundle_missing", lambda environ: False)
    monkeypatch.setattr(control, "port_free", lambda port, host="127.0.0.1": False)
    monkeypatch.setattr(control, "http_get_json", lambda url, timeout=2.0: None)
    monkeypatch.setenv("MAESTRO_HOME", str(tmp_path / "home"))
    assert cli.main(["start", "--no-browser"]) == 1
    err = capsys.readouterr().err
    assert err.startswith("Port ") and "is in use by another program" in err
    assert "Traceback" not in err


# --- Linux ---------------------------------------------------------------------------------

def linux_enable_creates_link(tmp_path):
    def after(argv):
        if argv[:3] == ["systemctl", "--user", "enable"]:
            wants = unit_file(tmp_path).parent / "default.target.wants"
            wants.mkdir(exist_ok=True)
            (wants / UNIT_NAME).symlink_to(unit_file(tmp_path))
        if argv[:3] == ["systemctl", "--user", "disable"]:
            (unit_file(tmp_path).parent / "default.target.wants" / UNIT_NAME).unlink()
    return after


SHOW_ENV = ["systemctl", "--user", "show-environment"]


def test_linux_on_writes_the_unit_reloads_enables_and_lingers(tmp_path):
    runner = Runner()
    runner.after = linux_enable_creates_link(tmp_path)
    auto, said = make(tmp_path, "linux", runner)
    assert auto.handle("on") == 0
    assert unit_file(tmp_path).read_text() == render_unit(SHIM, tmp_path / "data")
    assert runner.calls == [
        SHOW_ENV,
        ["systemctl", "--user", "daemon-reload"],
        ["systemctl", "--user", "enable", UNIT_NAME],
        ["loginctl", "enable-linger", "ann"],
    ]
    assert said == ["Autostart is on. Maestro will start when you log in."]
    assert auto.is_enabled() is True


def test_linux_unit_pins_maestro_home_even_when_the_shell_set_nothing(tmp_path):
    # XDG_DATA_HOME exists only in this shell; the user manager would not see it.
    env = {"XDG_DATA_HOME": str(tmp_path / "xdgdata")}
    auto, _ = make(tmp_path, "linux", environ=env)
    auto.handle("on")
    value = str(tmp_path / "data")
    if "\\" in value or " " in value:
        value = '"MAESTRO_HOME=' + value.replace("\\", "\\\\") + '"'
    else:
        value = "MAESTRO_HOME=" + value
    assert f"Environment={value}\n" in unit_file(tmp_path).read_text()


def test_linux_refused_linger_warns_but_succeeds(tmp_path):
    runner = Runner({"loginctl": (1, "Access denied\n")})
    auto, said = make(tmp_path, "linux", runner)
    assert auto.handle("on") == 0
    assert said[-1] == "Maestro will start when you log in, not at boot."


def test_linux_missing_loginctl_is_the_same_warning(tmp_path):
    auto, said = make(tmp_path, "linux", Runner(missing={"loginctl"}))
    assert auto.handle("on") == 0
    assert said[-1] == "Maestro will start when you log in, not at boot."


def test_linux_without_systemd_says_so_and_writes_nothing(tmp_path):
    auto, _ = make(tmp_path, "linux", which=lambda name: None)
    with pytest.raises(ControlError, match="needs systemd"):
        auto.handle("on")
    assert not unit_file(tmp_path).exists()
    # Unknown, not off: `maestro start` names `autostart on` only while it could work.
    assert auto.is_enabled() is None


def test_linux_a_refused_enable_rolls_the_unit_back(tmp_path):
    runner = Runner({"systemctl --user enable": (1, "Failed to connect to bus: No medium found\n")})
    auto, _ = make(tmp_path, "linux", runner)
    with pytest.raises(ControlError, match="No medium found"):
        auto.handle("on")
    assert not unit_file(tmp_path).exists()


def test_linux_off_disables_deletes_and_reloads(tmp_path):
    runner = Runner()
    runner.after = linux_enable_creates_link(tmp_path)
    auto, said = make(tmp_path, "linux", runner)
    auto.handle("on")
    runner.calls.clear()
    assert auto.handle("off") == 0
    assert runner.calls == [
        ["systemctl", "--user", "disable", UNIT_NAME],
        ["systemctl", "--user", "daemon-reload"],
    ]
    assert not unit_file(tmp_path).exists()
    assert said[-1] == "Autostart is off. Maestro no longer starts at login."
    assert auto.is_enabled() is False


def test_linux_a_refused_disable_still_removes_the_enable_link(tmp_path):
    runner = Runner()
    runner.after = linux_enable_creates_link(tmp_path)
    auto, _ = make(tmp_path, "linux", runner)
    auto.handle("on")
    link = unit_file(tmp_path).parent / "default.target.wants" / UNIT_NAME
    assert link.is_symlink()
    runner.plan = {"systemctl --user disable": (1, "Failed to connect to bus\n")}
    runner.after = None
    assert auto.handle("off") == 0
    assert not link.is_symlink() and not unit_file(tmp_path).exists()


def test_linux_unit_dir_defaults_to_dot_config_even_with_xdg_in_the_shell(tmp_path):
    auto, _ = make(tmp_path, "linux", environ={"XDG_CONFIG_HOME": str(tmp_path / "shell-only")})
    auto.handle("on")
    assert unit_file(tmp_path).is_file()
    assert not (tmp_path / "shell-only").exists()


def test_linux_unit_dir_follows_the_managers_xdg_config_home(tmp_path):
    runner = Runner({"systemctl --user show-environment": (0, "LANG=C\nXDG_CONFIG_HOME=" + str(tmp_path / "xdg") + "\n")})
    auto, _ = make(tmp_path, "linux", runner)
    auto.handle("on")
    assert (tmp_path / "xdg" / "systemd" / "user" / UNIT_NAME).is_file()
    assert not unit_file(tmp_path).exists()


def test_linux_a_relative_manager_xdg_config_home_is_ignored(tmp_path):
    runner = Runner({"systemctl --user show-environment": (0, "XDG_CONFIG_HOME=relative/dir\n")})
    auto, _ = make(tmp_path, "linux", runner)
    auto.handle("on")
    assert unit_file(tmp_path).is_file()


# --- Windows -------------------------------------------------------------------------------

class XmlSpy(Runner):
    """Captures the task file while schtasks 'reads' it, as the real program would."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.seen: list[tuple[Path, bytes]] = []

    def __call__(self, argv):
        if "/XML" in argv:
            path = Path(argv[argv.index("/XML") + 1])
            self.seen.append((path, path.read_bytes()))
        return super().__call__(argv)


def test_windows_on_creates_the_task_from_a_utf16_xml_file(tmp_path):
    runner = XmlSpy()
    auto, said = make(tmp_path, "win32", runner,
                      environ={"USERDOMAIN": "LAPTOP", "USERNAME": "ann"})
    assert auto.handle("on") == 0
    path = tmp_path / "data" / "run" / "autostart-task.xml"
    assert runner.calls == [render_schtasks_create(path)]
    (_, raw), = runner.seen
    assert raw[:2] == b"\xff\xfe"  # UTF-16 LE byte order mark
    text = raw.decode("utf-16")
    assert text.startswith('<?xml version="1.0" encoding="UTF-16"?>')
    root = ET.fromstring(text.split("?>", 1)[1])
    assert root.find(f"{NS}Triggers/{NS}LogonTrigger/{NS}UserId").text == "LAPTOP\\ann"
    assert root.find(f"{NS}Actions/{NS}Exec/{NS}Command").text == PYTHONW
    assert said == ["Autostart is on. Maestro will start when you log in."]
    assert not path.exists()  # deleted once schtasks has read it


def test_windows_the_xml_file_is_deleted_when_create_fails(tmp_path):
    runner = XmlSpy({"schtasks /Create": (1, "ERROR: Access is denied.\n")})
    auto, _ = make(tmp_path, "win32", runner)
    with pytest.raises(ControlError, match="Access is denied"):
        auto.handle("on")
    assert runner.seen and not runner.seen[0][0].exists()


def test_windows_user_without_a_domain_is_the_bare_name(tmp_path):
    auto, _ = make(tmp_path, "win32", environ={"USERNAME": "ann"})
    assert auto.windows_user == "ann"
    auto, _ = make(tmp_path, "win32", environ={})
    assert auto.windows_user == "ann"  # falls back to the injected account name


def test_windows_uses_the_windowless_interpreter_by_default(tmp_path, monkeypatch):
    seen = {}
    monkeypatch.setattr(
        autostart.runtime, "venv_python",
        lambda platform=None, windowless=False, **kw: seen.update(windowless=windowless) or Path(PYTHONW),
    )
    obj = Autostart(tmp_path, {}, platform="win32", user_home=tmp_path, runner=Runner(),
                    say=lambda *_: None, user="ann")
    obj.handle("on")
    assert seen == {"windowless": True}


def test_windows_a_path_with_spaces_needs_no_quoting_in_the_xml(tmp_path):
    runner = XmlSpy()
    auto, _ = make(tmp_path, "win32", runner, python=PYTHONW_SPACES)
    auto.handle("on")
    root = ET.fromstring(runner.seen[0][1].decode("utf-16").split("?>", 1)[1])
    assert root.find(f"{NS}Actions/{NS}Exec/{NS}Command").text == PYTHONW_SPACES


def test_windows_off_deletes_the_task(tmp_path):
    runner = Runner()
    auto, said = make(tmp_path, "win32", runner)
    assert auto.handle("off") == 0
    assert runner.calls == [["schtasks", "/Query", "/TN", TASK_NAME],
                            ["schtasks", "/Delete", "/TN", TASK_NAME, "/F"]]
    assert said == ["Autostart is off. Maestro no longer starts at login."]


def test_windows_off_when_there_is_no_task_calls_no_delete(tmp_path):
    runner = Runner({"schtasks /Query": (1, "ERROR: The system cannot find the file specified.")})
    auto, said = make(tmp_path, "win32", runner)
    assert auto.handle("off") == 0
    assert runner.verbs() == ["schtasks /Query /TN"] and said == ["Autostart is already off."]


def test_windows_cannot_carry_a_custom_home_and_says_so(tmp_path):
    auto, said = make(tmp_path, "win32", environ={"MAESTRO_HOME": r"D:\mine"})
    auto.handle("on")
    assert any("setx MAESTRO_HOME" in line for line in said)


# --- status and wiring ---------------------------------------------------------------------

@pytest.mark.parametrize("platform", ["darwin", "linux", "win32"])
def test_status_reports_on_and_off(tmp_path, platform):
    runner = Runner({"schtasks /Query": (1, "ERROR: not found")})
    if platform == "linux":
        runner.after = linux_enable_creates_link(tmp_path)
    auto, said = make(tmp_path, platform, runner)
    assert auto.handle("status") == 0
    assert said[-1] == "Autostart is off."
    runner.plan = {}
    auto.handle("on")
    assert auto.is_enabled() is True
    assert auto.handle("status") == 0
    assert said[-1] == "Autostart is on."


def test_status_is_unknown_when_windows_has_no_schtasks(tmp_path):
    auto, said = make(tmp_path, "win32", Runner(missing={"schtasks"}))
    assert auto.is_enabled() is None
    auto.handle("status")
    assert said[-1] == "Autostart: can't tell on this computer."


def test_a_timed_out_system_call_is_a_sentence(tmp_path):
    def slow(argv):
        raise subprocess.TimeoutExpired(argv, 30)
    auto, _ = make(tmp_path, "darwin", slow)
    with pytest.raises(ControlError, match="did not answer"):
        auto.handle("on")
    assert not plist_file(tmp_path).exists()


def test_the_real_is_enabled_answers_none_when_the_system_cannot_be_asked(real_is_enabled, tmp_path):
    assert real_is_enabled(platform="freebsd14", environ={}, user_home=tmp_path) is None

    def slow(argv):
        raise subprocess.TimeoutExpired(argv, 30)
    assert real_is_enabled(platform="win32", environ={}, user_home=tmp_path, runner=slow) is None


def test_unsupported_platform_is_a_sentence(tmp_path):
    auto, _ = make(tmp_path, "freebsd14")
    with pytest.raises(ControlError, match="isn't supported"):
        auto.handle("on")


def test_status_json_wiring_uses_is_enabled(monkeypatch):
    monkeypatch.setattr(autostart, "is_enabled", lambda *a, **k: True)
    assert control.autostart_enabled() is True


def test_module_is_enabled_reads_the_real_layout_from_injected_dirs(tmp_path):
    target = plist_file(tmp_path)
    target.parent.mkdir(parents=True)
    target.write_bytes(b"x")
    # conftest stubs the module-level is_enabled; go through the class it wraps.
    obj = Autostart(tmp_path, {}, platform="darwin", user_home=tmp_path / "user", runner=Runner())
    assert obj.is_enabled() is True


# --- the command line ----------------------------------------------------------------------

def test_cli_routes_autostart_actions(monkeypatch, tmp_path):
    seen = []

    class Fake:
        def __init__(self, home, environ, **kw):
            seen.append(("init", home))

        def handle(self, action):
            seen.append(action)
            return 0

    monkeypatch.setenv("MAESTRO_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(autostart, "Autostart", Fake)
    for action in ("on", "off", "status"):
        assert cli.main(["autostart", action]) == 0
    assert [s for s in seen if isinstance(s, str)] == ["on", "off", "status"]


def test_cli_rejects_other_actions(capsys):
    assert cli.main(["autostart", "maybe"]) == 2
    assert "invalid choice" in capsys.readouterr().err


def test_cli_prints_a_control_error_as_one_sentence(monkeypatch, tmp_path, capsys):
    class Boom:
        def __init__(self, *a, **k): ...
        def handle(self, action):
            raise ControlError("Autostart needs systemd.")

    monkeypatch.setenv("MAESTRO_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(autostart, "Autostart", Boom)
    assert cli.main(["autostart", "on"]) == 1
    assert capsys.readouterr().err.strip() == "Autostart needs systemd."
