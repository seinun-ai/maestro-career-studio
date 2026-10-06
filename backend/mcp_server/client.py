from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import tempfile
from email.message import Message
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

import httpx

from app.services.autofill_profile import canonical_identity_from_profile
from app.services.http_client import new_client
from app.write_origin import encode_detail

DEFAULT_BASE_URL = "http://localhost:8000"

# Client-side request windows. The default (60s) fits a plain read or write.
# The backend's own caps are longer for two kinds of call, and a client window
# shorter than the server's leaves the server finishing work the caller has
# already been told timed out:
#   - LLM calls: the backend's provider timeout is 120s (services/llm.py).
#   - renders/compiles: pdf_render and typst_compiler each kill a compile at
#     60s, and a request can fall back to a second engine.
_LLM_TIMEOUT = 300.0
_RENDER_TIMEOUT = 150.0

# An echoed error body is for diagnosis, not a data channel: a 422 can carry the
# caller's whole payload back, and one tool result must stay proportionate.
_ERROR_BODY_MAX_CHARS = 1000
_ERROR_ITEMS_MAX = 8

# Heavy per-row fields left out of list views; the detail tool carries them.
_KB_POINT_LIST_OMIT = frozenset({"usage", "merge_sources"})
_JOB_EXPORT_OMIT = frozenset({"raw_text", "raw_text_hash", "extracted_json"})

logger = logging.getLogger(__name__)

# Opt-in page images: default longest side, and a hard cap on the base64 payload
# the MCP client will accept. The live audit blew a ~617K-char tool result at
# the hardcoded 120 dpi; 1024px is legible and the 1MB encoded cap is the backstop.
_PAGE_IMAGE_MAX_DIMENSION_DEFAULT = 1024
_PAGE_IMAGE_B64_CAP = 1_000_000


def _drop_none(**kwargs: Any) -> dict[str, Any]:
    return {k: v for k, v in kwargs.items() if v is not None}


def _without_eeo_values(review: Any) -> Any:
    """The client's own strip, beside the server's (two gates, the `get_autofill_profile`
    precedent): an EEO answer's value never reaches an agent (SYSTEM.md
    {#inv-filled-answers-local})."""
    if not isinstance(review, dict):
        return review
    for flag in review.get("flags") or []:
        if isinstance(flag, dict) and flag.get("eeo"):
            flag.pop("answer", None)
    return review


def _origin_headers(origin_detail: str | None) -> dict[str, str]:
    """Provenance for a KB write or a proposal. Every MCP write is origin 'mcp';
    the detail names the client so the entity timeline (or the proposal's
    proposed_by) can say who. The name is percent-encoded (encode_detail), since
    a header value must be ASCII and a client may call itself "クロード"."""
    headers = {"X-Maestro-CS-Origin": "mcp"}
    detail = encode_detail(origin_detail)
    if detail:
        headers["X-Maestro-CS-Origin-Detail"] = detail
    return headers


def _inspect_pdf(pdf_path: Path) -> dict[str, Any]:
    """Return page count and em-dash findings without rasterizing the PDF."""
    degraded = {
        "page_count": None,
        "em_dash_found": False,
        "em_dash_pages": [],
    }
    try:
        import pdfplumber

        with pdfplumber.open(str(pdf_path)) as doc:
            page_texts = [page.extract_text() or "" for page in doc.pages]
    except Exception:
        logger.debug("PDF inspection failed for %s; degrading", pdf_path, exc_info=True)
        return degraded

    em_dash_pages = [
        page_number
        for page_number, text in enumerate(page_texts, start=1)
        if "\u2014" in text
    ]
    return {
        "page_count": len(page_texts),
        "em_dash_found": bool(em_dash_pages),
        "em_dash_pages": em_dash_pages,
    }


# PDFium is not thread-safe (the backend serializes it behind
# app.services.pdfium_lock.PDFIUM_LOCK). This process needs no lock today:
# FastMCP calls sync tools directly on its event-loop thread, so these two
# helpers never run concurrently. If a tool ever reaches them from a thread
# (asyncio.to_thread, a threaded HTTP transport), take a lock here too.
def _render_pdf_previews(pdf_path: Path, target_id: str) -> dict[str, Any]:
    """Render one PNG per page next to the PDF and scan for em dashes (U+2014).

    Degrades gracefully (page_count=None, no images) if the bytes aren't a real
    PDF or the render/extract libraries are unavailable — callers must not have
    their core result broken by a preview failure.
    """
    metadata = _inspect_pdf(pdf_path)
    try:
        # pypdfium2 (BSD-3-Clause/Apache-2.0) renders. PyMuPDF is deliberately
        # not used — it is AGPL-3.0.
        import pypdfium2 as pdfium
    except Exception:
        logger.debug("PDF preview skipped: render library unavailable", exc_info=True)
        return {**metadata, "page_images": []}

    page_images: list[str] = []
    try:
        # Drop any PNGs from a prior, possibly longer render of this id so a stale
        # {id}.pN.png can't be Read as if it belonged to the current render.
        for old in pdf_path.parent.glob(f"{target_id}.p*.png"):
            old.unlink()
        doc = pdfium.PdfDocument(str(pdf_path))
        try:
            page_count = len(doc)
            for i in range(page_count):
                png_path = pdf_path.parent / f"{target_id}.p{i + 1}.png"
                # One render at ~120 dpi keeps previews legible. Bytes stay on
                # disk unless the explicit one-page MCP tool is called.
                doc[i].render(scale=120 / 72).to_pil().save(png_path, format="PNG")
                page_images.append(str(png_path))
        finally:
            doc.close()
    except Exception:
        # Bad/corrupt PDF (pdfium raises PdfiumError) — degrade, don't raise.
        logger.debug("PDF preview failed for %s; degrading", pdf_path, exc_info=True)
        return {**metadata, "page_images": []}

    return {
        "page_count": page_count,
        "page_images": page_images,
        "em_dash_found": metadata["em_dash_found"],
        "em_dash_pages": metadata["em_dash_pages"],
    }


def _render_pdf_page_at_cap(pdf_path: Path, page_number: int, max_dimension_px: int) -> bytes:
    """Rasterize one 1-based page so its longest side equals max_dimension_px."""
    try:
        import pypdfium2 as pdfium
    except Exception as exc:
        raise BackendError(
            "page preview unavailable; ensure the MCP PDF render dependencies "
            "(pypdfium2 and Pillow) are installed, then retry"
        ) from exc
    if max_dimension_px < 1:
        raise BackendError("max_dimension_px must be >= 1")
    try:
        doc = pdfium.PdfDocument(str(pdf_path))
        try:
            page = doc[page_number - 1]
            longest = max(page.get_width(), page.get_height())
            scale = max_dimension_px / longest if longest else 1.0
            image = page.render(scale=scale).to_pil()
        finally:
            doc.close()
    except BackendError:
        raise
    except Exception as exc:
        raise BackendError(
            "page preview unavailable; ensure the MCP PDF render dependencies "
            "(pypdfium2 and Pillow) are installed, then retry"
        ) from exc
    from io import BytesIO

    buf = BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def _safe_filename(filename: str | None, fallback: str) -> str:
    """Reduce a server-supplied filename to one safe basename."""
    candidate = (filename or "").replace("\x00", "").replace("\\", "/")
    candidate = candidate.rsplit("/", 1)[-1].strip()
    return fallback if candidate in {"", ".", ".."} else candidate


def _response_filename(response: httpx.Response, fallback: str) -> str:
    disposition = response.headers.get("content-disposition")
    filename: str | None = None
    if disposition:
        message = Message()
        message["content-disposition"] = disposition
        filename = message.get_filename()
    return _safe_filename(filename, fallback)


def _default_upload_root() -> Path:
    return Path(__file__).resolve().parents[2] / ".playwright-mcp" / "uploads"


def _host_visible(path: Path, upload_root: Path) -> str:
    """Rewrite an upload path into the one the BROWSER can open.

    This server may run inside the backend container (`docker exec`), while the
    Playwright browser that opens the staged PDF runs on the host. The container
    path is correct for the write and useless to the browser, which fails to open
    it rather than erroring — a silent dead end. `MAESTRO_CS_UPLOAD_HOST_ROOT`
    names the host side of the same bind mount; unset (the venv transport, where
    both are one filesystem) this is inert, because rewriting a path that was
    already right is its own bug.

    The host may be Windows (`C:\\...`, or `\\\\wsl.localhost\\...` for a WSL
    clone) while this code runs on Linux, so the join follows the ROOT's
    flavour: a POSIX join would hand the browser `C:\\...\\uploads/<id>/<file>`.
    """
    host_root = os.environ.get("MAESTRO_CS_UPLOAD_HOST_ROOT")
    if not host_root:
        return str(path)
    windows = "\\" in host_root or (len(host_root) > 1 and host_root[1] == ":")
    root = PureWindowsPath(host_root) if windows else PurePosixPath(host_root)
    return str(root.joinpath(*path.relative_to(upload_root).parts))


def _upload_root() -> Path:
    return Path(
        os.environ.get("MAESTRO_CS_UPLOAD_DIR")
        or os.environ.get("CAREER_STUDIO_UPLOAD_DIR")
        or _default_upload_root()
    )


_PLAYWRIGHT_DIR = ".playwright-mcp"


def _mounted_playwright_path(file_path: str) -> Path | None:
    """Map a HOST path under a `.playwright-mcp/` directory onto this process's
    own copy of that tree, or None when the path has no such segment or the
    mapping would leave the tree.

    The Playwright browser runs on the host and reports host paths; this server
    may run inside the backend container (`docker exec`), where the same tree is
    bind-mounted at the PARENT of the upload dir (compose: `/app/.playwright-mcp`,
    with MAESTRO_CS_UPLOAD_DIR=/app/.playwright-mcp/uploads). Like _host_visible
    this follows the host path's own flavour, since the host may be Windows.
    Nothing here widens what can be read: a `..` component is refused outright
    and the resolved result (symlinks included) must stay inside the mount.
    """
    windows = "\\" in file_path or (len(file_path) > 1 and file_path[1] == ":")
    parts = (PureWindowsPath(file_path) if windows else PurePosixPath(file_path)).parts
    if _PLAYWRIGHT_DIR not in parts:
        return None
    suffix = parts[parts.index(_PLAYWRIGHT_DIR) + 1 :]
    if not suffix or any(part in {"..", "."} or "/" in part or "\\" in part for part in suffix):
        return None
    mount = _upload_root().parent.resolve()
    if mount.name != _PLAYWRIGHT_DIR:
        return None
    candidate = mount.joinpath(*suffix).resolve()
    return candidate if candidate.is_relative_to(mount) else None


_SESSION_SUMMARY_KEYS = (
    "id", "job_id", "base_resume", "status", "application_id", "user_prompt",
    "stale_reason", "created_at", "updated_at",
)


def _session_summary(session: dict[str, Any]) -> dict[str, Any]:
    summary = {k: session[k] for k in _SESSION_SUMMARY_KEYS if k in session}
    gaps = session.get("gaps_json")
    if isinstance(gaps, dict):
        summary["gap_count"] = sum(
            len(category.get("gaps") or [])
            for category in gaps.get("categories") or []
            if isinstance(category, dict)
        )
    resolutions = session.get("resolutions_json")
    if isinstance(resolutions, list):
        summary["resolution_count"] = len(resolutions)
    return summary


def _format_error_body(body: Any) -> str:
    """One readable line for an error body: FastAPI's `detail` (a string, or a
    pydantic list shown as `loc.path: message`), never the echoed `input`, and
    capped. The full structured body stays on BackendError.body."""
    detail = body.get("detail") if isinstance(body, dict) and "detail" in body else body
    if isinstance(detail, list):
        lines = []
        for item in detail[:_ERROR_ITEMS_MAX]:
            if isinstance(item, dict) and "msg" in item:
                loc = ".".join(str(part) for part in item.get("loc") or [])
                lines.append(f"{loc}: {item['msg']}" if loc else str(item["msg"]))
            else:
                lines.append(str(item))
        if len(detail) > _ERROR_ITEMS_MAX:
            lines.append(f"... and {len(detail) - _ERROR_ITEMS_MAX} more")
        text = "; ".join(lines)
    elif isinstance(detail, str):
        text = detail
    else:
        text = json.dumps(detail, default=str) if detail is not None else ""
    if len(text) > _ERROR_BODY_MAX_CHARS:
        text = text[:_ERROR_BODY_MAX_CHARS] + f"... [truncated, {len(text)} chars]"
    return text


def _atomic_write_bytes(destination: Path, content: bytes) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        suffix=".tmp",
        dir=destination.parent,
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, destination)
    finally:
        temp_path.unlink(missing_ok=True)


class BackendError(Exception):
    def __init__(self, message: str, status_code: int | None = None, body: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class BackendClient:
    def __init__(self, base_url: str | None = None, timeout: float = 60.0):
        self.base_url = (base_url or os.environ.get("BACKEND_URL") or DEFAULT_BASE_URL).rstrip("/")
        self._timeout = timeout

    def _send(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        """One HTTP round trip with the shared error mapping."""
        url = f"{self.base_url}{path}"
        try:
            with new_client(timeout=self._timeout) as client:
                response = client.request(method, url, **kwargs)
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout) as exc:
            # The request never left this process (no connection / no pooled
            # connection), so no write can have landed: same message as refused.
            raise BackendError(
                f"Could not reach the maestro-career-studio backend at {self.base_url}. "
                "Check that it is running; the BACKEND_URL environment variable sets "
                "the address this server uses."
            ) from exc
        except httpx.TimeoutException as exc:
            seconds = kwargs.get("timeout") or self._timeout
            message = f"{method} {path} timed out after {seconds:g}s."
            if method.upper() not in {"GET", "HEAD"}:
                message += (
                    " The backend may still have completed the write; read the "
                    "current state (the matching list_/get_ tool) before repeating it."
                )
            raise BackendError(message) from exc
        except httpx.HTTPError as exc:
            raise BackendError(f"HTTP error talking to backend: {exc}") from exc

        if response.status_code >= 400:
            try:
                body = response.json()
            except ValueError:
                body = response.text
            raise BackendError(
                f"Backend returned {response.status_code}: {_format_error_body(body)}",
                status_code=response.status_code,
                body=body,
            )
        return response

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        response = self._send(method, path, **kwargs)
        if response.status_code == 204 or not response.content:
            return None
        return response.json()

    def _request_raw_response(
        self, method: str, path: str, **kwargs: Any
    ) -> httpx.Response:
        return self._send(method, path, **kwargs)

    # ---- read ----
    def list_base_resumes(self) -> Any:
        return self._request("GET", "/api/base-resumes")

    def get_base_resume(self, slug: str) -> Any:
        return self._request("GET", f"/api/base-resumes/{slug}")

    def list_jobs(
        self,
        limit: int | None = None,
        offset: int | None = None,
        without_application: bool | None = None,
    ) -> Any:
        params: dict[str, Any] = {}
        if limit is not None:
            params["limit"] = limit
        if offset is not None:
            params["offset"] = offset
        if without_application is not None:
            params["without_application"] = without_application
        return self._request("GET", "/api/jobs", params=params)

    def get_job(self, job_id: str) -> Any:
        return self._request("GET", f"/api/jobs/{job_id}/detail")

    def get_job_search_brief(self) -> Any:
        return self._request("GET", "/api/jobs/search-brief")

    def sync_now(self) -> Any:
        try:
            return self._request("POST", "/api/sync/round", json={"force": True})
        except BackendError as exc:
            if exc.status_code != 404:
                raise
            sync = self.get_job_search_brief().get("sync", {})
            if sync.get("enabled") is False:
                return "Sync isn't set up."
            if sync.get("enabled") is True and sync.get("role") == "home":
                return "This is your laptop's copy; your bot runs the sync."
            raise

    def get_career_context(self) -> Any:
        return self._request("GET", "/api/kb/context")

    def get_career_export(self) -> str:
        return self._request_raw_response("GET", "/api/exports/career").text

    # ---- Career KB reads (ID-bearing; get_career_context returns prose only) ----
    def list_kb_entities(self, kind: str | None = None, status: str | None = None) -> Any:
        return self._request(
            "GET", "/api/kb/entities", params=_drop_none(kind=kind, status=status)
        )

    def get_kb_entity(self, entity_id: str) -> Any:
        return self._request("GET", f"/api/kb/entities/{entity_id}")

    def list_kb_points(
        self,
        state: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Any:
        points = self._request(
            "GET",
            "/api/kb/points",
            params=_drop_none(state=state, limit=limit, offset=offset),
        )
        # `usage` (per-resume port history) and `merge_sources` (consolidation
        # provenance) are ~60% of a row and no use for picking points to approve;
        # kb_get_entity and the web app carry them.
        if isinstance(points, list):
            return [
                {k: v for k, v in p.items() if k not in _KB_POINT_LIST_OMIT}
                if isinstance(p, dict)
                else p
                for p in points
            ]
        return points

    # ---- Career KB writes ----
    def kb_capture(
        self,
        text: str,
        entity_id: str | None = None,
        origin_detail: str | None = None,
    ) -> Any:
        # The backend matches the text to an entity with an LLM call (provider
        # timeout 120s), so the 60s default would time out a call the backend
        # then finishes, and a retry would draft the same points twice.
        return self._request(
            "POST",
            "/api/kb/capture",
            json=_drop_none(text=text, entity_id=entity_id),
            headers=_origin_headers(origin_detail),
            timeout=_LLM_TIMEOUT,
        )

    def kb_edit_point(
        self,
        point_id: str,
        text: str | None = None,
        tags: list[str] | None = None,
        origin_detail: str | None = None,
    ) -> Any:
        payload = _drop_none(text=text, tags=tags)
        # Changing the words invalidates any prior approval, so the edit and the
        # demotion travel together. There is deliberately no `state` parameter:
        # approving from MCP must stay unrepresentable.
        if text is not None:
            payload["state"] = "draft"
        return self._request(
            "PATCH",
            f"/api/kb/points/{point_id}",
            json=payload,
            headers=_origin_headers(origin_detail),
        )

    def create_kb_entity(
        self,
        kind: str,
        title: str,
        origin_detail: str | None = None,
        **fields: Any,
    ) -> Any:
        payload = _drop_none(**fields)
        payload.update(kind=kind, title=title)
        return self._request(
            "POST",
            "/api/kb/entities",
            json=payload,
            headers=_origin_headers(origin_detail),
        )

    def kb_edit_entity(
        self,
        entity_id: str,
        origin_detail: str | None = None,
        **fields: Any,
    ) -> Any:
        return self._request(
            "PATCH",
            f"/api/kb/entities/{entity_id}",
            json=_drop_none(**fields),
            headers=_origin_headers(origin_detail),
        )

    def kb_edit_profile(
        self,
        origin_detail: str | None = None,
        **fields: Any,
    ) -> Any:
        return self._request(
            "PATCH",
            "/api/kb/profile",
            json=_drop_none(**fields),
            headers=_origin_headers(origin_detail),
        )

    def kb_ingest_resume(
        self,
        resume_key: str,
        data: dict[str, Any],
        origin_detail: str | None = None,
    ) -> Any:
        return self._request(
            "POST",
            "/api/kb/ingest-parsed",
            json={"sources": [{"key": resume_key, "data": data}]},
            headers=_origin_headers(origin_detail),
        )

    def kb_approve_points(
        self,
        point_ids: list[str],
        state: str = "approved",
    ) -> Any:
        return self._request(
            "POST",
            "/api/kb/points/bulk-state",
            json={"ids": point_ids, "state": state},
        )

    def kb_sync_base(self, slug: str) -> Any:
        return self._request("POST", f"/api/base-resumes/{slug}/kb-sync")

    def create_base_resume_from_kb(
        self,
        entity_ids: list[str],
        role_category: str | None = None,
        role_label: str | None = None,
        display_name: str | None = None,
        include_summary: bool = False,
        summary: str | None = None,
    ) -> Any:
        return self._request(
            "POST",
            "/api/base-resumes/from-kb",
            json=_drop_none(
                entity_ids=entity_ids,
                role_category=role_category,
                role_label=role_label,
                display_name=display_name,
                include_summary=include_summary,
                summary=summary,
            ),
            timeout=_RENDER_TIMEOUT,
        )

    def get_autofill_context(
        self, application_id: str | None = None, base: str | None = None
    ) -> Any:
        # Same feed the extension's deterministic fill consumes. EEO answer
        # values are consent-gated for MCP: included only when Profile standing
        # consent is enabled (Playwright agents fill exact stored answers);
        # stripped when consent is off or missing. Consent metadata is always
        # normalized to the standing-consent shape. source + canonical_identity
        # label the stored profile as identity source of truth.
        params = _drop_none(application_id=application_id, base=base)
        ctx = self._request("GET", "/api/autofill/context", params=params)
        if not isinstance(ctx, dict):
            return ctx
        consent = ctx.get("eeo_consent")
        consent_enabled = False
        if isinstance(consent, dict):
            consent_enabled = bool(consent.get("enabled"))
            # Metadata only — drop anything that is not the standing-consent shape.
            ctx["eeo_consent"] = {
                "enabled": consent_enabled,
                "acknowledged_at": consent.get("acknowledged_at"),
                "policy_version": consent.get("policy_version") or "",
            }
        profile = ctx.get("profile")
        if isinstance(profile, dict) and not consent_enabled:
            profile.pop("eeo", None)
        ctx["source"] = "profile"
        ctx["canonical_identity"] = canonical_identity_from_profile(
            profile if isinstance(profile, dict) else None
        )
        return ctx

    def find_job_by_url(self, source_url: str) -> Any:
        # POSTING-equality lookup, answered server-side by GET /api/jobs/match
        # — the same directional containment the extension's widget uses
        # (services/job_url_match.py), and the atomic lookup SYSTEM.md §11
        # item 9 asked for. A referral link (?gh_src=, ?utm_*) or the
        # posting's /apply sub-path now finds the captured job instead of
        # prompting a duplicate extraction; tracking-param stripping is not
        # the agent's job. One request: match carries the newest-first job
        # AND its newest application summary.
        # Strip before building params (defense in depth): every write path
        # stores a stripped source_url, so a trailing-whitespace URL would
        # otherwise miss its own captured job. The server strips too.
        source_url = source_url.strip()
        match = self._request(
            "GET", "/api/jobs/match", params={"url": source_url}
        )
        job = (match or {}).get("job")
        if (match or {}).get("match") != "exact" or not job:
            return {
                "found": False,
                "job": None,
                "application_exists": False,
                "application_id": None,
            }
        application = match.get("application")
        return {
            "found": True,
            "job": job,
            "application_exists": application is not None,
            "application_id": application.get("id") if application else None,
        }

    def get_application(self, application_id: str) -> Any:
        return self._request("GET", f"/api/applications/{application_id}")

    def list_referrals(self) -> Any:
        return self._request("GET", "/api/referrals")

    def list_qa_entries(self, application_id: str) -> Any:
        return self._request("GET", "/api/qa", params={"application_id": application_id})

    # ---- health check ----
    def run_health_check(self, kind: str, key: str) -> Any:
        # Runs an LLM classification pass over every bullet; can exceed the 60s default.
        return self._request("POST", f"/api/resume-lint/{kind}/{key}/run", timeout=_LLM_TIMEOUT)

    def get_health_report(self, kind: str, key: str) -> Any:
        return self._request("GET", f"/api/resume-lint/{kind}/{key}")

    def waive_health_gate(self, kind: str, key: str, gate_id: str, reason: str) -> Any:
        return self._request(
            "POST",
            f"/api/resume-lint/{kind}/{key}/gates/{gate_id}/waive",
            json={"reason": reason},
        )

    def unwaive_health_gate(self, kind: str, key: str, gate_id: str) -> Any:
        return self._request(
            "DELETE", f"/api/resume-lint/{kind}/{key}/gates/{gate_id}/waive"
        )

    # ---- settings & setup ----
    def get_quick_tailor_profile(self) -> Any:
        return self._request("GET", "/api/settings/quick-tailor").get("value", {})

    def get_mcp_workflow_settings(self) -> Any:
        return self._request("GET", "/api/settings/mcp-workflow").get("value", {})

    def get_setup_status(self) -> Any:
        return self._request("GET", "/api/setup/status")

    # ---- write ----
    def store_extracted_jd(
        self,
        extracted_json: dict,
        raw_text: str | None = None,
        source_url: str | None = None,
        source: str = "user",
    ) -> Any:
        payload = {
            "extracted_json": extracted_json,
            "raw_text": raw_text,
            "source_url": source_url,
            "source": source,
        }
        return self._request("POST", "/api/jobs/ingest", json=payload)

    def update_base_resume(
        self, slug: str, data: dict, display_name: str | None = None
    ) -> Any:
        payload: dict[str, Any] = {"data": data}
        if display_name is not None:
            payload["display_name"] = display_name
        return self._request(
            "PUT", f"/api/base-resumes/{slug}", json=payload, timeout=_RENDER_TIMEOUT
        )

    def set_base_resume_identity(
        self,
        slug: str,
        display_name: str | None = None,
        role_category: str | None = None,
        role_label: str | None = None,
        countries: list[str] | None = None,
        company: str | None = None,
        focus: str | None = None,
    ) -> Any:
        # None is "not sent"; "" and [] are real values (they clear), so only
        # None is dropped.
        payload = _drop_none(
            display_name=display_name,
            role_category=role_category,
            role_label=role_label,
            countries=countries,
            company=company,
            focus=focus,
        )
        return self._request("PATCH", f"/api/base-resumes/{slug}/identity", json=payload)

    def edit_base_resume(self, slug: str, ops: list[dict]) -> Any:
        return self._request(
            "PATCH",
            f"/api/base-resumes/{slug}/edits",
            json={"ops": ops},
            timeout=_RENDER_TIMEOUT,
        )

    def create_base_resume(self, slug: str, display_name: str, data: dict) -> Any:
        return self._request(
            "POST",
            "/api/base-resumes",
            json={"slug": slug, "display_name": display_name, "data": data},
            timeout=_RENDER_TIMEOUT,
        )

    def duplicate_base_resume(
        self, slug: str, new_slug: str, new_display_name: str | None = None
    ) -> Any:
        payload: dict[str, Any] = {"new_slug": new_slug}
        if new_display_name is not None:
            payload["new_display_name"] = new_display_name
        return self._request(
            "POST",
            f"/api/base-resumes/{slug}/duplicate",
            json=payload,
            timeout=_RENDER_TIMEOUT,
        )

    def list_resume_versions(self, kind: str, key: str) -> Any:
        return self._request("GET", f"/api/resume-versions/{kind}/{key}")

    def get_resume_version(self, kind: str, key: str, number: int) -> Any:
        return self._request("GET", f"/api/resume-versions/{kind}/{key}/{number}")

    def restore_resume_version(self, kind: str, key: str, number: int) -> Any:
        return self._request(
            "POST",
            f"/api/resume-versions/{kind}/{key}/{number}/restore",
            timeout=_RENDER_TIMEOUT,
        )

    def archive_base_resume(self, slug: str) -> Any:
        return self._request("POST", f"/api/base-resumes/{slug}/archive")

    def unarchive_base_resume(self, slug: str) -> Any:
        return self._request("POST", f"/api/base-resumes/{slug}/unarchive")

    def tailor_application(
        self, job_id: str, base_resume: str, ops: list[dict], application_id: str | None = None
    ) -> Any:
        payload: dict[str, Any] = {"job_id": job_id, "base_resume": base_resume, "ops": ops}
        if application_id is not None:
            payload["application_id"] = application_id
        return self._request("POST", "/api/applications/from-base", json=payload)

    def edit_application(self, application_id: str, ops: list[dict]) -> Any:
        return self._request(
            "PATCH",
            f"/api/applications/{application_id}/edits",
            json={"ops": ops},
            timeout=_RENDER_TIMEOUT,
        )

    def update_application(
        self,
        application_id: str,
        status: str | None = None,
        applied_at: str | None = None,
        notes: str | None = None,
        referral_id: str | None = None,
    ) -> Any:
        payload = _drop_none(
            status=status, applied_at=applied_at, notes=notes, referral_id=referral_id
        )
        return self._request("PATCH", f"/api/applications/{application_id}", json=payload)

    # ---- apply package ----
    def generate_qa_answers(self, application_id: str, questions: list[str]) -> Any:
        return self._request(
            "POST",
            "/api/qa",
            json={"application_id": application_id, "questions": questions},
            timeout=_LLM_TIMEOUT,
        )

    def generate_cover_letter(self, application_id: str, tone: str) -> Any:
        return self._request(
            "POST",
            "/api/qa",
            json={"application_id": application_id, "cover_letter": {"tone": tone}},
            timeout=_LLM_TIMEOUT,
        )

    def render_base_resume(self, slug: str, template_id: str | None = None) -> Any:
        params = {"template_id": template_id} if template_id else {}
        return self._request(
            "POST", f"/api/base-resumes/{slug}/render", params=params, timeout=_RENDER_TIMEOUT
        )

    def render_application(self, application_id: str, template_id: str | None = None) -> Any:
        params = {"template_id": template_id} if template_id else {}
        return self._request(
            "POST",
            f"/api/applications/{application_id}/render",
            params=params,
            timeout=_RENDER_TIMEOUT,
        )

    # ---- templates ----
    def list_templates(self) -> Any:
        return self._request("GET", "/api/templates")

    def get_template(self, template_id: str) -> Any:
        return self._request("GET", f"/api/templates/{template_id}")

    def create_template_draft(
        self,
        id: str,
        display_name: str,
        source: str | None = None,
        validate: bool = False,
        engine: str = "latex",
    ) -> Any:
        return self._request(
            "POST",
            "/api/templates",
            json={
                "id": id,
                "display_name": display_name,
                "source": source,
                "origin": "mcp",
                "engine": engine,
            },
            params={"validate": validate},
            timeout=_RENDER_TIMEOUT,
        )

    def update_template_draft(
        self,
        template_id: str,
        source: str | None = None,
        display_name: str | None = None,
        validate: bool = False,
    ) -> Any:
        payload: dict[str, Any] = {}
        if source is not None:
            payload["source"] = source
        if display_name is not None:
            payload["display_name"] = display_name
        return self._request(
            "PUT",
            f"/api/templates/{template_id}",
            json=payload,
            params={"validate": validate},
            timeout=_RENDER_TIMEOUT,
        )

    def validate_template(self, template_id: str) -> Any:
        return self._request(
            "POST", f"/api/templates/{template_id}/validate", timeout=_RENDER_TIMEOUT
        )

    def get_rendered_pdf(self, target_type: str, target_id: str) -> Any:
        paths = {
            "base_resume": f"/api/base-resumes/{target_id}/pdf",
            "application": f"/api/applications/{target_id}/pdf",
            "template": f"/api/templates/{target_id}/preview.pdf",
        }
        if target_type not in paths:
            raise BackendError("target_type must be base_resume, application, or template")
        response = self._request_raw_response("GET", paths[target_type])
        content = response.content
        # Write the PDF to a local file instead of inlining it as base64 — a real
        # resume PDF base64-encodes to a payload large enough to stall the MCP client.
        out_dir = Path(
            os.environ.get("MAESTRO_CS_PDF_DIR")
            or os.environ.get("CAREER_STUDIO_PDF_DIR")
            # Back-compat: pre-rename installs may still export this.
            or os.environ.get("RESUME_TAILOR_PDF_DIR")
            or (Path(tempfile.gettempdir()) / "maestro-cs-pdfs")
        )
        out_dir.mkdir(parents=True, exist_ok=True)
        local_filename = _safe_filename(f"{target_id}.pdf", "rendered.pdf")
        out_path = out_dir / local_filename
        out_path.write_bytes(content)
        result = {
            "filename": _response_filename(response, local_filename),
            "path": str(out_path),
            "size_bytes": len(content),
            "mime_type": "application/pdf",
            **_render_pdf_previews(out_path, out_path.stem),
        }
        if target_type == "application":
            try:
                detail = self.get_application(target_id)
            except BackendError:
                detail = None
            artifact_dir = (detail or {}).get("artifact_dir") if isinstance(detail, dict) else None
            if artifact_dir:
                result["artifact_dir"] = artifact_dir
        return result

    def get_rendered_pdf_page_image(
        self,
        target_type: str,
        target_id: str,
        page_number: int,
        max_dimension_px: int = _PAGE_IMAGE_MAX_DIMENSION_DEFAULT,
    ) -> Any:
        pdf = self.get_rendered_pdf(target_type, target_id)
        page_count = pdf["page_count"]
        if page_count is None:
            raise BackendError("page images unavailable because the PDF could not be read")
        if page_number < 1 or page_number > page_count:
            raise BackendError(
                f"page_number must be between 1 and {page_count}; got {page_number}"
            )
        pdf_path = Path(pdf["path"])
        image = _render_pdf_page_at_cap(pdf_path, page_number, max_dimension_px)
        encoded = base64.b64encode(image).decode("ascii")
        if len(encoded) > _PAGE_IMAGE_B64_CAP:
            raise BackendError(
                f"encoded page image is {len(encoded)} chars "
                f"(cap {_PAGE_IMAGE_B64_CAP}); lower max_dimension_px and retry"
            )
        out_name = f"{pdf_path.stem}.p{page_number}.w{max_dimension_px}.png"
        out_path = pdf_path.parent / out_name
        out_path.write_bytes(image)
        return {
            "target_type": target_type,
            "target_id": target_id,
            "page_number": page_number,
            "page_count": page_count,
            "filename": out_name,
            "path": str(out_path),
            "size_bytes": len(image),
            "mime_type": "image/png",
            "page_image_b64": encoded,
        }

    def prepare_application_pdf_upload(self, application_id: str) -> Any:
        if (
            not application_id
            or application_id in {".", ".."}
            or Path(application_id).name != application_id
            or "\\" in application_id
        ):
            raise BackendError("application_id must be a safe path component")

        # P1: agent-sourced jobs must have an open proposal before staging upload.
        self._request(
            "POST",
            f"/api/applications/{application_id}/assert-open-proposal",
            json={"op": "prepare"},
        )

        pdf_path = f"/api/applications/{application_id}/pdf"
        try:
            response = self._request_raw_response("GET", pdf_path)
        except BackendError as exc:
            detail = exc.body.get("detail") if isinstance(exc.body, dict) else exc.body
            if exc.status_code != 404 or str(detail).lower() != "pdf not found":
                raise
            self.render_application(application_id)
            response = self._request_raw_response("GET", pdf_path)

        content = response.content
        canonical_filename = _response_filename(
            response, f"{application_id}.pdf"
        )
        upload_root = _upload_root()
        upload_path = upload_root / application_id / canonical_filename
        _atomic_write_bytes(upload_path, content)
        inspection = _inspect_pdf(upload_path)
        return {
            "application_id": application_id,
            "canonical_filename": canonical_filename,
            "upload_path": _host_visible(upload_path, upload_root),
            "size_bytes": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
            **inspection,
        }

    # ---- profile coach ----
    def explore_top_skills(
        self,
        role_category: str | None = None,
        level: str | None = None,
        employment_type: str | None = None,
        limit: int | None = None,
    ) -> Any:
        params = _drop_none(
            role_category=role_category,
            level=level,
            employment_type=employment_type,
            limit=limit,
        )
        return self._request("GET", "/api/explore/top-skills", params=params)

    def explore_skill_heatmap(self, limit: int | None = None) -> Any:
        return self._request("GET", "/api/explore/heatmap", params=_drop_none(limit=limit))

    def explore_role_mix_over_time(self) -> Any:
        return self._request("GET", "/api/explore/role-mix-over-time")

    def explore_fit_distribution(self) -> Any:
        return self._request("GET", "/api/explore/fit-distribution")

    def explore_gap_frequency(
        self,
        role_category: str | None = None,
        level: str | None = None,
        employment_type: str | None = None,
        limit: int | None = None,
    ) -> Any:
        params = _drop_none(
            role_category=role_category,
            level=level,
            employment_type=employment_type,
            limit=limit,
        )
        return self._request("GET", "/api/explore/gap-frequency", params=params)

    def explore_ats_over_time(
        self,
        role_category: str | None = None,
        level: str | None = None,
        employment_type: str | None = None,
    ) -> Any:
        params = _drop_none(
            role_category=role_category, level=level, employment_type=employment_type
        )
        return self._request("GET", "/api/explore/ats-over-time", params=params)

    def explore_tailoring_lift(
        self,
        role_category: str | None = None,
        level: str | None = None,
        employment_type: str | None = None,
    ) -> Any:
        params = _drop_none(
            role_category=role_category, level=level, employment_type=employment_type
        )
        return self._request("GET", "/api/explore/tailoring-lift", params=params)

    def list_applications(
        self,
        status: str | None = None,
        role_category: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> Any:
        return self._request(
            "GET",
            "/api/applications",
            params=_drop_none(
                status=status, role_category=role_category, limit=limit, offset=offset
            ),
        )

    def score_ats(
        self,
        job_id: str,
        target_type: str | None = None,
        target_id: str | None = None,
        include_other_countries: bool = False,
    ) -> Any:
        return self._request(
            "POST",
            "/api/ats-scores",
            json=_drop_none(
                job_id=job_id,
                target_type=target_type,
                target_id=target_id,
                # Sent only when true: the backend's default is the country rule.
                include_other_countries=True if include_other_countries else None,
            ),
        )

    def ats_candidates(self, job_id: str, include_other_countries: bool = False) -> Any:
        """How the country rule treats a job: {job_country, fallback, skipped}."""
        params = {"job_id": job_id}
        if include_other_countries:  # sent only when true, like score_ats
            params["include_other_countries"] = "true"
        return self._request("GET", "/api/ats-scores/candidates", params=params)

    def compare_ats(self, application_id: str) -> Any:
        return self._request("GET", f"/api/applications/{application_id}/ats-compare")

    def create_tailoring_session(
        self, job_id: str, base_resume: str, enrich: bool = True
    ) -> Any:
        # Session creation runs an LLM enrichment pass over the gap list by
        # default (enrich=True), which can take well past the 60s default.
        return self._request(
            "POST",
            "/api/tailoring-sessions",
            json={"job_id": job_id, "base_resume": base_resume, "enrich": enrich},
            timeout=_LLM_TIMEOUT,
        )

    def list_tailoring_sessions(self, job_id: str) -> Any:
        sessions = self._request("GET", "/api/tailoring-sessions", params={"job_id": job_id})
        # The REST rows carry the whole frozen gap list and every saved
        # resolution (~28k chars for ONE session); this is the "find a session
        # id" view, so project a summary and leave get_tailoring_session as the
        # detail path.
        if isinstance(sessions, list):
            return [_session_summary(s) if isinstance(s, dict) else s for s in sessions]
        return sessions

    def get_tailoring_session(self, session_id: str) -> Any:
        return self._request("GET", f"/api/tailoring-sessions/{session_id}")

    def close_tailoring_session(self, session_id: str) -> Any:
        return self._request("POST", f"/api/tailoring-sessions/{session_id}/close")

    def apply_quick_tailor_profile(self, tailoring_session_id: str) -> Any:
        return self._request(
            "POST", f"/api/tailoring-sessions/{tailoring_session_id}/apply-profile"
        )

    def resolve_gaps(self, session_id: str, resolutions: list[dict]) -> Any:
        return self._request(
            "PATCH",
            f"/api/tailoring-sessions/{session_id}",
            json={"resolutions": resolutions},
        )

    def tailor_session(
        self,
        session_id: str,
        user_prompt: str | None = None,
        ops: list[dict] | None = None,
    ) -> Any:
        # The tailor pipeline is an LLM call (resolutions -> edit ops); bump the
        # timeout well past the 60s default. When `ops` is supplied the backend
        # applies them directly and skips its own LLM pass. Only non-None keys are
        # sent (via _drop_none) so the no-ops body stays clean.
        return self._request(
            "POST",
            f"/api/tailoring-sessions/{session_id}/tailor",
            json=_drop_none(user_prompt=user_prompt, ops=ops),
            timeout=_LLM_TIMEOUT,
        )

    def export_jobs(
        self,
        role_category: str | None = None,
        level: str | None = None,
        since: str | None = None,
        skill: str | None = None,
        limit: int = 10,
        offset: int = 0,
    ) -> Any:
        params = _drop_none(
            role_category=role_category, level=level, since=since, skill=skill,
            limit=limit, offset=offset,
        )
        rows = self._request("GET", "/api/jobs/export", params=params)
        # raw_text, its hash and extracted_json are ~80% of a row (and duplicate the
        # flat extracted fields); get_job has them for the one posting that needs it.
        if isinstance(rows, list):
            return [
                {k: v for k, v in r.items() if k not in _JOB_EXPORT_OMIT}
                if isinstance(r, dict)
                else r
                for r in rows
            ]
        return rows

    def propose_application(
        self,
        job_id: str,
        fit: dict | None = None,
        plan: dict | None = None,
        application_id: str | None = None,
        referral_id: str | None = None,
        origin_detail: str | None = None,
    ) -> Any:
        payload = _drop_none(
            job_id=job_id,
            fit=fit,
            plan=plan,
            application_id=application_id,
            referral_id=referral_id,
        )
        # The origin headers name the filer (the proposal's proposed_by),
        # exactly as KB writes name their author; the body never does.
        return self._request(
            "POST", "/api/proposals", json=payload, headers=_origin_headers(origin_detail),
        )

    def list_proposals(
        self, status: str | None = None, limit: int = 20, offset: int = 0
    ) -> Any:
        params = _drop_none(status=status, limit=limit, offset=offset)
        return self._request("GET", "/api/proposals", params=params)

    def get_proposal(self, proposal_id: str) -> Any:
        return self._request("GET", f"/api/proposals/{proposal_id}")

    def get_job_site_login(self, proposal_id: str, origin_detail: str | None = None) -> Any:
        # Unlike ordinary errors, a login response must never be copied into
        # BackendError.body or a message/traceback surfaced by the MCP guard.
        try:
            return self._request(
                "POST", f"/api/proposals/{proposal_id}/job-site-login",
                headers=_origin_headers(origin_detail),
            )
        except BackendError as exc:
            messages = {
                None: "Maestro is not reachable; try again later.",
                403: "Only the connected agent can ask for the job-site login.",
                404: "No such proposal or no job-site login is saved in Settings.",
                409: "Full automation is off, the job is not queued or approved, or its company is on the skip list.",
                422: "The proposal ID is malformed.",
            }
            raise BackendError(
                messages.get(exc.status_code, "The job-site login could not be retrieved; try again later."),
                status_code=exc.status_code,
            ) from None
        except ValueError:
            raise BackendError("The backend returned an unreadable job-site login response.") from None

    def transition_proposal(
        self,
        proposal_id: str,
        status: str,
        consent: dict | None = None,
        reason: str | None = None,
        fit: dict | None = None,
        application_id: str | None = None,
        attested: bool = False,
    ) -> Any:
        payload = _drop_none(
            status=status, consent=consent, reason=reason, fit=fit,
            application_id=application_id,
        )
        if attested:
            payload["attested"] = True
        return self._request("PATCH", f"/api/proposals/{proposal_id}", json=payload)

    def bulk_transition_proposals(
        self,
        proposal_ids: list[str],
        status: str,
        channel: str,
        note: str | None = None,
        reason: str | None = None,
    ) -> Any:
        payload = _drop_none(
            ids=proposal_ids,
            status=status,
            consent=_drop_none(channel=channel, note=note),
            reason=reason,
        )
        return self._request("POST", "/api/proposals/bulk-transition", json=payload)

    def attach_evidence(
        self,
        proposal_id: str,
        step: int,
        label: str,
        image_base64: str,
        kind: str = "step",
    ) -> Any:
        data_bytes = base64.b64decode(image_base64)
        files = {"file": ("evidence.png", data_bytes, "image/png")}
        data = {"step": str(step), "label": label, "kind": kind}
        return self._request("POST", f"/api/proposals/{proposal_id}/evidence", files=files, data=data)

    def attach_evidence_file(
        self,
        proposal_id: str,
        step: int,
        label: str,
        file_path: str,
        kind: str = "step",
    ) -> Any:
        # Path-based variant so screenshot bytes never transit the model
        # context: the browser tool saves to disk, only the path string flows
        # through the agent. Magic-byte check limits what a caller can pull
        # off the host to actual PNG/JPEG images.
        if "\x00" in file_path:
            raise BackendError("evidence file path contains a NUL byte")
        p = Path(file_path).expanduser().resolve()
        if not p.is_file():
            # Under `docker exec` the browser's HOST path does not exist here;
            # the same file is in this process's mount of the .playwright-mcp tree.
            mapped = _mounted_playwright_path(file_path)
            if mapped is None or not mapped.is_file():
                raise BackendError(
                    f"evidence file not found: {p}"
                    + (f" (also tried {mapped})" if mapped is not None else "")
                )
            p = mapped
        data_bytes = p.read_bytes()
        if len(data_bytes) > 5 * 1024 * 1024:
            raise BackendError("evidence file exceeds 5 MB")
        if data_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
            mime = "image/png"
        elif data_bytes.startswith(b"\xff\xd8\xff"):
            mime = "image/jpeg"
        else:
            raise BackendError("evidence file is not a PNG or JPEG image")
        files = {"file": (p.name, data_bytes, mime)}
        data = {"step": str(step), "label": label, "kind": kind}
        return self._request("POST", f"/api/proposals/{proposal_id}/evidence", files=files, data=data)

    def record_decision(
        self,
        proposal_id: str,
        fit: dict,
        application_id: str | None = None,
    ) -> Any:
        return self.transition_proposal(
            proposal_id, "pending_review", fit=fit, application_id=application_id,
        )

    def request_decision(self, proposal_id: str, reason: str | None = None) -> Any:
        return self._request(
            "POST",
            f"/api/proposals/{proposal_id}/request-decision",
            json=_drop_none(reason=reason),
        )

    def resume_proposal(self, proposal_id: str) -> Any:
        return self._request("POST", f"/api/proposals/{proposal_id}/resume")

    def report_failure(self, proposal_id: str, reason: str) -> Any:
        return self._request(
            "POST",
            f"/api/proposals/{proposal_id}/report-failure",
            json={"reason": reason},
        )

    def get_final_review(self, proposal_id: str) -> Any:
        return _without_eeo_values(
            self._request("GET", f"/api/proposals/{proposal_id}/final-review")
        )

    def record_filled_answers(
        self, job_id: str, fields: list[dict[str, Any]], **page: Any
    ) -> Any:
        """`page` is the run's optional step (sent as text), application_id and base_resume."""
        if page.get("step") is not None:
            page["step"] = str(page["step"])
        body = {"channel": "agent", "fields": fields, **_drop_none(**page)}
        return self._request("POST", f"/api/jobs/{job_id}/filled-answers", json=body)

    def record_run(
        self, automation: str, outcome: str, report: dict[str, Any] | None,
        origin_detail: str | None = None,
    ) -> Any:
        """`report` is the run's optional counts, digest and job_ids, sent flat."""
        body = {"automation": automation, "outcome": outcome, **_drop_none(**(report or {}))}
        return self._request(
            "POST", "/api/agent-runs", json=body, headers=_origin_headers(origin_detail)
        )
