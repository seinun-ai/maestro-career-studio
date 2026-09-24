"""Pin: the web app's "Queue for agent" files its proposal as "you".

POST /api/proposals takes `proposed_by` from the body only for the web app
(an MCP client is named by its headers, and a body can say nothing but "you").
Without the field, a promotion made after the proposed_by migration stores
NULL and reads as "a connected agent" (tests/test_proposals_proposed_by.py).
"""

from __future__ import annotations

from pathlib import Path

_API = Path(__file__).resolve().parents[2] / "frontend" / "lib" / "api.ts"


def _promote_post_body() -> str:
    source = _API.read_text()
    fn = source[source.index("export async function promoteJobToAgentQueue"):]
    post = fn[fn.index('apiFetch<{ id: UUID }>("/api/proposals"'):]
    return " ".join(post[: post.index("});")].split())


def test_queue_for_agent_files_as_you():
    assert 'proposed_by: "you",' in _promote_post_body()

