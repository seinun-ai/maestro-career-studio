"""Pure helpers of scripts/build_wheel.py, check_wheel.py and smoke_uv_install.py.

The scripts themselves are exercised by the CI `uv-wheel`/`uv-smoke` jobs; what is pinned here
needs no npm, no uv and no network: which files may enter the wheel, the version rewrite, the
member rules, and the smoke's failure wording.
"""
import importlib.util
import json
import socket
import sys
import tomllib
import zipfile
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


build_wheel = _load("build_wheel")
check_wheel = _load("check_wheel")
smoke = _load("smoke_uv_install")

GOOD = [
    "app/main.py", "app/assets/fonts/xcharter/XCharter-Roman.otf", "app/prompts/extract.txt",
    "mcp_server/http.py", "migrations/env.py", "migrations/script.py.mako",
    "migrations/prompt_defaults.lock.json", "migrations/versions/0001_init.py",
    "maestro_cs/cli.py", "maestro_cs/maestro.env.template", "maestro_cs/data/example.json",
    "maestro_cs/web/server.js", "maestro_cs/web/.next/BUILD_ID",
    "maestro_cs/web/.next/static/chunks/main.js", "maestro_cs/web/public/favicon.ico",
    "maestro_career_studio-1.0.0.dist-info/METADATA",
    "app/templates/LICENSE-resume-templates.txt",
    "maestro_career_studio-1.0.0.dist-info/licenses/LICENSE",
    "maestro_career_studio-1.0.0.dist-info/licenses/NOTICE",
    "maestro_career_studio-1.0.0.dist-info/licenses/THIRD_PARTY_NOTICES.md",
]


# --- build_wheel -------------------------------------------------------------------------

def test_staging_drops_tests_and_host_scripts():
    tracked = [
        "backend/app/main.py", "backend/maestro_cs/cli.py", "backend/pyproject.toml",
        "backend/tests/conftest.py", "backend/tests/maestro_cs/test_cli.py",
        "backend/mcp_server/server.py", "backend/mcp_server/tests/test_http.py",
        "backend/scripts/sync_key.py", "frontend/app/page.tsx", "README.md",
    ]
    assert build_wheel.staged_paths(tracked) == [
        "backend/app/main.py", "backend/maestro_cs/cli.py", "backend/pyproject.toml",
        "backend/mcp_server/server.py",
    ]


def test_staging_keeps_a_file_that_only_looks_like_a_test_folder():
    assert build_wheel.staged_paths(["backend/app/tests_helpers.py", "backend/testsuite/x.py"]) == [
        "backend/app/tests_helpers.py", "backend/testsuite/x.py"]


PYPROJECT = '[build-system]\nrequires = ["setuptools"]\n\n[project]\nname = "x"\nversion = "0.8.0"\n' \
            'dependencies = ["a>=1"]\n\n[tool.other]\nversion = "9"\n'


def test_version_rewrite_touches_only_the_project_version():
    text = build_wheel.rewrite_version(PYPROJECT, "0.0.0.dev1")
    assert build_wheel.project_version(text) == "0.0.0.dev1"
    assert 'version = "9"' in text and 'name = "x"' in text
    assert text.count("0.0.0.dev1") == 1


def test_version_rewrite_refuses_a_file_without_a_version():
    with pytest.raises(ValueError):
        build_wheel.rewrite_version('[project]\nname = "x"\n', "1.0.0")


def test_the_real_pyproject_is_rewritable():
    text = (SCRIPTS.parent / "backend" / "pyproject.toml").read_text(encoding="utf-8")
    assert build_wheel.project_version(build_wheel.rewrite_version(text, "9.9.9")) == "9.9.9"


@pytest.mark.parametrize("with_notice", [True, False])
def test_staging_copies_root_licenses_and_declares_only_staged_files(tmp_path, monkeypatch, with_notice):
    root = tmp_path / "repo"
    (root / "backend").mkdir(parents=True)
    checkout = (SCRIPTS.parent / "backend/pyproject.toml").read_text(encoding="utf-8")
    (root / "backend/pyproject.toml").write_text(checkout, encoding="utf-8")
    licenses = ["LICENSE", "THIRD_PARTY_NOTICES.md"]
    if with_notice:
        licenses.insert(1, "NOTICE")
    for name in licenses:
        (root / name).write_text(f"legal text for {name}\n", encoding="utf-8")
    monkeypatch.setattr(build_wheel, "ROOT", root)
    monkeypatch.setattr(build_wheel, "git_tracked", lambda: ["backend/pyproject.toml"])

    stage = build_wheel.stage_backend(tmp_path / "stage", "9.9.9")

    config = tomllib.loads((stage / "pyproject.toml").read_text(encoding="utf-8"))
    assert config["project"]["license-files"] == licenses
    assert config["project"]["license"] == "Apache-2.0"
    assert config["project"]["version"] == "9.9.9"
    for name in licenses:
        assert (stage / name).read_bytes() == (root / name).read_bytes()
        assert not (root / "backend" / name).exists()
    assert (root / "backend/pyproject.toml").read_text(encoding="utf-8") == checkout


@pytest.mark.parametrize("missing", ["LICENSE", "THIRD_PARTY_NOTICES.md"])
def test_staging_refuses_a_missing_required_root_license(tmp_path, monkeypatch, missing):
    (tmp_path / "backend").mkdir()
    (tmp_path / "backend/pyproject.toml").write_text(PYPROJECT, encoding="utf-8")
    for name in ("LICENSE", "THIRD_PARTY_NOTICES.md"):
        if name != missing:
            (tmp_path / name).write_text("legal text", encoding="utf-8")
    monkeypatch.setattr(build_wheel, "ROOT", tmp_path)
    monkeypatch.setattr(build_wheel, "git_tracked", lambda: ["backend/pyproject.toml"])
    with pytest.raises(FileNotFoundError, match=missing):
        build_wheel.stage_backend(tmp_path / "stage", None)


# --- check_wheel -------------------------------------------------------------------------

def test_a_complete_member_list_has_no_problems():
    assert check_wheel.name_problems(GOOD) == []


@pytest.mark.parametrize("missing", [
    "app/main.py", "migrations/script.py.mako", "maestro_cs/web/server.js",
    "maestro_cs/data/example.json", "maestro_cs/web/.next/BUILD_ID",
])
def test_each_required_file_is_required(missing):
    assert any(missing in p for p in check_wheel.name_problems([n for n in GOOD if n != missing]))


@pytest.mark.parametrize("filename", [
    "LICENSE-resume-templates.txt", "LICENSE", "NOTICE", "THIRD_PARTY_NOTICES.md",
])
def test_each_license_file_is_required(filename):
    rest = [n for n in GOOD if Path(n).name != filename]
    assert any(filename in p for p in check_wheel.name_problems(rest))


@pytest.mark.parametrize("wrong_path", [
    "LICENSE", "app/LICENSE", "other/licenses/LICENSE",
    "maestro_career_studio-1.0.0.dist-info/LICENSE",
    "nested/maestro_career_studio-1.0.0.dist-info/licenses/LICENSE",
])
def test_a_license_outside_dist_info_licenses_does_not_count(wrong_path):
    rest = [n for n in GOOD if Path(n).name != "LICENSE"]
    assert any("LICENSE" in p for p in check_wheel.name_problems([*rest, wrong_path]))


def test_license_paths_accept_another_wheel_version():
    names = [n.replace("-1.0.0.dist-info/", "-9.9.9.dist-info/") for n in GOOD]
    assert check_wheel.name_problems(names) == []


@pytest.mark.parametrize("folder", [
    "maestro_cs/web/.next/static/", "maestro_cs/web/public/", "app/assets/fonts/xcharter/",
    "app/prompts/", "migrations/versions/",
])
def test_each_required_folder_needs_a_member(folder):
    rest = [n for n in GOOD if not n.startswith(folder)]
    assert any("missing" in p for p in check_wheel.name_problems(rest))


@pytest.mark.parametrize("extra", [
    "tests/test_x.py", "mcp_server/tests/test_http.py", "app/__pycache__/a.cpython-312.pyc",
    "app/.env", "maestro_cs/web/node_modules/sharp/lib/index.js",
    "maestro_cs/web/node_modules/@img/sharp-darwin-arm64/lib.js", "maestro_cs/web/a.node",
    "maestro_cs/web/.env", "maestro_cs/web/.env.production", "maestro_cs/web/.env.local",
    "maestro_cs/web/lib.dylib", "maestro_cs/web/lib.so", "maestro_cs/web/lib.so.1.2",
    "maestro_cs/web/lib.dll", "maestro_cs/web/node.exe", "base_resumes/me.json",
])
def test_each_forbidden_member_is_named(extra):
    problems = check_wheel.name_problems([*GOOD, extra])
    assert len(problems) == 1 and extra in problems[0]


def test_an_env_example_template_is_not_an_env_file():
    assert check_wheel.name_problems([*GOOD, "maestro_cs/web/.env.example"]) == []
    assert not check_wheel.is_env_file("maestro.env.template")


def test_the_build_drops_env_files_from_the_web_copy(tmp_path):
    web = tmp_path / "web"
    (web / "sub").mkdir(parents=True)
    for name in (".env", ".env.production", "sub/.env.local", ".env.example", "server.js"):
        (web / name).write_text("x", encoding="utf-8")
    build_wheel.drop_env_files(web)
    assert sorted(p.relative_to(web).as_posix() for p in web.rglob("*") if p.is_file()) == [
        ".env.example", "server.js"]


def test_the_demo_resume_is_the_only_base_resume_allowed():
    assert check_wheel.name_problems([*GOOD, "base_resumes/example.json"]) == []


def test_every_problem_is_listed_not_just_the_first():
    problems = check_wheel.name_problems(["app/x.pyc", "tests/a.py"])
    assert len([p for p in problems if p.startswith("forbidden")]) == 2
    assert len([p for p in problems if p.startswith("missing")]) > 5


def _wheel(path: Path, members: list[str], *, version="1.0.0", name="maestro-career-studio",
           scripts=("maestro", "maestro-career-studio-mcp")) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        for member in members:
            archive.writestr(member, "x")
        archive.writestr("maestro_career_studio-1.0.0.dist-info/METADATA",
                         f"Metadata-Version: 2.4\nName: {name}\nVersion: {version}\n")
        archive.writestr(
            "maestro_career_studio-1.0.0.dist-info/entry_points.txt",
            "[console_scripts]\n" + "".join(f"{s} = pkg:main\n" for s in scripts))
    return path


MEMBERS = [n for n in GOOD if not n.endswith("/METADATA")]


def test_a_good_wheel_passes(tmp_path):
    wheel = _wheel(tmp_path / "maestro_career_studio-1.0.0-py3-none-any.whl", MEMBERS)
    assert check_wheel.check(wheel, "1.0.0") == []


def test_the_file_name_and_metadata_must_agree(tmp_path):
    wheel = _wheel(tmp_path / "maestro_career_studio-1.0.0-py3-none-any.whl", MEMBERS, version="2.0.0")
    assert any("differs from the file name" in p for p in check_wheel.check(wheel))
    assert any("not the expected 3.0.0" in p for p in check_wheel.check(wheel, "3.0.0"))


def test_a_platform_tagged_or_misnamed_wheel_fails(tmp_path):
    tagged = _wheel(tmp_path / "maestro_career_studio-1.0.0-cp312-cp312-macosx_11_0_arm64.whl", MEMBERS)
    assert any("is not maestro_career_studio" in p for p in check_wheel.check(tagged))
    renamed = _wheel(tmp_path / "maestro_career_studio-1.0.0-py3-none-any.whl", MEMBERS, name="other")
    assert any("METADATA Name" in p for p in check_wheel.check(renamed))


def test_both_entry_points_are_required(tmp_path):
    wheel = _wheel(tmp_path / "maestro_career_studio-1.0.0-py3-none-any.whl", MEMBERS, scripts=("maestro",))
    assert check_wheel.check(wheel) == ["entry_points.txt has no maestro-career-studio-mcp script"]


def test_size_is_capped(tmp_path, monkeypatch):
    wheel = _wheel(tmp_path / "maestro_career_studio-1.0.0-py3-none-any.whl", MEMBERS)
    monkeypatch.setattr(check_wheel, "MAX_BYTES", 10)
    assert any("over the" in p for p in check_wheel.check(wheel))


def test_a_file_that_is_not_a_zip_is_a_problem_with_its_type(tmp_path):
    bad = tmp_path / "maestro_career_studio-1.0.0-py3-none-any.whl"
    bad.write_bytes(b"not a zip")
    assert any("BadZipFile" in p for p in check_wheel.check(bad))


# --- smoke_uv_install --------------------------------------------------------------------


def test_the_smoke_expects_the_tools_the_full_set_serves():
    # The smoke is stdlib only, so it can't import the registry; this keeps its count true.
    from mcp_server.server import list_registered_tool_names

    assert smoke.EXPECTED_TOOLS == len(list_registered_tool_names("full"))


@pytest.mark.parametrize("demo, pdf, message", [
    ({"slug": "example", "pdf_rendered_at": None, "render_error": "no ready template"},
     b"%PDF", "no ready template"),
    ({"slug": "example", "pdf_rendered_at": None, "render_error": None},
     b"%PDF", "startup finished"),
    ({"slug": "example", "pdf_rendered_at": "now", "render_error": None},
     b"not a PDF", "PDF"),
])
def test_demo_smoke_requires_the_demo_pdf_and_reports_startup_failure(monkeypatch, demo, pdf, message):
    probe = smoke.Smoke.__new__(smoke.Smoke)
    probe.backend_port, probe.facts = 18001, {}
    other = {"slug": "other", "pdf_rendered_at": "now"}

    def get(port, path):
        if path.endswith("/pdf"):
            return smoke.Reply(200, {}, pdf)
        return smoke.Reply(200, {}, json.dumps([other, demo]).encode())

    probe.get = get
    monkeypatch.setattr(smoke.time, "sleep", lambda _: pytest.fail("startup render is synchronous"))
    with pytest.raises(smoke.Failure, match=message):
        probe.demo_base()


def test_demo_smoke_accepts_a_committed_render_with_a_downloadable_pdf():
    probe = smoke.Smoke.__new__(smoke.Smoke)
    probe.backend_port, probe.facts = 18001, {}
    demo = {"slug": "example", "pdf_rendered_at": "now", "render_error": None}
    probe.get = lambda port, path: smoke.Reply(
        200, {}, b"%PDF-1.7" if path.endswith("/pdf") else json.dumps([demo]).encode())
    probe.demo_base()
    assert probe.facts["demo base"] == ["example"]

def test_a_refused_connection_reads_as_no_answer_but_a_bug_names_its_type():
    assert smoke.describe(ConnectionRefusedError(61, "Connection refused")).startswith("no answer")
    assert smoke.describe(socket.timeout("timed out")).startswith("no answer")
    assert smoke.describe(KeyError("score")).startswith("KeyError")
    assert smoke.describe(ValueError("bad json")) == "ValueError: bad json"
    assert smoke.describe(smoke.Failure("expected 400, got 200")) == "expected 400, got 200"


@pytest.mark.parametrize(("printed", "version"), [
    ("maestro-career-studio 0.8.0", "0.8.0"), ("maestro-career-studio 0.8.0\n", "0.8.0"),
    ("maestro-career-studio 10.8.0", "10.8.0"), ("", ""),
])
def test_the_printed_version_is_the_last_word(printed, version):
    assert smoke.version_printed(printed) == version


@pytest.mark.parametrize("suffix", ["0", "8.0", ".0"])
def test_a_version_suffix_is_not_the_version(suffix):
    assert smoke.version_printed("maestro-career-studio 10.8.0") != suffix


def test_the_bare_404_is_the_pinned_shape():
    assert smoke.bare_404_problems(404, {"content-length": "0", "date": "x"}, b"") == []
    assert smoke.bare_404_problems(404, {"content-length": "0"}, b"") == []


@pytest.mark.parametrize(("status", "headers", "body"), [
    (405, {"content-length": "0"}, b""),
    (404, {"content-length": "22", "content-type": "application/json"}, b'{"detail":"Not Found"}'),
    (404, {"content-length": "0", "vary": "Origin"}, b""),
    (404, {"content-length": "0", "access-control-allow-origin": "http://localhost:3000"}, b""),
    (404, {"content-length": "0", "server": "uvicorn"}, b""),
])
def test_a_drifted_404_is_caught(status, headers, body):
    assert smoke.bare_404_problems(status, headers, body)


def test_security_headers_match_next_config():
    text = (SCRIPTS.parent / "frontend" / "next.config.ts").read_text(encoding="utf-8")
    for name, value in smoke.NEXT_SECURITY_HEADERS.items():
        assert f'"{value}"' in text, f"{name} differs from frontend/next.config.ts"
    headers = dict(smoke.NEXT_SECURITY_HEADERS)
    assert smoke.security_header_problems(headers) == []
    headers["x-frame-options"] = "SAMEORIGIN"
    del headers["referrer-policy"]
    assert len(smoke.security_header_problems(headers)) == 2


def test_tail_lines_keeps_the_end_and_survives_a_missing_file(tmp_path):
    log = tmp_path / "a.log"
    log.write_text("\n".join(str(i) for i in range(100)), encoding="utf-8")
    assert smoke.tail_lines(log, 3) == ["97", "98", "99"]
    assert smoke.tail_lines(tmp_path / "none.log") == []
