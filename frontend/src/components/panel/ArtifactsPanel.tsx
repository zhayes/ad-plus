import { For, Show, createSignal } from "solid-js";
import type { Artifact } from "../../lib/types";
import { basename, fmtBytes } from "../../lib/format";
import Dialog from "../ui/Dialog";
import { CountBadge } from "../ui/Badge";
import Icon from "../ui/Icon";

interface Props {
  artifacts: Artifact[];
}

/** Media first; code files stay behind a toggle — non-technical users don't need them. */
export default function ArtifactsPanel(props: Props) {
  const [showCode, setShowCode] = createSignal(false);
  const [preview, setPreview] = createSignal<Artifact | null>(null);
  const media = () => props.artifacts.filter((a) => a.kind !== "code");
  const code = () => props.artifacts.filter((a) => a.kind === "code");

  return (
    <div class="px-2 pt-3">
      <div class="flex items-center px-1 pb-1 text-[11px] text-dim">
        <b class="font-semibold">产物</b>
        <CountBadge value={props.artifacts.length} />
      </div>

      <Show when={props.artifacts.length === 0}>
        <div class="px-1 py-2 text-[11px] text-faint">还没有产物</div>
      </Show>

      <div class="grid grid-cols-2 gap-2">
        <For each={media()}>
          {(artifact) => (
            <div class="overflow-hidden rounded-lg border border-line-soft bg-surface-2">
              <Show
                when={artifact.kind === "video"}
                fallback={
                  <Show
                    when={artifact.kind === "image"}
                    fallback={<div class="grid h-[74px] place-items-center text-[10px] text-faint">{artifact.kind}</div>}
                  >
                    <img
                      src={`/api/media?path=${encodeURIComponent(artifact.path)}`}
                      alt=""
                      class="h-[74px] w-full cursor-pointer bg-[#05060a] object-cover"
                      onClick={() => setPreview(artifact)}
                    />
                  </Show>
                }
              >
                <div class="relative cursor-pointer" onClick={() => setPreview(artifact)}>
                  <img
                    src={`/api/thumb?path=${encodeURIComponent(artifact.path)}`}
                    alt=""
                    loading="lazy"
                    class="h-[74px] w-full bg-[#05060a] object-cover ring-1 ring-inset ring-line-soft"
                  />
                  <span class="pointer-events-none absolute inset-0 grid place-items-center">
                    <span class="grid h-6 w-6 place-items-center rounded-full bg-black/55 text-white">
                      <Icon name="play" size={11} />
                    </span>
                  </span>
                </div>
              </Show>
              <div class="truncate px-1.5 py-1 text-[10.5px] text-dim" title={artifact.path}>
                {basename(artifact.path)}
              </div>
              <div class="px-1.5 pb-1 font-mono text-[9.5px] text-faint">{fmtBytes(artifact.bytes)}</div>
            </div>
          )}
        </For>
      </div>

      <Dialog open={!!preview()} onOpenChange={(open) => !open && setPreview(null)} title={basename(preview()?.path)}>
        <Show when={preview()}>
          {(artifact) => (
            <Show
              when={artifact().kind === "video"}
              fallback={
                <img
                  src={`/api/media?path=${encodeURIComponent(artifact().path)}`}
                  alt=""
                  class="mx-auto max-h-[70vh] rounded-lg object-contain"
                />
              }
            >
              <video
                src={`/api/media?path=${encodeURIComponent(artifact().path)}`}
                controls
                autoplay
                class="mx-auto max-h-[70vh] rounded-lg"
              />
            </Show>
          )}
        </Show>
      </Dialog>

      <Show when={code().length > 0}>
        <button class="mt-2 px-1 text-[10.5px] text-faint hover:text-dim" onClick={() => setShowCode((v) => !v)}>
          工程文件 {code().length} 个 · {showCode() ? "隐藏" : "显示"}
        </button>
        <Show when={showCode()}>
          <For each={code()}>
            {(artifact) => (
              <div class="truncate px-1 py-0.5 font-mono text-[10px] text-faint" title={artifact.path}>
                {basename(artifact.path)}
              </div>
            )}
          </For>
        </Show>
      </Show>
    </div>
  );
}
