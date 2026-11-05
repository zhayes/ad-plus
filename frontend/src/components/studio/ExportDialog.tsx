import { For, Show, createEffect, createSignal, on } from "solid-js";
import Dialog from "../ui/Dialog";
import Button from "../ui/Button";
import Input from "../ui/Input";
import Select from "../ui/Select";
import { endpoints } from "../../lib/api";
import { fmtBytes } from "../../lib/format";
import type { Deliverable, Version } from "../../lib/types";

const PRESETS = [
  { value: "douyin_1080", label: "抖音 1080×1920" },
  { value: "xiaohongshu_1080", label: "小红书 1080×1920" },
  { value: "preview_720", label: "预览 720×1280" },
  { value: "original", label: "原片（不转码）" },
];

interface Props {
  open: boolean;
  projectId: string;
  version: Version | null;
  onClose: () => void;
  onExported: () => void;
}

export default function ExportDialog(props: Props) {
  const [preset, setPreset] = createSignal("douyin_1080");
  const [filename, setFilename] = createSignal("");
  const [deliverables, setDeliverables] = createSignal<Deliverable[]>([]);
  const [result, setResult] = createSignal<Deliverable | null>(null);
  const [busy, setBusy] = createSignal(false);
  const [error, setError] = createSignal("");

  const hasRender = () => !!props.version?.render?.path;

  const defaultName = () =>
    `${props.projectId}-${props.version?.label ?? "v1"}-${preset()}`.replace(/[^A-Za-z0-9._-]+/g, "-");

  const load = async () => {
    if (!props.projectId) return;
    try {
      const data = await endpoints.deliverables(props.projectId);
      setDeliverables(data.deliverables ?? []);
    } catch {
      /* list is optional */
    }
  };

  createEffect(
    on(
      () => props.open,
      (open) => {
        if (!open) return;
        setResult(null);
        setError("");
        setFilename(defaultName());
        void load();
      },
    ),
  );

  const exportNow = async () => {
    if (!props.version) return;
    setBusy(true);
    setError("");
    setResult(null);
    try {
      const data = await endpoints.exportVersion(props.projectId, {
        version_id: props.version.id,
        preset: preset(),
        filename: filename().trim() || defaultName(),
      });
      setResult(data.deliverable);
      setDeliverables(data.deliverables ?? []);
      props.onExported();
    } catch (err) {
      setError(err instanceof Error ? err.message : "导出失败");
    } finally {
      setBusy(false);
    }
  };

  const reveal = async (path: string) => {
    try {
      await endpoints.reveal(path);
    } catch (err) {
      setError(err instanceof Error ? err.message : "无法打开 Finder");
    }
  };

  return (
    <Dialog open={props.open} onOpenChange={(open) => !open && props.onClose()} title="导出">
      <div class="space-y-3">
        <Show
          when={hasRender()}
          fallback={
            <div class="rounded-lg border border-dashed border-line p-8 text-center">
              <div class="text-[12px] text-dim">当前版本还没有成片</div>
              <p class="mt-1 text-[10.5px] text-faint">先在审片里通过，或在成片阶段生成一版。</p>
            </div>
          }
        >
          <div class="grid gap-3 md:grid-cols-[1fr_260px]">
            <div class="space-y-3">
              <div>
                <label class="mb-1.5 block text-[10.5px] text-faint">预设</label>
                <Select value={preset()} options={PRESETS} onChange={setPreset} variant="pill" />
              </div>
              <div>
                <label class="mb-1.5 block text-[10.5px] text-faint">文件名</label>
                <Input
                  value={filename()}
                  placeholder={defaultName()}
                  onInput={(event) => setFilename(event.currentTarget.value)}
                />
              </div>
              <div class="rounded-lg border border-line-soft bg-surface-2/30 p-2.5 text-[10.5px] leading-5 text-faint">
                导出会复制当前版本成片到 `projects/{props.projectId}/deliverables/`；预设会转码并补齐画幅。
                原片不转码，最快。
              </div>
              <Show when={error()}>
                <div class="text-[10.5px] text-bad">{error()}</div>
              </Show>
              <Show when={result()}>
                <div class="rounded-lg border border-ok/30 bg-ok/5 p-2.5">
                  <div class="flex items-center gap-2 text-[11px] text-ok">
                    <span>已导出</span>
                    <span class="truncate text-dim">{result()!.path}</span>
                  </div>
                  <div class="mt-1 text-[10px] text-faint">
                    {result()!.filename} · {fmtBytes(result()!.bytes)} · {result()!.preset}
                  </div>
                  <Button
                    size="sm"
                    variant="ghost"
                    class="mt-1 px-0"
                    onClick={() => void reveal(result()!.path)}
                  >
                    在 Finder 显示
                  </Button>
                </div>
              </Show>
            </div>

            <div class="rounded-lg border border-line-soft p-2.5">
              <div class="flex items-center">
                <span class="text-[10px] tracking-wide text-faint">历史交付</span>
                <span class="ml-auto text-[9.5px] text-faint">{deliverables().length}</span>
              </div>
              <Show
                when={deliverables().length > 0}
                fallback={<div class="mt-2 text-[10px] text-faint">还没有导出记录。</div>}
              >
                <div class="mt-1 max-h-[220px] space-y-1 overflow-auto">
                  <For each={deliverables()}>
                    {(item) => (
                      <button
                        type="button"
                        class="block w-full rounded border border-line-soft px-2 py-1.5 text-left hover:border-line"
                        onClick={() => void reveal(item.path)}
                      >
                        <div class="truncate text-[10.5px] text-dim">{item.filename}</div>
                        <div class="mt-0.5 text-[9.5px] text-faint">
                          {item.preset} · {fmtBytes(item.bytes)}
                        </div>
                      </button>
                    )}
                  </For>
                </div>
              </Show>
            </div>
          </div>
        </Show>

        <div class="flex items-center gap-2 border-t border-line-soft pt-3">
          <span class="text-[10px] text-faint">
            {props.version ? `${props.version.label} · ${props.version.duration_s}s` : "无版本"}
          </span>
          <div class="ml-auto flex gap-1.5">
            <Button size="sm" onClick={props.onClose}>
              关闭
            </Button>
            <Button size="sm" variant="primary" loading={busy()} disabled={!hasRender()} onClick={() => void exportNow()}>
              导出
            </Button>
          </div>
        </div>
      </div>
    </Dialog>
  );
}
