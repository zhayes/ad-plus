/** Live transcript: user turns + the agent's ordered work timeline. */

import { createStore, produce } from "solid-js/store";
import type { TimelineKind, TimelineStep, Turn } from "../lib/types";

interface State {
  turns: Turn[];
  running: boolean;
  usage: { input: number; output: number; cost: number } | null;
}

const [state, setState] = createStore<State>({ turns: [], running: false, usage: null });
export const turns = () => state.turns;
export const running = () => state.running;
export const usage = () => state.usage;

let counter = 0;
const nextId = () => `t${++counter}`;

interface HistoryMessage {
  role: "user" | "assistant";
  text?: string;
  blocks?: Array<{
    kind: string;
    text?: string;
    name?: string;
    args?: string;
    result?: string;
    ok?: boolean;
    durationMs?: number;
  }>;
}

/** Rebuild turns from a stored session (the same shape the live stream produces). */
export function hydrateTranscript(messages: HistoryMessage[]): number {
  const rebuilt: Turn[] = [];
  let n = 0;
  for (const message of messages) {
    const id = `h${++n}`;
    if (message.role === "user") {
      rebuilt.push({ id, role: "user", text: message.text ?? "" });
      continue;
    }
    const steps: TimelineStep[] = [];
    const texts: string[] = [];
    let step = 0;
    for (const block of message.blocks ?? []) {
      if (block.kind === "thinking") {
        steps.push({
          id: `${id}s${++step}`,
          kind: "think",
          label: "思考",
          detail: block.text ?? "",
          running: false,
          ok: true,
        });
      } else if (block.kind === "tool") {
        steps.push({
          id: `${id}s${++step}`,
          kind: "tool",
          label: shortToolName(block.name ?? "tool"),
          detail: [block.args, block.result ? `\n\n→ ${block.result}` : ""].join("").slice(0, 4000),
          seconds: (block.durationMs ?? 0) / 1000,
          running: false,
          ok: block.ok !== false,
        });
      } else if (block.kind === "text") {
        texts.push(block.text ?? "");
      }
    }
    rebuilt.push({ id, role: "assistant", text: texts.join(""), timeline: steps });
  }
  setState({ turns: rebuilt, running: false, usage: state.usage });
  return rebuilt.length;
}

export function resetTranscript(): void {
  setState({ turns: [], running: false, usage: null });
}

export function addUserTurn(text: string): void {
  setState("turns", (prev) => [...prev, { id: nextId(), role: "user", text }]);
}

function ensureAssistant(): Turn | null {
  let last = state.turns[state.turns.length - 1];
  if (last && last.role === "assistant" && !last.streaming) return last;
  if (last && last.role === "assistant") return last;
  const turn: Turn = { id: nextId(), role: "assistant", text: "", timeline: [], streaming: true };
  setState("turns", (prev) => [...prev, turn]);
  last = turn;
  return last;
}

function lastStep(): TimelineStep | undefined {
  const turn = state.turns[state.turns.length - 1];
  return turn?.timeline?.[turn.timeline.length - 1];
}

function pushStep(step: Omit<TimelineStep, "id">): void {
  const turn = ensureAssistant();
  if (!turn) return;
  setState(
    produce((draft) => {
      const target = draft.turns[draft.turns.length - 1];
      if (!target.timeline) target.timeline = [];
      target.timeline.push({ ...step, id: `s${++counter}` });
    }),
  );
}

function updateStep(kind: TimelineKind, patch: Partial<TimelineStep>, match?: (s: TimelineStep) => boolean): void {
  setState(
    produce((draft) => {
      const turn = draft.turns[draft.turns.length - 1];
      if (!turn?.timeline) return;
      const step = match ? [...turn.timeline].reverse().find(match) : [...turn.timeline].reverse().find((s) => s.kind === kind);
      if (step) Object.assign(step, patch);
    }),
  );
}

export function setUsage(totals: { input?: number; output?: number; cost?: number }): void {
  setState("usage", { input: totals.input ?? 0, output: totals.output ?? 0, cost: totals.cost ?? 0 });
}

export function shortToolName(name: string): string {
  return (name || "").replace(/^mcp__[^_]+__/, "").replace(/^mcp__/, "");
}

/** Translate one Pi/bridge event into transcript state. Mirrors the legacy page. */
export function handleEvent(event: Record<string, unknown>): void {
  const type = String(event.type ?? "");

  if (type === "message_start") {
    setState("running", true);
    ensureAssistant();
    return;
  }

  if (type === "message_update") {
    const ev = (event.assistantMessageEvent ?? {}) as Record<string, unknown>;
    const kind = String(ev.type ?? "");
    if (kind === "thinking_start") {
      pushStep({ kind: "think", label: "思考", running: true, detail: "" });
    } else if (kind === "thinking_delta") {
      const delta = String(ev.delta ?? "");
      const step = lastStep();
      if (!step || step.kind !== "think") pushStep({ kind: "think", label: "思考", running: true, detail: delta });
      else updateStep("think", { detail: `${step.detail ?? ""}${delta}`.slice(-4000) }, (s) => s.id === step.id);
    } else if (kind === "thinking_end") {
      updateStep("think", { running: false });
    } else if (kind === "text_delta") {
      const delta = String(ev.delta ?? "");
      setState(
        produce((draft) => {
          const turn = draft.turns[draft.turns.length - 1];
          if (turn?.role === "assistant") turn.text += delta;
        }),
      );
    }
    return;
  }

  if (type === "tool_execution_start") {
    setState("running", true);
    const label = shortToolName(String(event.toolName ?? "tool"));
    pushStep({
      kind: "tool",
      label,
      running: true,
      detail: JSON.stringify(event.args ?? {}, null, 1).slice(0, 900),
      ok: undefined,
    });
    return;
  }

  if (type === "tool_execution_end") {
    const callId = String(event.toolCallId ?? event.toolName ?? "");
    const seconds = Number(event.durationMs ?? 0) / 1000;
    const ok = !event.isError;
    const result = summarize(event.result);
    updateStep(
      "tool",
      { running: false, seconds, ok },
      (s) => s.kind === "tool" && !!s.running && (s.label === shortToolName(String(event.toolName ?? "")) || callId !== ""),
    );
    if (result) {
      setState(
        produce((draft) => {
          const turn = draft.turns[draft.turns.length - 1];
          const step = [...(turn?.timeline ?? [])].reverse().find((s) => s.kind === "tool" && s.running === false);
          if (step) step.detail = `${step.detail ?? ""}\n\n→ ${result}`.slice(-6000);
        }),
      );
    }
    return;
  }

  if (type === "message_end") {
    const message = (event.message ?? {}) as Record<string, unknown>;
    if (message.role === "assistant") {
      const text = ((message.content ?? []) as Array<Record<string, unknown>>)
        .filter((part) => part.type === "text")
        .map((part) => String(part.text ?? ""))
        .join("");
      if (text) {
        setState(
          produce((draft) => {
            const turn = draft.turns[draft.turns.length - 1];
            if (turn?.role === "assistant") turn.text = text;
          }),
        );
      }
    }
    return;
  }

  if (type === "agent_settled") {
    setState(
      produce((draft) => {
        draft.running = false;
        const turn = draft.turns[draft.turns.length - 1];
        if (turn?.role === "assistant") {
          turn.streaming = false;
          for (const step of turn.timeline ?? []) step.running = false;
        }
      }),
    );
    return;
  }

  if (type === "usage") {
    setUsage((event.totals ?? {}) as { input?: number; output?: number; cost?: number });
    return;
  }
}

function summarize(value: unknown): string {
  if (value === undefined || value === null) return "";
  const text = typeof value === "string" ? value : JSON.stringify(value);
  return text.replace(/\\n/g, "\n").slice(0, 600);
}
