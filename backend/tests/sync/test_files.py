"""Portable sync files must stay inside their roots and preserve verified bytes."""

import base64
import hashlib
import os
from pathlib import Path

import pytest

from app.config import settings


@pytest.fixture
def roots(tmp_path, monkeypatch):
    paths = {}
    for name in ("applications", "base_resumes", "kb_documents"):
        path = tmp_path / "source" / name
        path.mkdir(parents=True)
        monkeypatch.setattr(settings, f"{name}_dir", path)
        paths[name] = path
    return paths


def _file(value="applications:X/resume.pdf", data=b"verified bytes"):
    return {
        "path": value,
        "sha256": hashlib.sha256(data).hexdigest(),
        "b64": base64.b64encode(data).decode("ascii"),
    }


@pytest.mark.parametrize("name", ["applications", "base_resumes", "kb_documents"])
def test_round_trip_between_machine_roots(roots, tmp_path, monkeypatch, name):
    from app.services.sync import files

    source = roots[name] / "X" / "evidence" / "a.png"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"\x00\x01\x02\x03\xff")
    portable = f"{name}:X/evidence/a.png"
    assert files.to_portable(str(source)) == portable
    packed = files.pack_dir(name, "X", max_bytes=25 * 1024 * 1024)
    assert packed == [_file(portable, b"\x00\x01\x02\x03\xff")]

    target = tmp_path / "destination" / name
    monkeypatch.setattr(settings, f"{name}_dir", target)
    assert files.from_portable(portable) == str(target / "X/evidence/a.png")
    assert not target.exists()
    files.unpack(packed)
    files.unpack(packed)  # A resend replaces the same file safely.
    assert (target / "X/evidence/a.png").read_bytes() == b"\x00\x01\x02\x03\xff"
    assert source.read_bytes() == b"\x00\x01\x02\x03\xff"
    assert [p for p in target.rglob("*") if p.is_file()] == [target / "X/evidence/a.png"]


def test_none_and_paths_outside_roots_are_dropped(roots, tmp_path):
    from app.services.sync import files

    assert files.to_portable(None) is None
    assert files.from_portable(None) is None
    assert files.to_portable(str(tmp_path / "private.pdf")) is None
    assert (
        files.to_portable(str(roots["applications"].with_name("applications-extra") / "a")) is None
    )


@pytest.mark.parametrize(
    "relative",
    [
        "../outside.pdf",
        "X/../../outside.pdf",
        "/outside.pdf",
        "//host/file",
        "C:/file",
        "X\\file",
        "X/\x00file",
    ],
)
def test_unsafe_relative_paths_are_refused(roots, relative):
    from app.services.sync import files

    with pytest.raises(ValueError):
        files.from_portable(f"applications:{relative}")
    with pytest.raises(ValueError):
        files.pack_dir("applications", relative, max_bytes=1024)
    with pytest.raises(ValueError):
        files.unpack([_file(f"applications:{relative}")])
    assert list(roots["applications"].iterdir()) == []


@pytest.mark.parametrize("value", ["unknown:X/a", "applications/X/a", "/private.pdf", ""])
def test_unknown_or_missing_portable_root_is_refused(roots, value):
    from app.services.sync import files

    with pytest.raises(ValueError):
        files.from_portable(value)
    with pytest.raises(ValueError):
        files.unpack([_file(value)])


def test_unknown_pack_root_is_refused(roots):
    from app.services.sync import files

    with pytest.raises(ValueError):
        files.pack_dir("unknown", "X", max_bytes=1024)


@pytest.mark.parametrize("kind", ["file", "directory", "dangling", "inside"])
def test_symlinks_are_refused_in_both_directions(roots, tmp_path, kind):
    from app.services.sync import files

    root = roots["applications"]
    directory = root / "X"
    directory.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "a.pdf").write_bytes(b"outside")
    target = outside / "a.pdf"
    if kind == "directory":
        target = outside
    elif kind == "dangling":
        target = outside / "absent.pdf"
    elif kind == "inside":
        target = root / "original.pdf"
        target.write_bytes(b"original")
    link = directory / "link"
    link.symlink_to(target)
    relative = "X/link/a.pdf" if kind == "directory" else "X/link"

    with pytest.raises(ValueError):
        files.to_portable(str(root / relative))
    with pytest.raises(ValueError):
        files.from_portable(f"applications:{relative}")
    with pytest.raises(ValueError):
        files.pack_dir("applications", "X", max_bytes=1024)
    with pytest.raises(ValueError):
        files.unpack([_file(f"applications:{relative}")])
    assert (outside / "a.pdf").read_bytes() == b"outside"
    assert link.is_symlink()


def test_symlinked_root_is_refused(roots, tmp_path, monkeypatch):
    from app.services.sync import files

    alias = tmp_path / "alias"
    alias.symlink_to(roots["applications"], target_is_directory=True)
    monkeypatch.setattr(settings, "applications_dir", alias)
    with pytest.raises(ValueError):
        files.pack_dir("applications", "", max_bytes=1024)
    with pytest.raises(ValueError):
        files.from_portable("applications:X/a.pdf")
    with pytest.raises(ValueError):
        files.unpack([_file()])


def test_pack_skips_only_regenerated_page_preview_pngs(roots):
    from app.services.sync import files

    directory = roots["applications"] / "X"
    for relative in (
        "resume.pdf",
        "resume.pages/page-1.png",
        "resume.pages/info.json",
        "evidence/page-1.png",
    ):
        path = directory / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"a")
    packed = files.pack_dir("applications", "X", max_bytes=3)
    assert {entry["path"] for entry in packed} == {
        "applications:X/resume.pdf",
        "applications:X/resume.pages/info.json",
        "applications:X/evidence/page-1.png",
    }


def test_pack_skips_nonregular_files_without_blocking(roots):
    from app.services.sync import files

    directory = roots["applications"] / "X"
    directory.mkdir()
    os.mkfifo(directory / "pipe")
    (directory / "resume.pdf").write_bytes(b"a")
    assert files.pack_dir("applications", "X", max_bytes=1) == [
        _file("applications:X/resume.pdf", b"a")
    ]


def test_pack_enforces_total_bytes_across_files(roots):
    from app.services.sync import files

    directory = roots["applications"] / "X"
    directory.mkdir()
    (directory / "a").write_bytes(b"123")
    (directory / "b").write_bytes(b"456")
    with pytest.raises(ValueError):
        files.pack_dir("applications", "X", max_bytes=5)
    assert len(files.pack_dir("applications", "X", max_bytes=6)) == 2


def test_pack_root_and_empty_files_work_at_zero_limit(roots):
    from app.services.sync import files

    (roots["base_resumes"] / "base.json").write_bytes(b"")
    assert files.pack_dir("base_resumes", "", max_bytes=0) == [_file("base_resumes:base.json", b"")]
    assert files.pack_dir("applications", "missing", max_bytes=0) == []
    with pytest.raises(ValueError):
        files.pack_dir("base_resumes", "", max_bytes=-1)


def test_evidence_larger_than_five_mebibytes_is_refused(roots):
    from app.services.sync import files

    path = roots["applications"] / "X/evidence/a.png"
    path.parent.mkdir(parents=True)
    data = b"a" * (5 * 1024 * 1024 + 1)
    path.write_bytes(data)
    with pytest.raises(ValueError):
        files.pack_dir("applications", "X", max_bytes=25 * 1024 * 1024)
    path.unlink()
    with pytest.raises(ValueError):
        files.unpack([_file("applications:X/evidence/a.png", data)])
    assert not path.exists()


def test_bad_sha256_is_refused_before_any_disk_write(roots):
    from app.services.sync import files

    path = roots["applications"] / "X/resume.pdf"
    entry = _file()
    entry["sha256"] = "0" * 64
    with pytest.raises(ValueError):
        files.unpack([entry])
    assert not path.parent.exists()
    path.parent.mkdir()
    path.write_bytes(b"old")
    with pytest.raises(ValueError):
        files.unpack([entry])
    assert path.read_bytes() == b"old"


@pytest.mark.parametrize("encoded", ["%%%", "YQ==!", "not base64", "\u2603"])
def test_malformed_base64_is_refused_before_disk_write(roots, encoded):
    from app.services.sync import files

    entry = _file()
    entry["b64"] = encoded
    with pytest.raises(ValueError):
        files.unpack([entry])
    assert list(roots["applications"].iterdir()) == []


def test_unpack_writes_atomically_and_fsyncs(roots, monkeypatch):
    from app.services.sync import files

    target = roots["applications"] / "X/resume.pdf"
    target.parent.mkdir()
    target.write_bytes(b"old")
    replace, fsync = os.replace, os.fsync
    events = []

    def record_fsync(fd):
        fsync(fd)
        events.append("fsync")

    def record_replace(source, destination):
        assert events == ["fsync"]
        assert target.read_bytes() == b"old"
        assert Path(source).parent == target.parent
        assert Path(source).read_bytes() == b"verified bytes"
        replace(source, destination)
        events.append("replace")

    monkeypatch.setattr(os, "fsync", record_fsync)
    monkeypatch.setattr(os, "replace", record_replace)
    files.unpack([_file()])
    assert events == ["fsync", "replace"]
    assert target.read_bytes() == b"verified bytes"
    assert list(target.parent.iterdir()) == [target]


def test_failed_replace_preserves_existing_file_and_removes_temp(roots, monkeypatch):
    from app.services.sync import files

    target = roots["applications"] / "X/resume.pdf"
    target.parent.mkdir()
    target.write_bytes(b"old")

    def fail_replace(source, destination):
        raise OSError("simulated disk failure")

    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(OSError, match="simulated disk failure"):
        files.unpack([_file()])
    assert target.read_bytes() == b"old"
    assert list(target.parent.iterdir()) == [target]


def _tree(root):
    return sorted(str(p) for p in root.rglob("*"))


def test_to_portable_matches_a_root_reached_through_a_symlinked_parent(tmp_path, monkeypatch):
    from app.services.sync import files

    real = tmp_path / "real"
    (real / "applications" / "X").mkdir(parents=True)
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    for name in ("base_resumes", "kb_documents"):
        (real / name).mkdir()
        monkeypatch.setattr(settings, f"{name}_dir", link / name)
    monkeypatch.setattr(settings, "applications_dir", link / "applications")
    resolved_form = real / "applications" / "X" / "a.pdf"
    assert files.to_portable(str(resolved_form)) == "applications:X/a.pdf"
    assert files.to_portable(str(link / "applications" / "X" / "a.pdf")) == "applications:X/a.pdf"
    # The path itself is never followed through a symlink inside the root.
    (real / "applications" / "elsewhere").symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError):
        files.to_portable(str(real / "applications" / "elsewhere" / "a.pdf"))


def _unpack_refused(files, bundle, root, **kwargs):
    before = _tree(root)
    with pytest.raises(ValueError) as excinfo:
        files.unpack(bundle, **kwargs)
    assert _tree(root) == before
    message = str(excinfo.value)
    assert str(root) not in message
    assert not any(token.strip("'\"").startswith("/") for token in message.split())


def test_unpack_refuses_a_file_and_a_directory_at_the_same_name_before_any_write(roots):
    from app.services.sync import files

    bundle = [_file("applications:X/a", b"1"), _file("applications:X/a/b", b"2")]
    _unpack_refused(files, bundle, roots["applications"])
    _unpack_refused(files, bundle[::-1], roots["applications"])


def test_unpack_refuses_duplicate_and_case_or_unicode_variant_entries(roots):
    from app.services.sync import files

    root = roots["applications"]
    _unpack_refused(files, [_file("applications:X/a", b"1"), _file("applications:X/a", b"1")], root)
    _unpack_refused(files, [_file("applications:X/a", b"1"), _file("applications:x/A", b"1")], root)
    nfc, nfd = "applications:X/\u00e9", "applications:X/e\u0301"
    _unpack_refused(files, [_file(nfc, b"1"), _file(nfd, b"1")], root)
    _unpack_refused(
        files, [_file("applications:X/\u00e9", b"1"), _file("applications:x/e\u0301/b", b"1")], root
    )


def test_unpack_refuses_overlong_components_and_paths_before_any_write(roots):
    from app.services.sync import files

    root = roots["applications"]
    ok = "a" * 255
    _unpack_refused(
        files, [_file("applications:X/ok", b"1"), _file(f"applications:X/{ok}a", b"1")], root
    )
    _unpack_refused(
        files,
        [_file("applications:X/ok", b"1"), _file("applications:X/" + "\u00e9" * 128, b"1")],
        root,
    )
    deep = "/".join(["d" * 100] * 11)
    _unpack_refused(
        files, [_file("applications:X/ok", b"1"), _file(f"applications:{deep}", b"1")], root
    )
    files.unpack([_file(f"applications:X/{ok}", b"1")])
    assert (root / "X" / ok).read_bytes() == b"1"


def test_unpack_refuses_a_directory_target_and_a_file_parent_before_any_write(roots):
    from app.services.sync import files

    root = roots["applications"]
    (root / "X" / "dir").mkdir(parents=True)
    (root / "Y").write_bytes(b"a file")
    _unpack_refused(
        files, [_file("applications:Z/new", b"1"), _file("applications:X/dir", b"1")], root
    )
    _unpack_refused(
        files, [_file("applications:Z/new", b"1"), _file("applications:Y/b", b"1")], root
    )
    _unpack_refused(
        files, [_file("applications:Z/new", b"1"), _file("applications:Y/b/c", b"1")], root
    )


@pytest.mark.parametrize("entry", [None, "applications:X/a", 5, ["applications:X/a"]])
def test_unpack_refuses_a_non_dict_entry_before_any_write(roots, entry):
    from app.services.sync import files

    _unpack_refused(files, [_file("applications:X/ok", b"1"), entry], roots["applications"])


def test_unpack_turns_an_os_error_while_checking_into_a_pathless_value_error(roots, monkeypatch):
    from app.services.sync import files

    root = roots["applications"]
    real = files._checked

    def boom(name, rel, *, allow_empty):
        real(name, rel, allow_empty=allow_empty)
        raise OSError(f"[Errno 36] File name too long: '{root}/X/a'")

    monkeypatch.setattr(files, "_checked", boom)
    _unpack_refused(files, [_file()], root)


def test_unpack_enforces_a_total_decoded_byte_cap_before_any_write(roots):
    from app.services.sync import files

    root = roots["applications"]
    bundle = [_file("applications:X/a", b"123"), _file("applications:X/b", b"456")]
    _unpack_refused(files, bundle, root, max_bytes=5)
    files.unpack(bundle, max_bytes=6)
    assert (root / "X/a").read_bytes() == b"123" and (root / "X/b").read_bytes() == b"456"
    _unpack_refused(files, [_file("applications:X/c", b"1")], root, max_bytes=0)


def test_pack_skips_files_it_cannot_send_and_counts_them(roots, monkeypatch):
    from app.services.sync import files

    # The filesystem cannot hold a 256-byte name, so lower the cap instead.
    monkeypatch.setattr(files, "_MAX_COMPONENT_BYTES", 12)

    directory = roots["kb_documents"]
    (directory / "good.pdf").write_bytes(b"ok")
    (directory / "C:\\Users\\me\\resume.pdf").write_bytes(b"backslash")
    (directory / "a-long-name.pdf").write_bytes(b"long")
    os.mkfifo(directory / "pipe")
    unreadable = directory / "locked.pdf"
    unreadable.write_bytes(b"secret")
    unreadable.chmod(0)
    (directory / ".sync-abc123.tmp").write_bytes(b"leftover")
    try:
        packed, skipped = files.pack_dir_with_skips("kb_documents", "", max_bytes=1024)
        assert files.pack_dir("kb_documents", "", max_bytes=1024) == packed
    finally:
        unreadable.chmod(0o644)
    assert [entry["path"] for entry in packed] == ["kb_documents:good.pdf"]
    expected = 4 if os.geteuid() != 0 else 3
    assert skipped == expected


def test_pack_with_skips_reports_zero_when_nothing_is_skipped(roots):
    from app.services.sync import files

    (roots["kb_documents"] / "a.pdf").write_bytes(b"a")
    assert files.pack_dir_with_skips("kb_documents", "", max_bytes=10)[1] == 0


def test_unpack_still_refuses_a_backslash_name(roots):
    from app.services.sync import files

    _unpack_refused(
        files, [_file("kb_documents:C:\\Users\\me\\resume.pdf", b"1")], roots["kb_documents"]
    )
