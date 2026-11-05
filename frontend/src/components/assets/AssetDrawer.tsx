import { Show, createEffect, createSignal, on, onCleanup, onMount } from "solid-js";
import { useNavigate } from "@solidjs/router";
import Badge from "../ui/Badge";
import Button from "../ui/Button";
import Select from "../ui/Select";
import { endpoints } from "../../lib/api";
import { fmtBytes } from "../../lib/format";
import { kindLabel, sourceLabel } from "../../lib/assets";
import { mediaUrl } from "../../lib/projects";
import { projects, refreshProjects } from "../../stores/projects";
import type { Asset, ProjectDetail } from "../../lib/types";

interface Props {
  assetId: string | null;
  onClose: () => void;
  onChanged: () => void;
}

export default function AssetDrawer(props: Props) {
  const navigate = useNavigate();
  const [asset, setAsset] = createSignal<Asset | null>(null);
  const [loading, setLoading] = createSignal(false);
  const [error, setError] = createSignal("");
  const [mode, setMode] = createSignal<"reference" | "replace">("reference");
  const [targetProject, setTargetProject] = createSignal("");
  const [detail, setDetail] = createSignal<ProjectDetail | null>(null);
  const [targetShot, setTargetShot] = createSignal("");
  const [busy, setBusy] = createSignal(false);
  const [message, setMessage] = createSignal("");

  const shots = () => detail()?.current_version?.shots ?? [];

  const load = async () => {
    const id = props.assetId;
    if (!id) {
      setAsset(null);
      return;
    }
    setLoading(true);
    setError("");
    setMessage("");
    try {
      const data = await endpoints.asset(id);
      setAsset(data.asset);
    } catch (err) {
      setError(err instanceof Error ? err.message : "素材加载失败");
    } finally {
      setLoading(false);
    }
  };

  createEffect(
    on(
      () => props.assetId,
      () => {
        void load();
      },
    ),
  );

  createEffect(
    on(
      () => props.assetId,
      (id) => {
        if (!id) return;
        void refreshProjects();
        if (!targetProject() && projects().length > 0) setTargetProject(projects()[0].id);
      },
    ),
  );

  createEffect(
    on(
      () => projects().length,
      () => {
        if (!targetProject() && projects().length > 0) setTargetProject(projects()[0].id);
      },
    ),
  );

  createEffect(
    on(
      () => targetProject(),
      async (id) => {
        if (!id) {
          setDetail(null);
          setTargetShot("");
          return;
        }
        try {
          const data = await endpoints.project(id);
          setDetail(data);
          setTargetShot(data.current_version?.shots[0]?.id ?? "");
        } catch {
          setDetail(null);
        }
      },
    ),
  );

  onMount(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") props.onClose();
    };
    window.addEventListener("keydown", onKey);
    onCleanup(() => window.removeEventListener("keydown", onKey));
  });

  const reuse = async () => {
    const current = asset();
    if (!current) return;
    if (!targetProject()) {
      setError("先选一个项目");
      return;
    }
    if (mode() === "replace" && !targetShot()) {
      setError("先选一个镜头");
      return;
    }
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const result = await endpoints.reuseAsset(current.id, {
        project_id: targetProject(),
        shot_id: mode() === "replace" ? targetShot() : undefined,
        mode: mode(),
      });
      props.onChanged();
      if (mode() === "replace" && result.shot) {
        setMessage(`已替换 ${result.shot.id} · ${result.shot.description || "镜头已更新"}`);
      } else {
        setMessage("已复制到项目素材，可在脚本/分镜里引用。");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "复用失败");
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    const current = asset();
    if (!current) return;
    if (!window.confirm(`删除「${current.name}」？`)) return;
    setBusy(true);
    try {
      await endpoints.deleteAsset(current.id);
      props.onChanged();
      props.onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "删除失败");
    } finally {
      setBusy(false);
    }
  };

  const reveal = async () => {
    const current = asset();
    if (!current) return;
    try {
      await endpoints.reveal(current.path);
    } catch (err) {
      setError(err instanceof Error ? err.message : "无法打开 Finder");
    }
  };

  const projectOptions = () => projects().map((project) => ({ value: project.id, label: project.title }));
  const shotOptions = () => shots().map((shot) => ({ value: shot.id, label: `${shot.index}. ${shot.role} · ${shot.description.slice(0, 24)}` }));

  return (
    <Show when={props.assetId}>
      <div class="fixed inset-0 z-40" role="dialog" aria-modal="true">
        <div class="absolute inset-0 bg-black/55 backdrop-blur-sm" onClick={props.onClose} />
        <aside class="absolute right-0 top-0 flex h-full w-[min(380px,calc(100vw-16px))] flex-col border-l border-line-soft bg-surface shadow-2xl">
          <div class="flex h-11 shrink-0 items-center gap-2 border-b border-line-soft px-3">
            <span class="text-[12px] font-semibold">素材详情</span>
            <div class="ml-auto">
              <button type="button" class="rounded-md px-2 py-1 text-[11px] text-faint hover:bg-surface-2 hover:text-text" onClick={props.onClose}>
                关闭
              </button>
            </div>
          </div>

          <div class="min-h-0 flex-1 space-y-3 overflow-auto p-3.5">
            <Show when={!loading()} fallback={<div class="py-12 text-center text-[11px] text-faint">加载中…</div>}>
              <Show
                when={asset()}
                fallback={
                  <div class="py-10 text-center text-[11px] text-faint">
                    {error() || "素材不存在"}
                  </div>
                }
              >
                <div class="overflow-hidden rounded-lg border border-line-soft bg-[#0b0e15]">
                  <Show when={asset()!.kind === "image"}>
                    <img src={mediaUrl(asset()!.path) ?? undefined} alt="" class="max-h-[280px] w-full object-contain" />
                  </Show>
                  <Show when={asset()!.kind === "video"}>
                    <video controls class="max-h-[280px] w-full object-contain" src={mediaUrl(asset()!.path) ?? undefined} />
                  </Show>
                  <Show when={asset()!.kind === "audio"}>
                    <div class="p-4">
                      <div class="mb-2 text-center text-[28px] text-white/20">♫</div>
                      <audio controls class="w-full" src={mediaUrl(asset()!.path) ?? undefined} />
                    </div>
                  </Show>
                </div>

                <div>
                  <div class="flex items-center gap-1.5">
                    <span class="min-w-0 flex-1 truncate text-[12.5px] font-medium text-text">{asset()!.name}</span>
                    <Badge tone="neutral">{kindLabel(asset()!.kind)}</Badge>
                  </div>
                  <div class="mt-1 flex flex-wrap items-center gap-1.5 text-[10px] text-faint">
                    <span>{sourceLabel(asset()!.source)}</span>
                    <span>·</span>
                    <span>{fmtBytes(asset()!.bytes)}</span>
                    <Show when={asset()!.width && asset()!.height}>
                      <span>·</span>
                      <span>{asset()!.width}×{asset()!.height}</span>
                    </Show>
                    <Show when={asset()!.duration_s}>
                      <span>·</span>
                      <span>{asset()!.duration_s}s</span>
                    </Show>
                    <Show when={asset()!.project_id}>
                      <span>·</span>
                      <span>{asset()!.project_id}</span>
                    </Show>
                  </div>
                  <div class="mt-1 break-all text-[9.5px] text-faint">{asset()!.path}</div>
                </div>

                <div class="rounded-lg border border-line-soft p-2.5">
                  <div class="flex items-center gap-2">
                    <span class="text-[10px] tracking-wide text-faint">用到项目</span>
                    <div class="ml-auto flex gap-1">
                      <button
                        type="button"
                        class={`rounded border px-1.5 py-0.5 text-[9.5px] ${
                          mode() === "reference" ? "border-accent/50 text-text" : "border-line text-faint"
                        }`}
                        onClick={() => setMode("reference")}
                      >
                        用作参考
                      </button>
                      <button
                        type="button"
                        class={`rounded border px-1.5 py-0.5 text-[9.5px] ${
                          mode() === "replace" ? "border-accent/50 text-text" : "border-line text-faint"
                        }`}
                        disabled={asset()!.kind === "audio"}
                        onClick={() => setMode("replace")}
                      >
                        替换镜头
                      </button>
                    </div>
                  </div>

                  <div class="mt-2 space-y-2">
                    <Select value={targetProject()} options={projectOptions()} onChange={setTargetProject} variant="pill" placeholder="选择项目" />
                    <Show when={mode() === "replace"}>
                      <Select value={targetShot()} options={shotOptions()} onChange={setTargetShot} variant="pill" placeholder="选择镜头" />
                    </Show>
                    <Button size="sm" variant="primary" loading={busy()} disabled={!targetProject() || (mode() === "replace" && !targetShot())} onClick={() => void reuse()}>
                      {mode() === "replace" ? "替换这个镜头" : "复制为项目参考"}
                    </Button>
                  </div>

                  <Show when={message()}>
                    <div class="mt-2 flex items-center gap-2 text-[10px] text-ok">
                      <span class="min-w-0 flex-1">{message()}</span>
                      <button
                        type="button"
                        class="shrink-0 text-accent underline"
                        onClick={() => {
                          props.onClose();
                          navigate(`/studio/${targetProject()}/storyboard`);
                        }}
                      >
                        打开分镜
                      </button>
                    </div>
                  </Show>
                </div>

                <div class="flex items-center gap-1.5 border-t border-line-soft pt-3">
                  <Button size="sm" variant="ghost" onClick={() => void reveal()}>
                    在 Finder 显示
                  </Button>
                  <Show when={asset()!.source !== "render"}>
                    <Button size="sm" variant="danger" class="ml-auto" loading={busy()} onClick={() => void remove()}>
                      删除
                    </Button>
                  </Show>
                </div>

                <Show when={error()}>
                  <div class="text-[10.5px] text-bad">{error()}</div>
                </Show>
              </Show>
            </Show>
          </div>
        </aside>
      </div>
    </Show>
  );
}
