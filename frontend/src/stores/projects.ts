/** Project list shared by the shell (last project link) and the projects page. */

import { createSignal } from "solid-js";
import { endpoints } from "../lib/api";
import type { ProjectSummary } from "../lib/types";

const [projects, setProjects] = createSignal<ProjectSummary[]>([]);
const [loading, setLoading] = createSignal(true);
const [error, setError] = createSignal<string | null>(null);

export { projects, loading, error };

export async function refreshProjects(): Promise<void> {
  setLoading(true);
  setError(null);
  try {
    const data = await endpoints.projects();
    setProjects(data.projects ?? []);
  } catch (err) {
    setError(err instanceof Error ? err.message : "项目加载失败");
  } finally {
    setLoading(false);
  }
}

export function firstProjectId(): string | null {
  return projects()[0]?.id ?? null;
}

export function projectById(id: string): ProjectSummary | undefined {
  return projects().find((project) => project.id === id);
}
