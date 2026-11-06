/** The single HTTP entry point. Components must not call fetch directly. */

import type {
  AppConfig,
  ProductionView,
  ProposalResponse,
  Approval,
  Artifact,
  Asset,
  Brand,
  DigitalHumanTake,
  FormatPreset,
  PersonaGeneration,
  ModelProfile,
  ProductCompositeTake,
  Persona,
  Product,
  CreateProjectBody,
  Deliverable,
  Job,
  PlanPayload,
  ProjectDetail,
  ProjectRecord,
  ProjectSummary,
  Quote,
  ReuseAssetResult,
  ReviewPayload,
  Shot,
  Version,
  SessionSummary,
} from "./types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: init?.body ? { "Content-Type": "application/json" } : undefined,
    ...init,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`${res.status} ${text.slice(0, 200)}`);
  }
  const type = res.headers.get("content-type") || "";
  return (type.includes("application/json") ? res.json() : res.text()) as Promise<T>;
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) }),
  patch: <T>(path: string, body: unknown) =>
    request<T>(path, { method: "PATCH", body: JSON.stringify(body) }),
  del: <T>(path: string) => request<T>(path, { method: "DELETE" }),
};

export const endpoints = {
  sessions: () => api.get<{ sessions: SessionSummary[] }>("/api/sessions"),
  health: () => api.get<{ ok: boolean; version: string }>("/api/health"),
  quotes: () => api.get<{ quotes: Quote[] }>("/api/quotes"),
  approvals: () => api.get<{ approvals: Approval[] }>("/api/approvals"),
  decideQuote: (id: string, project_id: string, approved: boolean, comment = "") =>
    api.post(`/api/quotes/${encodeURIComponent(id)}`, { project_id, approved, comment }),
  decideApproval: (id: string, project_id: string, approved: boolean, comment = "") =>
    api.post(`/api/approvals/${encodeURIComponent(id)}`, { project_id, approved, comment }),
  jobs: (projectId?: string) =>
    api.get<{ jobs: Job[]; running: number }>(
      `/api/jobs${projectId ? `?project_id=${encodeURIComponent(projectId)}` : ""}`,
    ),
  retryJob: (id: string, projectId: string) =>
    api.post<{ job: Job }>(`/api/jobs/${encodeURIComponent(id)}/retry`, { project_id: projectId }),
  cancelJob: (id: string, project_id: string) =>
    api.post(`/api/jobs/${encodeURIComponent(id)}/cancel`, { project_id }),
  artifacts: (params: string) => api.get<{ artifacts: Artifact[] }>(`/api/artifacts?${params}`),
  workspace: (params: string) => api.get<Record<string, unknown>>(`/api/workspace?${params}`),

  projects: () => api.get<{ projects: ProjectSummary[] }>("/api/projects"),
  project: (id: string) => api.get<ProjectDetail>(`/api/projects/${encodeURIComponent(id)}`),
  createProject: (body: CreateProjectBody) =>
    api.post<{ project: ProjectRecord }>("/api/projects", body),
  patchProject: (id: string, body: Record<string, unknown>) =>
    api.patch<ProjectDetail>(`/api/projects/${encodeURIComponent(id)}`, body),
  deleteProject: (id: string) =>
    api.del<{ trash_id: string }>(`/api/projects/${encodeURIComponent(id)}`),
  restoreProject: (token: string) =>
    api.post<{ project: ProjectRecord }>(`/api/projects/restore/${encodeURIComponent(token)}`),
  reveal: (path: string) => api.post<{ ok: boolean }>("/api/reveal", { path }),

  reorderShots: (projectId: string, versionId: string, order: string[]) =>
    api.patch<{ version: Version }>(
      `/api/projects/${encodeURIComponent(projectId)}/versions/${encodeURIComponent(versionId)}/shots/reorder`,
      { order },
    ),
  addShot: (projectId: string, versionId: string, body: Record<string, unknown>) =>
    api.post<{ version: Version }>(
      `/api/projects/${encodeURIComponent(projectId)}/versions/${encodeURIComponent(versionId)}/shots`,
      body,
    ),
  updateShot: (projectId: string, versionId: string, shotId: string, body: Record<string, unknown>) =>
    api.patch<{ shot: Shot; version: Version }>(
      `/api/projects/${encodeURIComponent(projectId)}/versions/${encodeURIComponent(versionId)}/shots/${encodeURIComponent(shotId)}`,
      body,
    ),
  deleteShot: (projectId: string, versionId: string, shotId: string) =>
    api.del<{ version: Version }>(
      `/api/projects/${encodeURIComponent(projectId)}/versions/${encodeURIComponent(versionId)}/shots/${encodeURIComponent(shotId)}`,
    ),

  setCurrentVersion: (projectId: string, versionId: string) =>
    api.patch<{ version: Version; project: ProjectRecord }>(
      `/api/projects/${encodeURIComponent(projectId)}/versions/${encodeURIComponent(versionId)}`,
      { current: true },
    ),
  plan: (projectId: string) => api.get<PlanPayload>(`/api/projects/${encodeURIComponent(projectId)}/plan`),
  review: (projectId: string, versionId?: string) =>
    api.get<ReviewPayload>(
      `/api/projects/${encodeURIComponent(projectId)}/review${versionId ? `?version_id=${encodeURIComponent(versionId)}` : ""}`,
    ),
  decideReview: (
    projectId: string,
    body: { version_id: string; approved: boolean; decisions: unknown[]; comment: string },
  ) => api.post<{ review: unknown; detail: ProjectDetail }>(`/api/projects/${encodeURIComponent(projectId)}/review`, body),
  deliverables: (projectId: string) =>
    api.get<{ deliverables: Deliverable[] }>(`/api/projects/${encodeURIComponent(projectId)}/deliverables`),
  exportVersion: (
    projectId: string,
    body: { version_id: string; preset: string; filename?: string },
  ) =>
    api.post<{ deliverable: Deliverable; deliverables: Deliverable[]; detail: ProjectDetail }>(
      `/api/projects/${encodeURIComponent(projectId)}/export`,
      body,
    ),

  assets: (params: { project_id?: string; kind?: string; source?: string; q?: string } = {}) => {
    const query = new URLSearchParams();
    for (const [key, value] of Object.entries(params)) if (value) query.set(key, value);
    return api.get<{ assets: Asset[] }>(`/api/assets${query.size ? `?${query}` : ""}`);
  },
  asset: (id: string) => api.get<{ asset: Asset }>(`/api/assets/${encodeURIComponent(id)}`),
  reuseAsset: (id: string, body: { project_id: string; shot_id?: string; mode: "reference" | "replace" }) =>
    api.post<ReuseAssetResult>(`/api/assets/${encodeURIComponent(id)}/reuse`, body),
  deleteAsset: (id: string) => api.del<{ removed: boolean }>(`/api/assets/${encodeURIComponent(id)}`),

  products: () => api.get<{ products: Product[] }>("/api/products"),
  createProduct: (body: Record<string, unknown>) => api.post<{ product: Product }>("/api/products", body),
  patchProduct: (id: string, body: Record<string, unknown>) =>
    api.patch<{ product: Product }>(`/api/products/${encodeURIComponent(id)}`, body),
  deleteProduct: (id: string) => api.del<{ removed: boolean }>(`/api/products/${encodeURIComponent(id)}`),

  formats: () => api.get<{ formats: FormatPreset[] }>("/api/formats"),

  personas: () => api.get<{ personas: Persona[] }>("/api/personas"),
  createPersona: (body: Record<string, unknown>) => api.post<{ persona: Persona }>("/api/personas", body),
  generatePersona: (body: Record<string, unknown>) => api.post<PersonaGeneration>("/api/personas/generate", body),
  patchPersona: (id: string, body: Record<string, unknown>) =>
    api.patch<{ persona: Persona }>(`/api/personas/${encodeURIComponent(id)}`, body),
  deletePersona: (id: string) => api.del<{ removed: boolean }>(`/api/personas/${encodeURIComponent(id)}`),
  planDigitalHuman: (projectId: string, body: Record<string, unknown>) =>
    api.post<{ take: DigitalHumanTake }>(`/api/projects/${encodeURIComponent(projectId)}/digital-human/plan`, body),
  startDigitalHuman: (projectId: string, body: Record<string, unknown>) =>
    api.post<{ stage: string; status: string; take: DigitalHumanTake; checkpoint?: Record<string, unknown> | null }>(
      `/api/projects/${encodeURIComponent(projectId)}/pipeline/assets`, body,
    ),
  planProductComposite: (projectId: string, body: Record<string, unknown>) =>
    api.post<{ take: ProductCompositeTake }>(`/api/projects/${encodeURIComponent(projectId)}/product-composite/plan`, body),
  runProductComposite: (projectId: string, body: Record<string, unknown>) =>
    api.post<{ take: ProductCompositeTake }>(`/api/projects/${encodeURIComponent(projectId)}/product-composite/takes`, body),
  productCompositeTakes: (projectId: string) =>
    api.get<{ takes: ProductCompositeTake[] }>(`/api/projects/${encodeURIComponent(projectId)}/product-composite/takes`),

  models: (capability?: string) =>
    api.get<{ models: ModelProfile[] }>(`/api/models${capability ? `?capability=${encodeURIComponent(capability)}` : ""}`),

  brands: () => api.get<{ brands: Brand[] }>("/api/brands"),
  brand: (id: string) => api.get<{ brand: Brand }>(`/api/brands/${encodeURIComponent(id)}`),
  createBrand: (body: Record<string, unknown>) => api.post<{ brand: Brand }>("/api/brands", body),
  patchBrand: (id: string, body: Record<string, unknown>) =>
    api.patch<{ brand: Brand }>(`/api/brands/${encodeURIComponent(id)}`, body),
  defaultBrand: (id: string) => api.post<{ brand: Brand }>(`/api/brands/${encodeURIComponent(id)}/default`),
  applyBrand: (id: string, projectId: string) =>
    api.post<{ project: ProjectRecord }>(`/api/brands/${encodeURIComponent(id)}/apply`, { project_id: projectId }),
  deleteBrand: (id: string) => api.del<{ removed: boolean }>(`/api/brands/${encodeURIComponent(id)}`),

  production: (projectId: string) =>
    api.get<ProductionView>(`/api/projects/${encodeURIComponent(projectId)}/production`),
  setRoute: (projectId: string, routeId: string) =>
    api.post<ProductionView>(`/api/projects/${encodeURIComponent(projectId)}/route`, { route_id: routeId }),
  saveScript: (projectId: string, lines: { id?: string; text: string; kind?: string }[]) =>
    api.post<{ script: { lines: { id: string; text: string; kind?: string }[] } }>(
      `/api/projects/${encodeURIComponent(projectId)}/script`,
      { lines },
    ),
  compose: (projectId: string) =>
    api.post<{ job_id: string; output: string; composition: string }>(
      `/api/projects/${encodeURIComponent(projectId)}/compose`,
      {},
    ),
  approveStage: (projectId: string, stage: string, comment = "") =>
    api.post<ProductionView>(
      `/api/projects/${encodeURIComponent(projectId)}/stages/${encodeURIComponent(stage)}/approve`,
      { comment },
    ),
  proposal: (projectId: string) =>
    api.get<ProposalResponse>(`/api/projects/${encodeURIComponent(projectId)}/proposal`),
  generateProposal: (projectId: string, body: Record<string, unknown> = {}) =>
    api.post<ProposalResponse>(`/api/projects/${encodeURIComponent(projectId)}/proposal`, body),
  cancelProposal: (projectId: string) =>
    api.post<{ job: Job | null }>(`/api/projects/${encodeURIComponent(projectId)}/proposal/cancel`, {}),
  config: () => api.get<AppConfig>("/api/config"),
  saveConfig: (body: Record<string, unknown>) => api.post<AppConfig>("/api/config", body),
  notify: (title: string, body: string) => api.post<{ ok: boolean }>("/api/notify", { title, body }),
};

/** Raw-body upload; kept here so components never touch fetch. */
export async function uploadAsset(file: File): Promise<Asset> {
  const res = await fetch(`/api/upload?name=${encodeURIComponent(file.name)}`, {
    method: "POST",
    body: file,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`${res.status} ${text.slice(0, 200)}`);
  }
  const data = (await res.json()) as { asset: Asset };
  return data.asset;
}
