/** Pending quotes / approvals shown in the dock above the composer. */

import { createSignal } from "solid-js";
import { endpoints } from "../lib/api";
import type { Approval, Quote } from "../lib/types";

export interface AskItem {
  id: string;
  kind: "quote" | "gate";
  quote?: Quote;
  approval?: Approval;
  project_id: string;
}

const [asks, setAsks] = createSignal<AskItem[]>([]);
const [index, setIndex] = createSignal(0);

export { asks, index };

function toItems(quotes: Quote[], approvals: Approval[]): AskItem[] {
  const items: AskItem[] = [
    ...quotes.map((quote) => ({ id: quote.id, kind: "quote" as const, quote, project_id: quote.project_id })),
    ...approvals.map((approval) => ({
      id: approval.id,
      kind: "gate" as const,
      approval,
      project_id: approval.project_id,
    })),
  ];
  return items;
}

export async function refreshAsks(): Promise<void> {
  try {
    const [q, a] = await Promise.all([endpoints.quotes(), endpoints.approvals()]);
    const next = toItems(q.quotes ?? [], a.approvals ?? []);
    setAsks((prev) => {
      // keep the resolved cards out, merge the new ones in
      const known = new Set(prev.map((item) => item.id));
      const merged = [...prev, ...next.filter((item) => !known.has(item.id))];
      return merged.filter((item) => next.some((n) => n.id === item.id));
    });
    clampIndex();
  } catch {
    /* backend may be older */
  }
}

function clampIndex(): void {
  const total = asks().length;
  setIndex((i) => (total === 0 ? 0 : Math.min(i, total - 1)));
}

export function show(index_: number): void {
  const total = asks().length;
  if (total === 0) return;
  setIndex(Math.max(0, Math.min(total - 1, index_)));
}

export function next(): void {
  show(index() + 1);
}

export function prev(): void {
  show(index() - 1);
}

export function addAsk(item: AskItem): void {
  setAsks((prev) => (prev.some((a) => a.id === item.id) ? prev : [...prev, item]));
  clampIndex();
}

export async function decide(item: AskItem, approved: boolean, comment = ""): Promise<void> {
  if (item.kind === "quote") {
    await endpoints.decideQuote(item.id, item.project_id, approved, comment);
  } else {
    await endpoints.decideApproval(item.id, item.project_id, approved, comment);
  }
  setAsks((prev) => prev.filter((a) => a.id !== item.id));
  clampIndex();
}
