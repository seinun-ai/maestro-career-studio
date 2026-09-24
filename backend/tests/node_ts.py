"""Run a frontend TypeScript module under node's own type stripping.

For the parity tests that pin a Python twin to the web app's TypeScript
(`test_agent_names.py`, `test_server_words.py`). With no node, or a node too old
to strip types, the parity half SKIPS locally and FAILS in CI (`CI` set): the
backend job installs node 24 for exactly these tests, so a skip there would be
a parity check nobody runs.
"""
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"


def _unavailable(why: str) -> None:
    if os.environ.get("CI"):
        pytest.fail(f"{why}: the CI backend job must provide node 24 (setup-node)")
    pytest.skip(why)


def ts_map(module: str, export: str, values: list) -> list:
    """`values.map(module[export])`, computed by node, as JSON."""
    node = shutil.which("node")
    if node is None:
        _unavailable("node is not installed")
    probe = subprocess.run([node, "-p", "Boolean(process.features.typescript)"],
                           capture_output=True, text=True, check=False)
    if probe.stdout.strip() != "true":
        _unavailable("this node cannot strip TypeScript types")
    script = (
        f"import({json.dumps(module)}).then((m) => process.stdout.write("
        f"JSON.stringify({json.dumps(values)}.map((v) => m[{json.dumps(export)}](v)))))"
    )
    done = subprocess.run([node, "-e", script], cwd=FRONTEND, capture_output=True,
                          text=True, check=True)
    return json.loads(done.stdout)
