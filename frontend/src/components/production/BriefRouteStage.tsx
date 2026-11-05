import { For, Show, createEffect, createSignal, on } from "solid-js";
import Badge from "../ui/Badge";
import Button from "../ui/Button";
import Icon from "../ui/Icon";
import Input from "../ui/Input";
import TextArea from "../ui/TextArea";
import { endpoints } from "../../lib/api";
import type { PlanBrief, ProductionView, RouteOption, StageId } from "../../lib/types";

interface Props {
  production: ProductionView;
  onChanged: () => void;
  onAdvanced: (stage: StageId) => void;
}

function fromProduction(production: ProductionView): PlanBrief {
  const raw = production.brief;
  return {
    product: raw.product || production.project.title || "",
    audience: raw.audience || "",
    description: raw.description || "",
    tone: raw.tone || "",
    must_say: raw.must_say || "",
    avoid: raw.avoid || "",
    budget_usd: raw.budget_usd ?? null,
    references: raw.references || [],
  };
}

export default function BriefRouteStage(props: Props) {
  const [brief, setBrief] = createSignal<PlanBrief>(fromProduction(props.production));
  const [routeId, setRouteId] = createSignal(props.production.route.id);
  const [busy, setBusy] = createSignal(false);
  const [error, setError] = createSignal("");

  createEffect(
    on(
      () => props.production.project.id,
      () => {
        setBrief(fromProduction(props.production));
        setRouteId(props.production.route.id);
      },
    ),
  );

  const update = <K extends keyof PlanBrief>(key: K, value: PlanBrief[K]) => {
    setBrief((previous) => ({ ...previous, [key]: value }));
  };

  const saveBrief = async () => {
    await endpoints.patchProject(props.production.project.id, {
      brief: {
        ...brief(),
        product: brief().product.trim(),
        audience: brief().audience.trim(),
      },
    });
  };

  const saveOnly = async () => {
    setBusy(true);
    setError("");
    try {
      await saveBrief();
      await endpoints.setRoute(props.production.project.id, routeId());
      props.onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存失败");
    } finally {
      setBusy(false);
    }
  };

  const confirmBrief = async () => {
    if (!brief().product.trim()) {
      setError("先写一个产品 / 主题");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await saveBrief();
      await endpoints.setRoute(props.production.project.id, routeId());
      await endpoints.approveStage(props.production.project.id, "brief");
      props.onChanged();
      props.onAdvanced("proposal");
    } catch (err) {
      setError(err instanceof Error ? err.message : "确认简报失败");
    } finally {
      setBusy(false);
    }
  };

  const startProposal = async () => {
    if (!brief().product.trim()) {
      setError("先写一个产品 / 主题");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await saveBrief();
      await endpoints.setRoute(props.production.project.id, routeId());
      await endpoints.approveStage(props.production.project.id, "brief");
      await endpoints.generateProposal(props.production.project.id, { brief: brief() });
      props.onChanged();
      props.onAdvanced("proposal");
    } catch (err) {
      setError(err instanceof Error ? err.message : "启动方案失败");
    } finally {
      setBusy(false);
    }
  };

  const route = (): RouteOption => props.production.routes.find((item) => item.id === routeId()) ?? props.production.routes[0];
  const hasProposal = () => !!props.production.proposal || !!props.production.quote;
  const briefDone = () => props.production.approvals?.brief != null;

  return (
    <div class="h-full overflow-auto p-4 sm:p-5">
      <div class="mx-auto w-full max-w-[1120px]">
        <div class="mb-4">
          <div class="flex items-center gap-2">
            <h1 class="text-[16px] font-semibold text-text">简报与制作路线</h1>
            <Badge tone={briefDone() ? "ok" : "accent"}>{briefDone() ? "已确认" : "开始"}</Badge>
          </div>
          <p class="mt-1 max-w-[680px] text-[11.5px] leading-6 text-dim">
            先定这条广告怎么做，再生成方案。路线决定成本、时间和每镜的生产方式；报价确认前不会渲染。
          </p>
        </div>

        <Show when={error()}>
          <div class="mb-3 rounded-lg border border-bad/30 bg-bad/5 px-3 py-2 text-[11px] text-bad">{error()}</div>
        </Show>

        <div class="grid gap-4 lg:grid-cols-[minmax(0,1fr)_360px]">
          <section class="rounded-xl border border-line-soft bg-surface p-4 sm:p-5">
            <div class="text-[12.5px] font-semibold text-text">广告简报</div>
            <div class="mt-3 grid gap-3 sm:grid-cols-2">
              <label class="block sm:col-span-2">
                <span class="mb-1 block text-[10.5px] text-faint">产品 / 卖点 *</span>
                <Input value={brief().product} placeholder="例：QQ糖 · 真实果汁、Q 弹" onInput={(event) => update("product", event.currentTarget.value)} />
              </label>
              <label class="block">
                <span class="mb-1 block text-[10.5px] text-faint">目标人群</span>
                <Input value={brief().audience} placeholder="例：18–30 岁办公室零食用户" onInput={(event) => update("audience", event.currentTarget.value)} />
              </label>
              <label class="block">
                <span class="mb-1 block text-[10.5px] text-faint">调性</span>
                <Input value={brief().tone} placeholder="例：轻快、有食欲、带一点夸张" onInput={(event) => update("tone", event.currentTarget.value)} />
              </label>
              <label class="block sm:col-span-2">
                <span class="mb-1 block text-[10.5px] text-faint">核心利益点 / 一句话描述</span>
                <TextArea rows={2} value={brief().description} placeholder="例：咬下去果汁在嘴里弹回来" onInput={(event) => update("description", event.currentTarget.value)} />
              </label>
              <label class="block">
                <span class="mb-1 block text-[10.5px] text-faint">必须出现</span>
                <Input value={brief().must_say} placeholder="例：真实果汁添加" onInput={(event) => update("must_say", event.currentTarget.value)} />
              </label>
              <label class="block">
                <span class="mb-1 block text-[10.5px] text-faint">避免 / 合规</span>
                <Input value={brief().avoid} placeholder="例：不要绝对化用语" onInput={(event) => update("avoid", event.currentTarget.value)} />
              </label>
              <label class="block">
                <span class="mb-1 block text-[10.5px] text-faint">预算上限（USD）</span>
                <Input value={brief().budget_usd == null ? "" : String(brief().budget_usd)} placeholder="可选" onInput={(event) => update("budget_usd", event.currentTarget.value ? Number(event.currentTarget.value) : null)} />
              </label>
              <div class="flex items-end text-[10px] text-faint">
                {props.production.project.platform} · {props.production.project.aspect} · {props.production.project.duration_s}s
              </div>
            </div>
          </section>

          <section class="rounded-xl border border-line-soft bg-surface p-4">
            <div class="text-[12.5px] font-semibold text-text">制作路线</div>
            <div class="mt-3 space-y-2">
              <For each={props.production.routes}>
                {(item) => {
                  const selected = () => routeId() === item.id;
                  return (
                    <button
                      type="button"
                      disabled={!item.available}
                      class={`w-full rounded-lg border p-3 text-left transition-colors ${
                        selected() ? "border-accent/50 bg-accent/5" : "border-line-soft bg-surface-2/25 hover:border-line"
                      } ${item.available ? "" : "cursor-not-allowed opacity-55"}`}
                      onClick={() => item.available && setRouteId(item.id)}
                    >
                      <div class="flex items-center gap-2">
                        <span class={`h-2 w-2 rounded-full ${selected() ? "bg-accent" : "bg-line"}`} />
                        <span class="text-[11.5px] font-medium text-text">{item.label}</span>
                        <Show when={item.id === props.production.route.id && !selected()}>
                          <Badge tone="neutral">当前</Badge>
                        </Show>
                        <span class="ml-auto text-[9.5px] text-faint">{item.cost_hint}</span>
                      </div>
                      <div class="mt-1 text-[10.5px] leading-5 text-faint">{item.best_for}</div>
                      <div class="mt-1 flex flex-wrap gap-x-2 text-[9.5px] text-faint">
                        <span>{item.pipeline}</span>
                        <span>·</span>
                        <span>{item.eta_hint}</span>
                        <Show when={item.requires.length > 0}>
                          <span>·</span>
                          <span class="text-warn">缺：{item.requires.join("、")}</span>
                        </Show>
                      </div>
                    </button>
                  );
                }}
              </For>
            </div>

            <div class="mt-3 rounded-lg border border-line-soft bg-surface-2/25 p-2.5 text-[10px] leading-5 text-faint">
              <div class="flex items-center gap-1.5 text-dim"><Icon name="route" size={12} /> 路线决定 UI 里的“每镜生产方式”</div>
              <div class="mt-1">{route().description}</div>
            </div>
          </section>
        </div>

        <div class="mt-4 flex flex-wrap items-center gap-2">
          <Show
            when={!hasProposal()}
            fallback={
              <Show
                when={briefDone()}
                fallback={
                  <Button size="sm" variant="primary" loading={busy()} onClick={() => void confirmBrief()}>
                    确认简报，看方案
                  </Button>
                }
              >
                <Button size="sm" variant="primary" onClick={() => props.onAdvanced("proposal")}>
                  进入方案
                </Button>
              </Show>
            }
          >
            <Button size="sm" variant="primary" loading={busy()} onClick={() => void startProposal()}>
              保存并生成方案
            </Button>
          </Show>
          <Button size="sm" variant="ghost" disabled={busy()} onClick={() => void saveOnly()}>
            只保存
          </Button>
          <span class="text-[10px] text-faint">
            {hasProposal() ? "已有方案；修改简报后可在方案页重新生成。" : "生成方案不会渲染；确认报价后才进入脚本。"}
          </span>
        </div>
      </div>
    </div>
  );
}
