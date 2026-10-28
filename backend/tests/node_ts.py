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


def _node_with_typescript() -> str:
    node = shutil.which("node")
    if node is None:
        _unavailable("node is not installed")
    probe = subprocess.run([node, "-p", "Boolean(process.features.typescript)"],
                           capture_output=True, text=True, check=False)
    if probe.stdout.strip() != "true":
        _unavailable("this node cannot strip TypeScript types")
    return node


def run_node_test(test_file: str) -> subprocess.CompletedProcess[str]:
    """Run a frontend node:test file with node's built-in TypeScript support."""
    return subprocess.run([_node_with_typescript(), "--test", test_file], cwd=FRONTEND,
                          capture_output=True, text=True, check=False)


def run_node_render_test(test_file: str) -> subprocess.CompletedProcess[str]:
    """Run a `components/**/*.test.mjs` file, which renders real components and so needs the web
    app's installed packages (React, the TypeScript compiler; `components/render-harness.mjs`).

    The backend CI job installs none, so there this SKIPS and the frontend CI job runs every such
    file after `npm ci` (`.github/workflows/ci.yml`). A missing node still fails in CI: it is
    checked before the skip.
    """
    _node_with_typescript()
    if not (FRONTEND / "node_modules" / "typescript").is_dir():
        pytest.skip("frontend packages are not installed; the frontend CI job runs this file")
    return run_node_test(test_file)


def ts_map(module: str, export: str, values: list) -> list:
    """`values.map(module[export])`, computed by node, as JSON."""
    node = _node_with_typescript()
    script = (
        f"import({json.dumps(module)}).then((m) => process.stdout.write("
        f"JSON.stringify({json.dumps(values)}.map((v) => m[{json.dumps(export)}](v)))))"
    )
    done = subprocess.run([node, "-e", script], cwd=FRONTEND, capture_output=True,
                          text=True, check=True)
    return json.loads(done.stdout)
