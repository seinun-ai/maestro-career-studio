import { humanizeSlug } from "./humanize-slug";
import type { Provider } from "./model-catalog";
import type { Rung } from "./next-step";

export type UUID = string;

/** Provenance lane: who initiated the row — the user's own browsing/tracking
 * ("user") or the agent-hunted auto-apply lane ("agent"). */
type ProvenanceSource = "user" | "agent";

/**
 * Carried by every response that FOLLOWS a render. `render_note` is non-null
 * only when TeX is absent on the backend host and a LaTeX template rendered
 * through a Typst one instead — the render succeeded, under another engine.
 *
 * Optional because one caller can hit either arm of the `/edits` pair: the
 * base-resume arm re-renders and answers with the note, while the application
 * arm renders NOTHING (`resume_ops.edit_application` only clears the artifact
 * refs; the PDF is rendered later, on an explicit Render). So that arm has no
 * note to give and needs none.
 */
export interface RenderNoted {
  render_note?: string | null;
}

export interface JobOwnership {
  owned_here: boolean;
  owner: "laptop" | "bot" | null;
  handover: string | null;
  pending_requests: number;
  /** True only on the laptop, for a job it offered and still holds. */
  can_keep_here?: boolean;
}

export interface SyncQueued {
  queued: true;
  detail: string;
}

export interface Job {
  id: UUID;
  ownership?: JobOwnership;
  raw_text: string;
  raw_text_hash: string;
  source_url: string | null;
  /** The employer's own apply link, when the posting page exposed one; a run
   *  opens it before source_url. Optional: an older backend does not send it. */
  apply_url?: string | null;
  source: ProvenanceSource;
  extracted_json: Record<string, unknown> | null;
  title: string | null;
  company: string | null;
  requisition_id: string | null;
  role_category: string | null;
  level: string | null;
  employment_type: string | null;
  work_mode: string | null;
  location: string | null;
  city: string | null;
  state: string | null;
  /** As the posting wrote it; `country_code` is the one ISO code it names. */
  country: string | null;
  /** ISO 3166-1 alpha-2, derived at capture from the country, else the location line; null when
   *  neither names exactly one country. Optional: an older backend does not send it. */
  country_code?: string | null;
  location_raw: string | null;
  salary_min: string | number | null;
  salary_max: string | number | null;
  salary_period: string | null;
  salary_currency: string | null;
  /** True when the posting gave no currency (a bare "$" included) and capture took the job's
   *  country's, else the home currency. Optional: an older backend does not send it. */
  salary_currency_assumed?: boolean;
  salary_source_url: string | null;
  work_authorization: string | null;
  opt_accepted: string | null;
  years_experience_min: number | null;
  years_experience_max: number | null;
  extracted_at: string | null;
  created_at: string;
  /** Set by create/ingest when dedup returned an existing row instead of
   * extracting a fresh one — the capture UI must say "already tracked". */
  already_existed?: boolean;
  /** List/detail derived field: the job's newest proposal status, so
   * the tracker can show Skipped/Queued/Proposed instead of a flat Saved. */
  proposal_status?: string | null;
  /** Newest proposal id (paired with proposal_status) for job-page triage. */
  proposal_id?: UUID | null;
  /** Who filed the newest proposal: "you", an MCP client's name, or null.
   *  Optional: an older backend does not send it (reads as unknown). */
  proposal_proposed_by?: string | null;
  /** The best base-resume score, list endpoint only; null when never scored. */
  best_ats_score?: number | null;
  /** The job lists only (services/stage.py): the rung the job sits on, and the open gap analysis
   *  behind a `gaps` rung with its closed/listed counts. The detail sends them beside `job` (JobDetail,
   *  whose `job` leaves them out). Optional: an older backend omits them. */
  stage?: Rung;
  open_session_id?: UUID | null;
  gaps_done?: number;
  gaps_total?: number;
}

export interface JobCreate {
  raw_text: string;
  source_url?: string | null;
}

/** The one status vocabulary — mirrors backend ALLOWED_STATUSES exactly;
 * PATCH rejects anything else. */
export const APPLICATION_STATUSES = [
  "draft",
  "applied",
  "interviewing",
  "offered",
  "accepted",
  "rejected",
  "withdrawn",
] as const;

export type ApplicationStatus = (typeof APPLICATION_STATUSES)[number];

export interface Application {
  id: UUID;
  job_id: UUID;
  base_resume: string;
  source: ProvenanceSource;
  status: string | null;
  applied_at: string | null;
  notes: string | null;
  customized_json: Record<string, unknown> | null;
  pdf_path: string | null;
  tex_path: string | null;
  referral_id: UUID | null;
  user_prompt: string | null;
  pdf_pages: number | null;
  render_error: string | null;
  formatting: Record<string, unknown> | null;
  template_id: string | null;
  created_at: string;
  updated_at: string;
  /** Joined like the job fields. Optional: a backend that predates it omits it.
   *  Null when the résumé has no row. Archived and soft-deleted rows still name it. */
  base_resume_name?: string | null;
}

export interface ApplicationDetail extends Application {
  job: Job | null;
}

/** Thin list projection from GET /api/applications — job display fields are
 * joined server-side so the tracker needs no second jobs query. */
export interface ApplicationSummary {
  id: UUID;
  job_id: UUID;
  base_resume: string;
  source: ProvenanceSource;
  status: string | null;
  applied_at: string | null;
  referral_id: UUID | null;
  created_at: string;
  job_title: string | null;
  job_company: string | null;
  job_location: string | null;
  /** The job's ownership; absent when sync is off. */
  ownership?: JobOwnership;
  /** Joined like the job fields. Optional: a backend that predates it omits it. */
  base_resume_name?: string | null;
  /** Newest tailored score, else the base resume's; list endpoint only, null when unscored. */
  ats_score?: number | null;
  /** List endpoint only (services/stage.py): the rung, the open gap analysis behind a `gaps` rung with
   *  its closed/listed counts, and whether a draft or a PDF exists. Optional: an older backend omits them. */
  stage?: Rung;
  open_session_id?: UUID | null;
  gaps_done?: number;
  gaps_total?: number;
  has_draft?: boolean;
  has_pdf?: boolean;
  /** List endpoint only (`application_status.status_since`): when the current status began, from the status log;
   *  null when the log holds no change into it. Optional: an older backend omits it. */
  status_since?: string | null;
}

export type KnockoutStatus =
  | "conflict"
  | "clear"
  | "incomplete_profile"
  | "unstated";

export interface KnockoutCheck {
  kind: "work_authorization" | "opt" | "salary" | "experience" | "on_site";
  /** `cant_compare`: pay with no exchange rate, or a side that names no currency. Never a pass. */
  result: "pass" | "conflict" | "warning" | "job_unstated" | "profile_missing" | "cant_compare";
  job_value: string | null;
  profile_value: string | null;
  message: string | null;
}

/** Stated-JD-requirements vs profile pre-scan. `unstated` is NOT a pass —
 * the posting simply states nothing this scan can screen on. */
export interface KnockoutScan {
  status: KnockoutStatus;
  checks: KnockoutCheck[];
}

export interface JobDetail {
  /** The plain JobRead: the rung is not on it but beside it (below), so `detail.job.stage` does not compile. */
  job: Omit<Job, "stage" | "open_session_id" | "gaps_done" | "gaps_total">;
  application: Application | null;
  knockout: KnockoutScan | null;
  /** Whether anything was recorded as filled into this job's form (the What was submitted tab). */
  has_filled_answers: boolean;
  /** The application's base resume's own name; null with no application or no name. Optional: an older backend omits it. */
  base_resume_name?: string | null;
  /** The rung the job page is on (services/stage.py), and the open gap analysis behind a `gaps` rung with its
   *  closed/listed counts. Here, not on `job`: lib/job-steps `jobStepsInput` reads them from the detail. */
  stage?: Rung;
  open_session_id?: UUID | null;
  gaps_done?: number;
  gaps_total?: number;
}

export interface ContactInfo {
  name: string;
  email: string;
  phone?: string | null;
  location?: string | null;
  linkedin?: string | null;
  github?: string | null;
  website?: string | null;
}

export interface ExperienceEntry {
  company: string;
  role: string;
  location?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  enabled?: boolean;
  bullets: string[];
}

export interface EducationEntry {
  institution: string;
  degree?: string | null;
  field?: string | null;
  location?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  graduation_date?: string | null;
  gpa?: string | null;
  coursework: string[];
  bullets: string[];
}

export interface ProjectEntry {
  name: string;
  enabled?: boolean;
  tech?: string | null;
  link?: string | null;
  date?: string | null;
  bullets: string[];
}

export interface SkillGroup {
  category: string;
  items: string[];
}

// --- Custom (extra) sections -------------------------------------------------
// Mirrors backend `app/schemas/resume.py`: an ordered list of a discriminated
// union on `type`. `key` is the stable machine identity (lookups use it as
// `section_key`); `title` is editable display text. An `entries` section
// carries structured entries; a `bullets` section carries a flat bullet list —
// never both at once. Phase 2 exposes enabled custom content to ATS evidence and
// gap placement while retaining stable-key targeting.

export interface ExtraSectionEntry {
  heading: string;
  subheading?: string | null;
  location?: string | null;
  date?: string | null;
  link?: string | null;
  enabled?: boolean;
  bullets: string[];
}

interface ExtraSectionEntries {
  key: string;
  title: string;
  enabled?: boolean;
  type: "entries";
  entries: ExtraSectionEntry[];
}

interface ExtraSectionBullets {
  key: string;
  title: string;
  enabled?: boolean;
  type: "bullets";
  bullets: string[];
}

export type ExtraSection = ExtraSectionEntries | ExtraSectionBullets;
export type ExtraSectionType = ExtraSection["type"];

export interface ResumeData {
  contact: ContactInfo;
  summary?: string | null;
  skills: SkillGroup[];
  experience: ExperienceEntry[];
  projects: ProjectEntry[];
  education: EducationEntry[];
  certifications: string[];
  extra_sections: ExtraSection[];
}

export interface QAResponse {
  answers: string[] | null;
  cover_letter: string | null;
}

export interface QAEntry extends RenderNoted {
  id: UUID;
  application_id: UUID;
  kind: string;
  prompt: string | null;
  answer: string | null;
  model_used: string | null;
  pdf_path: string | null;
  created_at: string;
}

export interface SettingValue {
  key: string;
  value: string;
}

/** The envelope every `/api/settings/*` blob endpoint returns. */
export interface SettingEnvelope<T> {
  key: string;
  value: T;
}

export interface QuickTailorProfile {
  keywords_into_skills: boolean;
  mirror_wording: boolean;
  summary_rename: boolean;
  project_keyword_injection: boolean;
  instruction: string;
}
export type QuickTailorSetting = SettingEnvelope<QuickTailorProfile>;

export interface McpWorkflowSettings {
  hints: boolean;
}
export type McpWorkflowSetting = SettingEnvelope<McpWorkflowSettings>;

/** GET/PUT /api/settings/resumes-folder: where Maestro saves a visible copy of each finished PDF.
 *  `folder_display` is server-made (it knows the home folder), so show it as it is. */
export interface ResumesFolderSettings {
  available: boolean;
  reason: "not_here" | "always_on_copy" | null;
  enabled: boolean;
  folder: string | null;
  folder_display: string | null;
  default_folder: string | null;
  custom: boolean;
  platform: "macos" | "windows" | "linux";
  picker: boolean;
  last_error: { message: string; at: string } | null;
}

/** GET/PUT /api/settings/autofill-options: how far the Companion's fill may
 *  answer a screening question no saved answer covers. A bare object, no
 *  envelope. The fill re-reads it server-side. */
export interface AutofillOptions {
  answer_level: "facts" | "history" | "queued";
}

export interface EeoConsent {
  enabled: boolean;
  /** Ticking an application's own agreement boxes — terms, acknowledgements,
   *  attestations. Separate from `enabled` so opting into EEO fill cannot
   *  silently also opt into agreeing to terms; one record, two permissions. */
  consent_forms: boolean;
  /** Server-derived, never sent: `consent_forms` was agreed under an older
   *  policy that covered less, so it is served off until the user agrees
   *  again (backend/app/schemas/eeo_consent.py). */
  consent_forms_lapsed?: boolean;
  acknowledged_at: string | null;
  policy_version: string;
}

/** What the web app PUTs. The server owns `acknowledged_at` / `policy_version`;
 *  `agreed_policy` is request-only (never stored or served): the policy whose
 *  wording the agreement confirm showed, sent on that switch's yes. Without it
 *  the server holds `consent_forms` off, so a tab loaded before a policy change
 *  cannot grant the permission under the old wording. */
export interface EeoConsentUpdate extends EeoConsent {
  agreed_policy?: string;
}

export interface ModelOption {
  id: string;
  label: string;
  provider: string;
  tier: string;
  /** Built-in seed vs user-added via Sync +. Absent on older payloads = seed. */
  // "configured" = not seeded and not added on purpose; it is listed only
  // because a role still points at it (see model_settings.configured_options).
  source?: "seed" | "extra" | "configured";
}

/** One model's measured capabilities. Written by POST /api/settings/openai/probe. */
export interface CapabilityReport {
  model: string;
  base_url: string | null;
  text: boolean;
  json: boolean;
  tools: boolean;
  errors: Record<string, string>;
  checked_at: string;
  // false = the probe never reached the model (bad key, dead endpoint,
  // rate limit); nothing was recorded, so this is not a verdict on the model.
  reachable?: boolean;
}

export interface DiscoveredModel {
  id: string;
  label: string;
  provider: Provider;
  in_catalog: boolean;
}

export interface ModelSyncResult {
  models: DiscoveredModel[];
}

/** GET/PUT /api/settings/jev. The key is write-only: only `api_key_configured` comes back. */
export type JevInfo = {
  api_key_configured: boolean;
  base_url: string;
  model: string;
  engine: "fast" | "jev";
};

export interface OpenAIInfo {
  fast_model: string;
  smart_model: string;
  chat_model: string;
  /** The Companion's reasoning step; defaults to the chosen provider's strong model. */
  reasoning_model: string;
  api_key_configured: boolean;
  // The API never returns key material — only whether a key is configured.
  gemini_api_key_configured: boolean;
  anthropic_api_key_configured: boolean;
  openrouter_api_key_configured: boolean;
  /** Where the effective key comes from — one saved in the app ("settings")
   *  beats one from .env ("env"). */
  openai_key_source: "settings" | "env" | "none";
  gemini_key_source: "settings" | "env" | "none";
  anthropic_key_source: "settings" | "env" | "none";
  openrouter_key_source: "settings" | "env" | "none";
  model_options: ModelOption[];
  /** The OpenAI-compatible endpoint. A location, not a secret, so it is echoed. */
  base_url: string | null;
  /** When true, `model_options` is NOT exhaustive — we cannot enumerate what an
   *  arbitrary Ollama or vLLM host serves, so model ids become free text. */
  custom_endpoint: boolean;
  json_mode: "auto" | "on" | "off";
  /** Keyed by model id; only the configured models appear. */
  capabilities: Record<string, CapabilityReport>;
}

/** The four roles as a recommended set names them ("assistant" is `chat_model`). */
export type RoleModels = Record<"fast" | "smart" | "assistant" | "reasoning", string>;

/** GET/PUT /api/settings/models/recommended. PUT `{on, provider?}`: `provider` absent keeps the choice,
 *  null is the first provider with a key; one with no set is a 400. While on, OpenAIInfo's four
 *  role fields are the set's. */
export interface RecommendedModelsInfo {
  on: boolean;
  /** The provider you chose; null is the first (the screen's order) with a key and a set. */
  provider: "openai" | "gemini" | "anthropic" | "openrouter" | null;
  /** Whose set the roles use now; null while off, or when no provider with a set has a key. */
  active_provider: "openai" | "gemini" | "anthropic" | "openrouter" | null;
  models: RoleModels | null;
  /** Your own picks, which the roles use again once it is off. */
  own: RoleModels;
  /** Each provider's set; a provider with none (OpenRouter) is absent. */
  sets: Record<string, RoleModels>;
}

export interface CatalogRole {
  key: string;
  label: string;
}

/** GET /api/role-categories — the vocabulary, served from
 *  backend/app/services/ats/data/role_categories.yaml. Never duplicated here.
 *  `roles` is the specific-role layer: display and search only, never stored. */
export interface RoleCategory {
  key: string;
  label: string;
  reserved: boolean;
  roles: CatalogRole[];
}

/** One targeted role. `role === null` means the user typed it themselves;
 *  `category` is then their confirmed mapping, or null if left unmapped. */
export interface FavoredRole {
  role: string | null;
  label: string;
  category: string | null;
}

/** GET /api/role-categories/match — a MISS is `confidence: "none"` with a 200,
 *  never an error. Compare against the string: "none" is truthy. */
export interface RoleMatch {
  role: string | null;
  category: string | null;
  label: string;
  confidence: "exact" | "alias" | "none";
}

export interface JobPreferences {
  favored_roles: FavoredRole[];
  /** Derived server-side from favored_roles. Read-only in practice. */
  role_categories: string[];
  /** Years of experience the user claims (0–60). Replaces the old levels pills. */
  years_experience: number | null;
  employment_types: string[];
  locations: string[];
  remote: "remote" | "hybrid" | "onsite" | "any" | null;
  /** The lowest yearly pay you want. `currency` is filled with your home currency when read; `text` keeps
   *  an old free-text answer that was not a number (backend/app/schemas/job_preferences.py `MinSalary`). */
  min_salary: MinSalary | null;
  notes: string | null;
}

export interface MinSalary {
  amount: number | null;
  currency: string | null;
  text: string | null;
}

/** GET/PUT /api/settings/auto-apply — the agent lane's guardrails. The model
 * is extra="forbid" server-side: PUT the WHOLE object back, including fields
 * this UI does not surface (e.g. deprecated cooldown_days). */
export interface AutoApplySettings {
  max_proposals_per_run: number;
  max_submissions_per_day: number;
  cooldown_days: number;
  company_blocklist: string[];
  proposal_expiry_days: number;
  auto_pick_margin: number;
  auto_pick_floor: number;
  full_automation: boolean;
}

/** GET/PUT /api/settings/job-site-login: the web API never returns a password. */
export interface JobSiteLoginStatus {
  email: string | null;
  password_set: boolean;
}

/** GET /api/setup/connect: the backend composes every client's connection value. */
export interface ConnectClient {
  id: "claude-code" | "codex" | "codex-app" | "cursor" | "vscode" | "claude-desktop" | "other";
  label: string;
  kind: "command" | "deeplink" | "url" | "download" | "steps";
  value: string;
}

export interface ConnectProfile {
  name: "full" | "hunt" | "apply" | "explore" | "templates" | "career";
  url: string;
}

export interface ConnectInfo {
  backend_url: string;
  mcp_url: string;
  profiles: ConnectProfile[];
  bundle_available: boolean;
  clients: ConnectClient[];
}

interface SetupStep {
  done: boolean;
  detail: Record<string, unknown>;
}

interface EngineProbe {
  name: string;
  available: boolean;
  version: string | null;
  path: string | null;
  reason: string | null;
  /** Available, with a known defect worth fixing (e.g. pdfTeX 1.40.27). */
  warning: string | null;
}

export interface SetupStatus {
  /** A provider API key is configured (in-app or .env). Blocks everything. */
  model_key: SetupStep;
  import_resumes: SetupStep;
  autofill: {
    done: boolean;
    readiness: number;
    groups: Record<string, { answered: number; answerable: number }>;
    blocking: string[];
    /** Each apply-in market's work-permit answers ("UK"), summed in `groups.work_auth`. */
    work_auth_by_country: Record<string, { answered: number; answerable: number }>;
  };
  job_preferences: SetupStep;
  persona: SetupStep;
  template: SetupStep;
  /** Which PDF engines the backend can run. Informational, never blocks. */
  engines: {
    pdflatex: EngineProbe;
    typst: EngineProbe;
  };
  suggested_bases: { role_category: string; label: string }[];
  complete: boolean;
}

export interface BaseResumeSummary {
  slug: string;
  display_name: string | null;
  /** Target role projection. Always present; "unknown" means not declared yet. */
  role_category: string;
  /** User's own words for the tag when free text; null means the tag IS
   *  role_category (a catalog pick). Display prefers this when set. */
  role_label: string | null;
  pdf_rendered_at: string | null;
  updated_at: string;
  /** Set when the last auto-render failed — the PDF and its preview are the
   *  previous successful render. Drives the card's thumbnail state. */
  render_error: string | null;
  /** Hidden from pickers, still fully resolvable. */
  archived_at: string | null;
  /** The Target dialog's fields (the code calls them anchors). Countries are
   *  ISO 3166-1 alpha-2 codes; empty means the resume is scored for every job. */
  countries: string[];
  company: string | null;
  focus: string | null;
  /** The resume's colour as a hue 0-359; null draws neutral grey. Drawn by
   *  resumeColorStyle in lib/resume-color.ts. */
  color_hue: number | null;
}

/** GET /api/countries: one ISO country, in file (code) order. */
export interface Country {
  code: string;
  name: string;
}

/** GET /api/ats-scores/candidates: which base resumes the job's country left out.
 *  `job_country` is null when the job's country is unknown (nothing is left out);
 *  `fallback` is true when no resume is set for it, so every resume was scored. */
export interface AtsCandidates {
  job_country: string | null;
  fallback: boolean;
  skipped: string[];
}

/** POST /api/kb/import — one action mints base resumes AND feeds the Career KB.
 *  `proposed` is true when the system guessed the role from resume content and
 *  the UI must ask the user to confirm; false means "unknown", i.e. undeclared
 *  rather than guessed. */
interface ImportedBase extends RenderNoted {
  slug: string;
  display_name: string;
  role_category: string;
  role_label: string | null;
  proposed: boolean;
  render_error: string | null;
}

interface SkippedImportFile {
  filename: string;
  reason: string;
}

/** `POST /api/kb/import/consolidate` (backend schemas/career_kb.py `ConsolidationReport`): what joined
 *  career history. The newer counts are optional, so a reader shows what a response has. */
export interface ImportConsolidation {
  entities_created: number;
  entities_matched?: number;
  points_approved: number;
  points_draft?: number;
  /** The individual skills that landed; count these. */
  skills_items_added?: string[];
}

export interface ImportReport {
  bases: ImportedBase[];
  skipped: SkippedImportFile[];
  kb: ImportConsolidation | null;
}

export interface BaseResumeDetail extends BaseResumeSummary, RenderNoted {
  data: ResumeData;
  pdf_path: string | null;
  tex_path: string | null;
  pdf_pages: number | null;
  formatting: Record<string, unknown> | null;
  template_id: string | null;
  /** POST /import only: rows the parser dropped rather than fail the file. */
  parse_warnings?: string[] | null;
}

/** POST /api/applications/{id}/render */
export interface RenderResult extends RenderNoted {
  tex_path: string;
  pdf_path: string;
  resolved_template_id: string | null;
  resolved_engine: string | null;
  template_fallback: boolean | null;
  /** Where the visible copy sits in the resumes folder; null when there is none. */
  copy_path: string | null;
}

/** POST /api/base-resumes/{slug}/propose — a reviewed-before-applied proposal. */
export interface BaseResumeProposal {
  summary: string;
  notes: string;
  ops: Record<string, unknown>[];
  ops_count: number;
}

// ---------------------------------------------------------------------------
// Career Knowledge Base

export type KBEntityKind =
  | "experience"
  | "project"
  | "education"
  | "certification"
  | "extra";

export type KBEntityStatus = "ongoing" | "completed" | "archived";
export type KBPointState = "draft" | "approved" | "retired";
type KBPointOrigin =
  | "manual"
  | "ingested"
  | "chat"
  | "consolidated"
  | "mcp"
  | "gap_elicitation"
  | "base_sync";

export type KBPointProvenance =
  | "user_authored"
  | "user_stated"
  | "derived_unverified"
  | "user_cannot_confirm";

export interface KBEntityCreate {
  kind: KBEntityKind;
  title: string;
  org?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  status?: KBEntityStatus;
  detail?: Record<string, unknown>;
  notes?: string | null;
  section_key?: string | null;
  section_type?: "entries" | "bullets" | null;
  section_title?: string | null;
}

export interface KBEntityPatch {
  kind?: KBEntityKind;
  title?: string;
  org?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  status?: KBEntityStatus;
  detail?: Record<string, unknown> | null;
  notes?: string | null;
  section_key?: string | null;
  section_type?: "entries" | "bullets" | null;
  section_title?: string | null;
}

export interface KBPointPatch {
  text?: string | null;
  state?: KBPointState | null;
  tags?: string[] | null;
  entity_id?: UUID | null;
  /** Clears the "combined into" pointer. With `state` it is the split of a combined bullet. */
  unmerge?: boolean;
}

/** One other phrasing of a bullet and what can be done with it (see the backend's KBWordingOut). */
export interface KBWordingOut {
  kind: "resume" | "placed" | "merged" | "import";
  text: string;
  resume_keys: string[];
  section: string | null;
  point_id: UUID | null;
  adoptable: boolean;
  splittable: boolean;
}

export interface KBCaptureRequest {
  text: string;
  entity_id?: UUID | null;
}

interface KBUsageOut {
  resume_key: string;
  section: string;
  ported_text: string;
  ported_at: string;
  drifted: boolean;
  direction?: "to_resume" | "from_source" | null;
}

export interface KBPointOut {
  id: UUID;
  entity_id: UUID;
  text: string;
  state: KBPointState;
  origin: KBPointOrigin;
  origin_detail?: string | null;
  provenance: KBPointProvenance | null;
  source_document_id: UUID | null;
  tags: string[];
  merge_sources: KBMergeSource[] | null;
  approved_at: string | null;
  created_at: string;
  updated_at: string;
  usage: KBUsageOut[];
  wordings: KBWordingOut[];
  merged_into_point_id: UUID | null;
}

interface KBMergeSource {
  resume_key: string;
  section: string;
  text: string;
}

/** What Combine returns: the keeper, and the combined claims that were re-pointed from a loser onto it. */
export interface KBCombineResponse {
  keeper: KBPointOut;
  repointed: { point_id: UUID; from_id: UUID }[];
}

export interface GroomMember {
  id: UUID;
  text: string;
  state: KBPointState;
  origin: KBPointOrigin;
  provenance: KBPointProvenance | null;
  usage_count: number;
  best_score: number;
}

export interface GroomCluster {
  score: number;
  keeper_id: UUID;
  members: GroomMember[];
  pairs: [UUID, UUID, number][];
}

/** Similar bullets on one item, read-only. `compared_wording` false means the embedder could not run. */
export interface GroomReport {
  entity_id: UUID;
  entity_title: string;
  compared_wording: boolean;
  active_points: number;
  clusters: GroomCluster[];
}

export interface KBDocumentOut {
  id: UUID;
  filename: string;
  mime: string | null;
  size_bytes: number;
  ingest_status: string;
  ingest_summary: string | null;
  /** Text was read from the file. A `failed` document with text failed at
   *  suggesting bullets, not at reading. */
  has_text: boolean;
  created_at: string;
}

export interface KBDocumentIngestResponse {
  entity_id: UUID;
  entity_title: string;
  entity_kind: string;
  created_entity: boolean;
  point_count: number;
  document: KBDocumentOut;
}

export interface KBTimelineEvent {
  ts: string;
  type: string;
  label: string;
}

export interface KBEntitySummary {
  id: UUID;
  kind: KBEntityKind;
  title: string;
  org: string | null;
  status: KBEntityStatus;
  origin?: string | null;
  origin_detail?: string | null;
  start_date: string | null;
  end_date: string | null;
  point_count: number;
  draft_count: number;
  /** Bullets that go on a resume (`point_count` also holds drafts and Not used). */
  approved_count: number;
  document_count: number;
  last_activity: string;
  section_key?: string | null;
  section_type?: "entries" | "bullets" | null;
  section_title?: string | null;
  /** Slugs of the active base resumes this item was added to (absent from a backend that predates it). */
  used_in_bases?: string[];
}

export interface KBEntityDetail extends KBEntitySummary {
  detail: Record<string, unknown>;
  notes: string | null;
  points: KBPointOut[];
  documents: KBDocumentOut[];
  timeline: KBTimelineEvent[];
}

export interface KBInboxPoint extends KBPointOut {
  entity_title: string;
  entity_kind: KBEntityKind;
}

export interface KBCaptureResponse {
  entity_id: UUID;
  entity_title: string;
  point_ids: UUID[];
}

interface KBPortItem {
  entity_id: UUID;
  point_ids?: UUID[];
  section_key?: string | null;
}

export interface KBPortRequest {
  target_slug: string;
  items?: KBPortItem[];
  skill_categories?: string[];
  include_profile_summary?: boolean;
}

interface KBPortItemReport {
  entity_id: UUID;
  ported_point_ids: UUID[];
  skipped_duplicate_point_ids: UUID[];
  created_entry: boolean;
}

interface KBPortReport {
  items: KBPortItemReport[];
  skills_merged: string[];
}

export interface KBPortResponse {
  resume: BaseResumeDetail;
  report: KBPortReport;
}

export type KBAdaptAction = "kept" | "rewritten" | "merged" | "replace";

export interface KBAdaptRequest {
  target_slug: string;
  entity_id: UUID;
  point_ids?: UUID[];
}

interface KBAdaptBullet {
  text: string;
  source_point_ids: UUID[];
  replaces_bullet_index: number | null;
  action: KBAdaptAction;
  reason: string | null;
}

export interface KBAdaptDropped {
  point_id: UUID;
  reason: string;
}

export interface KBAdaptProposal {
  target_slug: string;
  entity_id: UUID;
  section: string;
  matched_entry_index: number | null;
  create_entry: boolean;
  existing_bullets: string[];
  bullets: KBAdaptBullet[];
  dropped: KBAdaptDropped[];
}

interface KBAdaptApplyBullet {
  text: string;
  source_point_ids: UUID[];
  replaces_bullet_index: number | null;
  /** Echo of the reviewed existing bullet; required when replacing. */
  replaces_text: string | null;
}

export interface KBAdaptApplyRequest {
  target_slug: string;
  entity_id: UUID;
  bullets: KBAdaptApplyBullet[];
}

// --- Analytics (/api/explore additions) -------------------------------------

interface ActivityBucket {
  bucket_start: string;
  drafted: number;
  submitted: number;
}

export interface ActivityResponse {
  granularity: "day" | "week";
  series: ActivityBucket[];
  totals: {
    applications: number;
    drafted_last7: number;
    submitted: number;
    submitted_last7: number;
    in_flight: number;
    /** Applications at interview or later now: the rate's numerator (`submitted` is its denominator). */
    interview_plus: number;
    /** Null below 20 submitted (`services/rates.py` MIN_RATE_N): show "1 of 3" from the counts instead. */
    interview_rate: number | null;
  };
  status_counts: Record<string, number>;
}

/** `services/rates.py` `rate()`: `rate`, `low` and `high` are null below `min_rate_n` in `of`; show "5 of 12". */
export interface RateCount {
  count: number;
  of: number;
  rate: number | null;
  /** Wilson 95% range, the likely true rate. */
  low: number | null;
  high: number | null;
}

/** GET /api/explore/search-summary?weeks=12|N|all&source=all|user|agent (`services/search_summary.py`). */
export interface SearchSummary {
  /** The weeks asked for; null for all time. */
  weeks: number | null;
  /** Monday (UTC) the window starts on: N-1 weeks before this one, or the first application's week. */
  window_start: string;
  source: "all" | "user" | "agent";
  applied: number;
  /** The mean over every week of `series`. */
  applied_per_week: number;
  /** Of `applied`. */
  heard_back: RateCount;
  /** Reached interviewing or later, of `heard_back.count`. */
  interview: RateCount;
  /** Of `interview.count`. */
  offer: RateCount;
  /** Dated replies only; the days are null while `replies` is under `min_replies_for_timing`. */
  time_to_hear_back: {
    replies: number;
    median_days: number | null;
    p25_days: number | null;
    p75_days: number | null;
  };
  /** Of the applications sent at least `after_days` ago, those with no event since. */
  quiet: RateCount & { after_days: number };
  /** Tailored minus base match score, medians over the applications tailored in the window. */
  score_gain: { n: number; median: number | null; median_base: number | null; median_tailored: number | null };
  /** Most applied first; both shares are of `applied`. */
  by_resume: {
    slug: string;
    name: string | null;
    color_hue: number | null;
    applied: number;
    heard_back: RateCount;
    interview: RateCount;
  }[];
  /** Every week of the window, zero-filled; a reply counts in the week it came. */
  series: { week_start: string; applied: number; replies: number }[];
  /** Replies the migration backfilled: counted in `heard_back`, in no week of `series`. */
  undated_replies: number;
  min_rate_n: number;
  min_replies_for_timing: number;
}

// --- Today (/api/today) -----------------------------------------------------

/** A dated step of "Where this job is", in ladder order; a step the data cannot date is absent. */
export interface TodayStep {
  key: "saved" | "gaps_closed" | "tailored" | "applied" | "interviewing" | "offered" | "proposed";
  at: string;
}

/** `services/today.py` NEXT_UP_ORDER: an offer awaiting your answer, the best ready PDF, a proposal's question. */
export interface TodayNextUp {
  kind: "offer" | "pdf_ready" | "needs_you";
  job_id: UUID;
  application_id: UUID | null;
  /** Set only for `needs_you`. */
  proposal_id: UUID | null;
  title: string | null;
  company: string | null;
  location: string | null;
  /** As posted (lib/money.ts `formatPay` words and converts it); null when the job states no pay. */
  pay: { min: number | null; max: number | null; currency: string | null; period: string | null } | null;
  base_resume: { slug: string; name: string | null; color_hue: number | null } | null;
  score: number | null;
  /** The application's status, or the proposal's for `needs_you`. */
  status: ApplicationStatus | ProposalStatus | null;
  /** `needs_you` only: the filer and what it asks. */
  proposed_by: string | null;
  reason: string | null;
  steps: TodayStep[];
}

/** One non-zero count; a zero count is left out of `also` and `more`. */
export interface TodayCount {
  key: "to_approve" | "to_check" | "quiet" | "gaps_to_close" | "health_check";
  count: number;
  href: string;
  /** `quiet`: the follow-up window. */
  days?: number;
  /** `gaps_to_close`: unanswered gaps across the `count` jobs. */
  gaps?: number;
}

/** GET /api/today?tz=<IANA>&utc_offset_minutes=<east positive> (send both). */
export interface TodayResponse {
  /** The local date the week ends on. */
  today: string;
  /** The zone used: the IANA name, else "UTC+05:30" from the offset, else "UTC". */
  time_zone: string;
  next_up: TodayNextUp | null;
  also: TodayCount[];
  more: TodayCount[];
  week: {
    /** Seven local days, oldest first; the last is `today`. */
    days: { date: string; applied: number }[];
    applied: number;
    replies: number;
    interviews: number;
    applied_all_time: number;
  };
}

interface AutofillKindRate {
  kind: string;
  success: number;
  failure: number;
  success_rate: number | null;
}

interface AutofillTopFailure {
  signature_hash: string;
  label: string;
  kind: string;
  host: string;
  rule_id: string | null;
  options_sample: string[];
  seen_count: number;
  outcomes: Record<string, number>;
  failure_share: number;
  score: number;
}

interface AutofillNoveltyPoint {
  at: string;
  new: number;
  total: number;
  share: number;
}

export interface AutofillTelemetrySummary {
  totals: { signatures: number; observations: number; hosts: number };
  by_kind: AutofillKindRate[];
  top_failures: AutofillTopFailure[];
  novelty: AutofillNoveltyPoint[];
  saturated: boolean;
  recommendation: string;
}

export interface BaseSummaryRow {
  slug: string;
  display_name: string | null;
  health_score: number | null;
  health_grade: string | null;
  avg_base_ats: number | null;
  n_scored: number;
  avg_lift: number | null;
  n_tailored: number;
  applications_total: number;
  applications_submitted: number;
  in_flight: number;
  last_activity: string | null;
}

export type BuildAreaStatus = "missing" | "in_kb" | "ported";

export type BuildAreaTier = "build" | "surface" | "wording";

/**
 * The gap categories that can reach build_areas. The other two in
 * gap_analysis.py cannot: weak_coverage is requirement-kind and
 * title_structure is title/summary/gate/format-kind, and build_areas keeps
 * only skill-kind gaps.
 */
export type BuildAreaCategory =
  | "missing_skills"
  | "mirror_wording"
  | "dual_place"
  | "resurface_recent"
  | "adjacent";

export interface BuildAreaRow {
  skill: string;
  n_jobs: number;
  avg_potential_points: number;
  requirement_level: string | null;
  status: BuildAreaStatus;
  kb_points: number;
  kb_entities: string[];
  tier: BuildAreaTier;
  /** Most-common effective gap category; null on wording-only rows. */
  category: BuildAreaCategory | null;
  /** Plain words for `category`, owned by the server. Absent on a backend that predates it. Render this, never `category`. */
  category_label?: string | null;
  /** Distinct jobs where this skill gapped only as a hygiene wording mismatch. */
  wording_jobs: number;
}

export interface KBProfileOut {
  contact: Partial<ContactInfo>;
  summary: string;
  skills: SkillGroup[];
  notes: string;
  updated_at: string;
}

export interface SyncItemOut {
  tier: string;
  section: string;
  entity_id: UUID | null;
  entity_proposal: Record<string, unknown> | null;
  matched_point_id: UUID | null;
  text: string;
}

export interface SyncStatus {
  items: SyncItemOut[];
  skills_new: string[];
  /** Tier tallies. The backend owns the vocabulary (the wire shape is an open
   *  map), so the index signature stays for keys it may grow later — but these
   *  five are REQUIRED: `kb_base_sync.classify` builds the dict with all five
   *  literal keys on every call, zero-filled. Marking them optional would be a
   *  lie that forces a `?? 0` at every read site.
   *
   *  `recorded_drift` (drift the KB already documents) is always present but
   *  is NOT actionable, and must never be added into the pill's count. */
  counts: {
    in_sync: number;
    drift: number;
    recorded_drift: number;
    new: number;
    skills_new: number;
  } & Record<string, number>;
  /** Null until the first sync. */
  last_kb_synced_at: string | null;
  /** False when the embedder could not run: every bullet then reads as new, nothing was matched. */
  compared_wording: boolean;
}

export interface SyncResult {
  /** Draft bullets written. */
  created: number;
  /** Career history items this sync created (a new job, school, certification
   *  or other-section item). Items that bring bullets are counted here too. */
  items_added: number;
  drifted: number;
  skipped: Record<string, unknown>[];
  /** CATEGORY names, one per category written. NEVER count these — two new
   *  skills in one category appear here once. Use `skills_added`. */
  skills: string[];
  /** The individual skills that landed in the profile. */
  skills_added: string[];
  last_kb_synced_at: string | null;
  /** False when the embedder could not run: every bullet then reads as new, nothing was matched. */
  compared_wording: boolean;
}

export interface KBProfilePatch {
  contact?: ContactInfo;
  summary?: string;
  skills?: SkillGroup[];
  notes?: string;
}

export interface BaseResumePortProjectResult extends RenderNoted {
  target_slug: string;
  project_index: number;
  /**
   * The port is committed before the target is re-rendered, so a render
   * failure comes back here (the project landed; only the PDF is stale)
   * instead of failing the call — never set together with `render_note`.
   */
  render_error?: string | null;
}

export interface TopSkillRow {
  skill_name: string;
  skill_category: string | null;
  n: number;
  n_required: number;
  n_preferred: number;
  n_mentioned: number;
  pct_jobs: number;
  rank: number;
  rank_percentile: number;
  tier: "top" | "below";
  bucket: "core" | "preferred_top" | "below_threshold";
  low_sample: boolean;
}

interface TopSkillsMeta {
  total_jobs: number;
  total_skills: number;
  top_count: number;
  top_tier_fraction: number;
}

export interface TopSkillsResponse {
  meta: TopSkillsMeta;
  top: TopSkillRow[];
  rest: TopSkillRow[];
}

export interface HeatmapRow {
  skill_name: string;
  role_category: string;
  pct_jobs: number;
  /** Jobs in the role that ask for the skill, of `of`, the role's jobs: a share shows from MIN_RATE_N in `of`. */
  count: number;
  of: number;
}

export interface FitDistributionRow {
  base_resume: string;
  /** The resume's own name; null for a slug with no row. Absent on a backend that predates it. */
  display_name?: string | null;
  buckets: Record<string, number>;
  n: number;
  low_sample: boolean;
}

export interface RoleMixRow {
  week_start: string;
  role_category: string;
  count: number;
}

/** `/api/explore/gap-frequency` — skill gaps ranked by how often they recur. */
export interface GapFrequencyRow {
  skill: string;
  n_jobs: number;
  avg_potential_points: number;
  category: string | null;
  /** Plain words for `category`, owned by the server. Absent on a backend that predates it. Render this, never `category`. */
  category_label?: string | null;
  requirement_level: string | null;
  low_sample: boolean;
}

/** `/api/explore/ats-over-time` — weekly avg composite split by phase + role. */
export interface AtsOverTimeRow {
  week_start: string;
  phase: "base" | "tailored";
  role_category: string;
  avg_composite: number;
  n: number;
  low_sample: boolean;
}

/**
 * `/api/explore/tailoring-lift` — per-role base→tailored composite lift, plus one
 * overall row where `role_category === "all"`.
 */
export interface TailoringLiftRow {
  role_category: string;
  n: number;
  avg_base: number;
  avg_tailored: number;
  avg_lift: number;
  low_sample: boolean;
}

export interface Referral {
  id: UUID;
  company: string;
  careers_url: string;
  contact_name: string | null;
  notes: string | null;
  applications_count: number;
  created_at: string;
  updated_at: string;
}

export interface ReferralCreate {
  company: string;
  careers_url: string;
  contact_name?: string | null;
  notes?: string | null;
}

export interface ReferralPatch {
  company?: string;
  careers_url?: string;
  contact_name?: string | null;
  notes?: string | null;
}

export function baseResumeLabel(
  slug: string,
  rows?: readonly Pick<BaseResumeSummary, "slug" | "display_name">[] | null,
): string {
  // The resume's own name when a list is at hand (useBaseResumeLabel reads the
  // cached one). The slug's words only while it loads, after it fails, or for a
  // resume no list has (a deleted one): never blank, never the raw slug.
  const name = rows?.find((r) => r.slug === slug)?.display_name?.trim();
  return name || humanizeSlug(slug);
}

type TemplateStatus = "draft" | "ready";

type TemplateEngine = "latex" | "typst";

export interface TemplateSummary {
  id: string;
  display_name: string | null;
  status: TemplateStatus;
  is_default: boolean;
  origin: string;
  /** Render engine for `source`: LaTeX (Jinja→pdflatex) or Typst (raw .typ). */
  engine: TemplateEngine;
  /**
   * False when this template's engine cannot run on the backend host (a LaTeX
   * template with no pdflatex). Still pickable: a render through it falls back
   * to a Typst template and the response says so in `render_note`.
   */
  engine_available: boolean;
  last_error: string | null;
  validated_at: string | null;
  updated_at?: string | null;
  /**
   * Whether the compiled sample survives a strict PDF text extractor with word
   * boundaries intact. `null` = not yet checked; `false` = an ATS may read
   * joined words ("DataScientist").
   */
  parse_certified: boolean | null;
  /**
   * Set = hidden from the gallery and the browse dialog. Not a delete: the
   * template still renders anything already pointed at it, which is why the
   * shared `["templates"]` query asks for archived rows too — a selection that
   * was archived after the fact must still resolve to a name and its fmt keys.
   */
  archived_at?: string | null;
  /** `fmt.*` variables the template's source opts into (empty when none). */
  supported_fmt_keys: string[];
  /** Partial `fmt.*` overlay baked into the theme; merged under resume values. */
  default_formatting: Record<string, unknown> | null;
}

export interface TemplateDetail extends TemplateSummary {
  source: string;
}

export interface TemplateValidationResult {
  ok: boolean;
  error: string | null;
}

/** Deterministic ATS engine subscores (0–1 floats) + gate/format diagnostics. */
interface AtsSubscores {
  keyword: number;
  placement_recency: number;
  semantic_fit: number;
  title: number;
  format: number;
  title_tier: string;
  gate_warnings: string[];
  format_flags: string[];
  jd_skills_extracted_count?: number;
  jd_skills_matched_count?: number;
  coverage_ratio?: number;
  coverage_warning?: string | null;
}

/** Per-JD-skill diagnostic row from `skill_table_json`. */
export interface AtsSkillRow {
  jd_skill: string;
  canonical: string;
  requirement_level: string;
  matched: boolean;
  match_form: string | null;
  match_credit: number;
  matched_term: string | null;
  placement: string | null;
  last_used: string | null;
  recency_weight: number | null;
  contribution: number;
  fix_hint: string | null;
  evidence_entries: string[];
}

export interface AtsScore {
  id: UUID;
  job_id: UUID;
  target_type: string;
  target_id: string;
  application_id: UUID | null;
  phase: string;
  composite: number;
  subscores_json: AtsSubscores;
  skill_table_json: AtsSkillRow[];
  config_version: string;
  engine_version: string;
  created_at: string;
  jd_skills_extracted_count?: number;
  jd_skills_matched_count?: number;
  coverage_ratio?: number;
  coverage_warning?: string | null;
}

interface AtsSkillDiffRow {
  jd_skill: string;
  before: AtsSkillRow | null;
  after: AtsSkillRow | null;
}

export interface AtsCompare {
  application_id: UUID;
  base: AtsScore;
  tailored: AtsScore;
  delta: {
    composite: number;
    subscores: Record<string, number>;
  };
  skill_diff: AtsSkillDiffRow[];
}

/**
 * Resolution vocabulary, mirroring `gap_analysis._ACTIONS`.
 *
 * `enable_entry` and `port_kb_point` pass structural references into
 * `payload` (see `EnableEntryPayload` / `PortKbPointPayload`); all others
 * pass string values (e.g. `add_keyword` passes `{keyword: string,
 * group_name: string}`).
 */
export type GapAction =
  | "add_keyword"
  | "user_input"
  | "attach_project"
  | "skip"
  | "enable_entry"
  | "port_kb_point"
  /**
   * "I can't confirm this": skip for the document plus a durable
   * user_cannot_confirm Career-KB record — never re-asked, never evidence.
   */
  | "cannot_confirm";

/** A concrete, server-canonical place on the resume a resolution can target. */
export type PlacementRef =
  | {
      section: "skills" | "experience" | "projects";
      section_key?: never;
      index_or_category: string | number;
    }
  | {
      section: "extra";
      /** Stable custom-section identity. */
      section_key: string;
      index_or_category: string | number;
    };

/**
 * Where an auto-resolution came from (`payload.provenance`, stamped by
 * `services/kb_resolver.auto_resolution_for_gap`). Present ONLY on
 * system-proposed resolutions — a hand-made one has no provenance, which is
 * exactly how the diff endpoint tells `kb_auto` hunks from `user` hunks.
 */
export interface ResolutionProvenance {
  source: "kb_auto" | "library_auto" | "kb_profile" | "wording_auto";
  kb_point_id?: string;
  kb_entity_id?: string;
}

/**
 * One piece of the user's own evidence that the resolver found for a gap, in the
 * user's disabled resume entries or their Career KB (`gaps_json[].library_candidates`,
 * a FLAT list — `kind` discriminates). Every candidate has passed the deterministic
 * gate at existence level; `auto: true` ones passed it fully and already have a
 * stored resolution. `auto: false` ones are suggestions the server would REJECT as
 * `enable_entry`/`port_kb_point` (draft point, no literal match, or no canonical
 * target), so the UI routes them to the Answer box instead.
 */
export interface LibraryCandidate {
  kind: "disabled" | "kb_point" | "kb_tech" | "profile";
  /** Passed the full verification gate → pre-applied as a stored resolution. */
  auto: boolean;
  match_form: string;
  evidence_snippet?: string | null;
  /** `disabled` only: the base-resume entry, at its FULL-array index. */
  section?: "experience" | "projects" | null;
  index?: number | null;
  name?: string | null;
  /** `kb_point`/`kb_tech` only. */
  entity_id?: string | null;
  point_id?: string | null;
  title?: string | null;
  /** `kb_point` only; null when the target failed to canonicalize. */
  placement_target?: PlacementRef | null;
}

/** LLM enrichment (display-only helper text); null when enrichment was skipped or failed. */
interface GapEnrichment {
  suggested_wording: string | null;
  project_candidates: string[];
  elicitation_question: string | null;
  /**
   * Server-validated best guess at where this keyword should live. A missing skill's
   * suggestion is forced to `skills`; invalid targets are dropped to null. Fixed
   * sections and entry-style custom sections retain original/full-array indices;
   * custom targets also carry the stable section key (used as the section-level
   * sentinel for bullet-style sections).
   */
  suggested_placement?: PlacementRef | null;
}

export interface Gap {
  gap_id: string;
  kind: "skill" | "title" | "gate" | "format" | "summary" | "requirement";
  jd_skill?: string;
  requirement_level?: string;
  detail?: string;
  /**
   * Skill gaps only: a DETERMINISTIC estimate (0-100 composite scale) of the ATS
   * headroom this gap could recover. It is a COARSE UPPER BOUND (the gain if this row
   * were the SOLE driver of its subscore), not an exact promise — present as a
   * relative signal.
   */
  potential_points?: number;
  /**
   * mirror_wording skill gaps only: whether adding the literal JD token is pure
   * keyword hygiene (already full credit) or actually adds keyword credit.
   */
  score_effect?: "hygiene" | "adds_credit";
  /**
   * Skill gaps carry the full AtsSkillRow; title gaps `{tier}`; requirement gaps
   * `{coverage_score}`; gate/format/summary `{}`.
   */
  diagnostic: Partial<AtsSkillRow> & { tier?: string; coverage_score?: number };
  actions: GapAction[];
  enrichment: GapEnrichment | null;
  /** Verified evidence from the user's own library/KB. Absent when the resolver
   * found nothing or enrichment was skipped/failed (the pre-KB manual flow). */
  library_candidates?: LibraryCandidate[];
}

export interface GapCategory {
  key: string;
  title: string;
  description: string;
  gaps: Gap[];
}

interface GapsJson {
  base_composite: number;
  subscores: Record<string, number>;
  engine_version: string;
  config_version: string;
  /**
   * Skill-coverage signal (`services/ats/engine.py` `_calc_coverage_signal`,
   * copied by `services/gap_analysis.py`). Optional because a Docker backend
   * predating the field returns gaps_json without it — same reasoning as the
   * `tier` fallback on build-areas rows. `coverage_warning` is set when the
   * resume shows under a quarter of the job's skills, or the job names none;
   * it is the server's whole sentence, shown as is, and an empty gap list must
   * then NOT be shown as "no gaps found".
   */
  jd_skills_extracted_count?: number;
  jd_skills_matched_count?: number;
  coverage_ratio?: number;
  coverage_warning?: string | null;
  categories: GapCategory[];
}

export interface Resolution {
  gap_id: string;
  action: GapAction;
  payload: Record<string, unknown>;
}

/**
 * `payload.provenance` when the resolution was proposed by the KB resolver, else
 * null. Kept as a reader (not a typed payload field) because payloads are
 * action-shaped and pass through the UI untouched — the autosave sends back
 * exactly what the server stored, provenance included.
 */
export function resolutionProvenance(
  resolution: Resolution,
): ResolutionProvenance | null {
  const raw = resolution.payload?.provenance;
  if (typeof raw !== "object" || raw === null) return null;
  const source = (raw as { source?: unknown }).source;
  if (
    source !== "kb_auto" &&
    source !== "library_auto" &&
    source !== "kb_profile" &&
    source !== "wording_auto"
  ) {
    return null;
  }
  return raw as ResolutionProvenance;
}

/** Auto-resolved by the resolver (system-proposed, not user-made) and still live. */
export function isAutoResolved(resolution: Resolution | undefined): boolean {
  if (!resolution || resolution.action === "skip") return false;
  return resolutionProvenance(resolution) !== null;
}

export interface TailoringSession {
  id: UUID;
  job_id: UUID;
  base_resume: string;
  status: "open" | "tailored" | "superseded" | "abandoned";
  gaps_json: GapsJson;
  resolutions_json: Resolution[];
  user_prompt: string | null;
  application_id: UUID | null;
  base_ats_score_id: UUID | null;
  /**
   * Transient, non-persisted warning set by create_session when the base resume's
   * health score is low. Only ever populated on the create response — absent (or
   * null) on subsequent GETs/list calls.
   */
  health_warning?: string | null;
  /** Transient (GET, open sessions): why the frozen gaps no longer match the current base/JD. */
  stale_reason?: string | null;
  created_at: string;
  updated_at: string;
}

/**
 * One change between the base resume and the application's tailored copy
 * (`services/resume_diff.py`). `index` is the ENTRY index for bullet_* kinds —
 * the bullet's own position is not recorded, so a revert matches on text.
 * Extra-section content collapses to a single `extra_section_changed`, and
 * certifications diff as `bullet_*` under section "certifications".
 */
export interface ResumeDiffHunk {
  kind:
    | "summary_changed"
    | "contact_changed"
    | "bullet_added"
    | "bullet_removed"
    | "bullet_edited"
    | "entry_added"
    | "entry_removed"
    | "entry_enabled"
    | "entry_disabled"
    | "skills_group_changed"
    | "extra_section_added"
    | "extra_section_removed"
    | "extra_section_changed"
    | "extra_section_enabled"
    | "extra_section_disabled";
  section: string;
  index: number | null;
  before: unknown;
  after: unknown;
  /** kb_auto = the resolver's own evidence; user = a resolution you made; llm = the tailor's wording. */
  provenance: "kb_auto" | "user" | "llm";
}

export interface ResumeDiff {
  hunks: ResumeDiffHunk[];
  /** The tailoring session the provenance was attributed from; null when none exists. */
  session_id: UUID | null;
  /** The application's updated_at this diff was computed against: a revert is allowed only while it matches. */
  updated_at: string;
}

export type CoherenceIssue =
  | "fragment"
  | "tense"
  | "summary_mismatch"
  | "dangling";

export interface CoherenceFlag {
  locus: {
    kind: string | null;
    section: string | null;
    index: number | null;
    /** The changed text the proposal replaces — the apply-by-exact-match needle. */
    after: string | null;
  };
  issue: CoherenceIssue;
  proposal: string;
}

/**
 * A deterministic `resume_lint.rule_notes` finding, scoped to loci the
 * tailoring changed and with any defect already present in the base resume
 * suppressed (`coherence_check.py`). `proposal` is non-null only for the two
 * mechanical trailing-punctuation rules — everything else (duplicates,
 * sentence-like items) is read-only, since the fix is a judgment call.
 */
export interface HygieneFlag {
  locus: {
    kind: "hygiene";
    section: string | null;
    index: number | null;
    /** The raw offending source string — the apply-by-exact-match needle. */
    after: string | null;
  };
  /** Stable rule slug, e.g. "skills.trailing_punct". */
  rule: string;
  issue: string;
  why: string;
  how: string;
  label: string;
  proposal: string | null;
}

/**
 * A structural gate run against the tailored document (`resume_lint._gate_dict`,
 * `health_gates.gate_dates`/`gate_placeholders`). Read-only here — unlike the
 * base health report, coherence-check gates have no waive/unwaive affordance.
 */
export interface HealthGate {
  id: string;
  tier: "fatal" | "serious";
  status: "pass" | "fail" | "not_assessed";
  label: string;
  detail: string;
}

export interface CoherenceCheckResult {
  flags: CoherenceFlag[];
  hygiene: HygieneFlag[];
  gates: HealthGate[];
}

/** One gap answer the KB write-back skipped, with why (never silent). */
export interface KBWritebackSkip {
  gap_id: string;
  skill: string | null;
  reason: "too_short" | "wrong_section" | "no_entity_match" | "duplicate" | "profile_owned_elsewhere";
  /** Server-composed sentence, e.g. "no Career KB entity titled “Acme Corp”". */
  detail: string;
}

export interface TailorResult {
  session: TailoringSession;
  /** Null when the post-tailor compare failed — tailoring itself succeeded; see compare_error. */
  compare: AtsCompare | null;
  compare_error: string | null;
  /** Gap answers not saved to the Career KB, rendered as a quiet note. */
  kb_writeback_skips: KBWritebackSkip[];
}

export interface ExploreCountRow {
  key: string;
  count: number;
}
interface ExploreSkillCountRow {
  skill_name: string;
  n: number;
}
interface ExplorePayByRoleRow {
  role_category: string;
  n: number;
  avg_min: number | null;
  avg_max: number | null;
  /** How many of the `n` jobs were posted in another currency and converted (shown with "≈"). */
  converted_count: number;
  posted_currencies: string[];
}
/** Yearly pay by role in your home currency (`explore_overview._pay_by_role`): numbers, worded by lib/money.ts. */
export interface ExplorePayByRole {
  currency: string;
  /** The ECB rate date, when any pay was converted. */
  rate_date: string | null;
  min_jobs: number;
  roles: ExplorePayByRoleRow[];
  /** Roles with fewer than `min_jobs` jobs that list pay. */
  hidden_roles: { role_category: string; n: number }[];
  converted_count: number;
  /** The converted jobs by the currency they were posted in. */
  posted_currencies: ExploreCountRow[];
  /** Jobs left out: their currency has no rate, or they name none. */
  unconverted: number;
}
export interface ExploreOverview {
  meta: {
    total_jobs: number;
    since: string | null;
    role_category_count: number;
    salary_year_avg_min: number | null;
    salary_year_avg_max: number | null;
    salary_year_currency: string | null;
    salary_mixed_currencies: boolean;
    jobs_with_salary: number;
    jobs_without_salary: number;
  };
  role_mix: ExploreCountRow[];
  level_breakdown: ExploreCountRow[];
  work_mode: ExploreCountRow[];
  top_required_skills: ExploreSkillCountRow[];
  pay_by_role: ExplorePayByRole;
  salary_by_currency: ExploreCountRow[];
  locations: ExploreCountRow[];
  countries: ExploreCountRow[];
  work_auth: { opt: ExploreCountRow[]; sponsorship: ExploreCountRow[] };
  /** Server-worded insights. One that names pay carries it as `amount` in `currency` (your home currency,
   * converted pay compared: `explore_overview._best_paying_signal`), worded here; `converted` adds "≈". */
  signals: {
    title: string;
    detail: string;
    currency?: string | null;
    amount?: number | null;
    converted?: boolean;
  }[];
}

// ---------------------------------------------------------------------------
// Resume version control

export type ResumeVersionSource =
  | "create"
  | "form_edit"
  | "edit_ops"
  | "chat"
  | "tailor"
  | "import"
  | "restore";

export interface ResumeVersion {
  id: UUID;
  resume_kind: "base" | "application";
  resume_key: string;
  version_number: number;
  parent_version_id: UUID | null;
  summary: string | null;
  source: ResumeVersionSource;
  source_ref: string | null;
  label: string | null;
  created_at: string;
}

export interface ResumeDiffChange {
  section: string;
  kind: "added" | "removed" | "modified";
  label: string;
  details?: string[];
}

export interface ResumeVersionDetail extends ResumeVersion {
  snapshot: ResumeData;
  diff: ResumeDiffChange[];
}

/**
 * POST /restore answers with the new version. A base restore re-renders the
 * PDF, so it carries the note; an application restore renders nothing (the
 * PDF comes on an explicit Render) and leaves it null. The restore is
 * committed before that render, so a render failure comes back as
 * `render_error` (the restore landed; only the PDF is stale) instead of
 * failing the call — the two are alternatives, never both.
 */
export type ResumeVersionRestoreResult = ResumeVersion &
  RenderNoted & { render_error?: string | null };

// ---------------------------------------------------------------------------
// Chat

export interface ChatSelection {
  /** Reference kind; missing = legacy resume-path chip. */
  kind?: "resume" | "kb_entity";
  section?: string;
  index?: number | null;
  bullet_index?: number | null;
  /** Set when kind === "kb_entity". */
  entity_id?: UUID;
  label?: string;
}

export interface ChatContext {
  target_kind?: "base" | "application";
  target_key?: string;
  selections?: ChatSelection[];
  attachment_ids?: UUID[];
}

/**
 * The chat edit tool's card. A BASE edit re-renders, so the card is a render
 * response and carries the note (optional: cards persisted before it existed
 * have no such key); an application edit renders nothing and leaves it null.
 */
export interface ChatChangeCard extends RenderNoted {
  resume_kind: "base" | "application";
  resume_key: string;
  version_number: number;
  summary: string | null;
  ops_count: number;
}

export interface ChatProposal {
  target_kind: "base" | "application";
  target_key: string;
  project: ProjectEntry;
}

export interface ChatProposalOps {
  target_kind: "base" | "application";
  target_key: string;
  ops: Record<string, unknown>[];
  ops_count: number;
  summary: string | null;
}

export interface ChatCardState {
  status: "applied" | "discarded";
  at: string;
}

export interface ChatKbCapture {
  entity_id: UUID;
  entity_title: string;
  point_count: number;
}

export interface ChatMessage {
  id: UUID;
  role: "user" | "assistant" | "tool";
  content: string | null;
  tool_calls: unknown[] | null;
  tool_call_id: string | null;
  meta_json: {
    change_card?: ChatChangeCard;
    proposal?: ChatProposal;
    proposal_ops?: ChatProposalOps;
    kb_capture?: ChatKbCapture;
    card_state?: ChatCardState;
    selections?: ChatSelection[];
    attachment_ids?: UUID[];
    target_kind?: string;
    target_key?: string;
  } | null;
  created_at: string;
}

export interface ChatSessionSummary {
  id: UUID;
  title: string | null;
  context_json: ChatContext | null;
  created_at: string;
  updated_at: string;
}

export interface ChatSessionDetail extends ChatSessionSummary {
  messages: ChatMessage[];
}

export interface ChatAttachmentInfo {
  id: UUID;
  filename: string;
  mime: string | null;
  chars: number;
  preview: string;
}

export type ChatStreamEvent =
  | { type: "delta"; text: string }
  | { type: "tool_start"; name: string; arguments: Record<string, unknown> | null }
  | ({ type: "change_card"; message_id?: UUID } & ChatChangeCard)
  | ({ type: "proposal"; message_id?: UUID } & ChatProposal)
  | ({ type: "proposal_ops"; message_id?: UUID } & ChatProposalOps)
  | ({ type: "kb_capture"; message_id?: UUID } & ChatKbCapture)
  | { type: "message"; id: UUID; role: string }
  | { type: "done"; session_id: UUID }
  | { type: "error"; detail: string };

// ---------------------------------------------------------------------------
// Resume health check

type LintFindingType = "gate" | "fix" | "ask" | "note";
type LintSeverity = "critical" | "minor";
export type EvidenceLevel =
  | "direct"
  | "analogue"
  | "adjacent"
  | "implied"
  | "unaddressed";
type LintGateStatus =
  | "pass"
  | "fail"
  | "not_assessed"
  | "waived"
  | "ask";

interface LintLocation {
  section: string;
  index?: number | null;
  bullet_index?: number | null;
}

export interface LintFinding {
  id: string;
  type: LintFindingType;
  severity: LintSeverity;
  location: LintLocation;
  label: string;
  issue: string;
  why: string;
  how: string;
  level?: number | null;
  cost?: number;
  zone?: "hot" | "cold" | null;
  suggestion?: string | null;
  question?: string | null;
  ask_kind?: "measure" | "detail" | "reword" | null;
  measure_target?: string | null;
  alt_question?: string | null;
  evidence?: string[];
  gain?: number;
  source: string;
  /** Stable hash of the normalized text, present only for classifier findings. */
  content_hash?: string | null;
  classification_level?: EvidenceLevel | null;
  classification_source?: "llm" | "cache" | "override" | "dispute" | "deterministic" | null;
  classification_reason?: string | null;
  /** Raw source string this finding is about — exact-match needle. Backend already sends this. */
  subject?: string;
  /** Detector id, e.g. `skills.undemonstrated`. Backend already sends this. */
  rule?: string;
}

/** GET /api/resume-lint/wording: the user's word bank, Never flag list and the default bank. */
export interface WordingRead {
  cliche: string[];
  filler: string[];
  /** "Never flag": skipped whether the word is on the bank or a slip. */
  ignored: string[];
  defaults: { cliche: string[]; filler: string[] };
}

/** PUT /api/resume-lint/wording: all three lists, whole (the backend normalizes them again). */
export type WordingBody = Pick<WordingRead, "cliche" | "filler" | "ignored">;

/** POST /api/resume-lint/{kind}/{key}/dispute: the bullet re-read with the user's note. */
export interface DisputeResult {
  before: { level: EvidenceLevel; question: string | null };
  after: {
    level: EvidenceLevel;
    question: string | null;
    ask_kind: "measure" | "detail" | null;
  };
  /** Written by the backend from the before/after comparison, never by the model. */
  reply: string;
  /** A guarded rewrite carrying a fact from the note; it counts only once applied. */
  suggestion: string | null;
  content_hash: string;
}

/** GET /api/resume-lint/{kind}/{key}/disputes: disputes whose text is still in the resume. */
export interface StoredDispute {
  content_hash: string;
  location: LintLocation;
  label: string;
  text: string;
  note: string;
  reply: string;
  suggestion: string | null;
  /** The user said no number exists; number asks stay off until the dispute is reopened. */
  metric_unavailable: boolean;
  before: DisputeResult["before"];
  after: DisputeResult["after"];
  created_at: string;
}

export interface LintGate {
  id: string;
  tier: "fatal" | "serious";
  status: LintGateStatus;
  label: string;
  detail: string;
  why: string;
  fix_hint: string;
  waiver_reason?: string;
}

export interface LintScoreBreakdown {
  raw_score: number;
  e_hot: number | null;
  n_scoreable: number;
  capped_by: "fatal" | "serious" | null;
}

export interface LintReport {
  id: UUID;
  resume_kind: "base" | "application";
  resume_key: string;
  resume_version_number: number | null;
  score: number;
  grade: string;
  tier?: string | null;
  counts: Record<string, number>;
  gates?: LintGate[];
  findings: LintFinding[];
  model: string | null;
  created_at: string;
  /** Absent until the scoring lane lands — treat missing as false. */
  stale?: boolean;
  /** Absent until the scoring lane lands — treat missing as false. */
  insufficient_evidence?: boolean;
  /** Absent until the scoring lane lands. */
  score_breakdown?: LintScoreBreakdown | null;
  next_grade?: { grade: string; points: number } | null;
}

/** ---- Agent proposal ledger (auto-apply lane) ---- */

/** Mirrors backend PROPOSAL_STATUSES exactly; transitions are backend-guarded. */
const PROPOSAL_STATUSES = [
  "pending_review",
  "needs_decision",
  "accepted",
  "approved",
  "submitted",
  "rejected",
  "expired",
  "needs_human",
  "submission_uncertain",
] as const;

export type ProposalStatus = (typeof PROPOSAL_STATUSES)[number];

/** Thin job projection joined into proposal rows (backend JobSummary). */
interface ProposalJobSummary {
  id: UUID;
  ownership?: JobOwnership;
  source_url: string | null;
  apply_url?: string | null;
  company: string | null;
  title: string | null;
  role_category: string | null;
  level: string | null;
  employment_type: string | null;
  work_mode: string | null;
  location: string | null;
  salary_min: string | number | null;
  salary_max: string | number | null;
  work_authorization: string | null;
  opt_accepted: string | null;
  disqualifying_for_opt: boolean | null;
  created_at: string;
}

interface ProposalEvidenceItem {
  step: number;
  label: string;
  /** Relative under the proposal's evidence dir; serve via
   * GET /api/proposals/{id}/evidence/{basename}. */
  path: string;
  sha256: string;
  captured_at: string;
}

export interface Proposal {
  id: UUID;
  job_id: UUID;
  application_id: UUID | null;
  referral_id: UUID | null;
  status: ProposalStatus;
  fit_json: Record<string, unknown> | null;
  plan_json: Record<string, unknown> | null;
  evidence_json: ProposalEvidenceItem[] | null;
  reason: string | null;
  /** "you" (the web app's queue), an MCP client's clientInfo.name, or null
   *  (unknown). Optional: an older backend does not send it. */
  proposed_by?: string | null;
  expires_at: string | null;
  created_at: string;
  updated_at: string;
  job: ProposalJobSummary;
  /** Open-lane rows only (backend services/inbox_readiness.py); null in History. Optional: an
   *  older backend does not send it. */
  readiness?: {
    tailored: boolean | null;
    knockout: string | null;
    to_check: number;
    base_country?: string | null;
  } | null;
}

interface ProposalQAEntry {
  id: UUID;
  kind: string;
  prompt: string | null;
  answer: string | null;
  created_at: string | null;
}

export interface ProposalDetail extends Proposal {
  application: { id: UUID; status: string | null; pdf_ready: boolean } | null;
  qa_entries: ProposalQAEntry[];
}

export interface ProposalListResponse {
  items: Proposal[];
  total: number;
}

export interface ProposalSummary {
  since: string;
  new: number;
  ready: number;
  /** Every pending_review row (the To review lane's count). */
  to_review: number;
  /** Every accepted row (the Queued lane's count). */
  queued: number;
  needs_you: number;
  applied_this_week: number;
}

export interface AgentRun {
  id: UUID;
  automation: string;
  title: string;
  outcome: "ok" | "partial" | "failed";
  agent: string | null;
  on_bot?: boolean;
  finished_at: string;
  counts: Record<string, number>;
  digest: string;
  jobs: { id: UUID; title: string | null; company: string | null }[];
}

export interface AgentRunList {
  items: AgentRun[];
  /** On `/latest` only; empty with sync off. */
  refused_requests?: RefusedJobRequest[];
}

export interface RefusedJobRequest {
  id: UUID;
  job_id: UUID | null;
  reason: string;
  answered_at: string | null;
  job_company: string | null;
  job_title: string | null;
}

interface ProposalBulkResult {
  id: UUID;
  ok: boolean;
  status?: string | null;
  detail?: string | null;
}

export interface ProposalBulkResponse {
  results: ProposalBulkResult[];
}

interface ProposalCapStatus {
  max_per_day: number;
  reserved_last_24h: number;
  remaining: number;
}

export interface ProposalFunnel {
  captured: number;
  proposed: number;
  approved: number;
  submitted: number;
  interviewing: number;
  rejected_proposals: number;
  needs_human: number;
  expired: number;
  /** Present at runtime after Task 9; keep optional for cache/typing safety. */
  accepted?: number;
  cap?: ProposalCapStatus | null;
}

export interface CareerExportMetadata {
  name: "career";
  filename: "career.md";
  generated_at: string;
  content_hash: string;
  download_url: "/api/exports/career";
}

/** One market the app knows (`markets.yaml`); `key` is what the setting stores ("UK"). */
export interface MarketOption {
  key: string;
  label: string;
  /** ISO 3166-1 alpha-2, as jobs and base resumes store it ("GB"). */
  country_code: string | null;
  currency: string;
  /** "DMY" or "MDY". */
  date_format: string;
  offers_eeo: boolean;
  /** How its work-permit questions are worded: `us_visa` (with the US visa status), `uk` or `generic`
   *  (markets.yaml; lib/autofill-options.ts `permitQuestions` reads an unknown one as generic). */
  work_auth_vocab: string;
}

/** Where the user lives and applies (`GET/PUT /api/settings/market`). */
export interface MarketSettingResponse {
  key: "market";
  /** `market` is the old single market, kept equal to `home` for readers not moved yet. */
  value: { home: string; apply_in: string[]; market: string };
  /** Where the user lives: the home currency and date format. */
  home: string;
  /** Every market the user applies in, each once; at least one. */
  apply_in: string[];
  /** Present on GET only; PUT returns just the resolved values. */
  markets?: MarketOption[];
  /** The home market's currency. */
  currency: string;
  /**
   * Whether a VERIFIED voluntary-disclosure question set exists for the
   * home market. Never decide this client-side: the categories are not
   * interchangeable between countries.
   */
  offers_eeo: boolean;
}

/** How pay reads (`GET/PUT /api/settings/money`; docs/entities/money.md). */
export interface MoneySettings {
  /** ISO 4217 the user picked; null follows where they live. */
  home_currency: string | null;
  period: "year" | "month" | "hour";
  show_posted: boolean;
  hours_per_year: number;
}

export interface MoneySettingsResponse {
  key: "money";
  value: MoneySettings;
  /** Resolved: the picked currency, else the home market's, else the deployment's. */
  home_currency: string;
}

/** `GET /api/fx/rates`: ECB reference rates per euro; `date` null = none yet. */
export interface FxRatesResponse {
  base: string;
  date: string | null;
  rates: Record<string, number>;
  fetched_at: string | null;
  source: string;
  source_url: string;
}

/** `GET /api/version` — baked image identity plus the live alembic head. */
export interface VersionInfo {
  version: string;
  git_sha: string | null;
  schema_revision: string;
}

// ── Automations (GET /api/automations; backend/app/services/automations.py) ──
export type AutomationKind = "scheduled" | "attended" | "custom";
export type AutomationNeed = "maestro" | "email" | "browser" | "web";
export type AutomationCard = {
  id: string;
  title: string;
  summary: string;
  kind: AutomationKind;
  needs: AutomationNeed[];
  never: string | null;
  body: string;
  prompt: string;
};
export type AutomationCatalog = { cards: AutomationCard[] };

/** Where a filled answer came from: the What was submitted tab's pill (backend
 * `schemas/filled_answers.py` `Source`; hand-synced like the status vocabulary). */
export type AnswerSource =
  | "profile"
  | "resume"
  | "custom"
  | "written"
  | "inferred"
  | "you"
  | "upload";

export type AnswerFlagId =
  | "guessed_screening"
  | "ticked_everything"
  | "differs_from_profile"
  | "eeo_without_saved_answer";

/** A warn-only flag on one answer, with its one-line reason (written by the backend). */
export interface AnswerFlag {
  id: AnswerFlagId;
  reason: string;
}

export interface FilledField {
  question: string;
  section: string | null;
  required: boolean;
  /** A list for a multi-select; null for an EEO answer kept without consent. */
  answer: string | string[] | null;
  options_count: number | null;
  source: AnswerSource;
  /** For an upload: "resume" or "cover_letter". */
  slot: string | null;
  eeo: boolean;
  /** True when an EEO question was answered, even though its value is not kept. */
  eeo_answered: boolean;
  edited_by_you: boolean;
  /** The application's resume version, on a resume upload. */
  version: number | null;
  /** Where an inferred answer was read from ("From your work history."). */
  note?: string | null;
  flags: AnswerFlag[];
}

export interface FilledSection {
  section: string | null;
  fields: FilledField[];
}

export interface FilledStep {
  step: string | null;
  host: string | null;
  channel: "companion" | "agent";
  captured_at: string;
  sections: FilledSection[];
}

/** `GET /api/jobs/{id}/filled-answers`: per question the latest answer, by page and section.
 * With nothing recorded, `steps` is empty and the counts are zero. */
export interface FilledAnswers {
  job_id: string;
  host: string | null;
  pages: number;
  captured_at: string | null;
  flag_count: number;
  steps: FilledStep[];
}
