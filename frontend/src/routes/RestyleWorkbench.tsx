import { For, Show, createMemo, createSignal, onCleanup, onMount } from "solid-js";
import { useNavigate, useParams } from "@solidjs/router";
import AppShellV2 from "../components/layout/AppShellV2";
import Badge from "../components/ui/Badge";
import Button from "../components/ui/Button";
import Icon from "../components/ui/Icon";
import { endpoints } from "../lib/api";
import { mediaUrl } from "../lib/projects";
import type { Job, RestyleDetail, RestyleShot } from "../lib/types";

const LEVELS = [
  { id: "light", label: "轻改" },
  { id: "recommended", label: "推荐" },
  { id: "all", label: "全改" },
];

export default function RestyleWorkbench() {
  const params = useParams();
  const navigate = useNavigate();
  const id = () => params.id ?? "";
  const [detail, setDetail] = createSignal<RestyleDetail | null>(null);
  const [selectedId, setSelectedId] = createSignal<string | null>(null);
  const [loading, setLoading] = createSignal(true);
  const [busy, setBusy] = createSignal(false);
  const [error, setError] = createSignal("");
  const [notice, setNotice] = createSignal("");
  const [job, setJob] = createSignal<Job | null>(null);
  let video: HTMLVideoElement | undefined;
  let timer: ReturnType<typeof setTimeout> | undefined;

  const blueprint = () => detail()?.blueprint ?? null;
  const plan = () => detail()?.plan ?? null;
  const shots = () => blueprint()?.shots ?? [];
  const selected = createMemo<RestyleShot | null>(
    () => shots().find((shot) => shot.id === selectedId()) ?? null,
  );

  const flash = (text: string) => {
    setNotice(text);
    if (timer) clearTimeout(timer);
    timer = setTimeout(() => setNotice(""), 3000);
  };

  const load = async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      const data = await endpoints.restyle(id());
      setDetail(data);
      setSelectedId((current) => current ?? data.blueprint?.shots?.[0]?.id ?? null);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载失败");
    } finally {
      if (!silent) setLoading(false);
    }
  };

  onMount(() => void load());
  onCleanup(() => {
    if (timer) clearTimeout(timer);
  });

  const poll = (jobId: string) => {
    const tick = async () => {
      try {
        const data = await endpoints.jobs(id());
        const current = (data.jobs ?? []).find((row) => row.id === jobId);
        if (!current) return;
        setJob(current);
        if (current.status === "done") {
          setJob(null);
          await load(true);
          flash("读片完成");
          return;
        }
        if (["failed", "cancelled", "interrupted"].includes(current.status)) {
          setJob(null);
          setError(current.error || "读片失败");
          return;
        }
        timer = setTimeout(tick, 900);
      } catch {
        timer = setTimeout(tick, 1500);
      }
    };
    void tick();
  };

  const analyze = async () => {
    setBusy(true);
    setError("");
    try {
      const data = await endpoints.analyzeRestyle(id());
      setJob(data.job);
      poll(data.job.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "读片失败");
    } finally {
      setBusy(false);
    }
  };

  const patchPlan = async (patch: Record<string, unknown>) => {
    const current = plan();
    if (!current) return;
    try {
      const data = await endpoints.saveRestylePlan(id(), current.revision, patch);
      setDetail((previous) => (previous ? { ...previous, plan: data.plan } : previous));
      flash("已保存");
    } catch (err) {
      const message = err instanceof Error ? err.message : "保存失败";
      setError(message);
      if (message.includes("revision")) await load(true);
    }
  };

  const setLevel = (level: string) => patchPlan({ change_level: level });
  const setScene = (sceneId: string, mode: string) =>
    patchPlan({ scenes: { [sceneId]: { mode } } });

  const selectShot = (shot: RestyleShot) => {
    setSelectedId(shot.id);
    if (video) {
      video.currentTime = Math.max(0, shot.start_s + 0.04);
      video.pause();
    }
  };

  const statusText = () => {
    if (job()) return `读片中 · ${Math.round((job()!.progress || 0) * 100)}%`;
    if (!blueprint()) return "待读片";
    return `${shots().length} 镜 · ${(detail()?.source?.probe?.duration_s ?? 0).toFixed(1)}s`;
  };

  return (
    <AppShellV2
      module="restyle"
      context={
        <div class="flex min-w-0 items-center gap-2">
          <button
            type="button"
            class="grid h-7 w-7 place-items-center rounded-md text-faint hover:bg-surface-2 hover:text-text"
            title="返回改写"
            onClick={() => navigate("/restyle")}
          >
            <Icon name="arrow-left" size={15} />
          </button>
          <span class="h-4 w-4 shrink-0 rounded bg-gradient-to-br from-violet to-accent" />
          <span class="max-w-[220px] truncate text-[12.5px] font-medium text-text">
            {detail()?.project.title ?? "改写"}
          </span>
          <Badge tone="accent">改写</Badge>
          <span class="hidden items-center gap-1 rounded border border-line px-1.5 py-0.5 text-[9.5px] text-faint sm:flex">
            <Icon name="layers" size={10} />
            逻辑已锁定
          </span>
        </div>
      }
      primary={
        <div class="flex items-center gap-1.5">
          <span class="hidden text-[10px] text-faint md:inline">{statusText()}</span>
          <Button size="sm" variant="ghost" loading={busy()} onClick={() => void analyze()}>
            {blueprint() ? "重新读片" : "开始读片"}
          </Button>
          <Button size="sm" variant="primary" disabled>
            导出
          </Button>
        </div>
      }
      footer="P1 骨架 · 读片 / 计划可用 · 合成在 P2"
    >
      <Show when={!loading()} fallback={<div class="grid h-full place-items-center text-[11px] text-faint">加载中…</div>}>
        <Show
          when={detail()}
          fallback={<div class="grid h-full place-items-center text-[11px] text-bad">{error() || "改写不存在"}</div>}
        >
          <div class="flex h-full min-h-0 flex-col">
            <Show when={error()}>
              <div class="border-b border-bad/30 bg-bad/10 px-3 py-1.5 text-[10.5px] text-bad">{error()}</div>
            </Show>
            <div class="flex min-h-0 flex-1">
              <div class="flex min-w-0 flex-1 flex-col">
                <div class="relative grid min-h-0 flex-1 place-items-center overflow-hidden bg-[#080b11] p-3">
                  <Show
                    when={mediaUrl(detail()?.source?.path)}
                    fallback={<div class="text-[11px] text-faint">没有视频源</div>}
                  >
                    <video
                      ref={video}
                      src={mediaUrl(detail()?.source?.path)!}
                      controls
                      playsinline
                      class="max-h-full max-w-full rounded-lg shadow-2xl"
                    />
                  </Show>
                  <Show when={job()}>
                    <div class="absolute bottom-5 left-1/2 -translate-x-1/2 rounded-full border border-line bg-black/70 px-3 py-1 text-[10px] text-text">
                      读片中 · {Math.round((job()!.progress || 0) * 100)}%
                    </div>
                  </Show>
                </div>

                <div class="shrink-0 border-t border-line-soft bg-surface">
                  <div class="flex items-center gap-2 px-3 py-2">
                    <span class="text-[11px] font-medium text-text">镜头</span>
                    <span class="text-[10px] text-faint">
                      {shots().length ? `${shots().length} 镜` : "还没读片"}
                    </span>
                    <Show when={blueprint()}>
                      <span class="ml-auto text-[10px] text-faint">
                        {blueprint()!.groups.scenes.length} 场景 · {blueprint()!.groups.outfits.length} 造型 ·{" "}
                        {blueprint()!.caption_count ?? 0} 条字幕
                      </span>
                    </Show>
                  </div>
                  <Show
                    when={shots().length > 0}
                    fallback={
                      <div class="px-3 pb-3">
                        <div class="rounded-lg border border-dashed border-line px-3 py-6 text-center text-[10.5px] text-faint">
                          点右上角「开始读片」，先拆镜头、读字幕、分组
                        </div>
                      </div>
                    }
                  >
                    <div class="flex gap-1.5 overflow-x-auto px-3 pb-3">
                      <For each={shots()}>
                        {(shot) => (
                          <button
                            type="button"
                            class={`w-[92px] shrink-0 overflow-hidden rounded-md border text-left transition-colors ${
                              selectedId() === shot.id ? "border-accent bg-accent/10" : "border-line-soft bg-surface-2 hover:border-line"
                            }`}
                            onClick={() => selectShot(shot)}
                          >
                            <div class="relative aspect-[9/16] bg-black/30">
                              <Show when={mediaUrl(shot.keyframe)}>
                                <img src={mediaUrl(shot.keyframe)!} alt="" class="h-full w-full object-cover" loading="lazy" />
                              </Show>
                              <span class="absolute left-1 top-1 rounded bg-black/60 px-1 text-[8.5px] text-white/80">
                                {String(shot.index).padStart(2, "0")}
                              </span>
                              <span class="absolute bottom-1 right-1 rounded bg-black/60 px-1 text-[8px] text-white/70">
                                {shot.duration_s.toFixed(1)}s
                              </span>
                            </div>
                            <div class="truncate px-1.5 py-1 text-[9px] text-dim">
                              {shot.caption?.text || "—"}
                            </div>
                          </button>
                        )}
                      </For>
                    </div>
                  </Show>
                </div>
              </div>

              <aside class="w-[330px] shrink-0 overflow-auto border-l border-line-soft bg-surface p-3">
                <Show when={blueprint()} fallback={<div class="text-[11px] text-faint">读片后这里会出现镜头、分组和计划。</div>}>
                  <div class="rounded-xl border border-line-soft bg-surface-2/60 p-3">
                    <div class="flex items-center gap-2">
                      <span class="text-[10px] text-faint">读片结果</span>
                      <Badge tone="accent">{blueprint()!.video_type === "product_demo" ? "产品演示" : "口播"}</Badge>
                      <span class="ml-auto text-[9.5px] text-faint">{blueprint()!.shots.length} 镜</span>
                    </div>
                    <div class="mt-2 grid grid-cols-3 gap-2 text-center">
                      <div class="rounded-lg border border-line-soft bg-surface px-1 py-1.5">
                        <div class="text-[15px] font-semibold text-text">{blueprint()!.groups.scenes.length}</div>
                        <div class="text-[9px] text-faint">场景</div>
                      </div>
                      <div class="rounded-lg border border-line-soft bg-surface px-1 py-1.5">
                        <div class="text-[15px] font-semibold text-text">{blueprint()!.groups.outfits.length}</div>
                        <div class="text-[9px] text-faint">造型</div>
                      </div>
                      <div class="rounded-lg border border-line-soft bg-surface px-1 py-1.5">
                        <div class="text-[15px] font-semibold text-text">{blueprint()!.caption_count ?? 0}</div>
                        <div class="text-[9px] text-faint">字幕</div>
                      </div>
                    </div>
                    <div class="mt-2 text-[9.5px] leading-5 text-faint">
                      {blueprint()!.suggestions?.reason}
                    </div>
                    <div class="mt-2 flex gap-1.5">
                      <Button size="sm" variant="subtle" onClick={() => void setLevel("recommended")}>
                        按建议执行
                      </Button>
                      <Button size="sm" variant="ghost" onClick={() => void setLevel("all")}>
                        全部可改
                      </Button>
                    </div>
                  </div>

                  <div class="mt-3 rounded-xl border border-line-soft bg-surface-2/60 p-3">
                    <div class="flex items-center gap-2">
                      <span class="text-[10px] text-faint">改动幅度</span>
                      <span class="ml-auto text-[9.5px] text-faint">
                        共 {shots().length} 镜
                      </span>
                    </div>
                    <div class="mt-2 grid grid-cols-3 gap-1">
                      <For each={LEVELS}>
                        {(level) => (
                          <button
                            type="button"
                            class={`rounded-md border px-2 py-1.5 text-[10.5px] transition-colors ${
                              plan()?.change_level === level.id
                                ? "border-accent bg-accent/15 text-text"
                                : "border-line-soft text-dim hover:bg-surface"
                            }`}
                            onClick={() => void setLevel(level.id)}
                          >
                            {level.label}
                          </button>
                        )}
                      </For>
                    </div>
                  </div>

                  <div class="mt-3 space-y-2">
                    <div class="rounded-xl border border-line-soft bg-surface-2/60 p-3">
                      <div class="flex items-center gap-2">
                        <span class="text-[10px] text-faint">人物</span>
                        <Badge tone="neutral">只换外观</Badge>
                        <span class="ml-auto text-[9.5px] text-faint">
                          {blueprint()!.groups.outfits.length} 套造型
                        </span>
                      </div>
                      <div class="mt-2 flex flex-wrap gap-1">
                        <For each={blueprint()!.groups.outfits}>
                          {(group) => (
                            <span class="rounded border border-line-soft bg-surface px-1.5 py-0.5 text-[9px] text-dim">
                              {group.label}
                            </span>
                          )}
                        </For>
                      </div>
                      <div class="mt-2 text-[9px] leading-4 text-faint">P1 骨架：换脸 / 换装 / 肤色在 P3 接入</div>
                    </div>

                    <div class="rounded-xl border border-line-soft bg-surface-2/60 p-3">
                      <div class="flex items-center gap-2">
                        <span class="text-[10px] text-faint">背景</span>
                        <span class="ml-auto text-[9.5px] text-faint">{blueprint()!.groups.scenes.length} 组</span>
                      </div>
                      <div class="mt-2 space-y-1.5">
                        <For each={blueprint()!.groups.scenes}>
                          {(group) => {
                            const mode = () => plan()?.scenes?.[group.id]?.mode ?? "keep";
                            return (
                              <div class="flex items-center gap-1.5 rounded-md border border-line-soft bg-surface px-2 py-1.5">
                                <span class="min-w-0 flex-1 truncate text-[10px] text-dim">{group.label}</span>
                                <span class="text-[9px] text-faint">{group.shot_ids.length} 镜</span>
                                <div class="flex gap-0.5">
                                  <For each={[{ id: "keep", label: "保留" }, { id: "relight", label: "换风格" }, { id: "replace", label: "换房间" }]}>
                                    {(option) => (
                                      <button
                                        type="button"
                                        class={`rounded px-1.5 py-0.5 text-[9px] ${
                                          mode() === option.id ? "bg-accent/20 text-text" : "text-faint hover:bg-surface-2"
                                        }`}
                                        onClick={() => void setScene(group.id, option.id)}
                                      >
                                        {option.label}
                                      </button>
                                    )}
                                  </For>
                                </div>
                              </div>
                            );
                          }}
                        </For>
                      </div>
                    </div>

                    <div class="rounded-xl border border-line-soft bg-surface-2/60 p-3">
                      <div class="flex items-center gap-2">
                        <span class="text-[10px] text-faint">商品</span>
                        <Badge tone="ok">锁定原商品</Badge>
                        <span class="ml-auto text-[9.5px] text-faint">不重画</span>
                      </div>
                      <div class="mt-1 text-[9px] leading-4 text-faint">商品原像素保留；换 SKU 在 P2 之后。</div>
                    </div>

                    <div class="rounded-xl border border-line-soft bg-surface-2/60 p-3">
                      <div class="flex items-center gap-2">
                        <span class="text-[10px] text-faint">字幕</span>
                        <span class="ml-auto text-[9.5px] text-faint">{blueprint()!.caption_count ?? 0} 条 · 需校对</span>
                      </div>
                      <div class="mt-2 space-y-1">
                        <For each={shots().filter((shot) => shot.caption?.text).slice(0, 6)}>
                          {(shot) => (
                            <div class="flex items-center gap-2 text-[9.5px] text-dim">
                              <span class="w-5 shrink-0 font-mono text-[8px] text-faint">{shot.id}</span>
                              <span class="truncate">{shot.caption?.text}</span>
                            </div>
                          )}
                        </For>
                      </div>
                    </div>

                    <div class="rounded-xl border border-line-soft bg-surface-2/60 p-3">
                      <div class="flex items-center gap-2">
                        <span class="text-[10px] text-faint">声音</span>
                        <Badge tone="neutral">保留原声</Badge>
                      </div>
                      <div class="mt-1 text-[9px] leading-4 text-faint">静音 / 重配在 P3 接入。</div>
                    </div>
                  </div>
                </Show>

                <Show when={selected()}>
                  {(shot) => (
                    <div class="mt-3 rounded-xl border border-line-soft bg-surface-2/60 p-3">
                      <div class="flex items-center gap-2">
                        <span class="text-[10px] text-faint">选中镜头</span>
                        <span class="font-mono text-[9.5px] text-dim">{shot().id}</span>
                        <span class="ml-auto text-[9px] text-faint">
                          {shot().start_s.toFixed(2)}–{shot().end_s.toFixed(2)}s
                        </span>
                      </div>
                      <div class="mt-1 text-[10px] text-dim">{shot().caption?.text || "无字幕"}</div>
                    </div>
                  )}
                </Show>
              </aside>
            </div>
          </div>
        </Show>
      </Show>
      <Show when={notice()}>
        <div class="pointer-events-none absolute bottom-16 left-1/2 z-40 -translate-x-1/2 rounded-full border border-line bg-black/80 px-3 py-1 text-[10px] text-text">
          {notice()}
        </div>
      </Show>
    </AppShellV2>
  );
}
