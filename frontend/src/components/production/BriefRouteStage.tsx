import { For, Show, createEffect, createSignal, on } from "solid-js";
import Badge from "../ui/Badge";
import Button from "../ui/Button";
import Icon from "../ui/Icon";
import Input from "../ui/Input";
import Select from "../ui/Select";
import TextArea from "../ui/TextArea";
import { endpoints } from "../../lib/api";
import type { PlanBrief, ProductionSettings, ProductionView, RouteOption, StageId } from "../../lib/types";

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

type BriefDraft = { brief: PlanBrief; routeId: string; settings: ProductionSettings | null };
const DRAFTS = new Map<string, BriefDraft>();

export default function BriefRouteStage(props: Props) {
  const cached = DRAFTS.get(props.production.project.id);
  const [brief, setBrief] = createSignal<PlanBrief>(cached?.brief ?? fromProduction(props.production));
  const [routeId, setRouteId] = createSignal(cached?.routeId ?? props.production.route.id);
  const [settings, setSettings] = createSignal<ProductionSettings | null>(cached?.settings ?? props.production.settings ?? null);
  const [busy, setBusy] = createSignal(false);
  const [error, setError] = createSignal("");

  createEffect(
    on(
      () => props.production.project.id,
      () => {
        const draft = DRAFTS.get(props.production.project.id);
        setBrief(draft?.brief ?? fromProduction(props.production));
        setRouteId(draft?.routeId ?? props.production.route.id);
        setSettings(draft?.settings ?? props.production.settings ?? null);
      },
    ),
  );

  createEffect(() => {
    DRAFTS.set(props.production.project.id, {
      brief: brief(),
      routeId: routeId(),
      settings: settings(),
    });
  });

  const update = <K extends keyof PlanBrief>(key: K, value: PlanBrief[K]) => {
    setBrief((previous) => ({ ...previous, [key]: value }));
  };

  const updateSetting = <K extends keyof ProductionSettings>(key: K, value: ProductionSettings[K]) => {
    setSettings((previous) => previous ? { ...previous, [key]: value } : previous);
  };

  const updateOutput = <K extends keyof ProductionSettings["output"]>(key: K, value: ProductionSettings["output"][K]) => {
    setSettings((previous) => previous ? { ...previous, output: { ...previous.output, [key]: value } } : previous);
  };

  const updateGeneration = <K extends keyof ProductionSettings["generation"]>(key: K, value: ProductionSettings["generation"][K]) => {
    setSettings((previous) => previous ? { ...previous, generation: { ...previous.generation, [key]: value } } : previous);
  };

  const updateAudio = <K extends keyof ProductionSettings["audio"]>(key: K, value: ProductionSettings["audio"][K]) => {
    setSettings((previous) => previous ? { ...previous, audio: { ...previous.audio, [key]: value } } : previous);
  };

  const updateVisual = <K extends keyof ProductionSettings["visual"]>(key: K, value: ProductionSettings["visual"][K]) => {
    setSettings((previous) => previous ? { ...previous, visual: { ...previous.visual, [key]: value } } : previous);
  };

  const updateBudget = <K extends keyof ProductionSettings["budget"]>(key: K, value: ProductionSettings["budget"][K]) => {
    setSettings((previous) => previous ? { ...previous, budget: { ...previous.budget, [key]: value } } : previous);
  };

  const saveBrief = async () => {
    const current = settings();
    const body: Record<string, unknown> = {
      brief: {
        ...brief(),
        product: brief().product.trim(),
        audience: brief().audience.trim(),
      },
    };
    if (current) {
      body.production_settings = { ...current, route_id: routeId() };
      body.aspect = current.output.aspect;
      body.duration_s = current.output.duration_s;
      body.quality_tier = current.generation.quality_tier;
    }
    const saved = await endpoints.patchProject(props.production.project.id, body) as {
      project?: { production_settings?: ProductionSettings };
    };
    if (saved?.project?.production_settings) setSettings(saved.project.production_settings);
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
      <div class="mx-auto w-full max-w-[1280px]">
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

            <Show when={settings()}>
              {(value) => (
                <div class="mt-5 space-y-3 border-t border-line-soft pt-4">
                  <div class="flex items-center gap-2">
                    <div class="text-[12px] font-semibold text-text">制作设置</div>
                    <span class="text-[10px] text-faint">配音与画面分开配置</span>
                  </div>

                  <div class="rounded-lg border border-line-soft bg-surface-2/25 p-3">
                    <div class="text-[10px] tracking-wide text-faint">输出</div>
                    <div class="mt-2 grid gap-2 sm:grid-cols-2">
                      <label class="block">
                        <span class="mb-1 block text-[10.5px] text-faint">画幅</span>
                        <Select value={value().output.aspect} options={[
                          { value: "9:16", label: "9:16 竖屏" },
                          { value: "16:9", label: "16:9 横屏" },
                          { value: "1:1", label: "1:1 方形" },
                        ]} onChange={(next) => updateOutput("aspect", next as ProductionSettings["output"]["aspect"])} variant="pill" class="w-full" />
                      </label>
                      <label class="block">
                        <span class="mb-1 block text-[10.5px] text-faint">时长</span>
                        <Input value={String(value().output.duration_s)} onInput={(event) => updateOutput("duration_s", Number(event.currentTarget.value) || 15)} />
                      </label>
                      <label class="block">
                        <span class="mb-1 block text-[10.5px] text-faint">分辨率</span>
                        <Select value={value().output.resolution} options={[
                          { value: "480p", label: "480p" },
                          { value: "720p", label: "720p" },
                          { value: "1080p", label: "1080p" },
                        ]} onChange={(next) => updateOutput("resolution", next as ProductionSettings["output"]["resolution"])} variant="pill" class="w-full" />
                      </label>
                      <label class="block">
                        <span class="mb-1 block text-[10.5px] text-faint">帧率</span>
                        <Select value={String(value().output.fps)} options={[{ value: "24", label: "24 fps" }, { value: "30", label: "30 fps" }]} onChange={(next) => updateOutput("fps", Number(next) as ProductionSettings["output"]["fps"])} variant="pill" class="w-full" />
                      </label>
                    </div>
                  </div>

                  <div class="rounded-lg border border-line-soft bg-surface-2/25 p-3">
                    <div class="flex items-center gap-2">
                      <div class="text-[10px] tracking-wide text-faint">配音</div>
                      <span class="text-[9.5px] text-faint">在 05 素材里单独生成</span>
                    </div>
                    <div class="mt-2 grid gap-2 sm:grid-cols-2">
                      <label class="block">
                        <span class="mb-1 block text-[10.5px] text-faint">音频策略</span>
                        <Select value={value().audio.mode} options={[
                          { value: "external_tts", label: "外部 TTS" },
                          { value: "model_native", label: "模型原生" },
                          { value: "silent", label: "无音频" },
                        ]} onChange={(next) => updateAudio("mode", next as ProductionSettings["audio"]["mode"])} variant="pill" class="w-full" />
                      </label>
                      <label class="block">
                        <span class="mb-1 block text-[10.5px] text-faint">声音 provider</span>
                        <Select value={value().audio.provider} options={[
                          { value: "local", label: "本地系统声音" },
                          { value: "minimax", label: "MiniMax" },
                          { value: "elevenlabs", label: "ElevenLabs" },
                          { value: "heygen", label: "HeyGen" },
                        ]} onChange={(next) => updateAudio("provider", next)} variant="pill" class="w-full" />
                      </label>
                      <label class="block">
                        <span class="mb-1 block text-[10.5px] text-faint">voice_id</span>
                        <Input value={value().audio.voice_id} placeholder="Tingting" onInput={(event) => updateAudio("voice_id", event.currentTarget.value)} />
                      </label>
                      <label class="block">
                        <span class="mb-1 block text-[10.5px] text-faint">超长处理</span>
                        <Select value={value().audio.fit} options={[
                          { value: "trim", label: "裁切到镜头" },
                          { value: "pad", label: "保留原长" },
                          { value: "stretch", label: "拉伸到镜头" },
                        ]} onChange={(next) => updateAudio("fit", next as ProductionSettings["audio"]["fit"])} variant="pill" class="w-full" />
                      </label>
                    </div>
                  </div>

                  <div class="rounded-lg border border-line-soft bg-surface-2/25 p-3">
                    <div class="text-[10px] tracking-wide text-faint">画面</div>
                    <div class="mt-2 grid gap-2 sm:grid-cols-2">
                      <label class="block">
                        <span class="mb-1 block text-[10.5px] text-faint">口播模型</span>
                        <Select value={value().visual.talking_head_profile ?? ""} options={[
                          { value: "", label: "不使用口播模型" },
                          ...(props.production.models ?? []).filter((profile) => profile.capability === "avatar" || profile.capability === "lip_sync").map((profile) => ({ value: profile.id, label: `${profile.label}${profile.status === "available" ? "" : " · 未配置"}` })),
                        ]} onChange={(next) => updateVisual("talking_head_profile", next || null)} variant="pill" class="w-full" />
                      </label>
                      <label class="block">
                        <span class="mb-1 block text-[10.5px] text-faint">B-roll 模型</span>
                        <Select value={value().visual.broll_profile ?? ""} options={[
                          { value: "", label: "不使用 B-roll 模型" },
                          ...(props.production.models ?? []).filter((profile) => profile.capability === "video_generation").map((profile) => ({ value: profile.id, label: `${profile.label}${profile.status === "available" ? "" : " · 未配置"}` })),
                        ]} onChange={(next) => updateVisual("broll_profile", next || null)} variant="pill" class="w-full" />
                      </label>
                      <label class="block">
                        <span class="mb-1 block text-[10.5px] text-faint">质量档位</span>
                        <Select value={value().visual.quality_tier} options={[
                          { value: "draft", label: "草稿 · 最快" },
                          { value: "standard", label: "标准 · 推荐" },
                          { value: "premium", label: "精修 · 高质量" },
                        ]} onChange={(next) => updateVisual("quality_tier", next as ProductionSettings["visual"]["quality_tier"])} variant="pill" class="w-full" />
                      </label>
                      <label class="block">
                        <span class="mb-1 block text-[10.5px] text-faint">生成方式</span>
                        <Select value={value().visual.mode} options={[{ value: "auto", label: "自动补镜" }, { value: "manual", label: "手动选材" }]} onChange={(next) => updateVisual("mode", next as ProductionSettings["visual"]["mode"])} variant="pill" class="w-full" />
                      </label>
                    </div>
                  </div>

                  <div class="rounded-lg border border-line-soft bg-surface-2/25 p-3">
                    <div class="text-[10px] tracking-wide text-faint">预算</div>
                    <div class="mt-2 grid gap-2 sm:grid-cols-3">
                      <label class="block">
                        <span class="mb-1 block text-[10.5px] text-faint">总预算</span>
                        <Input value={String(value().budget.total_usd)} onInput={(event) => updateBudget("total_usd", Number(event.currentTarget.value) || 0)} />
                      </label>
                      <label class="block">
                        <span class="mb-1 block text-[10.5px] text-faint">配音预算</span>
                        <Input value={String(value().budget.audio_usd)} onInput={(event) => updateBudget("audio_usd", Number(event.currentTarget.value) || 0)} />
                      </label>
                      <label class="block">
                        <span class="mb-1 block text-[10.5px] text-faint">画面预算</span>
                        <Input value={String(value().budget.video_usd)} onInput={(event) => updateBudget("video_usd", Number(event.currentTarget.value) || 0)} />
                      </label>
                    </div>
                  </div>

                  <div class="rounded-lg border border-line-soft bg-surface-2/30 px-2.5 py-2 text-[10px] leading-5 text-faint">
                    {value().output.aspect} · {value().output.duration_s}s · {value().output.resolution} · {value().output.fps}fps
                    {" · "}配音 {value().audio.mode} · 画面 {value().visual.talking_head_profile ?? "未选"}
                    {" · "}预算 ${value().budget.total_usd.toFixed(2)}
                  </div>
                </div>
              )}
            </Show>
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
                      onClick={() => {
                        if (!item.available) return;
                        setRouteId(item.id);
                        setSettings((previous) => previous ? { ...previous, route_id: item.id } : previous);
                      }}
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
