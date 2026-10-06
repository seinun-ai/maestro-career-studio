"""A wheel install must carry every runtime data file; the source tree hides a miss."""

import fnmatch
import tomllib
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent


def test_the_wheel_ships_every_service_data_yaml():
    globs = tomllib.loads((BACKEND / "pyproject.toml").read_text())[
        "tool"]["setuptools"]["package-data"]["app"]
    files = sorted((BACKEND / "app" / "services").glob("data/*.yaml"))
    files += sorted((BACKEND / "app" / "services" / "ats").glob("data/*.yaml"))
    assert {f.name for f in files} >= {"countries.yaml", "weights.yaml"}
    for path in files:
        rel = path.relative_to(BACKEND / "app").as_posix()
        assert any(fnmatch.fnmatchcase(rel, g) for g in globs), f"{rel} not in package-data"
