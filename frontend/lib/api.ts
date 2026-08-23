import type {
  Application,
  AtsCompare,
  AtsScore,
  CareerExportMetadata,
  KBCaptureRequest,
  KBCaptureResponse,
  KBDocumentOut,
  KBEntityCreate,
  KBEntityDetail,
  KBEntityKind,
  KBEntityPatch,
  KBEntityStatus,
  KBEntitySummary,
  KBInboxPoint,
  KBAdaptApplyRequest,
  KBAdaptProposal,
  KBAdaptRequest,
  KBPointCreate,
  KBPointOut,
  KBPointPatch,
  KBPortRequest,
  KBPortResponse,
  KBProfileOut,
  KBProfilePatch,
  SyncResult,
  SyncStatus,
  Resolution,
  CoherenceCheckResult,
  ResumeDiff,
  TailoringSession,
  TailorResult,
  UUID,
} from "@/lib/types";

/**
 * In the browser, default to same-origin `/api/...` (Next proxy → FastAPI).
 * Many dev environments set `NEXT_PUBLIC_API_URL=http://localhost:8000`; that breaks some
 * POST requests cross-origin while GET still works — so we ignore that unless opted in.
 *
 * Opt in to direct browser → backend: set `NEXT_PUBLIC_API_DIRECT=true` and optionally
 * `NEXT_PUBLIC_API_URL` (defaults to http://localhost:8001).
 *
 * Server-side (no `window`): uses `INTERNAL_API_URL` / `API_PROXY_BACKEND` / 127.0.0.1:8001.
 */
function getApiBase(): string {
  if (typeof window !== "undefined") {
    const bypass =
      process.env.NEXT_PUBLIC_API_DIRECT === "1" ||
      process.env.NEXT_PUBLIC_API_DIRECT === "true";
    if (bypass) {
      return (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8001")
        .trim()
        .replace(/\/$/, "");
    }
    return "";
  }
  return (
    process.env.INTERNAL_API_URL ??
    process.env.API_PROXY_BACKEND ??
    "http://127.0.0.1:8001"
  )
    .trim()
    .replace(/\/$/, "");
}

export class ApiError extends Error {
  status: number;
  body: unknown;

  constructor(status: number, message: string, body: unknown) {
    super(message);
    this.status = status;
    this.body = body;
  }
}

function networkErrorMessage(original: string): string {
  if (original !== "Failed to fetch" && !original.includes("NetworkError")) {
    return original;
  }
  const base = getApiBase();
  const label =
    base === "" ? "same-origin /api (Next.js → FastAPI proxy)" : base;
  return (
    `Cannot reach the API (${label}). ` +
    `Usually the FastAPI server is not listening on port 8001. From the repo root run ` +
    `docker compose up (or docker compose up postgres backend if you only run Next.js locally). ` +
    `Check with: curl http://localhost:8001/health — expect {"status":"ok"}. ` +
    `Original error: ${original}`
  );
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (
    init.body &&
    !(init.body instanceof FormData) &&
    !headers.has("Content-Type")
  ) {
    headers.set("Content-Type", "application/json");
  }

  let response: Response;
  const apiBase = getApiBase();
  const fullUrl = `${apiBase}${path}`;
  try {
    response = await fetch(fullUrl, { ...init, headers });
  } catch (err) {
    const original =
      err instanceof Error ? err.message : typeof err === "string" ? err : String(err);
    throw new ApiError(0, networkErrorMessage(original), err);
  }

  if (!response.ok) {
    let body: unknown = null;
    try {
      body = await response.json();
    } catch {
      body = await response.text().catch(() => null);
    }
    const detailRaw =
      typeof body === "object" && body !== null && "detail" in body
        ? (body as { detail: unknown }).detail
        : undefined;
    const message =
      detailRaw !== undefined
        ? typeof detailRaw === "string"
          ? detailRaw
          : JSON.stringify(detailRaw)
        : `Request failed: ${response.status}`;
    throw new ApiError(response.status, message, body);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  const contentType = response.headers.get("Content-Type") ?? "";
  if (contentType.includes("application/json")) {
    return (await response.json()) as T;
  }
  return (await response.text()) as unknown as T;
}

export const apiUrl = (path: string) => `${getApiBase()}${path}`;

// --- ATS scoring + tailoring sessions -------------------------------------

export function runAtsScores(jobId: UUID) {
  return apiFetch<AtsScore[]>("/api/ats-scores", {
    method: "POST",
    body: JSON.stringify({ job_id: jobId }),
  });
}

/**
 * Score a single target. Application targets default to phase "tailored"
 * server-side, which APPENDS a trajectory row; base_resume targets default to
 * phase "base" (upsert).
 */
export function runAtsScoreTarget(
  jobId: UUID,
  targetType: "base_resume" | "application",
  targetId: string,
  phase?: "base" | "tailored",
) {
  return apiFetch<AtsScore[]>("/api/ats-scores", {
    method: "POST",
    body: JSON.stringify({
      job_id: jobId,
      target_type: targetType,
      target_id: targetId,
      ...(phase === undefined ? {} : { phase }),
    }),
  });
}

export function listAtsScores(jobId: UUID) {
  return apiFetch<AtsScore[]>(
    `/api/ats-scores?job_id=${encodeURIComponent(jobId)}`,
  );
}

/** Promote a scored-but-unproposed capture into the agent queue: file a
 * proposal from the job's stored base scores, then straight to `accepted` —
 * the caller's click IS the user's triage decision. Used by the tracker's
 * saved-row action and the job page. */
export async function promoteJobToAgentQueue(jobId: UUID) {
  const scores = (await listAtsScores(jobId)).filter((s) => s.phase === "base");
  const chosen = [...scores].sort((a, b) => b.composite - a.composite)[0];
  const prop = await apiFetch<{ id: UUID }>("/api/proposals", {
    method: "POST",
    body: JSON.stringify({
      job_id: jobId,
      fit: chosen
        ? {
            chosen_base: chosen.target_id,
            scores: Object.fromEntries(
              scores.map((s) => [s.target_id, s.composite]),
            ),
            decided_by: "user",
          }
        : null,
      plan: { summary: "Promoted from the tracker by the user" },
    }),
  });
  await apiFetch(`/api/proposals/${prop.id}`, {
    method: "PATCH",
    body: JSON.stringify({
      status: "accepted",
      consent: { channel: "frontend" },
    }),
  });
}

export function getAtsCompare(applicationId: UUID) {
  return apiFetch<AtsCompare>(`/api/applications/${applicationId}/ats-compare`);
}

/**
 * Structural base→tailored diff with provenance labels, for the studio's review
 * mode. 409 = the application has no tailored resume yet (nothing to review) —
 * callers treat that as "hide review mode", not as an error worth surfacing.
 */
export function getResumeDiff(applicationId: UUID) {
  return apiFetch<ResumeDiff>(`/api/applications/${applicationId}/resume-diff`);
}

/**
 * Read-only coherence lint over the tailored resume's changed loci. Returns
 * proposals only; applying one is a normal studio edit. Best-effort server
 * side — an LLM failure comes back as zero flags, not an error.
 */
export function runCoherenceCheck(applicationId: UUID) {
  return apiFetch<CoherenceCheckResult>(
    `/api/applications/${applicationId}/coherence-check`,
    { method: "POST" },
  );
}

export function createTailoringSession(
  jobId: UUID,
  baseResume: string,
  enrich?: boolean,
) {
  return apiFetch<TailoringSession>("/api/tailoring-sessions", {
    method: "POST",
    body: JSON.stringify({
      job_id: jobId,
      base_resume: baseResume,
      ...(enrich === undefined ? {} : { enrich }),
    }),
  });
}

export function getTailoringSession(id: UUID) {
  return apiFetch<TailoringSession>(`/api/tailoring-sessions/${id}`);
}

export function listTailoringSessions(jobId: UUID) {
  return apiFetch<TailoringSession[]>(
    `/api/tailoring-sessions?job_id=${encodeURIComponent(jobId)}`,
  );
}

/** Abandon an OPEN session (terminal). 409 if it already tailored/closed —
 * the "changed my mind" exit, e.g. after using the base resume as-is. */
export function closeTailoringSession(id: UUID) {
  return apiFetch<TailoringSession>(`/api/tailoring-sessions/${id}/close`, {
    method: "POST",
  });
}

/**
 * replace=false merges by gap_id (incremental batches); replace=true makes the
 * list the whole truth — omitted gap_ids are DELETED server-side. The gap page
 * autosaves the full list with replace=true so retracted resolutions actually die.
 *
 * userPrompt persists the optional "how should this be tailored?" note alongside
 * the resolutions. undefined = leave the stored value untouched; "" clears it; a
 * string sets it. tailor() falls back to this stored value when its own request
 * omits a prompt.
 */
export function saveResolutions(
  id: UUID,
  resolutions: Resolution[],
  replace = false,
  userPrompt?: string | null,
) {
  return apiFetch<TailoringSession>(`/api/tailoring-sessions/${id}`, {
    method: "PATCH",
    body: JSON.stringify({
      resolutions,
      replace,
      ...(userPrompt === undefined ? {} : { user_prompt: userPrompt }),
    }),
  });
}

/**
 * Create (or update, when applicationId is given) an application by applying
 * typed edit ops to a base resume. `ops: []` produces a verbatim copy of the
 * base — the "use base resume as-is" path when there is nothing to tailor.
 */
export function createApplicationFromBase(
  jobId: UUID,
  baseResume: string,
  ops: unknown[] = [],
  applicationId?: UUID,
) {
  return apiFetch<Application>("/api/applications/from-base", {
    method: "POST",
    body: JSON.stringify({
      job_id: jobId,
      base_resume: baseResume,
      ops,
      ...(applicationId === undefined ? {} : { application_id: applicationId }),
    }),
  });
}

export function tailorSession(
  id: UUID,
  userPrompt?: string,
  applyProfile?: boolean,
) {
  return apiFetch<TailorResult>(`/api/tailoring-sessions/${id}/tailor`, {
    method: "POST",
    body: JSON.stringify({
      user_prompt: userPrompt ?? null,
      ...(applyProfile ? { apply_profile: true } : {}),
    }),
  });
}

/**
 * Use for PDFs shown in the browser (`iframe`, `target="_blank"`, `window.open`).
 * Always path-relative (`/api/...`) so requests go through the Next.js `/api/*` proxy
 * (same origin as the app). `apiUrl()` respects `NEXT_PUBLIC_API_DIRECT`, which points
 * at the FastAPI origin; embedding that cross-origin often yields a blank PDF preview
 * and can force downloads instead of inline viewing.
 */
export function apiUrlForBrowserPdf(path: string): string {
  return path.startsWith("/") ? path : `/${path}`;
}

// ---------------------------------------------------------------------------
// Resume versions

export function listResumeVersions(kind: "base" | "application", key: string) {
  return apiFetch<import("@/lib/types").ResumeVersion[]>(
    `/api/resume-versions/${kind}/${encodeURIComponent(key)}`,
  );
}

export function getResumeVersion(
  kind: "base" | "application",
  key: string,
  version: number,
) {
  return apiFetch<import("@/lib/types").ResumeVersionDetail>(
    `/api/resume-versions/${kind}/${encodeURIComponent(key)}/${version}`,
  );
}

export function restoreResumeVersion(
  kind: "base" | "application",
  key: string,
  version: number,
) {
  return apiFetch<import("@/lib/types").ResumeVersion>(
    `/api/resume-versions/${kind}/${encodeURIComponent(key)}/${version}/restore`,
    { method: "POST" },
  );
}

// ---------------------------------------------------------------------------
// Career Knowledge Base

export interface KBEntityFilters {
  kind?: KBEntityKind;
  status?: KBEntityStatus;
}

export function listKbEntities(filters: KBEntityFilters = {}) {
  const params = new URLSearchParams();
  if (filters.kind) params.set("kind", filters.kind);
  if (filters.status) params.set("status", filters.status);
  const query = params.toString();
  return apiFetch<KBEntitySummary[]>(`/api/kb/entities${query ? `?${query}` : ""}`);
}

export function getKbEntity(entityId: UUID) {
  return apiFetch<KBEntityDetail>(`/api/kb/entities/${entityId}`);
}

export function createKbEntity(payload: KBEntityCreate) {
  return apiFetch<KBEntityDetail>("/api/kb/entities", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function patchKbEntity(entityId: UUID, payload: KBEntityPatch) {
  return apiFetch<KBEntityDetail>(`/api/kb/entities/${entityId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function deleteKbEntity(entityId: UUID) {
  return apiFetch<void>(`/api/kb/entities/${entityId}`, { method: "DELETE" });
}

/**
 * Fold `entityId` into `targetId` and return the SURVIVING target's detail.
 *
 * The server refuses a cross-kind merge, an `extra` section-key mismatch, and
 * an archived target with a 400 carrying a human sentence; a lost race returns
 * 409. Callers get those verbatim through `ApiError.message`.
 */
export function mergeKbEntity(entityId: UUID, targetId: UUID) {
  return apiFetch<KBEntityDetail>(`/api/kb/entities/${entityId}/merge`, {
    method: "POST",
    body: JSON.stringify({ target_id: targetId }),
  });
}

export function createKbPoint(entityId: UUID, payload: KBPointCreate) {
  return apiFetch<KBPointOut>(`/api/kb/entities/${entityId}/points`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function patchKbPoint(pointId: UUID, payload: KBPointPatch) {
  return apiFetch<KBPointOut>(`/api/kb/points/${pointId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function bulkKbPointState(
  ids: UUID[],
  state: "approved" | "retired",
) {
  return apiFetch<{
    results: {
      id: UUID;
      ok: boolean;
      state: string | null;
      detail: string | null;
    }[];
  }>("/api/kb/points/bulk-state", {
    method: "POST",
    body: JSON.stringify({ ids, state }),
  });
}

export function deleteKbPoint(pointId: UUID) {
  return apiFetch<void>(`/api/kb/points/${pointId}`, { method: "DELETE" });
}

export function listKbDrafts() {
  return apiFetch<KBInboxPoint[]>("/api/kb/points?state=draft");
}

export function uploadKbDocument(entityId: UUID, file: File) {
  const form = new FormData();
  form.append("file", file);
  return apiFetch<KBDocumentOut>(`/api/kb/entities/${entityId}/documents`, {
    method: "POST",
    body: form,
  });
}

/** Document-first ingest: the doc itself supplies the entity metadata. */
export function kbIngestDocument(file: File) {
  const form = new FormData();
  form.append("file", file);
  return apiFetch<import("@/lib/types").KBDocumentIngestResponse>(
    "/api/kb/documents/ingest",
    { method: "POST", body: form },
  );
}

export function kbImportResume(file: File, consolidate = true) {
  const form = new FormData();
  form.append("files", file);
  const q = consolidate ? "" : "?consolidate=false";
  return apiFetch<import("@/lib/types").ImportReport>(`/api/kb/import${q}`, {
    method: "POST",
    body: form,
  });
}

export function kbImportConsolidate(slugs: string[]) {
  return apiFetch<{ entities_created: number; points_approved: number }>(
    "/api/kb/import/consolidate",
    { method: "POST", body: JSON.stringify({ slugs }) },
  );
}

export function remintKbDocument(documentId: UUID) {
  return apiFetch<KBDocumentOut>(`/api/kb/documents/${documentId}/mint`, {
    method: "POST",
  });
}

export function deleteKbDocument(documentId: UUID) {
  return apiFetch<void>(`/api/kb/documents/${documentId}`, { method: "DELETE" });
}

export function kbCapture(payload: KBCaptureRequest) {
  return apiFetch<KBCaptureResponse>("/api/kb/capture", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function kbPort(payload: KBPortRequest) {
  return apiFetch<KBPortResponse>("/api/kb/port", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function kbAdapt(payload: KBAdaptRequest) {
  return apiFetch<KBAdaptProposal>("/api/kb/port/adapt", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function kbAdaptApply(payload: KBAdaptApplyRequest) {
  return apiFetch<KBPortResponse>("/api/kb/port/adapt/apply", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getKbSyncStatus(slug: string) {
  return apiFetch<SyncStatus>(`/api/base-resumes/${slug}/kb-sync-status`);
}

export function applyKbSync(slug: string) {
  return apiFetch<SyncResult>(`/api/base-resumes/${slug}/kb-sync`, {
    method: "POST",
  });
}

export function getKbProfile() {
  return apiFetch<KBProfileOut>("/api/kb/profile");
}

export function patchKbProfile(payload: KBProfilePatch) {
  return apiFetch<KBProfileOut>("/api/kb/profile", {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

// ---------------------------------------------------------------------------
// Chat

export function createChatSession(context?: import("@/lib/types").ChatContext) {
  return apiFetch<import("@/lib/types").ChatSessionSummary>("/api/chat/sessions", {
    method: "POST",
    body: JSON.stringify({ context: context ?? null }),
  });
}

export function listChatSessions() {
  return apiFetch<import("@/lib/types").ChatSessionSummary[]>("/api/chat/sessions");
}

export function getChatSession(id: UUID) {
  return apiFetch<import("@/lib/types").ChatSessionDetail>(`/api/chat/sessions/${id}`);
}

export function deleteChatSession(id: UUID) {
  return apiFetch<void>(`/api/chat/sessions/${id}`, { method: "DELETE" });
}

export function setChatCardState(messageId: UUID, status: "applied" | "discarded") {
  return apiFetch<import("@/lib/types").ChatMessage>(`/api/chat/messages/${messageId}/card-state`, {
    method: "PATCH",
    body: JSON.stringify({ status }),
  });
}

export async function uploadChatAttachment(sessionId: UUID, file: File) {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(apiUrl(`/api/chat/sessions/${sessionId}/attachments`), {
    method: "POST",
    body: form,
  });
  if (!res.ok) {
    let detail = `Upload failed (${res.status})`;
    try {
      const body = (await res.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      // keep default detail
    }
    throw new ApiError(res.status, detail, null);
  }
  return (await res.json()) as import("@/lib/types").ChatAttachmentInfo;
}

/**
 * Send a chat message and consume the SSE stream. Calls onEvent per parsed
 * event; resolves when the stream closes. The Next proxy streams the body
 * through, so this works same-origin in dev and prod.
 */
export async function streamChatMessage(
  sessionId: UUID,
  content: string,
  context: import("@/lib/types").ChatContext | null,
  onEvent: (event: import("@/lib/types").ChatStreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(apiUrl(`/api/chat/sessions/${sessionId}/messages`), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content, context }),
    signal,
  });
  if (!res.ok || !res.body) {
    let detail = `Chat request failed (${res.status})`;
    try {
      const body = (await res.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      // keep default detail
    }
    throw new ApiError(res.status, detail, null);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let sep;
    while ((sep = buffer.indexOf("\n\n")) !== -1) {
      const raw = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);
      const line = raw.split("\n").find((l) => l.startsWith("data: "));
      if (!line) continue;
      try {
        onEvent(JSON.parse(line.slice(6)) as import("@/lib/types").ChatStreamEvent);
      } catch {
        // Malformed frame — skip rather than kill the stream.
      }
    }
  }
}

// ---------------------------------------------------------------------------
// Resume health check

export function getLintReport(kind: "base" | "application", key: string) {
  return apiFetch<import("@/lib/types").LintReport>(
    `/api/resume-lint/${kind}/${encodeURIComponent(key)}`,
  );
}

export function runLintReport(kind: "base" | "application", key: string) {
  return apiFetch<import("@/lib/types").LintReport>(
    `/api/resume-lint/${kind}/${encodeURIComponent(key)}/run`,
    { method: "POST" },
  );
}

export function waiveGate(
  kind: "base" | "application",
  key: string,
  gateId: string,
  reason: string,
) {
  return apiFetch(
    `/api/resume-lint/${kind}/${encodeURIComponent(key)}/gates/${encodeURIComponent(gateId)}/waive`,
    { method: "POST", body: JSON.stringify({ reason }) },
  );
}

export function unwaiveGate(
  kind: "base" | "application",
  key: string,
  gateId: string,
) {
  return apiFetch(
    `/api/resume-lint/${kind}/${encodeURIComponent(key)}/gates/${encodeURIComponent(gateId)}/waive`,
    { method: "DELETE" },
  );
}

export function overrideLevel(
  contentHash: string,
  level: import("@/lib/types").EvidenceLevel | null,
  reason?: string,
) {
  return apiFetch(`/api/resume-lint/classification-override`, {
    method: "POST",
    body: JSON.stringify({ content_hash: contentHash, level, reason }),
  });
}

export function answerAsk(
  kind: "base" | "application",
  key: string,
  findingId: string,
  answer: string,
) {
  return apiFetch<{ suggestion: string }>(
    `/api/resume-lint/${kind}/${encodeURIComponent(key)}/ask/${encodeURIComponent(findingId)}/answer`,
    { method: "POST", body: JSON.stringify({ answer }) },
  );
}

export function listCareerExports() {
  return apiFetch<CareerExportMetadata[]>("/api/exports");
}

export function refreshCareerExport() {
  return apiFetch<CareerExportMetadata>("/api/exports/career/refresh", {
    method: "POST",
  });
}

export function careerExportDownloadUrl() {
  return apiUrl("/api/exports/career");
}

