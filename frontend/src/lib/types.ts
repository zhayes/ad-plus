/** DTOs mirroring app/settings_server.py — change here first. */

export interface SessionSummary {
  id: string;
  path: string;
  title: string;
  updated: number;
  bytes: number;
  running?: boolean;
}

export interface QuoteLine {
  tool: string;
  label: string;
  usd: number;
  unit_usd?: number;
  count?: number;
  seconds?: number;
  status?: "estimated" | "free" | "quote_required" | "unknown";
}

export interface Quote {
  decision?: { comment?: string; by?: string; at?: string };
  id: string;
  project_id: string;
  status: "pending" | "approved" | "rejected" | "timeout";
  headline: string;
  currency: "USD";
  total_usd: number;
  low_usd: number;
  high_usd: number;
  eta_seconds: number;
  assumptions?: string[];
  line_items: QuoteLine[];
  created_at: string;
}

export interface Approval {
  id: string;
  project_id: string;
  stage: string;
  status: "pending" | "approved" | "rejected" | "timeout";
  note?: string;
  artifacts?: string[];
  previews?: string[];
  created_at: string;
}

export interface Job {
  id: string;
  project_id: string;
  kind: "render" | "preview" | "tool" | "proposal";
  status: "queued" | "running" | "done" | "failed" | "cancelled" | "interrupted";
  stage?: string;
  progress: number;
  frames_done: number;
  frames_total: number;
  started_at: string;
  finished_at?: string | null;
  elapsed_seconds?: number;
  output?: string | null;
  error?: string | null;
  composition?: string;
  log_tail?: string[];
  retry_of?: string | null;
  cost_usd?: number;
}

export interface AppConfig {
  output_dir: string;
  default_output_dir: string;
  configured: boolean;
  app_data: string;
  notifications: { approvals: boolean; done: boolean; failed: boolean };
  daily_budget_usd: number;
}

export interface Artifact {
  path: string;
  name: string;
  kind: "video" | "image" | "audio" | "doc" | "code";
  bytes?: number;
}

export type TimelineKind = "think" | "tool";

export interface TimelineStep {
  id: string;
  kind: TimelineKind;
  label: string;
  detail?: string;
  seconds?: number;
  running?: boolean;
  ok?: boolean;
}

export interface Turn {
  id: string;
  role: "user" | "assistant";
  text: string;
  timeline?: TimelineStep[];
  streaming?: boolean;
}

export interface WsEvent {
  type: string;
  [key: string]: unknown;
}

export interface KeyInfo {
  name: string;
  label: string;
  configured: boolean;
  masked: string;
  capabilities: string[];
  unlocks: number;
  instructions: string;
  in_keychain: boolean;
}

export interface CapabilityRow {
  capability: string;
  configured: number;
  total: number;
}

export interface Snapshot {
  keys: KeyInfo[];
  matrix: {
    runtimes: Record<string, boolean>;
    capabilities: CapabilityRow[];
  };
  pi: { executable?: string; version?: string; running?: boolean };
  app_data: string;
}

export interface ProviderInfo {
  provider: string;
  env: string;
  configured: boolean;
  masked: string;
}

export interface BootstrapInfo {
  ready: boolean;
  has_model: boolean;
  models: { provider: string; model: string }[];
  first_run: boolean;
  version: string;
  app_data: string;
}

export interface ProviderEntry {
  provider: string;
  label: string;
  env: string;
  configured: boolean;
  masked: string;
}

export interface PiIntegration {
  config: string;
  servers: { name: string; exposure: string; timeout: number; cwd: string }[];
  trust: { approve_flag: boolean; note: string };
}

export interface PiStatus {
  version: { available: boolean; stdout: string };
  models: { available: boolean; stdout: string };
  mcp?: { stdout?: string };
}

/* ---------------------------------------------------------------- projects */

export type ProjectStatus =
  | "draft"
  | "briefing"
  | "quoted"
  | "storyboard"
  | "producing"
  | "review"
  | "delivered"
  | "archived";

export interface ProjectBrief {
  product?: string;
  audience?: string;
  tone?: string;
  description?: string;
  cta?: string;
  selling_points?: string[];
  [key: string]: unknown;
}

export interface ProjectSummary {
  id: string;
  title: string;
  status: ProjectStatus;
  platform: string;
  aspect: string;
  duration_s: number;
  quality_tier: string;
  cover: string | null;
  updated: number;
  updated_at?: string | null;
  version_count: number;
  current_version: string | null;
  current_version_label: string | null;
  pending_count: number;
  cost_usd: number;
  brand_id: string | null;
  route_label?: string;
  stage_label?: string;
  next_action?: string;
}

export interface ProjectRecord {
  id: string;
  project_id: string;
  title: string;
  status: ProjectStatus;
  platform: string;
  aspect: string;
  duration_s: number;
  quality_tier: string;
  pipeline_type?: string;
  brand_id?: string | null;
  persona_id?: string | null;
  product_id?: string | null;
  format_id?: string | null;
  route?: RouteOption | null;
  brief?: ProjectBrief;
  current_version_id?: string | null;
  cover?: string | null;
  created_at?: string;
  updated_at?: string;
}

export interface Shot {
  id: string;
  index: number;
  role: "hook" | "build" | "proof" | "cta" | string;
  description: string;
  framing?: string;
  movement?: string;
  transition_in?: string;
  transition_out?: string;
  on_screen_text?: string;
  narration?: string;
  status: "planned" | "generating" | "ready" | "approved" | "needs_rework" | string;
  locked: boolean;
  preview?: string | null;
  start_s: number;
  end_s: number;
  duration_s: number;
  take_count?: number;
  cost_usd?: number;
  production_method?: string;
  persona_id?: string | null;
  product_id?: string | null;
  asset_refs?: Record<string, unknown>;
  generation_spec?: Record<string, unknown>;
  shot_language?: Record<string, unknown>;
  timeline?: Record<string, unknown>;
}

export interface RenderInfo {
  path?: string | null;
  poster?: string | null;
  bytes?: number;
  width?: number;
  height?: number;
  duration_s?: number;
}

export interface VersionSummary {
  id: string;
  label: string;
  status: "draft" | "producing" | "review" | "approved" | "superseded" | string;
  created_at?: string;
  shots_count: number;
  duration_s: number;
  cost_usd: number;
  render?: RenderInfo | null;
  has_review?: boolean;
  brand?: string | null;
}

export interface Version extends VersionSummary {
  project_id: string;
  parent_id?: string | null;
  shots: Shot[];
  review?: unknown;
  brand_snapshot?: Brand | null;
}

export interface Brand {
  id: string;
  name: string;
  logo?: string | null;
  colors?: string[];
  font_cn?: string;
  font_en?: string;
  tone?: string[];
  voice?: Record<string, unknown>;
  banned_words?: string[];
  default?: boolean;
  created_at?: string;
  updated_at?: string;
}


export type PersonaKind = "photo" | "video" | "avatar";
export type PersonaStatus = "draft" | "ready" | "archived";

export interface PersonaRights {
  ai_allowed: boolean;
  consent: boolean;
  commercial_use: boolean;
  note?: string;
  expires_at?: string;
}

export interface PersonaCandidate {
  index: number;
  path: string;
  filename: string;
}

export interface PersonaGeneration {
  candidates: PersonaCandidate[];
  prompt: string;
  model: string;
  aspect_ratio: string;
  reference_used: boolean;
  cost_usd: number;
}

export interface Persona {
  id: string;
  name: string;
  kind: PersonaKind;
  status: PersonaStatus;
  source_path?: string | null;
  preview_path?: string | null;
  asset_paths?: string[];
  description?: string;
  gender?: string;
  age_range?: string;
  look?: string;
  wardrobe?: string;
  scene?: string;
  tags?: string[];
  voice?: Record<string, unknown>;
  rights: PersonaRights;
  providers?: Record<string, string>;
  created_at?: string;
  updated_at?: string;
}



export interface ProductCompositeTake {
  id: string;
  project_id: string;
  version_id: string;
  shot_id: string;
  product_id?: string | null;
  status: "ready" | "blocked" | "done" | "failed" | string;
  blockers: string[];
  warnings: string[];
  input?: Record<string, unknown>;
  output_path?: string;
  label_qa?: { verdict: string; expected?: string; actual?: string; detail?: string };
  result?: { success?: boolean; error?: string | null; output?: string | null; label_qa?: Record<string, unknown> } | null;
}

export interface DigitalHumanTake {
  id: string;
  project_id: string;
  version_id: string;
  shot_id: string;
  profile_id: string;
  persona_id?: string | null;
  product_id?: string | null;
  status: "ready" | "blocked" | "failed" | "running" | string;
  blockers: string[];
  warnings: string[];
  profile?: ModelProfile;
  input?: Record<string, unknown>;
  output_path?: string;
  result?: Record<string, unknown> | null;
  created_at?: string;
  updated_at?: string;
}


export interface FormatPreset {
  id: string;
  label: string;
  pipeline: string;
  route: string;
  duration_s: number;
  aspect: string;
  description: string;
  required_capabilities: string[];
  best_for: string;
}

export interface ModelProfile {
  id: string;
  label: string;
  provider: string;
  capability: string;
  kind: string;
  region: string;
  requires: string[];
  model?: string;
  resolutions: string[];
  durations: number[];
  native_audio: boolean;
  lip_sync?: boolean;
  reference_images?: number;
  supports: string[];
  cost_note?: string;
  configured: boolean;
  status: "available" | "unconfigured" | "blocked" | string;
  status_reason?: string;
}


export interface Product {
  id: string;
  name: string;
  sku?: string;
  brand?: string;
  label_text?: string;
  category?: string;
  hero_path?: string | null;
  detail_paths?: string[];
  tags?: string[];
  status: "draft" | "locked" | "archived" | string;
  locked: boolean;
  rights: { commercial_use: boolean; ai_reference_allowed: boolean; note?: string };
  created_at?: string;
  updated_at?: string;
}

export interface Asset {
  id: string;
  name: string;
  path: string;
  kind: "image" | "video" | "audio" | "file" | string;
  source: "upload" | "project" | "render" | string;
  project_id: string | null;
  bytes: number;
  mtime: number;
  width?: number;
  height?: number;
  duration_s?: number;
  codec?: string;
}

export interface ReuseAssetResult {
  asset: Asset;
  project: ProjectRecord;
  shot: Shot | null;
  version: Version | null;
}

export interface PendingRecord {
  id: string;
  project_id: string;
  kind: "quotes" | "approvals";
  status: string;
  headline?: string;
  stage?: string;
  total_usd?: number;
  created_at?: string;
}

export interface ReviewDecision {
  shot_id: string;
  status: "pass" | "flag" | string;
  note?: string;
}

export interface ReviewRecord {
  id: string;
  project_id: string;
  version_id: string;
  status: "approved" | "rejected" | string;
  approved: boolean;
  decisions: ReviewDecision[];
  comment: string;
  qa_status: string;
  created_at: string;
}

export interface ReviewCheck {
  key: string;
  label: string;
  verdict: "pass" | "pass_with_note" | "fail" | "warn" | "not_applicable" | "unknown" | string;
  detail: string;
  note?: string;
}

export interface ReviewQA {
  status: "pass" | "warn" | "fail" | "unknown" | "none" | string;
  checks: ReviewCheck[];
  brand_hits: string[];
  issues: string[];
}

export interface ProposalConcept {
  id?: string;
  title?: string;
  hook?: string;
  visual_approach?: string;
  target_audience?: string;
  target_platform?: string;
  target_duration_seconds?: number;
  key_points?: string[];
}

export interface Proposal {
  selected_concept?: {
    concept_id?: string;
    rationale?: string;
    modifications?: string[];
  };
  concept_options?: ProposalConcept[];
  production_plan?: {
    delivery_promise?: Record<string, unknown>;
    stages?: Array<Record<string, unknown>>;
    quality_tradeoffs?: Array<Record<string, unknown>>;
    [key: string]: unknown;
  };
  cost_estimate?: Record<string, unknown>;
  approval?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface PlanPayload {
  project: ProjectRecord;
  quote: Quote | null;
  proposal: Proposal | null;
  keyframes: string[];
  version: VersionSummary | null;
}

export interface Deliverable {
  id: string;
  project_id: string;
  version_id: string;
  preset: string;
  filename: string;
  path: string;
  bytes: number;
  created_at: string;
  source?: string;
  width?: number | null;
  height?: number | null;
}

export interface ReviewPayload {
  project: ProjectRecord;
  version: VersionSummary;
  final_review: Record<string, unknown> | null;
  render_report: Record<string, unknown> | null;
  review: ReviewRecord | null;
  qa: ReviewQA;
}

export interface ProjectDetail {
  project: ProjectRecord;
  versions: VersionSummary[];
  current_version: Version | null;
  pending: PendingRecord[];
  brand: Brand | null;
  latest_quote?: Quote | null;
  latest_review?: ReviewRecord | null;
  deliverables?: Deliverable[];
}

export interface CreateProjectBody {
  title: string;
  project_id?: string;
  brief?: ProjectBrief;
  platform?: string;
  aspect?: string;
  duration_s?: number;
  quality_tier?: string;
  pipeline_type?: string;
  persona_id?: string | null;
}

export type ProposalStatus = "none" | "ready" | "approved" | "rejected";

export interface PlanConcept {
  title: string;
  hook: string;
  insight: string;
  visual_approach: string;
  core_message: string;
  cta: string;
  rationale: string;
}

export interface PlanShot {
  id: string;
  index: number;
  role: string;
  duration_s: number;
  start_s: number;
  visual: string;
  text: string;
  narration: string;
  transition: string;
}

export interface PlanDeliverables {
  platform: string;
  aspect: string;
  duration_s: number;
  versions: number;
  captions: boolean;
  music: string;
  voice: string;
  note: string;
}

export interface PlanBrief {
  product: string;
  audience: string;
  description: string;
  tone: string;
  must_say: string;
  avoid: string;
  budget_usd?: number | null;
  references: string[];
}

export interface ProposalView {
  project: ProjectRecord;
  brief: PlanBrief;
  status: ProposalStatus;
  concept: PlanConcept;
  script: string[];
  shots: PlanShot[];
  deliverables: PlanDeliverables;
  keyframes: { path: string; label: string }[];
  assumptions: string[];
  exclusions: string[];
  quote: Quote | null;
  generated_at?: string | null;
  has_packet: boolean;
  has_quote: boolean;
}

export interface ProposalResponse {
  proposal: ProposalView;
  job: Job | null;
}

export type StageId = "brief" | "proposal" | "script" | "scene" | "assets" | "compose" | "review";

export type StageStatus = "locked" | "ready" | "running" | "review" | "approved" | "failed" | "stale";

export interface RouteOption {
  id: string;
  label: string;
  pipeline: string;
  runtime: string;
  description: string;
  best_for: string;
  cost_hint: string;
  eta_hint: string;
  requires: string[];
  available: boolean;
}

export interface StageRow {
  canonical_stage?: string | null;
  canonical_artifact?: string | null;
  checkpoint_status?: string | null;
  id: StageId;
  label: string;
  short: string;
  icon: string;
  status: StageStatus;
  summary: string;
  action: string;
  artifact: string;
}

export interface ProductionView {
  project: ProjectRecord;
  route: RouteOption;
  routes: RouteOption[];
  models?: ModelProfile[];
  persona?: Persona | null;
  product?: Product | null;
  brief: PlanBrief;
  stages: StageRow[];
  current_stage: StageId;
  next_action: string;
  budget_usd: number;
  spent_usd: number;
  quote: Quote | null;
  proposal: Record<string, unknown> | null;
  script: { lines: { id: string; text: string; kind?: string }[]; source?: string } | null;
  version: VersionSummary | null;
  shots: Shot[];
  preview_count: number;
  render: { path?: string; poster?: string; width?: number; height?: number; duration_s?: number } | null;
  review: ReviewRecord | null;
  final_review: Record<string, unknown> | null;
  approvals: Record<string, { at?: string; comment?: string }>;
}

// ---------------------------------------------------------------------------
// Restyle (改写)
// ---------------------------------------------------------------------------

export interface RestyleCaption {
  text: string;
  bbox?: number[] | null;
  status?: string;
}

export interface RestyleShot {
  id: string;
  index: number;
  start_s: number;
  end_s: number;
  duration_s: number;
  keyframe?: string | null;
  caption?: RestyleCaption;
  groups?: Record<string, string>;
  risk?: { score: number; reasons: string[] };
  suggested?: string;
}

export interface RestyleGroup {
  id: string;
  label: string;
  shot_ids: string[];
  thumb?: string | null;
}

export interface RestyleBlueprint {
  version: number;
  video_type: string;
  shots: RestyleShot[];
  groups: {
    scenes: RestyleGroup[];
    outfits: RestyleGroup[];
    products: RestyleGroup[];
    objects: RestyleGroup[];
  };
  suggestions?: {
    change_shot_ids: string[];
    keep_shot_ids: string[];
    reason: string;
  };
  caption_count?: number;
}

export interface RestylePlan {
  revision: number;
  change_level: "light" | "recommended" | "all" | string;
  cast?: Record<string, unknown>;
  scenes?: Record<string, { mode?: string; [key: string]: unknown }>;
  objects?: Record<string, { mode?: string; [key: string]: unknown }>;
  product?: Record<string, unknown>;
  output?: Record<string, unknown>;
  captions?: Record<string, unknown>;
  overrides?: Record<string, unknown>;
  updated_at?: string;
}

export interface RestyleSource {
  path: string;
  original_path?: string;
  hash?: string;
  probe?: {
    duration_s?: number;
    width?: number;
    height?: number;
    fps?: number;
    aspect?: string;
    has_audio?: boolean;
  };
  rights?: { confirmed?: boolean; note?: string };
}

export interface RestyleSummary {
  id: string;
  title: string;
  status: string;
  aspect?: string;
  duration_s?: number;
  cover?: string | null;
  shot_count: number;
  caption_count: number;
  analyzed: boolean;
  updated_at?: string | null;
  source_path?: string | null;
}

export interface RestyleDetail {
  project: ProjectRecord;
  source: RestyleSource | null;
  blueprint: RestyleBlueprint | null;
  plan: RestylePlan | null;
  jobs: Job[];
}
