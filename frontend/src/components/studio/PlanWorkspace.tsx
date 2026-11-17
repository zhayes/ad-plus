import { For, Show, createEffect, createSignal, on, onCleanup } from "solid-js";
import Badge from "../ui/Badge";
import Button from "../ui/Button";
import Dialog from "../ui/Dialog";
import Input from "../ui/Input";
import TextArea from "../ui/TextArea";
import { endpoints } from "../../lib/api";
import { fmtEta, fmtUsd } from "../../lib/format";
import { mediaUrl, platformLabel, tierLabel } from "../../lib/projects";
import type { PlanBrief, ProposalResponse, ProposalView, Quote, RouteOption } from "../../lib/types";

interface Props {
  projectId: string;
  route?: RouteOption | null;
  onChanged: () => void;
  onGoNext: () => void;
}

const CHIPS = [
  "再快一点",
  "更有食欲",
  "更高级",
  "预算压一点",
  "镜头少一点",
  "换一个 hook",
];

const STAGES = ["理解简报", "创意方向", "粗分镜", "报价", "完成"];

function emptyBrief(product: string, brief?: Record<string, unknown> | null): PlanBrief {
  const raw = brief ?? {};
  return {
    product: String(raw.product || product || ""),
    audience: String(raw.audience || ""),
    description: String(raw.description || ""),
    tone: String(raw.tone || ""),
    must_say: String(raw.must_say || ""),
    avoid: String(raw.avoid || ""),
    budget_usd: raw.budget_usd == null ? null : Number(raw.budget_usd),
    references: Array.isArray(raw.references) ? raw.references.map(String) : [],
  };
}

function statusTone(status: string): "neutral" | "ok" | "warn" | "bad" | "accent" {
  if (status === "approved") return "ok";
  if (status === "rejected") return "warn";
  if (status === "ready") return "accent";
  return "neutral";
}

export default function PlanWorkspace(props: Props) {
  const [data, setData] = createSignal<ProposalResponse | null>(null);
  const [brief, setBrief] = createSignal<PlanBrief>(emptyBrief(""));
  const [loading, setLoading] = createSignal(true);
  const [busy, setBusy] = createSignal(false);
  const [error, setError] = createSignal("");
  const [revising, setRevising] = createSignal(false);
  const [feedback, setFeedback] = createSignal("");
  const [chips, setChips] = createSignal<string[]>([]);
  const [confirmOpen, setConfirmOpen] = createSignal(false);
  const [briefTouched, setBriefTouched] = createSignal(false);

  let timer: ReturnType<typeof setTimeout> | undefined;

  const proposal = (): ProposalView | null => data()?.proposal ?? null;
  const job = () => data()?.job ?? null;
  const quote = (): Quote | null => proposal()?.quote ?? null;
  const generating = () => {
    const status = job()?.status;
    return status === "running" || status === "queued";
  };
  const approved = () => proposal()?.status === "approved";
  const rejected = () => proposal()?.status === "rejected";
  const hasOutput = () => !!proposal() && (proposal()!.has_packet || proposal()!.has_quote);

  const briefFrom = (value: ProposalView | null): PlanBrief =>
    value ? value.brief : emptyBrief("", propsProjectBrief());

  function propsProjectBrief(): Record<string, unknown> | null {
    return null;
  }

  const load = async (silent = false) => {
    if (!silent) setLoading(true);
    setError("");
    try {
      const result = await endpoints.proposal(props.projectId);
      setData(result);
      if (!briefTouched() && result.proposal) setBrief(briefFrom(result.proposal));
      if (result.job && (result.job.status === "running" || result.job.status === "queued")) {
        schedule();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "方案加载失败");
    } finally {
      if (!silent) setLoading(false);
    }
  };

  const schedule = () => {
    if (timer) clearTimeout(timer);
    timer = setTimeout(async () => {
      await load(true);
    }, 1600);
  };

  createEffect(
    on(
      () => props.projectId,
      () => {
        setBriefTouched(false);
        setData(null);
        void load();
      },
    ),
  );

  onCleanup(() => {
    if (timer) clearTimeout(timer);
  });

  const patchBriefField = <K extends keyof PlanBrief>(key: K, value: PlanBrief[K]) => {
    setBriefTouched(true);
    setBrief((previous) => ({ ...previous, [key]: value }));
  };

  const saveBrief = async () => {
    await endpoints.patchProject(props.projectId, {
      brief: {
        ...brief(),
        product: brief().product.trim(),
        audience: brief().audience.trim(),
      },
    });
    props.onChanged();
  };

  const start = async (feedbackText = "") => {
    setBusy(true);
    setError("");
    try {
      await saveBrief();
      const result = await endpoints.generateProposal(props.projectId, {
        brief: brief(),
        feedback: feedbackText,
      });
      setData(result);
      setRevising(false);
      setFeedback("");
      setChips([]);
      if (result.job) schedule();
    } catch (err) {
      const message = err instanceof Error ? err.message : "方案生成失败";
      setError(message);
      await load(true);
    } finally {
      setBusy(false);
    }
  };

  const reviseAndStart = async () => {
    const note = [...chips(), feedback().trim()].filter(Boolean).join("；");
    if (!note) {
      setError("先说一句想改什么");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const current = quote();
      if (current && current.status === "pending") {
        await endpoints.decideQuote(current.id, props.projectId, false, note);
      }
      await start(note);
    } catch (err) {
      setError(err instanceof Error ? err.message : "提交失败");
    } finally {
      setBusy(false);
    }
  };

  const regenerate = async () => {
    setBusy(true);
    setError("");
    try {
      const current = quote();
      if (current && current.status === "pending") {
        await endpoints.decideQuote(current.id, props.projectId, false, "重新生成方案");
      }
      await start("重新生成，保留项目简报");
    } catch (err) {
      setError(err instanceof Error ? err.message : "重新生成失败");
    } finally {
      setBusy(false);
    }
  };

  const cancel = async () => {
    try {
      await endpoints.cancelProposal(props.projectId);
      await load(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "取消失败");
    }
  };

  const confirm = async () => {
    const current = quote();
    if (!current) return;
    if (current.stale) {
      setError("配置已变更，请重新生成报价后再确认");
      setConfirmOpen(false);
      return;
    }
    if (current.over_budget) {
      setError("报价超过预算上限，请调整预算或生成方式");
      setConfirmOpen(false);
      return;
    }
    setBusy(true);
    setError("");
    try {
      await endpoints.decideQuote(current.id, props.projectId, true, "");
      setConfirmOpen(false);
      await load(true);
      props.onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "确认失败");
    } finally {
      setBusy(false);
    }
  };

  const price = () => {
    const current = quote();
    if (!current) return "—";
    if ((current.low_usd || 0) > 0 || (current.high_usd || 0) > 0) {
      return `${fmtUsd(current.low_usd)}–${fmtUsd(current.high_usd)}`;
    }
    return (current.total_usd || 0) > 0 ? fmtUsd(current.total_usd) : "无付费项";
  };

  const stageIndex = () => {
    const stage = job()?.stage ?? "";
    if (stage === "生成方案") return 2;
    if (stage === "完成") return 4;
    const index = STAGES.findIndex((item) => stage.includes(item));
    return index >= 0 ? index : 0;
  };

  const toggleChip = (chip: string) => {
    setChips((previous) => previous.includes(chip) ? previous.filter((item) => item !== chip) : [...previous, chip]);
  };

  const statusLabel = () => {
    if (approved()) return "方案已确认";
    if (rejected()) return "方案已打回";
    if (quote()?.status === "pending") return "方案待确认";
    return "方案草稿";
  };

  return (
    <div class="h-full overflow-auto px-4 py-4 sm:px-5">
      <div class="mx-auto w-full max-w-[1440px]">
        <div class="mb-4 flex flex-wrap items-end gap-2">
          <div>
            <div class="flex items-center gap-2">
              <h1 class="text-[16px] font-semibold text-text">方案</h1>
              <Badge tone={statusTone(proposal()?.status ?? "none")}>{statusLabel()}</Badge>
            </div>
            <div class="mt-1 flex flex-wrap items-center gap-1.5 text-[11.5px] text-faint">
              <span>{platformLabel(proposal()?.project.platform)} · {proposal()?.project.aspect ?? "9:16"} · {proposal()?.project.duration_s ?? 15}s · {tierLabel(proposal()?.project.quality_tier)}</span>
              <Show when={props.route}>
                <span class="inline-flex items-center gap-1 rounded border border-line px-1.5 py-px text-[9.5px] text-dim">
                  <span class="h-1.5 w-1.5 rounded-full bg-accent" />
                  {props.route!.label} · {props.route!.runtime}
                </span>
              </Show>
            </div>
          </div>
          <div class="ml-auto text-right text-[10.5px] text-faint">
            方案确认后再进入脚本
          </div>
        </div>

        <Show when={quote()?.stale}>
          <div class="mb-3 flex items-center gap-2 rounded-lg border border-warn/30 bg-warn/5 px-3 py-2 text-[11px] text-warn">
            <span class="min-w-0 flex-1">制作设置已变更，当前报价已过期，请重新生成方案与报价。</span>
            <Button size="sm" variant="secondary" onClick={() => void regenerate()}>重新报价</Button>
          </div>
        </Show>

        <Show when={quote()?.over_budget}>
          <div class="mb-3 flex items-center gap-2 rounded-lg border border-bad/30 bg-bad/5 px-3 py-2 text-[11px] text-bad">
            <span class="min-w-0 flex-1">当前报价超过预算上限，不能确认。</span>
            <span class="font-mono">${quote()?.total_usd?.toFixed(2)} / ${quote()?.budget_usd?.toFixed(2)}</span>
          </div>
        </Show>

        <Show when={error()}>
          <div class="mb-3 flex items-center gap-2 rounded-lg border border-bad/30 bg-bad/5 px-3 py-2 text-[11px] text-bad">
            <span class="min-w-0 flex-1">{error()}</span>
            <button type="button" class="underline" onClick={() => void load()}>
              重试
            </button>
          </div>
        </Show>

        <Show when={job()?.status === "failed" && !hasOutput()}>
          <div class="mb-3 flex items-center gap-2 rounded-lg border border-bad/30 bg-bad/5 px-3 py-2 text-[11px] text-bad">
            <span class="min-w-0 flex-1">生成失败：{job()?.error || "未知错误"}</span>
            <button type="button" class="underline" onClick={() => void start()}>
              重试
            </button>
          </div>
        </Show>

        <Show when={!loading()} fallback={<div class="py-20 text-center text-[12px] text-faint">方案加载中…</div>}>
          <Show
            when={hasOutput() || generating()}
            fallback={
              <div class="grid gap-4 xl:grid-cols-[minmax(0,1fr)_300px]">
                <div class="rounded-xl border border-line-soft bg-surface p-5">
                  <div class="text-[13px] font-semibold text-text">先做一份方案，再决定要不要开工</div>
                  <p class="mt-1 max-w-[560px] text-[11.5px] leading-6 text-dim">
                    方案会给出概念、粗分镜、交付规格和报价。确认报价后才进入分镜制作，不会直接渲染整片。
                  </p>
                  <div class="mt-4 grid gap-3 sm:grid-cols-3">
                    <For each={["概念与 hook", "5 镜粗分镜", "报价与 ETA"]}>
                      {(item) => (
                        <div class="rounded-lg border border-line-soft bg-surface-2/40 px-3 py-2 text-[11px] text-dim">
                          <span class="mr-1 text-accent">·</span>{item}
                        </div>
                      )}
                    </For>
                  </div>
                </div>
                <div class="rounded-xl border border-line-soft bg-surface p-3">
                  <div class="text-[10px] tracking-wide text-faint">开始前</div>
                  <div class="mt-2 space-y-1.5 text-[10.5px] text-faint">
                    <div>· 报价未确认前不产生付费生成</div>
                                        <div>· 可先离开，生成完成后回来</div>
                  </div>
                </div>
              </div>
            }
          >
            <Show when={generating()} fallback={<ProposalContent />}>
              <Generating />
            </Show>
          </Show>

          <Show when={!hasOutput() && !generating()}>
            <BriefCard />
          </Show>
        </Show>
      </div>

      <Dialog open={confirmOpen()} onOpenChange={setConfirmOpen} title="确认方案，进入分镜">
        <div class="space-y-3">
          <p class="text-[12px] leading-6 text-dim">
            确认后先写脚本、再做分镜，不会直接渲染整片。当前报价：
            <b class="ml-1 text-text">{price()}</b>
            <Show when={quote()?.eta_seconds}>，预计 {fmtEta(quote()?.eta_seconds)}</Show>。
          </p>
          <div class="rounded-lg border border-line-soft bg-surface-2/40 p-3 text-[11px] leading-5 text-faint">
            方案和报价会锁定为当前版本；修改需要重新生成。
          </div>
          <div class="flex justify-end gap-2">
            <Button size="sm" onClick={() => setConfirmOpen(false)}>再看看</Button>
            <Button size="sm" variant="primary" loading={busy()} disabled={Boolean(quote()?.stale || quote()?.over_budget)} onClick={() => void confirm()}>
              确认方案
            </Button>
          </div>
        </div>
      </Dialog>
    </div>
  );

  function BriefCard() {
    return (
      <div class="mt-4 rounded-xl border border-line-soft bg-surface p-4 sm:p-5">
        <div class="flex items-center gap-2">
          <div class="text-[12.5px] font-semibold text-text">方案简报</div>
          <span class="text-[10.5px] text-faint">只问必要信息；其余用推荐值</span>
        </div>
        <div class="mt-4 grid gap-3 sm:grid-cols-2">
          <label class="block">
            <span class="mb-1 block text-[10.5px] text-faint">产品 / 卖点 *</span>
            <Input value={brief().product} onInput={(event) => patchBriefField("product", event.currentTarget.value)} />
          </label>
          <label class="block">
            <span class="mb-1 block text-[10.5px] text-faint">目标人群</span>
            <Input value={brief().audience} placeholder="例：18–30 岁办公室零食用户" onInput={(event) => patchBriefField("audience", event.currentTarget.value)} />
          </label>
          <label class="block sm:col-span-2">
            <span class="mb-1 block text-[10.5px] text-faint">一句话描述 / 核心利益点</span>
            <TextArea rows={2} value={brief().description} placeholder="例：真实果汁，Q 弹到会自己弹回来" onInput={(event) => patchBriefField("description", event.currentTarget.value)} />
          </label>
          <label class="block">
            <span class="mb-1 block text-[10.5px] text-faint">调性</span>
            <Input value={brief().tone} placeholder="例：轻快、有食欲、带一点夸张" onInput={(event) => patchBriefField("tone", event.currentTarget.value)} />
          </label>
          <label class="block">
            <span class="mb-1 block text-[10.5px] text-faint">预算上限（USD，可选）</span>
            <Input value={brief().budget_usd == null ? "" : String(brief().budget_usd)} placeholder="例：0.8" onInput={(event) => patchBriefField("budget_usd", event.currentTarget.value ? Number(event.currentTarget.value) : null)} />
          </label>
          <label class="block">
            <span class="mb-1 block text-[10.5px] text-faint">必须出现</span>
            <Input value={brief().must_say} placeholder="例：真实果汁添加" onInput={(event) => patchBriefField("must_say", event.currentTarget.value)} />
          </label>
          <label class="block">
            <span class="mb-1 block text-[10.5px] text-faint">避免 / 合规</span>
            <Input value={brief().avoid} placeholder="例：不要绝对化用语" onInput={(event) => patchBriefField("avoid", event.currentTarget.value)} />
          </label>
        </div>
        <div class="mt-4 flex flex-wrap items-center gap-2 border-t border-line-soft pt-3">
          <Button size="sm" variant="primary" loading={busy()} disabled={!brief().product.trim()} onClick={() => void start()}>
            生成方案与报价
          </Button>
          <span class="text-[10px] text-faint">生成后可逐项改；不会自动渲染。</span>
          <Show when={briefTouched()}>
            <button type="button" class="ml-auto text-[10.5px] text-faint underline hover:text-text" onClick={() => void saveBrief()}>
              只保存简报
            </button>
          </Show>
        </div>
      </div>
    );
  }

  function Generating() {
    return (
      <div class="rounded-xl border border-line-soft bg-surface p-5">
        <div class="flex items-center gap-2">
          <span class="h-2 w-2 animate-pulse rounded-full bg-accent" />
          <div class="text-[13px] font-semibold text-text">导演正在做方案</div>
          <span class="ml-auto font-mono text-[10.5px] text-faint">{Math.round((job()?.progress ?? 0) * 100)}%</span>
        </div>
        <p class="mt-1 text-[11.5px] text-faint">可以离开；完成后回来继续。报价未确认前不会渲染。</p>
        <div class="mt-4 h-1.5 overflow-hidden rounded-full bg-surface-2">
          <div class="h-full rounded-full bg-gradient-to-r from-violet to-accent transition-[width] duration-500" style={{ width: `${Math.max(4, Math.round((job()?.progress ?? 0.04) * 100))}%` }} />
        </div>
        <div class="mt-4 grid gap-2 sm:grid-cols-4">
          <For each={STAGES}>
            {(stage, index) => (
              <div class={`rounded-lg border px-2.5 py-2 ${index() <= stageIndex() ? "border-accent/30 bg-accent/5" : "border-line-soft bg-surface-2/30"}`}>
                <div class="text-[9.5px] text-faint">0{index() + 1}</div>
                <div class={`mt-1 text-[11px] ${index() <= stageIndex() ? "text-text" : "text-faint"}`}>{stage}</div>
              </div>
            )}
          </For>
        </div>
        <div class="mt-4 flex items-center gap-2">
          <Button size="sm" variant="ghost" onClick={() => void cancel()}>取消生成</Button>
          <span class="text-[10px] text-faint">{job()?.stage || "准备中"}</span>
        </div>
        <Show when={job()?.error}>
          <div class="mt-3 rounded-lg border border-bad/30 bg-bad/5 px-3 py-2 text-[10.5px] text-bad">{job()?.error}</div>
        </Show>
      </div>
    );
  }

  function ProposalContent() {
    const value = () => proposal()!;
    return (
      <div class="grid gap-4 xl:grid-cols-[minmax(0,1fr)_300px]">
        <div class="min-w-0 space-y-4 pb-4">
          <Show when={approved()}>
            <div class="flex flex-wrap items-center gap-3 rounded-xl border border-ok/30 bg-ok/5 px-4 py-3">
              <div class="min-w-0 flex-1">
                <div class="text-[12px] font-medium text-ok">方案已确认，下一步做分镜</div>
                <div class="mt-0.5 text-[10.5px] text-faint">方案与报价已锁定；不会直接渲染整片。</div>
              </div>
              <Button size="sm" variant="primary" onClick={props.onGoNext}>看脚本</Button>
            </div>
          </Show>
          <Show when={rejected()}>
            <div class="rounded-xl border border-warn/30 bg-warn/5 px-4 py-3">
              <div class="text-[12px] font-medium text-warn">方案已打回</div>
              <div class="mt-0.5 text-[10.5px] text-faint">
                {quote()?.decision?.comment || "按修改意见重新生成一版。"}
              </div>
            </div>
          </Show>

          <section class="rounded-xl border border-line-soft bg-surface p-4 sm:p-5">
            <div class="flex items-center gap-2">
              <span class="font-mono text-[9.5px] text-accent">01</span>
              <span class="text-[10px] tracking-wide text-faint">概念</span>
            </div>
            <h2 class="mt-2 text-[17px] font-semibold leading-7 text-text">{value().concept.title}</h2>
            <Show when={value().concept.hook}>
              <div class="mt-1 text-[12.5px] leading-6 text-accent">{value().concept.hook}</div>
            </Show>
            <div class="mt-3 grid gap-3 2xl:grid-cols-2">
              <div>
                <div class="text-[9.5px] uppercase tracking-wide text-faint">为什么会成立</div>
                <p class="mt-1 text-[11.5px] leading-6 text-dim">{value().concept.insight || "—"}</p>
              </div>
              <div>
                <div class="text-[9.5px] uppercase tracking-wide text-faint">视觉方向</div>
                <p class="mt-1 text-[11.5px] leading-6 text-dim">{value().concept.visual_approach || "—"}</p>
              </div>
            </div>
            <Show when={value().concept.core_message || value().concept.cta}>
              <div class="mt-3 flex flex-wrap gap-x-5 gap-y-1 border-t border-line-soft pt-3 text-[11px] text-dim">
                <Show when={value().concept.core_message}><span>核心信息：{value().concept.core_message}</span></Show>
                <Show when={value().concept.cta}><span>CTA：{value().concept.cta}</span></Show>
              </div>
            </Show>
          </section>

          <Show when={value().script.length > 0}>
            <section class="rounded-xl border border-line-soft bg-surface p-4 sm:p-5">
              <div class="flex items-center gap-2">
                <span class="font-mono text-[9.5px] text-accent">02</span>
                <span class="text-[10px] tracking-wide text-faint">脚本 / 节奏</span>
              </div>
              <div class="mt-2 space-y-1.5">
                <For each={value().script}>{(line) => <div class="text-[11.5px] leading-6 text-dim">{line}</div>}</For>
              </div>
            </section>
          </Show>

          <section class="rounded-xl border border-line-soft bg-surface p-4 sm:p-5">
            <div class="flex items-center gap-2">
              <span class="font-mono text-[9.5px] text-accent">03</span>
              <span class="text-[10px] tracking-wide text-faint">粗分镜</span>
              <span class="ml-auto text-[9.5px] text-faint">报价用，不是最终运镜</span>
            </div>
            <Show when={value().shots.length > 0} fallback={<div class="mt-3 rounded-lg border border-dashed border-line px-3 py-8 text-center text-[10.5px] text-faint">方案里还没有镜头；可以点“改一下”重生成。</div>}>
              <div class="mt-3 divide-y divide-line-soft">
                <For each={value().shots}>
                  {(shot) => (
                    <div class="grid gap-1 py-2.5 sm:grid-cols-[34px_54px_1fr_74px] sm:items-start sm:gap-2">
                      <div class="font-mono text-[10px] text-faint">0{shot.index}</div>
                      <div class="text-[10.5px] text-dim">{shot.role}</div>
                      <div>
                        <div class="text-[11.5px] leading-5 text-text">{shot.visual || "—"}</div>
                        <Show when={shot.text || shot.narration}>
                          <div class="mt-0.5 text-[10.5px] leading-5 text-faint">
                            {[shot.text, shot.narration].filter(Boolean).join(" · ")}
                          </div>
                        </Show>
                      </div>
                      <div class="text-left font-mono text-[10px] text-faint sm:text-right">{shot.duration_s.toFixed(1)}s</div>
                    </div>
                  )}
                </For>
              </div>
            </Show>
          </section>

          <section class="rounded-xl border border-line-soft bg-surface p-4 sm:p-5">
            <div class="flex items-center gap-2">
              <span class="font-mono text-[9.5px] text-accent">04</span>
              <span class="text-[10px] tracking-wide text-faint">交付什么</span>
            </div>
            <div class="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
              <For each={[
                `${platformLabel(value().deliverables.platform)} · ${value().deliverables.aspect}`,
                `${value().deliverables.duration_s}s 成片 · ${value().deliverables.versions} 版`,
                value().deliverables.captions ? "字幕：有" : "字幕：无",
                `音乐：${value().deliverables.music}`,
              ]}>
                {(item) => <div class="rounded-lg border border-line-soft bg-surface-2/30 px-2.5 py-2 text-[10.5px] leading-5 text-dim">{item}</div>}
              </For>
            </div>
            <Show when={value().exclusions.length > 0}>
              <div class="mt-3 border-t border-line-soft pt-2 text-[10.5px] leading-5 text-faint">
                不含：{value().exclusions.join("；")}
              </div>
            </Show>
          </section>

          <Show when={value().assumptions.length > 0}>
            <section class="rounded-xl border border-line-soft bg-surface p-4 sm:p-5">
              <div class="text-[10px] tracking-wide text-faint">假设与前提</div>
              <ul class="mt-2 list-disc space-y-1 pl-4 text-[11px] leading-5 text-dim">
                <For each={value().assumptions}>{(item) => <li>{item}</li>}</For>
              </ul>
            </section>
          </Show>
        </div>

        <aside class="space-y-3 xl:sticky xl:top-0 xl:self-start">
          <div class="rounded-xl border border-line-soft bg-surface p-4">
            <div class="flex items-center gap-2">
              <span class="text-[10px] tracking-wide text-faint">报价</span>
              <span class="ml-auto text-[10px] text-faint">{tierLabel(value().project.quality_tier)}</span>
            </div>
            <div class="mt-1 text-[24px] font-semibold leading-8 text-text">{price()}</div>
            <div class="mt-0.5 text-[10.5px] text-faint">
              ETA {fmtEta(quote()?.eta_seconds)} · {quote()?.currency ?? "USD"}
            </div>
            <Show when={quote()?.audio_budget_usd != null}>
              <div class="mt-1 flex gap-3 text-[9.5px] text-faint">
                <span>配音预算 {fmtUsd(quote()!.audio_budget_usd)}</span>
                <span>画面预算 {fmtUsd(quote()!.video_budget_usd)}</span>
              </div>
            </Show>
            <div class="mt-3 space-y-1 border-t border-line-soft pt-2">
              <For each={quote()?.line_items ?? []}>
                {(line) => (
                  <div class="flex items-center gap-2 text-[10.5px]">
                    <span class="min-w-0 flex-1 truncate text-dim">{line.label || line.tool}</span>
                    <Show when={line.status === "quote_required"}><Badge tone="warn">待询价</Badge></Show>
                    <span class="font-mono text-text">{fmtUsd(line.usd)}</span>
                  </div>
                )}
              </For>
              <Show when={(quote()?.line_items ?? []).length === 0}>
                <div class="text-[10.5px] text-faint">暂无明细</div>
              </Show>
            </div>
            <Show when={quote()?.status === "pending" && !approved()}>
              <div class="mt-3 space-y-2 border-t border-line-soft pt-3">
                <Button class="w-full" size="sm" variant="primary" disabled={busy()} onClick={() => setConfirmOpen(true)}>
                  确认方案，写脚本
                </Button>
                <div class="flex gap-2">
                  <Button class="flex-1" size="sm" disabled={busy()} onClick={() => setRevising((value) => !value)}>
                    改一下
                  </Button>
                  <Button class="flex-1" size="sm" variant="ghost" disabled={busy()} onClick={() => void regenerate()}>
                    重新生成
                  </Button>
                </div>
                <div class="text-[9.5px] leading-4 text-faint">确认后先写脚本，再进入分镜；不会直接渲染。</div>
              </div>
            </Show>
            <Show when={approved()}>
              <div class="mt-3 border-t border-line-soft pt-3">
                <Button class="w-full" size="sm" variant="primary" onClick={props.onGoNext}>看脚本</Button>
              </div>
            </Show>
            <Show when={rejected()}>
              <div class="mt-3 border-t border-line-soft pt-3">
                <Button class="w-full" size="sm" variant="primary" disabled={busy()} onClick={() => void regenerate()}>
                  按意见重新生成
                </Button>
              </div>
            </Show>
            <Show when={!quote() || (quote()?.status !== "pending" && !approved() && !rejected())}>
              <div class="mt-3 border-t border-line-soft pt-3">
                <Button class="w-full" size="sm" variant="primary" disabled={busy()} onClick={() => void regenerate()}>
                  生成报价
                </Button>
              </div>
            </Show>
          </div>

          <Show when={revising() && !approved()}>
            <div class="rounded-xl border border-accent/30 bg-accent/5 p-3">
              <div class="text-[10.5px] text-faint">想改什么？</div>
              <div class="mt-2 flex flex-wrap gap-1">
                <For each={CHIPS}>
                  {(chip) => (
                    <button
                      type="button"
                      class={`rounded border px-1.5 py-0.5 text-[9.5px] ${chips().includes(chip) ? "border-accent/50 bg-accent/10 text-text" : "border-line text-faint hover:text-text"}`}
                      onClick={() => toggleChip(chip)}
                    >
                      {chip}
                    </button>
                  )}
                </For>
              </div>
              <TextArea
                class="mt-2 h-16"
                rows={2}
                value={feedback()}
                placeholder="补充一句（可选）"
                onInput={(event) => setFeedback(event.currentTarget.value)}
              />
              <div class="mt-2 flex gap-2">
                <Button size="sm" onClick={() => setRevising(false)}>取消</Button>
                <Button size="sm" variant="primary" loading={busy()} onClick={() => void reviseAndStart()}>
                  按这个改
                </Button>
              </div>
            </div>
          </Show>

          <div class="rounded-lg border border-line-soft bg-surface px-3 py-2 text-[10px] leading-5 text-faint">
            方案确认后先进入脚本；报价与方案锁定为当前版本。
          </div>
        </aside>
      </div>
    );
  }
}
