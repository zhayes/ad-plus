import { For, Show, createEffect, createSignal, on, onCleanup, onMount } from "solid-js";
import Badge from "../ui/Badge";
import Icon from "../ui/Icon";
import Button from "../ui/Button";
import Input from "../ui/Input";
import Select from "../ui/Select";
import AssetDrawer from "./AssetDrawer";
import { endpoints, uploadAsset } from "../../lib/api";
import { fmtBytes, fmtTime } from "../../lib/format";
import { kindLabel, sourceLabel } from "../../lib/assets";
import { mediaUrl } from "../../lib/projects";
import { projects, refreshProjects } from "../../stores/projects";
import type { Asset } from "../../lib/types";

const KINDS = [
  { value: "all", label: "全部类型" },
  { value: "image", label: "图片" },
  { value: "video", label: "视频" },
  { value: "audio", label: "音频" },
];

const SOURCES = [
  { value: "all", label: "全部来源" },
  { value: "upload", label: "上传" },
  { value: "project", label: "项目素材" },
  { value: "render", label: "成片" },
];

interface Props {
  onPrimaryReady?: (open: () => void) => void;
}

export default function AssetsPanel(props: Props) {
  const [assets, setAssets] = createSignal<Asset[]>([]);
  const [loading, setLoading] = createSignal(true);
  const [error, setError] = createSignal("");
  const [kind, setKind] = createSignal("all");
  const [source, setSource] = createSignal("all");
  const [project, setProject] = createSignal("all");
  const [query, setQuery] = createSignal("");
  const [nonce, setNonce] = createSignal(0);
  const [selectedId, setSelectedId] = createSignal<string | null>(null);
  const [busy, setBusy] = createSignal(false);
  const [dragging, setDragging] = createSignal(false);
  const [view, setView] = createSignal<"cards" | "table">(
    (localStorage.getItem("adplus.assets.view") as "cards" | "table") || "cards",
  );

  const changeView = (next: "cards" | "table") => {
    setView(next);
    localStorage.setItem("adplus.assets.view", next);
  };

  let fileInput: HTMLInputElement | undefined;
  let debounce: ReturnType<typeof setTimeout> | undefined;

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const data = await endpoints.assets({
        kind: kind() === "all" ? undefined : kind(),
        source: source() === "all" ? undefined : source(),
        project_id: project() === "all" ? undefined : project(),
        q: query().trim() || undefined,
      });
      setAssets(data.assets ?? []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "素材加载失败");
    } finally {
      setLoading(false);
    }
  };

  createEffect(
    on(
      () => [kind(), source(), project(), query(), nonce()] as const,
      () => {
        if (debounce) clearTimeout(debounce);
        debounce = setTimeout(() => void load(), 180);
      },
    ),
  );

  onCleanup(() => {
    if (debounce) clearTimeout(debounce);
  });

  onMount(() => {
    void refreshProjects();
    props.onPrimaryReady?.(() => fileInput?.click());
  });

  const uploadFiles = async (files: FileList | File[]) => {
    const list = Array.from(files);
    if (list.length === 0) return;
    setBusy(true);
    setError("");
    const uploaded: Asset[] = [];
    try {
      for (const file of list) {
        try {
          uploaded.push(await uploadAsset(file));
        } catch (err) {
          setError(err instanceof Error ? err.message : `上传失败：${file.name}`);
        }
      }
      if (uploaded.length > 0) {
        setSelectedId(uploaded[0].id);
        setNonce((value) => value + 1);
      }
    } finally {
      setBusy(false);
      if (fileInput) fileInput.value = "";
    }
  };

  const onDrop = (event: DragEvent) => {
    event.preventDefault();
    setDragging(false);
    if (event.dataTransfer?.files?.length) void uploadFiles(event.dataTransfer.files);
  };

  const projectOptions = () => [
    { value: "all", label: "全部项目" },
    ...projects().map((item) => ({ value: item.id, label: item.title })),
  ];

  const thumb = (asset: Asset): string | null => {
    if (asset.kind === "image") return mediaUrl(asset.path);
    if (asset.kind === "video") return `/api/thumb?path=${encodeURIComponent(asset.path)}&width=480`;
    return null;
  };

  return (
    <div
      class="relative h-full overflow-auto px-5 py-4"
      onDragOver={(event) => {
        event.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={onDrop}
    >
      <input
        ref={fileInput}
        type="file"
        multiple
        class="hidden"
        accept="image/*,video/*,audio/*"
        onChange={(event) => {
          if (event.currentTarget.files) void uploadFiles(event.currentTarget.files);
        }}
      />

      <div class="mb-3 flex flex-wrap items-center gap-2">
        <div class="w-[230px]">
          <Input value={query()} placeholder="搜索素材名 / 路径" onInput={(event) => setQuery(event.currentTarget.value)} />
        </div>
        <Select value={kind()} options={KINDS} onChange={setKind} variant="pill" />
        <Select value={source()} options={SOURCES} onChange={setSource} variant="pill" />
        <Select value={project()} options={projectOptions()} onChange={setProject} variant="pill" />
        <Show when={busy()}>
          <span class="text-[10px] text-faint">上传中…</span>
        </Show>
        <div class="ml-auto flex items-center gap-2">
          <span class="text-[10.5px] text-faint">{assets().length} 个素材</span>
          <div class="flex items-center rounded-md border border-line-soft bg-surface p-0.5">
            <button
              type="button"
              class={`grid h-6 w-6 place-items-center rounded ${view() === "cards" ? "bg-surface-2 text-text" : "text-faint hover:text-text"}`}
              title="卡片视图"
              onClick={() => changeView("cards")}
            >
              <Icon name="grid" size={13} />
            </button>
            <button
              type="button"
              class={`grid h-6 w-6 place-items-center rounded ${view() === "table" ? "bg-surface-2 text-text" : "text-faint hover:text-text"}`}
              title="表格视图"
              onClick={() => changeView("table")}
            >
              <Icon name="list" size={13} />
            </button>
          </div>
        </div>
      </div>

      <Show when={error()}>
        <div class="mb-3 flex items-center gap-2 rounded-lg border border-bad/30 bg-bad/5 px-3 py-2 text-[11px] text-bad">
          <span class="min-w-0 flex-1 truncate">{error()}</span>
          <button type="button" class="text-[10.5px] underline" onClick={() => void load()}>
            重试
          </button>
        </div>
      </Show>

      <Show when={!loading() || assets().length > 0} fallback={<Skeleton />}>
        <Show
          when={assets().length > 0}
          fallback={
            <div
              class={`grid place-items-center rounded-xl border border-dashed py-20 ${
                dragging() ? "border-accent/70 bg-accent/5" : "border-line bg-surface/40"
              }`}
            >
              <div class="max-w-[360px] text-center">
                <div class="text-[13px] font-medium text-text">把素材拖进来，或选择文件</div>
                <p class="mt-1.5 text-[11px] leading-5 text-faint">
                  图片、视频、音频都可以；上传后可以复制为项目参考，或直接替换某个镜头。
                </p>
                <Button class="mt-3" size="sm" variant="primary" disabled={busy()} onClick={() => fileInput?.click()}>
                  ＋ 选择文件
                </Button>
              </div>
            </div>
          }
        >
          <Show
            when={view() === "cards"}
            fallback={<AssetTable assets={assets()} thumb={thumb} onOpen={setSelectedId} />}
          >
          <div class="grid grid-cols-2 gap-3 pb-6 md:grid-cols-3 xl:grid-cols-4">
            <For each={assets()}>
              {(asset) => (
                <button
                  type="button"
                  class="group overflow-hidden rounded-lg border border-line-soft bg-surface text-left transition-colors hover:border-line"
                  onClick={() => setSelectedId(asset.id)}
                >
                  <div class="relative bg-[#0b0e15]" style={{ "aspect-ratio": "4 / 3" }}>
                    <Show
                      when={thumb(asset)}
                      fallback={
                        <div class="grid h-full w-full place-items-center">
                          <span class="text-[28px] text-white/15">{asset.kind === "audio" ? "♫" : "▣"}</span>
                        </div>
                      }
                    >
                      <img src={thumb(asset)!} alt="" class="h-full w-full object-cover" loading="lazy" />
                    </Show>
                    <div class="absolute left-1.5 top-1.5 flex gap-1">
                      <Badge tone={asset.kind === "video" ? "accent" : "neutral"}>{kindLabel(asset.kind)}</Badge>
                    </div>
                    <div class="absolute bottom-1.5 right-1.5">
                      <span class="rounded bg-black/45 px-1 py-px text-[9px] text-white/70">{sourceLabel(asset.source)}</span>
                    </div>
                  </div>
                  <div class="p-2">
                    <div class="truncate text-[10.5px] text-dim">{asset.name}</div>
                    <div class="mt-0.5 flex items-center gap-1 text-[9.5px] text-faint">
                      <span>{fmtBytes(asset.bytes)}</span>
                      <Show when={asset.project_id}>
                        <span>·</span>
                        <span class="truncate">{asset.project_id}</span>
                      </Show>
                    </div>
                  </div>
                </button>
              )}
            </For>
          </div>
          </Show>
        </Show>
      </Show>

      <Show when={dragging()}>
        <div class="pointer-events-none absolute inset-3 grid place-items-center rounded-xl border-2 border-dashed border-accent/60 bg-accent/5">
          <div class="text-[12px] text-accent">松手上传</div>
        </div>
      </Show>

      <AssetDrawer
        assetId={selectedId()}
        onClose={() => setSelectedId(null)}
        onChanged={() => {
          setNonce((value) => value + 1);
          void refreshProjects();
        }}
      />
    </div>
  );
}

function AssetTable(props: {
  assets: Asset[];
  thumb: (asset: Asset) => string | null;
  onOpen: (id: string) => void;
}) {
  return (
    <div class="overflow-hidden rounded-xl border border-line-soft bg-surface">
      <table class="w-full border-collapse text-left">
        <thead class="border-b border-line-soft bg-surface-2/40">
          <tr class="text-[10px] text-faint">
            <th class="px-3 py-2 font-normal">素材</th>
            <th class="px-3 py-2 font-normal">类型</th>
            <th class="hidden px-3 py-2 font-normal sm:table-cell">来源</th>
            <th class="hidden px-3 py-2 font-normal md:table-cell">项目</th>
            <th class="px-3 py-2 font-normal">大小</th>
            <th class="hidden px-3 py-2 font-normal lg:table-cell">更新</th>
            <th class="px-3 py-2 text-right font-normal">操作</th>
          </tr>
        </thead>
        <tbody>
          <For each={props.assets}>
            {(asset) => (
              <tr
                class="group cursor-pointer border-b border-line-soft/70 last:border-0 hover:bg-surface-2/40"
                onClick={() => props.onOpen(asset.id)}
              >
                <td class="max-w-[320px] px-3 py-2">
                  <div class="flex min-w-0 items-center gap-2.5">
                    <span class="h-9 w-12 shrink-0 overflow-hidden rounded-md border border-line-soft bg-[#0b0e15]">
                      <Show
                        when={props.thumb(asset)}
                        fallback={<span class="grid h-full w-full place-items-center text-[14px] text-white/20">{asset.kind === "audio" ? "♫" : "▣"}</span>}
                      >
                        <img src={props.thumb(asset)!} alt="" class="h-full w-full object-cover" loading="lazy" />
                      </Show>
                    </span>
                    <span class="min-w-0">
                      <span class="block truncate text-[12px] text-text">{asset.name}</span>
                      <span class="mt-0.5 block truncate font-mono text-[9.5px] text-faint">{asset.path}</span>
                    </span>
                  </div>
                </td>
                <td class="px-3 py-2">
                  <Badge tone={asset.kind === "video" ? "accent" : "neutral"}>{kindLabel(asset.kind)}</Badge>
                </td>
                <td class="hidden px-3 py-2 text-[10.5px] text-dim sm:table-cell">{sourceLabel(asset.source)}</td>
                <td class="hidden max-w-[140px] truncate px-3 py-2 text-[10.5px] text-dim md:table-cell">{asset.project_id || "—"}</td>
                <td class="px-3 py-2 font-mono text-[10px] text-faint">{fmtBytes(asset.bytes)}</td>
                <td class="hidden px-3 py-2 text-[10.5px] text-faint lg:table-cell">{fmtTime(asset.mtime) || "—"}</td>
                <td class="px-3 py-2 text-right">
                  <Button size="sm" variant="ghost" onClick={(event) => { event.stopPropagation(); props.onOpen(asset.id); }}>
                    详情
                  </Button>
                </td>
              </tr>
            )}
          </For>
        </tbody>
      </table>
    </div>
  );
}

function Skeleton() {
  return (
    <div class="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-4">
      <For each={[0, 1, 2, 3, 4, 5, 6, 7]}>
        {() => <div class="animate-pulse rounded-lg border border-line-soft bg-surface" style={{ "aspect-ratio": "4 / 3" }} />}
      </For>
    </div>
  );
}
