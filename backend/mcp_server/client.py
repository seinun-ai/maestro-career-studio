from __future__ import annotations

import base64
import hashlib
import logging
import os
import tempfile
from email.message import Message
from pathlib import Path
from typing import Any

import httpx

from app.services.autofill_profile import canonical_identity_from_profile

DEFAULT_BASE_URL = "http://localhost:8000"

logger = logging.getLogger(__name__)


def _drop_none(**kwargs: Any) -> dict[str, Any]:
    return {k: v for k, v in kwargs.items() if v is not None}


def _origin_headers(origin_detail: str | None) -> dict[str, str]:
    """Provenance for a KB write. Every MCP write is origin 'mcp'; the detail
    names the client so the entity timeline can say who."""
    headers = {"X-Maestro-CS-Origin": "mcp"}
    if origin_detail:
        headers["X-Maestro-CS-Origin-Detail"] = origin_detail
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

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        url = f"{self.base_url}{path}"
        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.request(method, url, **kwargs)
        except httpx.ConnectError as exc:
            raise BackendError(
                f"Could not reach the maestro-career-studio backend at {self.base_url}. "
                "Is it running on :8000?",
            ) from exc
        except httpx.HTTPError as exc:
            raise BackendError(f"HTTP error talking to backend: {exc}") from exc

        if response.status_code >= 400:
            try:
                body = response.json()
            except ValueError:
                body = response.text
            raise BackendError(
                f"Backend returned {response.status_code}: {body}",
                status_code=response.status_code,
                body=body,
            )
        if response.status_code == 204 or not response.content:
            return None
        return response.json()

    def _request_raw_response(
        self, method: str, path: str, **kwargs: Any
    ) -> httpx.Response:
        url = f"{self.base_url}{path}"
        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.request(method, url, **kwargs)
        except httpx.ConnectError as exc:
            raise BackendError(
                f"Could not reach the maestro-career-studio backend at {self.base_url}. "
                "Is it running on :8000?",
            ) from exc
        except httpx.HTTPError as exc:
            raise BackendError(f"HTTP error talking to backend: {exc}") from exc
        if response.status_code >= 400:
            try:
                body = response.json()
            except ValueError:
                body = response.text
            raise BackendError(
                f"Backend returned {response.status_code}: {body}",
                status_code=response.status_code,
                body=body,
            )
        return response

    def _request_raw(self, method: str, path: str, **kwargs: Any) -> bytes:
        return self._request_raw_response(method, path, **kwargs).content

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

    def list_kb_points(self, state: str | None = None) -> Any:
        return self._request("GET", "/api/kb/points", params=_drop_none(state=state))

    # ---- Career KB writes ----
    def kb_capture(
        self,
        text: str,
        entity_id: str | None = None,
        origin_detail: str | None = None,
    ) -> Any:
        return self._request(
            "POST",
            "/api/kb/capture",
            json=_drop_none(text=text, entity_id=entity_id),
            headers=_origin_headers(origin_detail),
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
        # Exact-match dedupe lookup, answered server-side: the list endpoint's
        # source_url filter (newest-first) plus the detail endpoint's joined
        # application. Lets a browsing agent skip an extraction spend on a
        # posting that is already captured.
        # Strip before building params (defense in depth): every write path
        # stores a stripped source_url, so a trailing-whitespace URL would
        # otherwise miss its own captured job. The server strips too.
        source_url = source_url.strip()
        matches = self._request(
            "GET", "/api/jobs", params={"source_url": source_url, "limit": 5}
        )
        if not matches:
            return {
                "found": False,
                "job": None,
                "application_exists": False,
                "application_id": None,
            }
        job = matches[0]  # list endpoint orders created_at desc — newest wins
        detail = self._request("GET", f"/api/jobs/{job['id']}/detail")
        application = (detail or {}).get("application")
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
        return self._request("POST", f"/api/resume-lint/{kind}/{key}/run", timeout=300.0)

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
        return self._request("PUT", f"/api/base-resumes/{slug}", json=payload)

    def edit_base_resume(self, slug: str, ops: list[dict]) -> Any:
        return self._request("PATCH", f"/api/base-resumes/{slug}/edits", json={"ops": ops})

    def create_base_resume(self, slug: str, display_name: str, data: dict) -> Any:
        return self._request(
            "POST",
            "/api/base-resumes",
            json={"slug": slug, "display_name": display_name, "data": data},
        )

    def duplicate_base_resume(
        self, slug: str, new_slug: str, new_display_name: str | None = None
    ) -> Any:
        payload: dict[str, Any] = {"new_slug": new_slug}
        if new_display_name is not None:
            payload["new_display_name"] = new_display_name
        return self._request("POST", f"/api/base-resumes/{slug}/duplicate", json=payload)

    def tailor_application(
        self, job_id: str, base_resume: str, ops: list[dict], application_id: str | None = None
    ) -> Any:
        payload: dict[str, Any] = {"job_id": job_id, "base_resume": base_resume, "ops": ops}
        if application_id is not None:
            payload["application_id"] = application_id
        return self._request("POST", "/api/applications/from-base", json=payload)

    def edit_application(self, application_id: str, ops: list[dict]) -> Any:
        return self._request("PATCH", f"/api/applications/{application_id}/edits", json={"ops": ops})

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
            timeout=300.0,
        )

    def generate_cover_letter(self, application_id: str, tone: str) -> Any:
        return self._request(
            "POST",
            "/api/qa",
            json={"application_id": application_id, "cover_letter": {"tone": tone}},
            timeout=300.0,
        )

    def render_base_resume(self, slug: str, template_id: str | None = None) -> Any:
        params = {"template_id": template_id} if template_id else {}
        return self._request("POST", f"/api/base-resumes/{slug}/render", params=params)

    def render_application(self, application_id: str, template_id: str | None = None) -> Any:
        params = {"template_id": template_id} if template_id else {}
        return self._request("POST", f"/api/applications/{application_id}/render", params=params)

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
        )

    def validate_template(self, template_id: str) -> Any:
        return self._request("POST", f"/api/templates/{template_id}/validate")

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
        self, target_type: str, target_id: str, page_number: int
    ) -> Any:
        pdf = self.get_rendered_pdf(target_type, target_id)
        page_count = pdf["page_count"]
        if page_count is None:
            raise BackendError("page images unavailable because the PDF could not be read")
        if page_number < 1 or page_number > page_count:
            raise BackendError(
                f"page_number must be between 1 and {page_count}; got {page_number}"
            )

        page_images = pdf.get("page_images") or []
        if page_number > len(page_images):
            raise BackendError(
                "page preview unavailable; ensure the MCP PDF render dependencies "
                "(pypdfium2 and Pillow) are installed, then retry"
            )
        page_path = Path(page_images[page_number - 1])
        image = page_path.read_bytes()
        return {
            "target_type": target_type,
            "target_id": target_id,
            "page_number": page_number,
            "page_count": page_count,
            "filename": page_path.name,
            "path": str(page_path),
            "size_bytes": len(image),
            "mime_type": "image/png",
            "page_image_b64": base64.b64encode(image).decode("ascii"),
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
        upload_root = Path(
            os.environ.get("MAESTRO_CS_UPLOAD_DIR")
            or os.environ.get("CAREER_STUDIO_UPLOAD_DIR")
            or _default_upload_root()
        )
        upload_path = upload_root / application_id / canonical_filename
        _atomic_write_bytes(upload_path, content)
        inspection = _inspect_pdf(upload_path)
        return {
            "application_id": application_id,
            "canonical_filename": canonical_filename,
            "upload_path": str(upload_path),
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
    ) -> Any:
        return self._request(
            "POST",
            "/api/ats-scores",
            json=_drop_none(job_id=job_id, target_type=target_type, target_id=target_id),
        )

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
            timeout=300.0,
        )

    def list_tailoring_sessions(self, job_id: str) -> Any:
        return self._request("GET", "/api/tailoring-sessions", params={"job_id": job_id})

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
            timeout=300.0,
        )

    def export_jobs(
        self,
        role_category: str | None = None,
        level: str | None = None,
        since: str | None = None,
        skill: str | None = None,
    ) -> Any:
        params = _drop_none(role_category=role_category, level=level, since=since, skill=skill)
        return self._request("GET", "/api/jobs/export", params=params)

    def propose_application(
        self,
        job_id: str,
        fit: dict | None = None,
        plan: dict | None = None,
        application_id: str | None = None,
        referral_id: str | None = None,
    ) -> Any:
        payload = _drop_none(
            job_id=job_id,
            fit=fit,
            plan=plan,
            application_id=application_id,
            referral_id=referral_id,
        )
        return self._request("POST", "/api/proposals", json=payload)

    def list_proposals(self, status: str | None = None) -> Any:
        params = _drop_none(status=status)
        return self._request("GET", "/api/proposals", params=params)

    def get_proposal(self, proposal_id: str) -> Any:
        return self._request("GET", f"/api/proposals/{proposal_id}")

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
        import base64

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
        from pathlib import Path

        p = Path(file_path).expanduser().resolve()
        if not p.is_file():
            raise BackendError(f"evidence file not found: {p}")
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
        return self._request("GET", f"/api/proposals/{proposal_id}/final-review")
