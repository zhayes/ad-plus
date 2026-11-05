import type { JSX } from "solid-js";
import { Show } from "solid-js";
import Badge from "../ui/Badge";
import { coverUrl, platformLabel, statusInfo, tierLabel } from "../../lib/projects";
import { fmtTime, fmtUsd } from "../../lib/format";
import type { ProjectSummary } from "../../lib/types";

interface Props {
  project: ProjectSummary;
  menuOpen: boolean;
  onOpen: () => void;
  onOverview: () => void;
  onReveal: () => void;
  onArchive: () => void;
  onDelete: () => void;
  onToggleMenu: () => void;
}

function MenuItem(props: { children: JSX.Element; danger?: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      class={`block w-full rounded-md px-2 py-1.5 text-left text-[11px] ${
        props.danger ? "text-bad hover:bg-bad/10" : "text-dim hover:bg-surface-2 hover:text-text"
      }`}
      onClick={props.onClick}
    >
      {props.children}
    </button>
  );
}

export default function ProjectCard(props: Props) {
  const status = () => statusInfo(props.project.status);
  const cover = () => coverUrl(props.project.cover);
  const portrait = () => props.project.aspect === "9:16";

  return (
    <div
      class={`group relative rounded-xl border bg-surface transition-colors ${
        props.menuOpen ? "border-line" : "border-line-soft hover:border-line"
      }`}
    >
      <button
        type="button"
        class="relative block w-full overflow-hidden rounded-t-xl bg-[#0b0e15] text-left"
        style={{ "aspect-ratio": "16 / 9" }}
        onClick={props.onOpen}
      >
        <Show
          when={cover()}
          fallback={
            <div
              class="grid h-full w-full place-items-center"
              style={{ "background-image": "radial-gradient(circle at 30% 20%, #2a1730, #0b0e15 60%)" }}
            >
              <div class="text-center">
                <div class="text-[17px] font-semibold tracking-tight text-white/15">Ad+</div>
                <div class="mt-1 text-[10px] text-white/25">
                  {props.project.aspect} · {props.project.duration_s}s
                </div>
              </div>
            </div>
          }
        >
          <Show
            when={portrait()}
            fallback={<img src={cover()!} alt="" class="absolute inset-0 h-full w-full object-cover" loading="lazy" />}
          >
            <img src={cover()!} alt="" aria-hidden="true" class="absolute inset-0 h-full w-full scale-110 object-cover opacity-40 blur-xl" />
            <img src={cover()!} alt="" class="absolute inset-0 h-full w-full object-contain" loading="lazy" />
          </Show>
        </Show>

        <div class="pointer-events-none absolute inset-0 bg-gradient-to-t from-black/70 via-black/0 to-black/20" />
        <div class="pointer-events-none absolute inset-x-0 top-0 h-16 bg-gradient-to-b from-black/55 to-transparent" />

        <div class="absolute left-2 top-2 flex items-center gap-1">
          <Badge tone={status().tone}>{status().label}</Badge>
          <Show when={props.project.pending_count > 0}>
            <Badge tone="warn">{props.project.pending_count} 待办</Badge>
          </Show>
        </div>

        <div class="absolute bottom-2 left-2 right-2 flex items-center justify-between text-[10px] text-white/80">
          <span>
            {platformLabel(props.project.platform)} · {props.project.aspect} · {props.project.duration_s}s
            {props.project.route_label ? ` · ${props.project.route_label}` : ""}
          </span>
          <span>
            {props.project.current_version_label ? `${props.project.current_version_label} · ${props.project.version_count} 版` : "无版本"}
          </span>
        </div>
      </button>

      <div class="flex items-start gap-2 rounded-b-xl px-3 py-2.5">
        <button type="button" class="min-w-0 flex-1 text-left" onClick={props.onOpen}>
          <div class="truncate text-[12.5px] font-medium text-text">{props.project.title}</div>
          <div class="mt-1 flex items-center gap-1.5 text-[10.5px] text-faint">
            <Show when={props.project.stage_label} fallback={<span>{tierLabel(props.project.quality_tier)}</span>}>
              <span class="text-dim">{props.project.stage_label}</span>
            </Show>
            <span>·</span>
            <span class="truncate">{props.project.next_action || fmtTime(props.project.updated) || "未保存"}</span>
            <Show when={props.project.cost_usd > 0}>
              <span>·</span>
              <span>{fmtUsd(props.project.cost_usd)}</span>
            </Show>
          </div>
        </button>

        <div class="relative">
          <button
            type="button"
            class="grid h-6 w-6 place-items-center rounded-md text-[13px] text-faint hover:bg-surface-2 hover:text-text"
            title="更多"
            aria-label="更多"
            onClick={(event) => {
              event.stopPropagation();
              props.onToggleMenu();
            }}
          >
            ⋯
          </button>

          <Show when={props.menuOpen}>
            <div class="absolute right-0 top-7 z-20 w-44 rounded-lg border border-line-soft bg-surface p-1 shadow-2xl">
              <MenuItem onClick={props.onOpen}>打开制作</MenuItem>
              <MenuItem onClick={props.onOverview}>项目总览</MenuItem>
              <MenuItem onClick={props.onReveal}>在 Finder 显示</MenuItem>
              <div class="my-1 h-px bg-line-soft" />
              <MenuItem onClick={props.onArchive}>归档</MenuItem>
              <MenuItem danger onClick={props.onDelete}>删除</MenuItem>
            </div>
          </Show>
        </div>
      </div>
    </div>
  );
}
