/** Session list + current selection (the URL param is the source of truth). */

import { createSignal } from "solid-js";
import { endpoints } from "../lib/api";
import { poll } from "../lib/poller";
import type { SessionSummary } from "../lib/types";

const [sessions, setSessions] = createSignal<SessionSummary[]>([]);
const [currentId, setCurrentId] = createSignal<string | null>(null);
const [loading, setLoading] = createSignal(true);

export { sessions, currentId, loading };

export async function refreshSessions(): Promise<void> {
  try {
    const data = await endpoints.sessions();
    setSessions(data.sessions ?? []);
  } catch {
    /* keep the rail quiet on a transient failure */
  } finally {
    setLoading(false);
  }
}

export function watchSessions(): void {
  poll("sessions", refreshSessions, 4000);
}

export function selectSession(id: string | null): void {
  setCurrentId(id);
}

export function currentSession(): SessionSummary | undefined {
  const id = currentId();
  return sessions().find((s) => s.id === id);
}
