export type UUID = string;

/** Provenance lane: who initiated the row — the user's own browsing/tracking
 * ("user") or the agent-hunted auto-apply lane ("agent"). */
type ProvenanceSource = "user" | "agent";

export interface Job {
  id: UUID;
  raw_text: string;
  raw_text_hash: string;
  source_url: string | null;
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
  country: string | null;
  location_raw: string | null;
  salary_min: string | number | null;
  salary_max: string | number | null;
  salary_period: string | null;
  salary_currency: string | null;
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
}

export interface JobDetail {
  job: Job;
  application: Application | null;
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
  start_date: string;
  end_date?: string | null;
  enabled?: boolean;
  bullets: string[];
}

export interface EducationEntry {
  institution: string;
  degree: string;
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

export interface QAEntry {
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

export interface ModelOption {
  id: string;
  label: string;
  provider: string;
  tier: string;
  /** Built-in seed vs user-added via Sync +. Absent on older payloads = seed. */
  source?: "seed" | "extra";
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
}

export interface DiscoveredModel {
  id: string;
  label: string;
  provider: "openai" | "gemini";
  in_catalog: boolean;
}

export interface ModelSyncResult {
  models: DiscoveredModel[];
}

export interface OpenAIInfo {
  fast_model: string;
  smart_model: string;
  chat_model: string;
  api_key_configured: boolean;
  // The API never returns key material — only whether a key is configured.
  gemini_api_key_configured: boolean;
  model_options: ModelOption[];
  /** The OpenAI-compatible endpoint. A location, not a secret, so it is echoed. */
  base_url: string | null;
  /** When true, `model_options` is NOT exhaustive — we cannot enumerate what an
   *  arbitrary Ollama or vLLM host serves, so model ids become free text. */
  custom_endpoint: boolean;
  json_mode: "auto" | "on" | "off";
  /** Keyed by model id; only the three configured models appear. */
  capabilities: Record<string, CapabilityReport>;
}

/** GET /api/role-categories — the vocabulary, served from
 *  backend/app/services/ats/data/role_categories.yaml. Never duplicated here. */
export interface RoleCategory {
  key: string;
  label: string;
  reserved: boolean;
}

export interface JobPreferences {
  role_categories: string[];
  levels: string[];
  employment_types: string[];
  locations: string[];
  remote: "remote" | "hybrid" | "onsite" | "any" | null;
  min_salary: string | null;
  notes: string | null;
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
}

interface SetupStep {
  done: boolean;
  detail: Record<string, unknown>;
}

export interface SetupStatus {
  import_resumes: SetupStep;
  autofill: {
    done: boolean;
    readiness: number;
    groups: Record<string, { answered: number; answerable: number }>;
    blocking: string[];
  };
  job_preferences: SetupStep;
  persona: SetupStep;
  template: SetupStep;
  suggested_bases: { role_category: string; label: string }[];
  complete: boolean;
}

export interface BaseResumeSummary {
  slug: string;
  display_name: string | null;
  /** Target role. Always present; "unknown" means not declared yet. */
  role_category: string;
  pdf_rendered_at: string | null;
  updated_at: string;
  /** Set when the last auto-render failed — the PDF and its preview are the
   *  previous successful render. Drives the card's thumbnail state. */
  render_error: string | null;
  /** Hidden from pickers, still fully resolvable. */
  archived_at: string | null;
}

/** POST /api/kb/import — one action mints base resumes AND feeds the Career KB.
 *  `proposed` is true when the system guessed the role from resume content and
 *  the UI must ask the user to confirm; false means "unknown", i.e. undeclared
 *  rather than guessed. */
interface ImportedBase {
  slug: string;
  display_name: string;
  role_category: string;
  proposed: boolean;
  render_error: string | null;
}

interface SkippedImportFile {
  filename: string;
  reason: string;
}

export interface ImportReport {
  bases: ImportedBase[];
  skipped: SkippedImportFile[];
  kb: { entities_created: number; points_approved: number } | null;
}

export interface BaseResumeDetail extends BaseResumeSummary {
  data: ResumeData;
  pdf_path: string | null;
  tex_path: string | null;
  pdf_pages: number | null;
  formatting: Record<string, unknown> | null;
  template_id: string | null;
}

// ---------------------------------------------------------------------------
// Career Knowledge Base

export type KBEntityKind =
  | "experience"
  | "project"
  | "education"
  | "certification";

export type KBEntityStatus = "ongoing" | "completed" | "archived";
export type KBPointState = "draft" | "approved" | "retired";
type KBPointOrigin =
  | "manual"
  | "ingested"
  | "chat"
  | "consolidated"
  | "mcp"
  | "gap_elicitation";

export interface KBEntityCreate {
  kind: KBEntityKind;
  title: string;
  org?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  status?: KBEntityStatus;
  detail?: Record<string, unknown>;
  notes?: string | null;
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
}

export interface KBPointCreate {
  text: string;
  tags?: string[];
}

export interface KBPointPatch {
  text?: string | null;
  state?: KBPointState | null;
  tags?: string[] | null;
  entity_id?: UUID | null;
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
}

export interface KBPointOut {
  id: UUID;
  entity_id: UUID;
  text: string;
  state: KBPointState;
  origin: KBPointOrigin;
  origin_detail?: string | null;
  source_document_id: UUID | null;
  tags: string[];
  merge_sources: KBMergeSource[] | null;
  approved_at: string | null;
  created_at: string;
  updated_at: string;
  usage: KBUsageOut[];
}

interface KBMergeSource {
  resume_key: string;
  section: string;
  text: string;
}

export interface KBDocumentOut {
  id: UUID;
  filename: string;
  mime: string | null;
  size_bytes: number;
  ingest_status: string;
  ingest_summary: string | null;
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
  document_count: number;
  last_activity: string;
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
    interview_rate: number | null;
  };
  status_counts: Record<string, number>;
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

export interface KBProfilePatch {
  contact?: ContactInfo;
  summary?: string;
  skills?: SkillGroup[];
  notes?: string;
}

export interface BaseResumePortProjectResult {
  target_slug: string;
  project_index: number;
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
}

export interface FitDistributionRow {
  base_resume: string;
  buckets: Record<string, number>;
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
  requirement_level: string | null;
}

/** `/api/explore/ats-over-time` — weekly avg composite split by phase + role. */
export interface AtsOverTimeRow {
  week_start: string;
  phase: "base" | "tailored";
  role_category: string;
  avg_composite: number;
  n: number;
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
}

/** @deprecated Base resumes are user-created; there is no fixed list.
 *  Kept only as the acronym table for `baseResumeLabel`. */
const SLUG_ACRONYMS: Record<string, string> = {
  ai_ml_engineer: "AI/ML Engineer",
  bi_developer: "BI Developer",
  mlops_engineer: "MLOps Engineer",
};

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

export function baseResumeLabel(slug: string): string {
  // Base resumes are user-created with arbitrary slugs. This used to look up a
  // hardcoded 5-entry list, so ANY resume outside it (data_scientist_new,
  // business_analyst, example, ...) rendered as a raw slug. Prefer the row's
  // display_name where the caller has it; this is the fallback.
  if (SLUG_ACRONYMS[slug]) return SLUG_ACRONYMS[slug];
  return slug
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
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
  | "port_kb_point";

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
   * JD-comprehension signal (`services/gap_analysis.py`). Optional because a
   * Docker backend predating the field returns gaps_json without it — same
   * reasoning as the `tier` fallback on build-areas rows. When
   * `coverage_warning` is set, the engine recognised too little of the posting
   * for the gap list to mean anything, and an empty list must NOT be shown as
   * "no gaps found".
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

export interface CoherenceCheckResult {
  flags: CoherenceFlag[];
}

export interface TailorResult {
  session: TailoringSession;
  /** Null when the post-tailor compare failed — tailoring itself succeeded; see compare_error. */
  compare: AtsCompare | null;
  compare_error: string | null;
}

export interface ExploreCountRow {
  key: string;
  count: number;
}
interface ExploreSkillCountRow {
  skill_name: string;
  n: number;
}
interface ExploreSalaryByRole {
  role_category: string;
  currency: string | null;
  n: number;
  avg_min: number | null;
  avg_max: number | null;
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
  salary_by_role: ExploreSalaryByRole[];
  salary_by_currency: ExploreCountRow[];
  locations: ExploreCountRow[];
  countries: ExploreCountRow[];
  work_auth: { opt: ExploreCountRow[]; sponsorship: ExploreCountRow[] };
  signals: { title: string; detail: string }[];
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

export interface ChatChangeCard {
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
  source: string;
  /** Stable hash of the normalized text, present only for classifier findings. */
  content_hash?: string | null;
  classification_level?: EvidenceLevel | null;
  classification_source?: "llm" | "cache" | "override" | "deterministic" | null;
  classification_reason?: string | null;
}

export interface LintGate {
  id: string;
  tier: "fatal" | "serious";
  status: LintGateStatus;
  label: string;
  detail: string;
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
  source_url: string | null;
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
  expires_at: string | null;
  created_at: string;
  updated_at: string;
  job: ProposalJobSummary;
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

/** Which market the user applies in (`GET/PUT /api/settings/market`). */
export interface MarketSettingResponse {
  key: string;
  value: { market: string };
  /** Present on GET only; PUT returns just the resolved values. */
  supported: { key: string; label: string; currency: string; offers_eeo: boolean }[];
  currency: string;
  /**
   * Whether a VERIFIED voluntary-disclosure question set exists for the
   * selected market. Never decide this client-side — the categories are not
   * interchangeable between countries.
   */
  offers_eeo: boolean;
}
