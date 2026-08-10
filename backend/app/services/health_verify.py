"""LLM verification of rule-detector accusations (framework hatch: detectors
allege, the model may veto or annotate — never create). Keeps deterministic
arithmetic intact: a veto only removes a weight-0 ask; an annotation only adds
context text. Verdicts are cached via the prior report so re-runs are stable."""
import hashlib
import json
import logging
from string import Template as StringTemplate

from sqlalchemy.orm import Session

from app.services import llm, model_settings, prompts

logger = logging.getLogger(__name__)


def _payload_hash(kind: str, payload: dict) -> str:
    body = json.dumps({"kind": kind, "payload": payload}, sort_keys=True)
    return hashlib.sha256(body.encode()).hexdigest()[:16]


def verify_detections(
    db: Session,
    resume: dict,
    gap_hits: list[dict],
    c2_hit: dict | None,
    *,
    prior_cache: dict | None = None,
) -> tuple[list[dict], dict | None, dict]:
    """Returns (gap_hits, c2_hit, cache). Vetoed detections are dropped;
    annotated ones gain a 'context' key. On any LLM failure the detections
    pass through unchanged (the verifier must never block the report)."""
    items = []
    for i, gap in enumerate(gap_hits):
        items.append({"id": f"gap:{i}", "kind": "employment_gap", "detail": gap,
                      "hash": _payload_hash("gap", gap)})
    if c2_hit:
        items.append({"id": "c2", "kind": "years_overclaim", "detail": c2_hit,
                      "hash": _payload_hash("c2", c2_hit)})
    if not items:
        return gap_hits, c2_hit, {}

    prior_cache = prior_cache or {}
    cache: dict = {}
    pending = []
    for item in items:
        if item["hash"] in prior_cache:
            cache[item["hash"]] = prior_cache[item["hash"]]
        else:
            pending.append(item)

    if pending:
        try:
            template = prompts.get_prompt("resume_finding_verify", db)
            prompt = StringTemplate(template).safe_substitute(
                resume_json=json.dumps(resume, indent=2),
                detections_json=json.dumps(
                    [{"id": p["id"], "kind": p["kind"], "detail": p["detail"]}
                     for p in pending], indent=2),
            )
            raw = llm.call_openai(
                prompt=prompt, model=model_settings.get_smart_model(db),
                response_format="json", trace_name="resume_finding_verify",
            )
            by_id = {v.get("id"): v for v in (raw or {}).get("verdicts") or []
                     if isinstance(v, dict)}
            for p in pending:
                v = by_id.get(p["id"]) or {}
                verdict = v.get("verdict") if v.get("verdict") in ("keep", "veto") else "keep"
                cache[p["hash"]] = {"verdict": verdict,
                                    "context": str(v.get("context") or "")[:200]}
        except Exception:  # noqa: BLE001 — verifier failure must never block the report
            logger.exception("finding verifier failed; keeping detections as-is")
            for p in pending:
                cache[p["hash"]] = {"verdict": "keep", "context": ""}

    kept_gaps = []
    for gap in gap_hits:
        entry = cache.get(_payload_hash("gap", gap), {"verdict": "keep", "context": ""})
        if entry["verdict"] == "veto":
            continue
        if entry.get("context"):
            gap = dict(gap, context=entry["context"])
        kept_gaps.append(gap)

    kept_c2 = c2_hit
    if c2_hit:
        entry = cache.get(_payload_hash("c2", c2_hit), {"verdict": "keep", "context": ""})
        if entry["verdict"] == "veto":
            kept_c2 = None
        elif entry.get("context"):
            kept_c2 = dict(c2_hit, context=entry["context"])
    return kept_gaps, kept_c2, cache
