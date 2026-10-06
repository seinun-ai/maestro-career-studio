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
    assert files.to_portable(str(roots["applications"].with_name("applications-extra") / "a")) is None


@pytest.mark.parametrize(
    "relative",
    ["../outside.pdf", "X/../../outside.pdf", "/outside.pdf", "//host/file", "C:/file", "X\\file", "X/\x00file"],
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
    for relative in ("resume.pdf", "resume.pages/page-1.png", "resume.pages/info.json", "evidence/page-1.png"):
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
    assert files.pack_dir("applications", "X", max_bytes=1) == [_file("applications:X/resume.pdf", b"a")]


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
