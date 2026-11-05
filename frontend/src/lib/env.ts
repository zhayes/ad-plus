/** Workspace facts from the backend, so the UI never hardcodes a path. */

import { api } from "./api";

let workspace = "";

export async function loadWorkspace(): Promise<string> {
  if (workspace) return workspace;
  try {
    const boot = await api.get<{ workspace?: string }>("/api/bootstrap");
    workspace = boot.workspace ?? "";
  } catch {
    workspace = "";
  }
  return workspace;
}

export const workspacePath = (): string => workspace;
