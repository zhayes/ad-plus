import { For, Show, createMemo, createSignal } from "solid-js";
import type { TimelineStep } from "../../lib/types";
import { fmtStepTime } from "../../lib/format";
import Icon from "../ui/Icon";

interface Props {
  steps: TimelineStep[];
}

/** One collapsed timeline per user turn — the only implementation of this view. */
export default function Timeline(props: Props) {
  const [open, setOpen] = createSignal(false);
  const steps = () => props.steps ?? [];
  const thinks = createMemo(() => steps().filter((s) => s.kind === "think").length);
  const tools = createMemo(() => steps().filter((s) => s.kind === "tool").length);
  const anyRunning = createMemo(() => steps().some((s) => s.running));
  const tooShort = createMemo(() => thinks() === 0 && tools() === 0);

  const header = () => {
    if (anyRunning()) return `执行中 · ${tools()} 次工具`;
    return [thinks() ? `${thinks()} 次思考` : "", tools() ? `${tools()} 次工具` : ""].filter(Boolean).join(" · ") || "执行过程";
  };

  return (
    <Show when={!tooShort()}>
      <div class="my-2 overflow-hidden rounded-[11px] border border-line-soft bg-surface">
        <button
          class="flex w-full items-center gap-2 px-3 py-2 text-left text-[11.5px] text-dim hover:text-text"
          onClick={() => setOpen((v) => !v)}
        >
          <Chevron open={open()} />
          <Show when={anyRunning()}>
            <span class="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-accent" />
          </Show>
          <span class="truncate">{header()}</span>
        </button>

        <Show when={open()}>
          <div class="max-h-[300px] overflow-auto border-t border-line-soft py-1">
            <For each={steps()}>
              {(step) => <StepRow step={step} />}
            </For>
          </div>
        </Show>
      </div>
    </Show>
  );
}

function Chevron(props: { open: boolean }) {
  return (
    <span
      class="grid h-4 w-4 shrink-0 place-items-center rounded text-dim transition-transform hover:text-text"
      classList={{ "rotate-90": props.open }}
    >
      <Icon name="chevron-right" size={13} />
    </span>
  );
}

function StepRow(props: { step: TimelineStep }) {
  const [open, setOpen] = createSignal(false);
  const step = () => props.step;
  const preview = () => (step().detail ?? "").replace(/\s+/g, " ").slice(0, 70);

  return (
    <div class="px-3">
      <button
        class="flex min-h-[22px] w-full items-center gap-2 text-left text-[11.5px] text-faint"
        onClick={() => setOpen((v) => !v)}
      >
        <Chevron open={open()} />
        <span
          class="shrink-0 rounded border px-1 text-[10px]"
          classList={{
            "border-ok/35 text-ok": step().ok === true,
            "border-bad/35 text-bad": step().ok === false,
            "border-line text-faint": step().ok === undefined,
          }}
        >
          {step().kind === "think" ? "思考" : "工具"}
        </span>
        <Show
          when={step().kind === "think"}
          fallback={<span class="truncate font-mono text-[#b8c0d4]">{step().label}</span>}
        >
          <span class="truncate text-faint">{preview() || "思考"}</span>
        </Show>
        <Show when={step().seconds !== undefined}>
          <span class="ml-auto shrink-0 font-mono text-[10.5px] tabular-nums">{fmtStepTime(step().seconds)}</span>
        </Show>
        <Show when={step().running}>
          <span class="ml-auto inline-block h-1.5 w-1.5 shrink-0 animate-pulse rounded-full bg-accent" />
        </Show>
      </button>

      <Show when={open() && step().detail}>
        <div class="mb-1.5 ml-[19px] max-h-[200px] overflow-auto whitespace-pre-wrap break-words rounded-[7px] border border-line-soft bg-[#0a0c11] p-2 font-mono text-[10.5px] text-[#8d95a6]">
          {step().detail}
        </div>
      </Show>
    </div>
  );
}
