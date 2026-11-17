import { For, Show, createMemo, createSignal, onCleanup, onMount } from "solid-js";
import { useNavigate, useParams } from "@solidjs/router";
import AppShellV2 from "../components/layout/AppShellV2";
import Button from "../components/ui/Button";
import { endpoints } from "../lib/api";
import type { RecreateDetail } from "../lib/types";

const STEPS = ["analyze", "gag", "script", "board", "shots", "finish"] as const;
const LABELS: Record<string, string> = {
  analyze: "① 解析",
  gag: "② 抽梗",
  script: "③ 脚本",
  board: "④ 分镜",
  shots: "⑤ 出片",
  finish: "⑥ 成片",
};

const mediaUrl = (path?: string | null) => (path ? `/api/media?path=${encodeURIComponent(path)}` : "");

type Beat = { id: string; start_s: number; end_s: number; function: string; dialogue?: { speaker?: string; text: string }[] };
type Gag = { mechanism?: string; mechanism_label?: string; confidence?: number; must_keep?: { id: string; text: string; beat?: string }[]; timing?: { punchline_beat?: string; punchline_at_s?: number } };
type ScriptBeat = { id: string; fit: string; chars: number; max_chars: number; lines: { speaker: string; text: string }[] };
type BoardItem = { beat: string; chosen?: string | null; status: string };
type QaCheck = { id: string; label: string; status: string; value: unknown };

export default function RecreateWorkbench() {
  const params = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [detail, setDetail] = createSignal<RecreateDetail | null>(null);
  const [error, setError] = createSignal("");
  const [busy, setBusy] = createSignal<string>("");
  const [product, setProduct] = createSignal({ name: "原味鹰嘴豆", category: "休闲零食", price: "39.9", promo_price: "19.9", selling_points: "追剧零食、酥脆不油", tone: "生活化" });
  const [boardMode, setBoardMode] = createSignal<"auto" | "cast_only">("auto");
  const [castPath, setCastPath] = createSignal("");
  const [shotsMode, setShotsMode] = createSignal<"video" | "still">("video");
  const [provider, setProvider] = createSignal<"auto" | "seedance" | "minimax">("auto");
  const [editing, setEditing] = createSignal(false);
  let timer: number | undefined;

  const skeleton = createMemo(() => (detail()?.skeleton ?? null) as { beats?: Beat[]; source?: Record<string, unknown> } | null);
  const gag = createMemo(() => (detail()?.gag ?? null) as Gag | null);
  const script = createMemo(() => (detail()?.script ?? null) as { beats?: ScriptBeat[]; totals?: Record<string, unknown> } | null);
  const board = createMemo(() => (detail()?.board ?? null) as { items?: BoardItem[] } | null);
  const qa = createMemo(() => (detail()?.qa ?? null) as { checks?: QaCheck[]; summary?: Record<string, unknown> } | null);
  const qaSummary = createMemo(() => {
    const summary = qa()?.summary as { pass?: number; warn?: number; fail?: number; shippable?: boolean } | undefined;
    if (!summary) return null;
    return { pass: summary.pass ?? 0, warn: summary.warn ?? 0, fail: summary.fail ?? 0, shippable: Boolean(summary.shippable) };
  });

  const load = async () => {
    try {
      const data = await endpoints.recreate(params.id);
      setDetail(data);
      const running = Object.values(data.steps ?? {}).some((step) => step.status === "running");
      if (running && !timer) {
        timer = window.setInterval(() => void load(), 2500);
      }
      if (!running && timer) {
        window.clearInterval(timer);
        timer = undefined;
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载失败");
    }
  };

  onMount(() => void load());
  onCleanup(() => {
    if (timer) window.clearInterval(timer);
  });

  const run = async (step: string, extra: Record<string, unknown> = {}) => {
    setBusy(step);
    setError("");
    try {
      await endpoints.recreateStep(params.id, step, extra);
      await load();
      if (!timer) timer = window.setInterval(() => void load(), 2500);
    } catch (err) {
      setError(err instanceof Error ? err.message : "启动失败");
    } finally {
      setBusy("");
    }
  };

  const status = (step: string) => detail()?.steps?.[step]?.status ?? "pending";

  const productPayload = () => {
    const value = product();
    return {
      name: value.name,
      category: value.category,
      price: value.price,
      promo_price: value.promo_price,
      selling_points: value.selling_points.split(/[、,，]/).map((item) => item.trim()).filter(Boolean),
      tone: value.tone,
    };
  };

  return (
    <AppShellV2
      module="recreate"
      context={
        <div class="flex min-w-0 items-center gap-2">
          <span class="text-[12.5px] font-medium text-text">{detail()?.project.title || "复制爆款"}</span>
          <span class="text-[10px] text-faint">下一步 {LABELS[detail()?.next_step ?? ""] ?? "完成"}</span>
        </div>
      }
      footer={`复制爆款 · ${params.id}`}
    >
      <div class="flex flex-col gap-3 overflow-auto p-4">
        <div class="flex flex-wrap items-center gap-2 rounded-xl border border-line bg-surface px-3 py-2">
          <span class="text-[11.5px] text-dim">成片</span>
          <Show when={detail()?.files?.final} fallback={<span class="text-[11px] text-faint">还没有成片</span>}>
            <a class="text-[11.5px] text-accent" href={mediaUrl(detail()?.files?.final)} target="_blank" rel="noreferrer">下载</a>
          </Show>
          <span class="text-[10px] text-faint">·</span>
          <span class="text-[11px] text-dim">QA {qaSummary() ? `${qaSummary()!.pass} 通过 / ${qaSummary()!.fail} 失败` : "未运行"}</span>
          <div class="flex-1" />
          <Button size="sm" variant="ghost" onClick={() => navigate("/chat?tab=scene")}>返回场景应用</Button>
          <Button size="sm" variant={editing() ? "subtle" : "primary"} onClick={() => setEditing((v) => !v)}>
            {editing() ? "退出编辑" : "高级编辑"}
          </Button>
        </div>
        <div class="flex flex-wrap items-center gap-2 rounded-xl border border-line bg-surface px-3 py-2">
          <For each={STEPS}>
            {(step) => (
              <span
                class={`rounded-full border px-2.5 py-1 text-[10.5px] ${
                  status(step) === "done"
                    ? "border-ok/40 bg-ok/10 text-ok"
                    : status(step) === "running"
                      ? "border-warn/40 bg-warn/10 text-warn"
                      : status(step) === "failed"
                        ? "border-bad/40 bg-bad/10 text-bad"
                        : "border-line text-faint"
                }`}
              >
                {LABELS[step]}
              </span>
            )}
          </For>
          <div class="flex-1" />
          <Button size="sm" variant="subtle" disabled={!editing()} loading={busy() === "analyze"} onClick={() => void run("analyze", { max_frames: 6 })}>
            重新解析
          </Button>
          <Button size="sm" variant="subtle" loading={busy() === "gag"} disabled={!editing() || status("analyze") !== "done"} onClick={() => void run("gag")}>
            {LABELS.gag}
          </Button>
        </div>

        <Show when={error()}>
          <div class="rounded-lg border border-bad/40 bg-bad/10 px-3 py-2 text-[11px] text-bad">{error()}</div>
        </Show>

        <div class="grid items-start gap-3 lg:grid-cols-3">
          <section class="rounded-xl border border-line bg-surface p-3">
            <div class="mb-2 flex items-center justify-between text-[11.5px] font-medium text-text">
              <span>拆解</span>
              <span class="text-[10px] text-faint">
                {skeleton()?.beats?.length ?? 0} beat · {String((skeleton()?.source as { duration_s?: number } | undefined)?.duration_s ?? "—")}s
              </span>
            </div>
            <Show when={skeleton()?.beats?.length} fallback={<div class="py-8 text-center text-[10.5px] text-faint">还没解析</div>}>
              <div class="flex flex-col gap-1">
                <For each={skeleton()?.beats ?? []}>
                  {(beat) => (
                    <div class="rounded-lg border border-line/60 px-2 py-1.5">
                      <div class="flex items-center justify-between text-[10px] text-faint">
                        <span>{beat.id} · {beat.function}</span>
                        <span>{beat.start_s.toFixed(1)}–{beat.end_s.toFixed(1)}s</span>
                      </div>
                      <div class="text-[11px] text-dim">
                        {(beat.dialogue ?? []).map((line) => line.text).join(" / ") || "（无台词）"}
                      </div>
                    </div>
                  )}
                </For>
              </div>
            </Show>
          </section>

          <section class="flex flex-col gap-3">
            <div class="rounded-xl border border-line bg-surface p-3">
              <div class="mb-2 text-[11.5px] font-medium text-text">梗</div>
              <Show when={gag()} fallback={<div class="py-6 text-center text-[10.5px] text-faint">还没抽梗</div>}>
                <div class="text-[11px] text-dim">{gag()?.mechanism_label}</div>
                <div class="mt-1 text-[10px] text-faint">
                  {gag()?.mechanism} · 置信 {gag()?.confidence} · 落点 {gag()?.timing?.punchline_beat ?? "—"}
                </div>
                <ul class="mt-2 flex flex-col gap-1">
                  <For each={gag()?.must_keep ?? []}>
                    {(item) => (
                      <li class="text-[10.5px] text-dim">
                        ✓ {item.text} <span class="text-faint">({item.beat ?? "不限"})</span>
                      </li>
                    )}
                  </For>
                </ul>
              </Show>
            </div>

            <div class="rounded-xl border border-line bg-surface p-3">
              <div class="mb-2 text-[11.5px] font-medium text-text">商品</div>
              <div class="grid gap-2 sm:grid-cols-2">
                <input class="rounded-lg border border-line bg-surface-2 px-2 py-1 text-[11px] text-text" value={product().name} onInput={(e) => setProduct({ ...product(), name: e.currentTarget.value })} placeholder="商品名" />
                <input class="rounded-lg border border-line bg-surface-2 px-2 py-1 text-[11px] text-text" value={product().category} onInput={(e) => setProduct({ ...product(), category: e.currentTarget.value })} placeholder="品类" />
                <input class="rounded-lg border border-line bg-surface-2 px-2 py-1 text-[11px] text-text" value={product().price} onInput={(e) => setProduct({ ...product(), price: e.currentTarget.value })} placeholder="原价占位" />
                <input class="rounded-lg border border-line bg-surface-2 px-2 py-1 text-[11px] text-text" value={product().promo_price} onInput={(e) => setProduct({ ...product(), promo_price: e.currentTarget.value })} placeholder="活动价占位" />
                <input class="col-span-2 rounded-lg border border-line bg-surface-2 px-2 py-1 text-[11px] text-text" value={product().selling_points} onInput={(e) => setProduct({ ...product(), selling_points: e.currentTarget.value })} placeholder="卖点（顿号分隔）" />
              </div>
              <div class="mt-2 flex items-center gap-2">
                <Button size="sm" variant="primary" loading={busy() === "script"} disabled={!editing() || status("gag") !== "done"} onClick={() => void run("script", { product: productPayload() })}>
                  ③ 改编脚本
                </Button>
                <span class="text-[10px] text-faint">价格是占位，上线前替换</span>
              </div>
            </div>
          </section>

          <section class="flex flex-col gap-3">
            <div class="rounded-xl border border-line bg-surface p-3">
              <div class="mb-2 flex items-center justify-between text-[11.5px] font-medium text-text">
                <span>脚本</span>
                <span class="text-[10px] text-faint">
                  {String((script()?.totals as { est_s?: number } | undefined)?.est_s ?? "—")}s / 原片 {String((script()?.totals as { source_s?: number } | undefined)?.source_s ?? "—")}s
                </span>
              </div>
              <Show when={script()?.beats?.length} fallback={<div class="py-6 text-center text-[10.5px] text-faint">还没改编</div>}>
                <For each={script()?.beats ?? []}>
                  {(beat) => (
                    <div class="mb-1 rounded-lg border border-line/60 px-2 py-1">
                      <div class="flex items-center justify-between text-[9.5px] text-faint">
                        <span>{beat.id}</span>
                        <span class={beat.fit === "over" ? "text-bad" : beat.fit === "tight" ? "text-warn" : "text-ok"}>
                          {beat.chars}/{beat.max_chars}
                        </span>
                      </div>
                      <div class="text-[10.5px] text-dim">{(beat.lines ?? []).map((line) => `[${line.speaker}] ${line.text}`).join(" ")}</div>
                    </div>
                  )}
                </For>
              </Show>
            </div>

            <div class="rounded-xl border border-line bg-surface p-3">
              <div class="mb-2 flex flex-wrap items-center gap-2 text-[11.5px] font-medium text-text">
                <span>分镜 / 出片</span>
                <select class="rounded-md border border-line bg-surface-2 px-1.5 py-0.5 text-[10px]" value={boardMode()} onChange={(e) => setBoardMode(e.currentTarget.value as "auto" | "cast_only")}>
                  <option value="auto">真实生成</option>
                  <option value="cast_only">干跑（用定妆照）</option>
                </select>
                <select class="rounded-md border border-line bg-surface-2 px-1.5 py-0.5 text-[10px]" value={shotsMode()} onChange={(e) => setShotsMode(e.currentTarget.value as "video" | "still")}>
                  <option value="video">i2v</option>
                  <option value="still">静帧</option>
                </select>
                <select class="rounded-md border border-line bg-surface-2 px-1.5 py-0.5 text-[10px]" value={provider()} onChange={(e) => setProvider(e.currentTarget.value as "auto" | "seedance" | "minimax")}>
                  <option value="auto">自动选通道</option>
                  <option value="seedance">Seedance</option>
                  <option value="minimax">MiniMax</option>
                </select>
              </div>
              <Show when={boardMode() === "cast_only"}>
                <input class="mb-2 w-full rounded-lg border border-line bg-surface-2 px-2 py-1 text-[10.5px] text-text" placeholder="定妆照路径，例如 uploads/recreate/p2/guazi/cast/cast_1.png" value={castPath()} onInput={(e) => setCastPath(e.currentTarget.value)} />
              </Show>
              <div class="flex flex-wrap gap-2">
                <Button size="sm" variant="subtle" loading={busy() === "board"} disabled={!editing() || status("script") !== "done"} onClick={() => void run("board", { mode: boardMode(), cast: castPath() || undefined, per_beat: 1 })}>
                  ④ 分镜板
                </Button>
                <Button size="sm" variant="subtle" loading={busy() === "shots"} disabled={!editing() || status("board") !== "done"} onClick={() => void run("shots", { mode: shotsMode(), provider: provider() })}>
                  ⑤ 出片
                </Button>
                <Button size="sm" variant="primary" loading={busy() === "finish"} disabled={!editing() || status("shots") !== "done"} onClick={() => void run("finish", { voice: true, audio_mode: "native" })}>
                  ⑥ 装配 + QA
                </Button>
              </div>
              <Show when={board()?.items?.length}>
                <div class="mt-2 grid grid-cols-3 gap-1">
                  <For each={board()?.items ?? []}>
                    {(item) => (
                      <img class="h-16 w-full rounded object-cover" src={mediaUrl(item.chosen)} alt={item.beat} title={item.beat} />
                    )}
                  </For>
                </div>
              </Show>
            </div>
          </section>
        </div>

        <Show when={detail()?.files?.final}>
          <div class="grid gap-3 lg:grid-cols-[320px_1fr]">
            <video
              class="w-full rounded-xl border border-line bg-black"
              src={mediaUrl(detail()?.files?.final)}
              poster={mediaUrl(board()?.items?.[0]?.chosen)}
              preload="metadata"
              controls
            />
            <div class="rounded-xl border border-line bg-surface p-3">
              <div class="mb-2 flex items-center justify-between text-[11.5px] font-medium text-text">
                <span>QA</span>
                <span class={qaSummary()?.shippable ? "text-ok" : "text-warn"}>
                  {qaSummary() ? `${qaSummary()!.pass} 通过 · ${qaSummary()!.fail} 失败` : "未运行"}
                </span>
              </div>
              <For each={qa()?.checks ?? []}>
                {(check) => (
                  <div class="flex items-start justify-between gap-2 border-b border-line/40 py-1 text-[10.5px]">
                    <span class="text-dim">{check.label}</span>
                    <span class={check.status === "pass" ? "text-ok" : check.status === "warn" ? "text-warn" : "text-bad"}>
                      {check.status}
                    </span>
                  </div>
                )}
              </For>
            </div>
          </div>
        </Show>
      </div>
    </AppShellV2>
  );
}
