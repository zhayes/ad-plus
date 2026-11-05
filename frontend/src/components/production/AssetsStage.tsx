import { For, Show, createSignal } from "solid-js";
import Badge from "../ui/Badge";
import Button from "../ui/Button";
import Icon from "../ui/Icon";
import { endpoints } from "../../lib/api";
import { mediaUrl } from "../../lib/projects";
import type { ProductionView, StageId } from "../../lib/types";

interface Props {
  production: ProductionView;
  onChanged: () => void;
  onAdvanced: (stage: StageId) => void;
}

export default function AssetsStage(props: Props) {
  const [busy, setBusy] = createSignal(false);
  const [error, setError] = createSignal("");

  const approved = () => props.production.approvals?.assets != null;
  const previewed = () => props.production.shots.filter((shot) => shot.preview).length;
  const local = () => props.production.route.id === "local_motion";

  const approve = async () => {
    setBusy(true);
    setError("");
    try {
      await endpoints.approveStage(props.production.project.id, "assets");
      props.onChanged();
      props.onAdvanced("compose");
    } catch (err) {
      setError(err instanceof Error ? err.message : "确认素材失败");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div class="h-full overflow-auto p-4 sm:p-5">
      <div class="mx-auto w-full max-w-[1180px]">
        <div class="mb-4 flex flex-wrap items-end gap-2">
          <div>
            <div class="flex items-center gap-2">
              <h1 class="text-[16px] font-semibold text-text">素材</h1>
              <Badge tone={approved() ? "ok" : "accent"}>{approved() ? "已确认" : "准备中"}</Badge>
            </div>
            <p class="mt-1 text-[11.5px] text-faint">
              {local() ? "本地动效路线以程序化画面为主；这里确认每镜的画面方向和素材状态。" : "确认每个镜头的素材、来源与可用性。"}
            </p>
          </div>
          <div class="ml-auto text-[10px] text-faint">{previewed()} / {props.production.shots.length} 镜有预览</div>
        </div>

        <Show when={error()}>
          <div class="mb-3 rounded-lg border border-bad/30 bg-bad/5 px-3 py-2 text-[11px] text-bad">{error()}</div>
        </Show>

        <Show
          when={props.production.shots.length > 0}
          fallback={
            <div class="rounded-xl border border-dashed border-line bg-surface/40 py-16 text-center">
              <div class="text-[12px] text-dim">还没有镜头</div>
              <div class="mt-1 text-[10.5px] text-faint">先去分镜添加镜头，再回来准备素材。</div>
              <Button class="mt-3" size="sm" onClick={() => props.onAdvanced("scene")}>去分镜</Button>
            </div>
          }
        >
          <div class="grid gap-3 pb-4 sm:grid-cols-2 xl:grid-cols-3">
            <For each={props.production.shots}>
              {(shot) => (
                <div class="overflow-hidden rounded-xl border border-line-soft bg-surface">
                  <div class="relative bg-[#0b0e15]" style={{ "aspect-ratio": "16 / 9" }}>
                    <Show
                      when={shot.preview}
                      fallback={
                        <div class="flex h-full flex-col items-center justify-center gap-1.5 text-faint">
                          <Icon name="image" size={20} />
                          <span class="text-[9.5px]">{local() ? "动效镜头，无需外部素材" : "待生成"}</span>
                        </div>
                      }
                    >
                      <img src={mediaUrl(shot.preview) ?? undefined} alt="" class="h-full w-full object-cover" />
                    </Show>
                    <span class="absolute left-2 top-2"><Badge tone="neutral">{shot.id}</Badge></span>
                  </div>
                  <div class="p-2.5">
                    <div class="flex items-center gap-2">
                      <span class="text-[11px] text-text">{shot.role}</span>
                      <span class="ml-auto font-mono text-[9.5px] text-faint">{shot.duration_s.toFixed(1)}s</span>
                    </div>
                    <div class="mt-1 line-clamp-2 text-[10.5px] leading-5 text-faint">{shot.description || "（空描述）"}</div>
                    <div class="mt-1.5 flex items-center gap-1.5 text-[9.5px] text-faint">
                      <span class="rounded border border-line px-1 py-px">{local() ? "动效" : "生成/素材"}</span>
                      <Show when={shot.preview}><span class="text-ok">已有预览</span></Show>
                    </div>
                  </div>
                </div>
              )}
            </For>
          </div>
        </Show>

        <div class="sticky bottom-0 flex flex-wrap items-center gap-2 border-t border-line-soft bg-bg/95 py-3 backdrop-blur">
          <Show when={!approved()} fallback={<Button size="sm" variant="primary" onClick={() => props.onAdvanced("compose")}>看成片</Button>}>
            <Button size="sm" variant="primary" loading={busy()} disabled={props.production.shots.length === 0} onClick={() => void approve()}>
              素材通过，开始合成
            </Button>
            <span class="text-[10px] text-faint">确认后进入成片；不会自动渲染。</span>
          </Show>
        </div>
      </div>
    </div>
  );
}
