"""The web UI is one build run one way: Next's standalone server.

Docker and the `uv tool install` wheel both run `.next/standalone/server.js`
(docs/plans/2026-10-10-desktop-step3-uv-install.md). Two properties are easy to
lose silently and expensive to find late, so they are pinned as source text:

1. The bundle carries no native code. Next's image optimizer pulls in `sharp`
   (libvips, per-OS binaries); nothing here uses `next/image`, so the optimizer
   is off and sharp is excluded from output tracing. One build then runs on
   every OS, which is what lets the wheel stay `py3-none-any`.
2. The Docker runner stage runs that same server. A container must listen on
   all interfaces; docker-compose.yml binds only the HOST side to 127.0.0.1.
"""

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CONFIG = (REPO / "frontend" / "next.config.ts").read_text()
DOCKERFILE = (REPO / "frontend" / "Dockerfile").read_text()
COMPOSE = (REPO / "docker-compose.yml").read_text()


def _runner_stage() -> str:
    stages = [s for s in re.split(r"(?m)^FROM ", DOCKERFILE) if s.strip()]
    runner = [s for s in stages if re.search(r"\bAS runner\b", s.splitlines()[0])]
    assert len(runner) == 1, "frontend/Dockerfile needs exactly one `AS runner` stage"
    return runner[0]


def test_next_builds_a_standalone_server():
    assert 'output: "standalone"' in CONFIG


def test_image_optimizer_is_off_so_no_native_sharp_ships():
    assert "images: { unoptimized: true }" in CONFIG


def test_sharp_is_excluded_from_output_tracing():
    assert "outputFileTracingExcludes" in CONFIG
    assert "node_modules/sharp/**" in CONFIG
    assert "node_modules/@img/**" in CONFIG


def test_runner_copies_standalone_static_and_public():
    runner = _runner_stage()
    assert re.search(r"COPY --from=builder\b.*/app/\.next/standalone \./", runner)
    assert re.search(r"COPY --from=builder\b.*/app/\.next/static \./\.next/static", runner)
    assert re.search(r"COPY --from=builder\b.*/app/public \./public", runner)


def test_runner_no_longer_copies_node_modules_or_package_json():
    runner = _runner_stage()
    assert "/app/node_modules" not in runner
    assert "/app/package.json" not in runner


def test_runner_runs_node_server_js_not_next_start():
    runner = _runner_stage()
    assert 'CMD ["node", "server.js"]' in runner
    assert "npm" not in runner.split("CMD", 1)[1]


def test_runner_listens_on_all_interfaces_and_port_3000():
    runner = _runner_stage()
    assert re.search(r"(?m)^ENV HOSTNAME=0\.0\.0\.0\b", runner)
    assert re.search(r"(?m)^ENV .*\bPORT=3000\b", runner)


def test_compose_still_binds_the_host_side_to_loopback():
    # The runner listens on 0.0.0.0 inside the container only because of this.
    assert '"127.0.0.1:${FRONTEND_HOST_PORT:-3000}:3000"' in COMPOSE


def test_compose_web_origins_follow_the_published_web_port():
    """The browser's Origin carries the HOST port. A default fixed at :3000 made the
    backend refuse every save once FRONTEND_HOST_PORT moved, while pages still loaded."""
    line = next(s for s in COMPOSE.splitlines() if s.strip().startswith("ALLOWED_WEB_ORIGINS:"))
    port = "${FRONTEND_HOST_PORT:-3000}"
    assert f"http://localhost:{port}" in line
    assert f"http://127.0.0.1:{port}" in line
    assert line.strip().startswith("ALLOWED_WEB_ORIGINS: ${ALLOWED_WEB_ORIGINS:-")  # an explicit value still wins


def test_npm_start_runs_the_standalone_server_on_loopback():
    """`next start` warns under standalone output; `npm start` assembles and runs server.js."""
    package = json.loads((REPO / "frontend" / "package.json").read_text())
    assert package["scripts"]["start"] == "node scripts/start-standalone.mjs"
    script = (REPO / "frontend" / "scripts" / "start-standalone.mjs").read_text()
    assert 'HOSTNAME: "127.0.0.1"' in script
    assert "server.js" in script
    assert '".next", "static"' in script and '"public"' in script
