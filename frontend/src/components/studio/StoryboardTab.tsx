import { For, Show, createEffect, createSignal } from "solid-js";
import Badge from "../ui/Badge";
import Button from "../ui/Button";
import { coverUrl } from "../../lib/projects";
import { timecode, totalDuration } from "../../lib/storyboard";
import type { Shot, Version } from "../../lib/types";

const SHOT_STATUS: Record<string, { label: string; tone: "neutral" | "ok" | "warn" | "bad" | "accent" }> = {
  planned: { label: "待生成", tone: "neutral" },
  generating: { label: "生成中", tone: "warn" },
  ready: { label: "已生成", tone: "ok" },
  approved: { label: "已通过", tone: "ok" },
  needs_rework: { label: "待改", tone: "warn" },
};

interface Props {
  version: Version;
  selectedId: string | null;
  busy: boolean;
  onSelect: (id: string) => void;
  onReorder: (fromId: string, toId: string, after: boolean) => void;
  onAdd: (afterId: string | null) => void;
  onDelete: (id: string) => void;
  onUpdate: (id: string, fields: Record<string, unknown>) => void;
}

export default function StoryboardTab(props: Props) {
  const shots = () => props.version.shots;
  const [draggingId, setDraggingId] = createSignal<string | null>(null);
  const [dropTarget, setDropTarget] = createSignal<string | null>(null);

  const clearDrag = () => {
    setDraggingId(null);
    setDropTarget(null);
  };

  const startDrag = (event: DragEvent, id: string) => {
    if (props.busy) {
      event.preventDefault();
      return;
    }
    const target = event.target as HTMLElement;
    if (target.closest("button, input, textarea")) {
      event.preventDefault();
      return;
    }
    setDraggingId(id);
    if (event.dataTransfer) {
      event.dataTransfer.effectAllowed = "move";
      event.dataTransfer.setData("text/plain", id);
    }
  };

  const dragOver = (event: DragEvent, id: string) => {
    if (!draggingId() || draggingId() === id) return;
    event.preventDefault();
    setDropTarget(id);
  };

  const dropOn = (event: DragEvent, id: string) => {
    event.preventDefault();
    const from = draggingId();
    if (from && dropTarget() === id) props.onReorder(from, id, false);
    clearDrag();
  };

  const addAfter = () => props.onAdd(props.selectedId);

  return (
    <div class="flex h-full flex-col">
      <div class="mb-3 flex flex-wrap items-center gap-2">
        <span class="text-[12px] font-medium text-text">分镜</span>
        <span class="text-[10px] text-faint">
          {shots().length} 镜 · {totalDuration(shots()).toFixed(1)}s
        </span>
        <span class="hidden text-[10px] text-faint sm:inline">拖拽排序 · 双击描述编辑</span>
        <div class="ml-auto flex items-center gap-1.5">
          <Button size="sm" variant="primary" disabled={props.busy} onClick={addAfter}>
            ＋ 添加镜头
          </Button>
        </div>
      </div>

      <div class="min-h-0 flex-1 overflow-auto">
        <Show
          when={shots().length > 0}
          fallback={<div class="py-14 text-center text-[11px] text-faint">还没有分镜，先确认脚本再添加镜头。</div>}
        >
          <div class="grid gap-2.5 pb-3 sm:grid-cols-2 xl:grid-cols-3">
            <For each={shots()}>
              {(shot) => (
                <ShotCard
                  shot={shot}
                  selected={props.selectedId === shot.id}
                  dragging={draggingId() === shot.id}
                  dropBefore={dropTarget() === shot.id}
                  busy={props.busy}
                  onSelect={() => props.onSelect(shot.id)}
                  onDragStart={(event) => startDrag(event, shot.id)}
                  onDragOver={(event) => dragOver(event, shot.id)}
                  onDrop={(event) => dropOn(event, shot.id)}
                  onDragEnd={clearDrag}
                  onUpdate={(fields) => props.onUpdate(shot.id, fields)}
                  onDelete={() => props.onDelete(shot.id)}
                />
              )}
            </For>

            <button
              type="button"
              class={`grid min-h-[250px] place-items-center rounded-lg border border-dashed bg-surface/30 text-faint transition-colors hover:border-line hover:bg-surface ${
                dropTarget() === "__end__" ? "border-accent/70" : "border-line"
              }`}
              disabled={props.busy}
              onClick={addAfter}
              onDragOver={(event) => {
                if (!draggingId()) return;
                event.preventDefault();
                setDropTarget("__end__");
              }}
              onDrop={(event) => {
                event.preventDefault();
                const from = draggingId();
                const last = shots().at(-1);
                if (from && last) props.onReorder(from, last.id, true);
                clearDrag();
              }}
            >
              <div class="text-center">
                <div class="text-[20px]">＋</div>
                <div class="mt-1 text-[10.5px]">添加镜头</div>
                <div class="mt-0.5 text-[9.5px] text-faint">插入到选中镜之后；拖到这里移到末尾</div>
              </div>
            </button>
          </div>
        </Show>
      </div>

      <div class="mt-2 shrink-0">
        <div class="flex h-2 gap-0.5 overflow-hidden rounded-full bg-surface-2">
          <For each={shots()}>
            {(shot) => (
              <button
                type="button"
                class={`h-full rounded-full transition-colors ${
                  props.selectedId === shot.id ? "bg-accent" : "bg-[#2a3145] hover:bg-[#3a435c]"
                }`}
                style={{ flex: `${shot.duration_s} 1 0` }}
                title={`${shot.id} · ${shot.start_s.toFixed(1)}–${shot.end_s.toFixed(1)}s`}
                onClick={() => props.onSelect(shot.id)}
              />
            )}
          </For>
        </div>
        <div class="mt-1 flex justify-between font-mono text-[9px] text-faint">
          <span>0:00.0</span>
          <span>{timecode(totalDuration(shots()))}</span>
        </div>
      </div>
    </div>
  );
}

interface CardProps {
  shot: Shot;
  selected: boolean;
  dragging: boolean;
  dropBefore: boolean;
  busy: boolean;
  onSelect: () => void;
  onDragStart: (event: DragEvent) => void;
  onDragOver: (event: DragEvent) => void;
  onDrop: (event: DragEvent) => void;
  onDragEnd: () => void;
  onUpdate: (fields: Record<string, unknown>) => void;
  onDelete: () => void;
}

function ShotCard(props: CardProps) {
  const status = () => SHOT_STATUS[props.shot.status] ?? { label: props.shot.status, tone: "neutral" as const };
  const [editing, setEditing] = createSignal(false);
  const [draft, setDraft] = createSignal(props.shot.description);
  const [duration, setDuration] = createSignal(props.shot.duration_s.toFixed(1));
  const [confirmingDelete, setConfirmingDelete] = createSignal(false);

  createEffect(() => setDuration(props.shot.duration_s.toFixed(1)));
  createEffect(() => {
    if (!editing()) setDraft(props.shot.description);
  });

  const openEditor = () => {
    setDraft(props.shot.description);
    setEditing(true);
  };

  const saveDescription = () => {
    const text = draft().trim();
    setEditing(false);
    if (text !== props.shot.description) props.onUpdate({ description: text });
  };

  const commitDuration = () => {
    const value = Number(duration());
    if (!Number.isFinite(value) || value < 0.2) {
      setDuration(props.shot.duration_s.toFixed(1));
      return;
    }
    const rounded = Math.round(value * 10) / 10;
    if (Math.abs(rounded - props.shot.duration_s) > 0.05) props.onUpdate({ duration_s: rounded });
  };

  return (
    <div
      draggable={!props.busy}
      class={`relative cursor-grab rounded-lg border bg-[#0b0e15] transition-colors active:cursor-grabbing ${
        props.selected ? "border-accent/70" : "border-line-soft hover:border-line"
      } ${props.dragging ? "opacity-45" : ""}`}
      onClick={props.onSelect}
      onDragStart={props.onDragStart}
      onDragOver={props.onDragOver}
      onDrop={props.onDrop}
      onDragEnd={props.onDragEnd}
    >
      <Show when={props.dropBefore}>
        <span class="absolute -left-[7px] bottom-0 top-0 z-10 w-1 rounded-full bg-accent shadow-[0_0_10px_rgba(224,51,138,0.75)]" />
      </Show>

      <div class="relative overflow-hidden rounded-t-lg bg-[#0b0e15]" style={{ "aspect-ratio": "16 / 9" }}>
        <Show
          when={coverUrl(props.shot.preview)}
          fallback={
            <div
              class="grid h-full w-full place-items-center"
              style={{ "background-image": "radial-gradient(circle at 35% 20%, #241a2c, #0b0e15 65%)" }}
            >
              <div class="text-center">
                <div class="text-[18px] text-white/12">▣</div>
                <div class="mt-0.5 text-[9px] text-white/20">无预览</div>
              </div>
            </div>
          }
        >
          <img src={coverUrl(props.shot.preview)!} alt="" class="absolute inset-0 h-full w-full object-cover" loading="lazy" />
          <img
            src={coverUrl(props.shot.preview)!}
            alt=""
            class="absolute inset-0 m-auto h-full w-auto max-w-full object-contain"
            loading="lazy"
          />
        </Show>
        <div class="pointer-events-none absolute inset-0 bg-gradient-to-t from-black/55 to-transparent" />
        <div class="absolute left-1.5 top-1.5 flex items-center gap-1">
          <span class="rounded bg-black/45 px-1 py-px font-mono text-[9px] text-white/75">
            {String(props.shot.index).padStart(2, "0")}
          </span>
          <Badge tone={status().tone}>{status().label}</Badge>
        </div>
        <div class="absolute bottom-1.5 left-1.5 right-1.5 flex items-center gap-1 text-[9.5px] text-white/70">
          <span>{props.shot.role}</span>
          <span>·</span>
          <span class="font-mono">
            {props.shot.start_s.toFixed(1)}–{props.shot.end_s.toFixed(1)}s
          </span>
          <Show when={props.shot.locked}>
            <span class="ml-auto">🔒</span>
          </Show>
        </div>
      </div>

      <div class="space-y-1.5 p-2">
        <div class="flex items-center gap-1.5">
          <span class="cursor-grab text-[10px] tracking-tight text-faint" title="拖拽排序">⋮⋮</span>
          <span class="font-mono text-[9.5px] text-faint">{props.shot.role}</span>
          <div class="ml-auto flex items-center gap-1">
            <input
              type="number"
              min="0.2"
              step="0.1"
              value={duration()}
              disabled={props.busy}
              class="h-5 w-11 rounded border border-line bg-transparent px-1 text-right font-mono text-[9.5px] text-dim outline-none focus:border-accent/60"
              onClick={(event) => event.stopPropagation()}
              onInput={(event) => setDuration(event.currentTarget.value)}
              onBlur={commitDuration}
              onKeyDown={(event) => {
                if (event.key === "Enter") event.currentTarget.blur();
              }}
            />
            <span class="text-[9px] text-faint">s</span>
          </div>
        </div>

        <Show
          when={!editing()}
          fallback={
            <textarea
              class="h-[54px] w-full resize-none rounded border border-accent/40 bg-[#0b0e13] p-1 text-[10px] leading-4 text-text outline-none"
              value={draft()}
              autofocus
              onClick={(event) => event.stopPropagation()}
              onInput={(event) => setDraft(event.currentTarget.value)}
              onBlur={saveDescription}
              onKeyDown={(event) => {
                if (event.key === "Escape") setEditing(false);
                if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
                  event.preventDefault();
                  saveDescription();
                }
              }}
            />
          }
        >
          <div
            class="line-clamp-3 min-h-[54px] cursor-text text-[10px] leading-[18px] text-dim"
            title="双击编辑描述"
            onDblClick={(event) => {
              event.stopPropagation();
              openEditor();
            }}
          >
            {props.shot.description || "（空描述，双击编辑）"}
          </div>
        </Show>

        <div class="flex items-center gap-1">
          <button
            type="button"
            class="rounded px-1 py-0.5 text-[9.5px] text-faint hover:bg-surface-2 hover:text-text"
            onClick={(event) => {
              event.stopPropagation();
              props.onUpdate({ locked: !props.shot.locked });
            }}
          >
            {props.shot.locked ? "解锁" : "锁定"}
          </button>
          <button
            type="button"
            class="rounded px-1 py-0.5 text-[9.5px] text-faint hover:bg-surface-2 hover:text-text"
            onClick={(event) => {
              event.stopPropagation();
              openEditor();
            }}
          >
            改描述
          </button>
          <Show
            when={confirmingDelete()}
            fallback={
              <button
                type="button"
                class="ml-auto rounded px-1 py-0.5 text-[9.5px] text-faint hover:bg-bad/10 hover:text-bad disabled:opacity-30"
                disabled={props.busy}
                onClick={(event) => {
                  event.stopPropagation();
                  setConfirmingDelete(true);
                }}
              >
                删除
              </button>
            }
          >
            <button
              type="button"
              class="ml-auto rounded px-1 py-0.5 text-[9.5px] text-bad hover:bg-bad/10 disabled:opacity-30"
              disabled={props.busy}
              onClick={(event) => {
                event.stopPropagation();
                props.onDelete();
              }}
            >
              确认删除
            </button>
            <button
              type="button"
              class="rounded px-1 py-0.5 text-[9.5px] text-faint hover:bg-surface-2 hover:text-text"
              onClick={(event) => {
                event.stopPropagation();
                setConfirmingDelete(false);
              }}
            >
              取消
            </button>
          </Show>
        </div>
      </div>
    </div>
  );
}

