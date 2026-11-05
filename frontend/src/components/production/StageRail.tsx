import { For, Show, createEffect } from "solid-js";
import Icon, { type IconName } from "../ui/Icon";
import type { StageId, StageRow } from "../../lib/types";

interface Props {
  stages: StageRow[];
  current: StageId;
  onSelect: (stage: StageId) => void;
}

const ICONS: Record<string, IconName> = {
  brief: "file-text",
  proposal: "lightbulb",
  script: "script",
  scene: "layout",
  assets: "image",
  compose: "film",
  review: "check",
};

const DOT: Record<string, string> = {
  approved: "bg-ok",
  review: "bg-warn",
  ready: "bg-accent",
  running: "bg-accent animate-pulse",
  failed: "bg-bad",
  stale: "bg-warn",
  locked: "bg-line",
};

export default function StageRail(props: Props) {
  let nav: HTMLElement | undefined;

  createEffect(() => {
    const current = props.current;
    queueMicrotask(() => {
      nav?.querySelector<HTMLElement>(`[data-stage="${current}"]`)?.scrollIntoView({ inline: "center", block: "nearest" });
    });
  });

  return (
    <nav ref={nav} class="flex w-full shrink-0 gap-1 overflow-x-auto xl:w-[220px] xl:flex-col xl:gap-0.5 xl:overflow-visible">
      <For each={props.stages}>
        {(stage, index) => {
          const active = () => props.current === stage.id;
          const locked = () => stage.status === "locked";
          return (
            <button
              type="button"
              data-stage={stage.id}
              disabled={locked()}
              class={`group flex min-w-[150px] items-start gap-2 rounded-lg px-2.5 py-2 text-left transition-colors xl:w-full xl:min-w-0 ${
                active() ? "bg-surface-2" : locked() ? "cursor-not-allowed opacity-45" : "hover:bg-surface-2/60"
              }`}
              onClick={() => !locked() && props.onSelect(stage.id)}
            >
              <span class="mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-md border border-line-soft bg-surface">
                <Show when={stage.status === "approved"} fallback={<Icon name={ICONS[stage.id] ?? "file-text"} size={13} />}>
                  <Icon name="check" size={13} class="text-ok" />
                </Show>
              </span>
              <span class="min-w-0 flex-1">
                <span class="flex items-center gap-1.5">
                  <span class="font-mono text-[9px] text-faint">0{index() + 1}</span>
                  <span class={`truncate text-[11.5px] ${active() ? "font-medium text-text" : "text-dim"}`}>{stage.label}</span>
                  <span class={`ml-auto h-1.5 w-1.5 shrink-0 rounded-full ${DOT[stage.status] ?? "bg-line"}`} />
                </span>
                <span class="mt-0.5 block truncate text-[9.5px] text-faint">
                  {stage.status === "locked" ? "先完成上一阶段" : stage.action}
                </span>
              </span>
            </button>
          );
        }}
      </For>
    </nav>
  );
}
