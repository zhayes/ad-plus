import type { JSX } from "solid-js";
import { Show } from "solid-js";

type Tone = "neutral" | "ok" | "warn" | "bad" | "accent";

const tones: Record<Tone, string> = {
  neutral: "border-line text-faint",
  ok: "border-ok/35 text-ok",
  warn: "border-warn/35 text-warn",
  bad: "border-bad/35 text-bad",
  accent: "border-accent/40 text-accent",
};

export default function Badge(props: { tone?: Tone; children?: JSX.Element; class?: string }) {
  return (
    <span
      class={`inline-flex items-center rounded border px-1 py-px text-[10px] ${tones[props.tone ?? "neutral"]} ${props.class ?? ""}`}
    >
      {props.children}
    </span>
  );
}

/** Small right-aligned counter — renders nothing when the value is zero. */
export function CountBadge(props: { value: number; class?: string }) {
  return (
    <Show when={props.value > 0}>
      <span class={`ml-auto font-mono text-[10.5px] text-faint ${props.class ?? ""}`}>{props.value}</span>
    </Show>
  );
}
