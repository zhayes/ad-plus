import { For, Show, createEffect } from "solid-js";
import { coverUrl, mediaUrl } from "../../lib/projects";
import type { Version } from "../../lib/types";

interface Props {
  version: Version | null;
  selectedId: string | null;
  onSelect: (id: string) => void;
}

export default function CanvasTab(props: Props) {
  let video: HTMLVideoElement | undefined;
  const shots = () => props.version?.shots ?? [];
  const selected = () => shots().find((shot) => shot.id === props.selectedId);
  const renderPath = () => props.version?.render?.path;

  createEffect(() => {
    const shot = selected();
    if (!video || !shot) return;
    if (Math.abs(video.currentTime - shot.start_s) > 0.2) {
      video.currentTime = shot.start_s;
    }
  });

  const syncSelection = () => {
    if (!video) return;
    const time = video.currentTime;
    const shot = shots().find((item) => time >= item.start_s && time < item.end_s);
    if (shot && shot.id !== props.selectedId) props.onSelect(shot.id);
  };

  return (
    <div class="flex h-full flex-col">
      <div class="grid min-h-0 flex-1 place-items-center">
        <Show
          when={renderPath()}
          fallback={
            <div class="max-w-[420px] text-center">
              <div class="mx-auto flex w-[180px] items-center justify-center rounded-xl border border-dashed border-line bg-[#0b0e15]" style={{ "aspect-ratio": "9 / 16" }}>
                <div class="text-center">
                  <div class="text-[20px] text-white/15">▣</div>
                  <div class="mt-1 text-[10px] text-white/30">{shots().length} 镜</div>
                </div>
              </div>
              <div class="mt-3 text-[12px] text-dim">还没有成片</div>
              <p class="mt-1 text-[10.5px] leading-5 text-faint">
                方案确认后生成；现在可以在「分镜」里排镜头、改时长和描述。
              </p>
            </div>
          }
        >
          <div
            class="relative flex w-[min(330px,100%)] items-center justify-center overflow-hidden rounded-xl border border-line bg-black"
            style={{ "aspect-ratio": "9 / 16", "max-height": "min(600px, 100%)" }}
          >
            <video
              ref={video}
              controls
              class="h-full w-full object-contain"
              src={mediaUrl(renderPath())!}
              poster={coverUrl(props.version?.render?.poster || renderPath()) ?? undefined}
              onTimeUpdate={syncSelection}
            />
          </div>
        </Show>
      </div>

      <Show when={shots().length > 0}>
        <div class="mx-auto mt-2 w-full max-w-[680px] shrink-0 border-t border-line-soft pt-2">
          <div class="flex justify-center gap-1 overflow-x-auto pb-1">
            <For each={shots()}>
              {(shot) => (
                <button
                  type="button"
                  class={`group w-[56px] shrink-0 overflow-hidden rounded border text-left transition-colors ${
                    props.selectedId === shot.id ? "border-accent/70" : "border-line-soft hover:border-line"
                  }`}
                  title={`${shot.id} · ${shot.start_s.toFixed(1)}–${shot.end_s.toFixed(1)}s`}
                  onClick={() => {
                    props.onSelect(shot.id);
                    if (video) video.currentTime = shot.start_s;
                  }}
                >
                  <div class="relative bg-[#0b0e15]" style={{ "aspect-ratio": "9 / 16" }}>
                    <Show
                      when={coverUrl(shot.preview)}
                      fallback={
                        <div class="grid h-full w-full place-items-center font-mono text-[10px] text-white/25">
                          {String(shot.index).padStart(2, "0")}
                        </div>
                      }
                    >
                      <img src={coverUrl(shot.preview)!} alt="" class="h-full w-full object-cover" loading="lazy" />
                    </Show>
                  </div>
                  <div class="flex items-center justify-between px-1 py-0.5 font-mono text-[8px] text-faint">
                    <span>{String(shot.index).padStart(2, "0")}</span>
                    <span>{shot.duration_s.toFixed(1)}s</span>
                  </div>
                </button>
              )}
            </For>
          </div>

          <Show when={selected()}>
            <div class="mt-1 flex items-center gap-2 text-[10px] text-faint">
              <span class="font-mono text-dim">{selected()!.id}</span>
              <span>
                {selected()!.start_s.toFixed(1)}–{selected()!.end_s.toFixed(1)}s
              </span>
              <span>· {selected()!.role}</span>
              <span class="min-w-0 flex-1 truncate">{selected()!.description}</span>
            </div>
          </Show>
        </div>
      </Show>
    </div>
  );
}
