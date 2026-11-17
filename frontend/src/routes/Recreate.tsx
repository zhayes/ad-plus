import { For, Show, createSignal, onMount } from "solid-js";
import { useNavigate } from "@solidjs/router";
import AppShellV2 from "../components/layout/AppShellV2";
import Button from "../components/ui/Button";
import Icon from "../components/ui/Icon";
import { endpoints, uploadAsset } from "../lib/api";
import type { RecreateSummary } from "../lib/types";

const STEP_LABELS: Record<string, string> = {
  analyze: "解析",
  gag: "梗",
  script: "脚本",
  board: "分镜",
  shots: "出片",
  finish: "成片",
};

export default function Recreate() {
  const navigate = useNavigate();
  const [items, setItems] = createSignal<RecreateSummary[]>([]);
  const [busy, setBusy] = createSignal(false);
  const [dragging, setDragging] = createSignal(false);
  const [error, setError] = createSignal("");
  let input: HTMLInputElement | undefined;

  const load = async () => {
    try {
      const data = await endpoints.recreates();
      setItems(data.recreates ?? []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载失败");
    }
  };

  onMount(() => void load());

  const ingest = async (file: File) => {
    setBusy(true);
    setError("");
    try {
      const asset = await uploadAsset(file);
      const created = await endpoints.createRecreate({
        path: asset.path,
        title: file.name.replace(/\.[^.]+$/, ""),
        rights_confirmed: true,
      });
      navigate(`/recreate/${created.recreate.project.project_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "创建失败");
    } finally {
      setBusy(false);
    }
  };

  const doneCount = (item: RecreateSummary) =>
    Object.values(item.steps ?? {}).filter((step) => step.status === "done").length;

  return (
    <AppShellV2
      module="recreate"
      context={
        <div class="flex min-w-0 items-center gap-2">
          <span class="h-4 w-4 shrink-0 rounded bg-gradient-to-br from-violet to-accent" />
          <span class="text-[12.5px] font-medium text-text">复制爆款</span>
          <span class="hidden text-[10px] text-faint sm:inline">拆骨架、抽梗，换商品重拍</span>
        </div>
      }
      primary={
        <Button size="sm" variant="primary" loading={busy()} onClick={() => input?.click()}>
          ＋ 复制一条
        </Button>
      }
      footer="复制爆款 · P0–P3"
    >
      <div class="mx-auto flex h-full max-w-[1100px] flex-col gap-4 overflow-auto p-5">
        <input
          ref={input}
          type="file"
          accept="video/mp4,video/quicktime,video/webm"
          class="hidden"
          onChange={(event) => {
            const file = event.currentTarget.files?.[0];
            if (file) void ingest(file);
            event.currentTarget.value = "";
          }}
        />

        <div
          class={`rounded-2xl border-2 border-dashed p-8 text-center transition-colors ${
            dragging() ? "border-accent bg-accent/5" : "border-line bg-surface/60"
          }`}
          onDragOver={(event) => {
            event.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(event) => {
            event.preventDefault();
            setDragging(false);
            const file = event.dataTransfer?.files?.[0];
            if (file) void ingest(file);
          }}
        >
          <div class="mx-auto grid h-11 w-11 place-items-center rounded-xl border border-line bg-surface">
            <Icon name="layers" size={20} class="text-accent" />
          </div>
          <div class="mt-3 text-[14px] font-medium text-text">把爆款视频拖进来</div>
          <div class="mt-1 text-[11px] text-faint">
            先拆结构和梗，再换商品重拍；生成的画面会重新创作，不是替换原片
          </div>
          <div class="mt-4 flex flex-wrap items-center justify-center gap-3">
            <Button size="sm" variant="primary" loading={busy()} onClick={() => input?.click()}>
              选择视频
            </Button>
          </div>
          <Show when={error()}>
            <div class="mt-3 text-[11px] text-bad">{error()}</div>
          </Show>
        </div>

        <div class="flex items-center gap-2">
          <span class="text-[12px] font-medium text-text">最近复制</span>
          <span class="text-[10px] text-faint">{items().length}</span>
        </div>

        <Show
          when={items().length > 0}
          fallback={
            <div class="rounded-xl border border-dashed border-line py-10 text-center text-[11px] text-faint">
              还没有复制记录
            </div>
          }
        >
          <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <For each={items()}>
              {(item) => (
                <button
                  class="rounded-xl border border-line bg-surface p-3 text-left transition-colors hover:border-accent/60"
                  onClick={() => navigate(`/recreate/${item.project_id}`)}
                >
                  <div class="flex items-center justify-between">
                    <span class="truncate text-[12.5px] font-medium text-text">{item.title || item.project_id}</span>
                    <span class="text-[10px] text-faint">{item.duration_s ? `${item.duration_s.toFixed(1)}s` : "—"}</span>
                  </div>
                  <div class="mt-1 text-[10px] text-faint">
                    {doneCount(item)}/6 步 · 下一步 {STEP_LABELS[item.next_step ?? ""] ?? "完成"}
                  </div>
                  <div class="mt-2 flex gap-1">
                    <For each={["analyze", "gag", "script", "board", "shots", "finish"]}>
                      {(step) => (
                        <span
                          class={`h-1 flex-1 rounded ${
                            item.steps?.[step]?.status === "done"
                              ? "bg-ok"
                              : item.steps?.[step]?.status === "failed"
                                ? "bg-bad"
                                : item.steps?.[step]?.status === "running"
                                  ? "bg-warn"
                                  : "bg-line"
                          }`}
                        />
                      )}
                    </For>
                  </div>
                </button>
              )}
            </For>
          </div>
        </Show>
      </div>
    </AppShellV2>
  );
}
