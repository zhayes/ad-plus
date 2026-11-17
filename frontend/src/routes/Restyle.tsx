import { For, Show, createSignal, onMount } from "solid-js";
import { useNavigate } from "@solidjs/router";
import AppShellV2 from "../components/layout/AppShellV2";
import Button from "../components/ui/Button";
import Icon from "../components/ui/Icon";
import { endpoints, uploadAsset } from "../lib/api";
import { coverUrl } from "../lib/projects";
import type { RestyleSummary } from "../lib/types";

export default function Restyle() {
  const navigate = useNavigate();
  const [items, setItems] = createSignal<RestyleSummary[]>([]);
  const [busy, setBusy] = createSignal(false);
  const [dragging, setDragging] = createSignal(false);
  const [error, setError] = createSignal("");
  let input: HTMLInputElement | undefined;

  const messageFor = (err: unknown, fallback: string) => {
    const text = err instanceof Error ? err.message : fallback;
    if (text.includes("Not Found") || text.includes("404")) {
      return "后端还没加载改写接口，重启 Ad+ 后再试";
    }
    return text || fallback;
  };

  const load = async () => {
    try {
      const data = await endpoints.restyles();
      setItems(data.restyles ?? []);
    } catch (err) {
      setError(messageFor(err, "加载失败"));
    }
  };

  onMount(() => void load());

  const ingest = async (file: File) => {
    setBusy(true);
    setError("");
    try {
      const asset = await uploadAsset(file);
      const created = await endpoints.createRestyle({
        path: asset.path,
        title: file.name.replace(/\.[^.]+$/, ""),
        rights_confirmed: true,
      });
      navigate(`/restyle/${created.restyle.project.project_id}`);
    } catch (err) {
      setError(messageFor(err, "创建失败"));
    } finally {
      setBusy(false);
    }
  };

  const onDrop = (event: DragEvent) => {
    event.preventDefault();
    setDragging(false);
    const file = event.dataTransfer?.files?.[0];
    if (file) void ingest(file);
  };

  return (
    <AppShellV2
      module="restyle"
      context={
        <div class="flex min-w-0 items-center gap-2">
          <span class="h-4 w-4 shrink-0 rounded bg-gradient-to-br from-violet to-accent" />
          <span class="text-[12.5px] font-medium text-text">改写</span>
          <span class="hidden text-[10px] text-faint sm:inline">保留结构，换人物外观和背景</span>
        </div>
      }
      primary={
        <Button size="sm" variant="primary" disabled={busy()} onClick={() => input?.click()}>
          ＋ 新建改写
        </Button>
      }
      footer="改写 · P1 骨架"
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
          onDrop={onDrop}
        >
          <div class="mx-auto grid h-11 w-11 place-items-center rounded-xl border border-line bg-surface">
            <Icon name="layers" size={20} class="text-accent" />
          </div>
          <div class="mt-3 text-[14px] font-medium text-text">拖一条广告视频进来</div>
          <div class="mt-1 text-[11px] text-faint">
            先读片，再决定换谁、换哪个房间；商品和节奏保持原样
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
          <span class="text-[12px] font-medium text-text">最近改写</span>
          <span class="text-[10px] text-faint">{items().length}</span>
        </div>

        <Show
          when={items().length > 0}
          fallback={<div class="rounded-xl border border-dashed border-line py-10 text-center text-[11px] text-faint">还没有改写记录</div>}
        >
          <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <For each={items()}>
              {(item) => {
                const cover = () => coverUrl(item.cover);
                return (
                  <button
                    type="button"
                    class="group overflow-hidden rounded-xl border border-line-soft bg-surface text-left transition-colors hover:border-line"
                    onClick={() => navigate(`/restyle/${item.id}`)}
                  >
                    <div class="relative h-[240px] w-full overflow-hidden bg-surface-2">
                      <Show
                        when={cover()}
                        fallback={<div class="grid h-full place-items-center text-[10px] text-faint">无封面</div>}
                      >
                        <img src={cover()!} alt="" class="h-full w-full object-cover opacity-90 transition-transform duration-500 group-hover:scale-[1.03]" />
                      </Show>
                      <div class="absolute left-2 top-2 flex gap-1">
                        <span class="rounded bg-black/55 px-1.5 py-0.5 text-[9px] text-white/85">
                          {item.shot_count || "—"} 镜
                        </span>
                        <Show when={item.analyzed} fallback={<span class="rounded bg-warn/80 px-1.5 py-0.5 text-[9px] text-black">待读片</span>}>
                          <span class="rounded bg-ok/80 px-1.5 py-0.5 text-[9px] text-black">已读片</span>
                        </Show>
                      </div>
                    </div>
                    <div class="p-3">
                      <div class="truncate text-[12px] font-medium text-text">{item.title}</div>
                      <div class="mt-1 flex items-center gap-2 text-[10px] text-faint">
                        <span>{Number(item.duration_s || 0).toFixed(1)}s</span>
                        <span>·</span>
                        <span>{item.caption_count || 0} 条字幕</span>
                        <span class="ml-auto">{item.aspect || "9:16"}</span>
                      </div>
                    </div>
                  </button>
                );
              }}
            </For>
          </div>
        </Show>
      </div>
    </AppShellV2>
  );
}
