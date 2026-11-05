import { For, Show, createEffect, createSignal, on } from "solid-js";
import Badge from "../ui/Badge";
import Button from "../ui/Button";
import TextArea from "../ui/TextArea";
import { endpoints } from "../../lib/api";
import { coverUrl, mediaUrl } from "../../lib/projects";
import type { ReviewCheck, ReviewPayload, Version } from "../../lib/types";

type Decision = "pass" | "flag";

const VERDICT: Record<string, { label: string; tone: "neutral" | "ok" | "warn" | "bad" }> = {
  pass: { label: "通过", tone: "ok" },
  pass_with_note: { label: "通过·有备注", tone: "warn" },
  fail: { label: "未通过", tone: "bad" },
  warn: { label: "注意", tone: "warn" },
  not_applicable: { label: "不适用", tone: "neutral" },
  unknown: { label: "未知", tone: "neutral" },
};

interface Props {
  projectId: string;
  version: Version | null;
  onChanged: () => void;
  onExport: () => void;
}

export default function ReviewTab(props: Props) {
  const [payload, setPayload] = createSignal<ReviewPayload | null>(null);
  const [decisions, setDecisions] = createSignal<Record<string, Decision>>({});
  const [comment, setComment] = createSignal("");
  const [loading, setLoading] = createSignal(false);
  const [busy, setBusy] = createSignal(false);
  const [error, setError] = createSignal("");
  const [result, setResult] = createSignal("");

  const shots = () => props.version?.shots ?? [];
  const qa = () => payload()?.qa;
  const review = () => payload()?.review;
  const flagged = () => shots().filter((shot) => decisions()[shot.id] === "flag").length;
  const canReview = () => !!(props.version?.render?.path);

  const tone = () => {
    const status = qa()?.status;
    if (status === "fail") return "bad" as const;
    if (status === "warn" || status === "unknown") return "warn" as const;
    if (status === "pass") return "ok" as const;
    return "neutral" as const;
  };

  const qaLabel = () => {
    const status = qa()?.status;
    if (status === "pass") return "QA 通过";
    if (status === "warn") return "QA 有备注";
    if (status === "fail") return "QA 未通过";
    if (status === "none") return "还没有成片";
    return "QA 未就绪";
  };

  const load = async () => {
    if (!props.version) {
      setPayload(null);
      return;
    }
    setLoading(true);
    setError("");
    try {
      const data = await endpoints.review(props.projectId, props.version.id);
      setPayload(data);
      const next: Record<string, Decision> = {};
      for (const shot of props.version.shots) next[shot.id] = "pass";
      for (const item of data.review?.decisions ?? []) {
        if (item.status === "flag") next[item.shot_id] = "flag";
      }
      setDecisions(next);
      setComment(data.review?.comment ?? "");
    } catch (err) {
      setError(err instanceof Error ? err.message : "审片数据加载失败");
    } finally {
      setLoading(false);
    }
  };

  createEffect(
    on(
      () => [props.projectId, props.version?.id] as const,
      () => {
        void load();
      },
    ),
  );

  const setDecision = (shotId: string, value: Decision) => {
    setDecisions((previous) => ({ ...previous, [shotId]: value }));
  };

  const allPass = () => {
    const next: Record<string, Decision> = {};
    for (const shot of shots()) next[shot.id] = "pass";
    setDecisions(next);
  };

  const submit = async (approved: boolean) => {
    if (!props.version) return;
    setBusy(true);
    setError("");
    try {
      await endpoints.decideReview(props.projectId, {
        version_id: props.version.id,
        approved,
        decisions: shots().map((shot) => ({
          shot_id: shot.id,
          status: decisions()[shot.id] ?? "pass",
          note: "",
        })),
        comment: comment().trim(),
      });
      setResult(approved ? "已通过，可以导出。" : "已打回，修复后重新审片。");
      await load();
      props.onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "提交失败");
    } finally {
      setBusy(false);
    }
  };

  const checkRow = (check: ReviewCheck) => {
    const state = VERDICT[check.verdict] ?? { label: check.verdict, tone: "neutral" as const };
    return (
      <div class="rounded-md border border-line-soft bg-surface px-2 py-1.5">
        <div class="flex items-center gap-1.5">
          <span class="text-[10.5px] text-dim">{check.label}</span>
          <Badge tone={state.tone}>{state.label}</Badge>
        </div>
        <Show when={check.detail}>
          <div class="mt-1 line-clamp-2 text-[9.5px] leading-4 text-faint">{check.detail}</div>
        </Show>
      </div>
    );
  };

  return (
    <div class="flex h-full flex-col">
      <Show
        when={!loading()}
        fallback={<div class="grid h-full place-items-center text-[11px] text-faint">审片数据加载中…</div>}
      >
        <div class="min-h-0 flex-1 overflow-auto">
          <div class="mb-2 flex flex-wrap items-center gap-2">
            <span class="text-[12px] font-medium text-text">审片</span>
            <Badge tone={tone()}>{qaLabel()}</Badge>
            <span class="text-[10px] text-faint">
              {props.version?.label ?? "—"} · {shots().length} 镜 · {props.version?.duration_s ?? 0}s
            </span>
            <div class="ml-auto flex items-center gap-1.5">
              <Show when={qa()?.brand_hits?.length}>
                <Badge tone="bad">禁用词 {qa()!.brand_hits.length}</Badge>
              </Show>
              <Show when={flagged() > 0}>
                <Badge tone="warn">标了 {flagged()} 镜</Badge>
              </Show>
            </div>
          </div>

          <Show when={review()}>
            <div
              class={`mb-2 flex items-center gap-2 rounded-lg border px-2.5 py-1.5 text-[10.5px] ${
                review()!.status === "approved" ? "border-ok/30 bg-ok/5 text-ok" : "border-bad/30 bg-bad/5 text-bad"
              }`}
            >
              <span>{review()!.status === "approved" ? "已通过" : "已打回"}</span>
              <span class="text-faint">· {review()!.created_at}</span>
              <Show when={review()!.comment}>
                <span class="truncate text-dim">· {review()!.comment}</span>
              </Show>
            </div>
          </Show>

          <div class="grid gap-3 lg:grid-cols-[180px_1fr]">
            <div class="space-y-2">
              <Show
                when={props.version?.render?.path}
                fallback={
                  <div class="grid place-items-center rounded-lg border border-dashed border-line bg-[#0b0e15] p-4 text-center" style={{ "aspect-ratio": "9 / 16" }}>
                    <div>
                      <div class="text-[18px] text-white/15">▣</div>
                      <div class="mt-1 text-[10px] text-white/30">还没有成片</div>
                    </div>
                  </div>
                }
              >
                <div class="overflow-hidden rounded-lg border border-line bg-black" style={{ "aspect-ratio": "9 / 16" }}>
                  <video
                    controls
                    class="h-full w-full object-contain"
                    src={mediaUrl(props.version!.render!.path)!}
                    poster={coverUrl(props.version!.render!.poster || props.version!.render!.path) ?? undefined}
                  />
                </div>
              </Show>

            </div>

            <div class="min-w-0 space-y-2">
              <div class="flex items-center gap-2">
                <span class="text-[10px] tracking-wide text-faint">逐镜</span>
                <span class="text-[9.5px] text-faint">默认全通过；只标有问题的镜</span>
                <button type="button" class="ml-auto text-[9.5px] text-faint underline hover:text-text" onClick={allPass}>
                  全部通过
                </button>
              </div>

              <div class="space-y-1">
                <For each={shots()}>
                  {(shot) => (
                    <div
                      class={`flex items-start gap-2 rounded-lg border px-2 py-1.5 ${
                        decisions()[shot.id] === "flag" ? "border-bad/40 bg-bad/5" : "border-line-soft bg-surface"
                      }`}
                    >
                      <span class="mt-0.5 font-mono text-[9.5px] text-faint">{String(shot.index).padStart(2, "0")}</span>
                      <div class="min-w-0 flex-1">
                        <div class="flex items-center gap-1.5">
                          <span class="text-[10.5px] text-dim">{shot.role}</span>
                          <span class="font-mono text-[9.5px] text-faint">
                            {shot.start_s.toFixed(1)}–{shot.end_s.toFixed(1)}s
                          </span>
                          <Show when={shot.locked}>
                            <span class="text-[9px] text-faint">🔒</span>
                          </Show>
                        </div>
                        <div class="line-clamp-1 text-[9.5px] text-faint">{shot.description}</div>
                      </div>
                      <button
                        type="button"
                        class={`shrink-0 rounded border px-1.5 py-0.5 text-[9.5px] ${
                          decisions()[shot.id] === "flag"
                            ? "border-bad/40 text-bad"
                            : "border-line text-faint hover:text-text"
                        }`}
                        onClick={() => setDecision(shot.id, decisions()[shot.id] === "flag" ? "pass" : "flag")}
                      >
                        {decisions()[shot.id] === "flag" ? "已标问题" : "标问题"}
                      </button>
                    </div>
                  )}
                </For>
              </div>

              <div class="rounded-lg border border-line-soft p-2">
                <div class="flex items-center gap-2">
                  <span class="text-[10px] tracking-wide text-faint">QA 检查</span>
                  <span class="text-[9.5px] text-faint">{(qa()?.checks ?? []).length} 项</span>
                </div>
                <div class="mt-1 grid grid-cols-2 gap-1">
                  <For each={(qa()?.checks ?? []).slice(0, 6)}>{(check) => checkRow(check)}</For>
                </div>
                <Show when={(qa()?.checks ?? []).length === 0}>
                  <div class="mt-1 text-[10px] text-faint">还没有 QA 记录。</div>
                </Show>
              </div>

              <Show when={(qa()?.issues ?? []).length > 0}>
                <div class="rounded-lg border border-warn/25 bg-warn/5 p-2">
                  <div class="text-[10px] text-warn">QA 备注</div>
                  <ul class="mt-1 list-disc space-y-0.5 pl-4 text-[9.5px] leading-4 text-dim">
                    <For each={qa()!.issues.slice(0, 4)}>{(issue) => <li>{issue}</li>}</For>
                  </ul>
                </div>
              </Show>
            </div>
          </div>
        </div>

        <div class="mt-2 shrink-0 space-y-2 border-t border-line-soft pt-2">
          <TextArea
            rows={2}
            value={comment()}
            placeholder="审片备注（可选）：哪里不对、要修什么"
            onInput={(event) => setComment(event.currentTarget.value)}
          />
          <div class="flex flex-wrap items-center gap-1.5">
            <Show when={review()?.status === "approved"}>
              <span class="text-[10.5px] text-ok">已通过。</span>
              <Button size="sm" variant="primary" onClick={props.onExport}>
                导出成片
              </Button>
            </Show>
            <Show when={review()?.status !== "approved"}>
              <Show
                when={qa()?.status === "fail" || flagged() > 0}
                fallback={
                  <Button size="sm" variant="primary" loading={busy()} disabled={!canReview()} onClick={() => void submit(true)}>
                    通过并交付（{shots().length} 镜）
                  </Button>
                }
              >
                <Button size="sm" variant="primary" loading={busy()} disabled={!canReview()} onClick={() => void submit(false)}>
                  修复并继续
                </Button>
                <Button size="sm" disabled={busy()} onClick={() => void submit(true)}>
                  仍然通过
                </Button>
              </Show>
            </Show>
            <Show when={!canReview()}>
              <span class="text-[10px] text-faint">还没有成片，先去成片阶段生成。</span>
            </Show>
            <Show when={result()}>
              <span class="ml-auto text-[10.5px] text-dim">{result()}</span>
            </Show>
            <Show when={error()}>
              <span class="text-[10.5px] text-bad">{error()}</span>
            </Show>
          </div>
        </div>
      </Show>
    </div>
  );
}
