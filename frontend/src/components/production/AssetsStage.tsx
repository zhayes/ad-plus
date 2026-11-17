import { For, Show, createSignal, onCleanup, onMount } from "solid-js";
import Badge from "../ui/Badge";
import Button from "../ui/Button";
import Dialog from "../ui/Dialog";
import Icon from "../ui/Icon";
import { endpoints } from "../../lib/api";
import { mediaUrl } from "../../lib/projects";
import type { Asset, Job, Persona, Product, ProductionView, StageId } from "../../lib/types";

interface Props {
  production: ProductionView;
  onChanged: () => void;
  onAdvanced: (stage: StageId) => void;
}

export default function AssetsStage(props: Props) {
  const [busy, setBusy] = createSignal(false);
  const [setupBusy, setSetupBusy] = createSignal(false);
  const [error, setError] = createSignal("");
  const [setupMessage, setSetupMessage] = createSignal("");
  const [personas, setPersonas] = createSignal<Persona[]>([]);
  const [products, setProducts] = createSignal<Product[]>([]);
  const [personaId, setPersonaId] = createSignal(props.production.persona?.id ?? "");
  const [productId, setProductId] = createSignal(props.production.product?.id ?? "");
  const [assetOpen, setAssetOpen] = createSignal(false);
  const [assetLoading, setAssetLoading] = createSignal(false);
  const [assetRows, setAssetRows] = createSignal<Asset[]>([]);
  const [assetTarget, setAssetTarget] = createSignal<string | null>(null);
  const [tab, setTab] = createSignal<"audio" | "visual">(
    (props.production.settings?.audio.mode ?? "silent") === "external_tts" ? "audio" : "visual",
  );
  const [genJob, setGenJob] = createSignal<Job | null>(null);
  const [genError, setGenError] = createSignal("");
  const [audioJob, setAudioJob] = createSignal<Job | null>(null);
  const [audioError, setAudioError] = createSignal("");
  let genTimer: ReturnType<typeof setTimeout> | undefined;
  let audioTimer: ReturnType<typeof setTimeout> | undefined;

  onMount(() => {
    void endpoints.personas().then((data) => setPersonas(data.personas ?? [])).catch(() => undefined);
    void endpoints.products().then((data) => setProducts(data.products ?? [])).catch(() => undefined);
    if (!personaId()) {
      const bound = props.production.shots.find((shot) => shot.persona_id)?.persona_id;
      if (bound) setPersonaId(bound);
    }
    if (!productId()) {
      const bound = props.production.shots.find((shot) => shot.product_id)?.product_id;
      if (bound) setProductId(bound);
    }
    void endpoints.jobs(props.production.project.id).then((data) => {
      const rows = (data.jobs ?? []).slice().sort((a, b) => String(b.created_at ?? "").localeCompare(String(a.created_at ?? "")));
      const audio = rows.filter((job) => job.kind === "audio_generation");
      const audioActive = audio.find((job) => job.status === "running" || job.status === "queued");
      if (audioActive) {
        setAudioJob(audioActive);
        void pollAudio(audioActive.id);
      } else if (audio[0]?.status === "failed") {
        setAudioJob(audio[0]);
        setAudioError(audio[0].error || "部分配音失败");
      }
      const generation = rows.filter((job) => job.kind === "asset_generation");
      const active = generation.find((job) => job.status === "running" || job.status === "queued");
      if (active) {
        setGenJob(active);
        void pollGeneration(active.id);
      } else if (generation[0]?.status === "failed" && !props.production.shots.some((shot) => shot.preview)) {
        setGenJob(generation[0]);
        setGenError(generation[0].error || "部分镜头生成失败");
      }
    }).catch(() => undefined);
  });

  const approved = () => props.production.stages.find((stage) => stage.id === "assets")?.status === "approved";
  const previewed = () => props.production.shots.filter((shot) => shot.preview).length;
  const local = () => props.production.route.id === "local_motion";
  const shotAudioMode = (shot: { audio?: { mode?: string }; production_method?: string; kind?: string }) => {
    if (shot.audio?.mode) return shot.audio.mode;
    if (shot.production_method === "avatar" || shot.production_method === "lip_sync" || shot.kind === "talking_head") return "external_tts";
    return props.production.settings?.audio.mode ?? "silent";
  };
  const audioRequired = () => props.production.shots.filter((shot) => shotAudioMode(shot) === "external_tts");
  const audioReady = () => audioRequired().filter((shot) => shot.audio?.status === "ready").length;
  const audioFor = (shot: { id: string }) => props.production.shots.find((item) => item.id === shot.id)?.audio;
  const canApprove = () => local() || (
    previewed() >= props.production.shots.length && audioReady() >= audioRequired().length
  );
  const needsAudio = (shot: { id: string; audio?: { mode?: string; status?: string } }) => {
    const mode = shotAudioMode(shot);
    return mode === "external_tts" && shot.audio?.status !== "ready";
  };

  const versionId = () => props.production.version?.id ?? "";

  const pollGeneration = async (jobId: string) => {
    try {
      const data = await endpoints.jobs(props.production.project.id);
      const job = data.jobs.find((item) => item.id === jobId) ?? null;
      setGenJob(job);
      if (job && (job.status === "running" || job.status === "queued")) {
        genTimer = setTimeout(() => void pollGeneration(jobId), 1800);
        return;
      }
      if (job?.status === "failed") setGenError(job.error || "部分镜头生成失败，可查看任务日志");
      props.onChanged();
    } catch {
      genTimer = setTimeout(() => void pollGeneration(jobId), 2500);
    }
  };

  const startGeneration = async (shotIds?: string[], force = false) => {
    setGenError("");
    try {
      const result = await endpoints.startAssetGeneration(props.production.project.id, { shot_ids: shotIds, force });
      await pollGeneration(result.job_id);
    } catch (err) {
      setGenError(err instanceof Error ? err.message : "启动生成失败");
    }
  };

  const generateMissing = () => {
    const missing = audioRequired().length - audioReady();
    if (missing > 0) {
      setTab("audio");
      setAudioError(`还有 ${missing} 个镜头缺少配音，先生成配音`);
      return;
    }
    return startGeneration(undefined, false);
  };

  const pollAudio = async (jobId: string) => {
    try {
      const data = await endpoints.jobs(props.production.project.id);
      const job = data.jobs.find((item) => item.id === jobId) ?? null;
      setAudioJob(job);
      if (job && (job.status === "running" || job.status === "queued")) {
        audioTimer = setTimeout(() => void pollAudio(jobId), 1600);
        return;
      }
      if (job?.status === "failed") setAudioError(job.error || "部分配音失败");
      props.onChanged();
    } catch {
      audioTimer = setTimeout(() => void pollAudio(jobId), 2400);
    }
  };

  const startAudio = async (shotIds?: string[], force = false) => {
    setAudioError("");
    try {
      const result = await endpoints.startAudioGeneration(props.production.project.id, { shot_ids: shotIds, force });
      await pollAudio(result.job_id);
    } catch (err) {
      setAudioError(err instanceof Error ? err.message : "启动配音失败");
    }
  };

  onCleanup(() => {
    if (genTimer) clearTimeout(genTimer);
    if (audioTimer) clearTimeout(audioTimer);
  });

  const personaName = (id?: string | null) => personas().find((item) => item.id === id)?.name ?? (id ? id : "");
  const productName = (id?: string | null) => products().find((item) => item.id === id)?.name ?? (id ? id : "");
  const selectedPersona = () => personas().find((item) => item.id === personaId()) ?? null;
  const selectedProduct = () => products().find((item) => item.id === productId()) ?? null;

  const bindShot = async (shotId: string, fields: { persona_id?: string | null; product_id?: string | null }) => {
    if (!versionId()) return;
    try {
      await endpoints.updateShot(props.production.project.id, versionId(), shotId, fields);
      props.onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "绑定镜头失败");
    }
  };

  const applyToAll = async () => {
    if (!versionId()) return;
    setSetupBusy(true);
    setError("");
    setSetupMessage("");
    try {
      // Version writes are read-modify-write on one JSON file; concurrent
      // PATCHes lose updates. Apply sequentially so every shot is persisted.
      for (const shot of props.production.shots) {
        await endpoints.updateShot(
          props.production.project.id, versionId(), shot.id,
          {
            persona_id: personaId() || null,
            product_id: productId() || null,
            ...(personaId() ? { production_method: "avatar" } : {}),
          },
        );
      }
      setSetupMessage(
        `已应用到 ${props.production.shots.length} 个镜头` +
        (personaId() ? ` · 主播 ${personaName(personaId())}` : "") +
        (productId() ? ` · 商品 ${productName(productId())}` : ""),
      );
      props.onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "应用失败");
    } finally {
      setSetupBusy(false);
    }
  };

  const openAssets = async (shotId: string) => {
    setAssetTarget(shotId);
    setAssetOpen(true);
    setAssetLoading(true);
    try {
      const data = await endpoints.assets();
      setAssetRows((data.assets ?? []).filter((asset) => asset.kind === "image" || asset.kind === "video"));
    } catch (err) {
      setError(err instanceof Error ? err.message : "素材加载失败");
    } finally {
      setAssetLoading(false);
    }
  };

  const bindAsset = async (asset: Asset) => {
    const shotId = assetTarget();
    const shot = props.production.shots.find((item) => item.id === shotId);
    if (!shot || !versionId()) return;
    setAssetOpen(false);
    try {
      await endpoints.updateShot(props.production.project.id, versionId(), shot.id, {
        preview: asset.path,
        asset_refs: { ...(shot.asset_refs ?? {}), source_video: asset.path },
        status: "ready",
      });
      props.onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "绑定素材失败");
    }
  };

  const approve = async () => {
    if (!local() && previewed() < props.production.shots.length) {
      setError(`还有 ${props.production.shots.length - previewed()} 个镜头没有素材；先为每个镜头选择或生成素材，再通过。`);
      return;
    }
    setBusy(true);
    setError("");
    try {
      await endpoints.approveStage(props.production.project.id, "assets");
      props.onChanged();
      props.onAdvanced("compose");
    } catch (err) {
      setError(err instanceof Error ? err.message : "确认素材失败");
    } finally {
      setBusy(false);
    }
  };

  const isVideoPath = (path?: string | null) => Boolean(path && /\.(mp4|mov|webm|m4v)$/i.test(path));

  function AudioPanel() {
    const audioCfg = () => props.production.settings?.audio;
    const backfill = async () => {
      try {
        const result = await endpoints.backfillNarration(props.production.project.id);
        setAudioError("");
        props.onChanged();
        if (!result.updated) setAudioError("脚本里没有可补全的口播句");
      } catch (err) {
        setAudioError(err instanceof Error ? err.message : "补全台词失败");
      }
    };
    const useExternal = async () => {
      const settings = props.production.settings;
      if (!settings) return;
      try {
        await endpoints.patchProject(props.production.project.id, {
          production_settings: {
            ...settings,
            audio: { ...settings.audio, mode: "external_tts", provider: "local", voice_id: settings.audio.voice_id || "Tingting", generate_before_video: true },
          },
        });
        props.onChanged();
      } catch (err) {
        setAudioError(err instanceof Error ? err.message : "切换音频策略失败");
      }
    };
    return (
      <div class="space-y-3 pb-4">
        <div class="flex flex-wrap items-center gap-2 rounded-xl border border-line-soft bg-surface/50 px-3 py-2.5">
          <div class="text-[11px] text-text">项目配音</div>
          <span class="rounded border border-line px-1.5 py-px text-[9.5px] text-dim">
            {audioCfg()?.mode === "external_tts" ? `${audioCfg()?.provider} · ${audioCfg()?.voice_id}` : audioCfg()?.mode === "model_native" ? "模型原生" : "无音频"}
          </span>
          <Show when={audioCfg()?.mode === "external_tts"}>
            <span class="text-[9.5px] text-faint">语速 {audioCfg()?.speed} · 超长 {audioCfg()?.fit}</span>
          </Show>
          <Show when={audioCfg()?.mode !== "external_tts"}>
            <span class="text-[9.5px] text-warn">口播镜头会按外部 TTS 生成</span>
            <button type="button" class="text-[9.5px] text-accent underline" onClick={() => void useExternal()}>改为外部 TTS</button>
          </Show>
          <Button class="ml-auto" size="sm" variant="secondary" onClick={() => void backfill()}>
            补全台词
          </Button>
          <Button size="sm" variant="primary" loading={!!audioJob() && audioJob()!.status === "running"} onClick={() => void startAudio(undefined, false)}>
            生成缺失配音
          </Button>
        </div>
        <For each={props.production.shots}>
          {(shot) => {
            const audio = () => audioFor(shot);
            const mode = () => shotAudioMode(shot);
            return (
              <div class="flex flex-wrap items-center gap-3 rounded-xl border border-line-soft bg-surface px-3 py-2.5">
                <span class="w-8 font-mono text-[10px] text-faint">{shot.id}</span>
                <div class="min-w-[180px] flex-1">
                  <div class="flex items-center gap-2">
                    <span class="text-[11px] text-text">{shot.role}</span>
                    <Show when={audio()?.status === "ready"}>
                      <Badge tone="ok">已配音</Badge>
                    </Show>
                    <Show when={audio()?.status === "failed"}>
                      <Badge tone="bad">失败</Badge>
                    </Show>
                    <Show when={mode() !== "external_tts"}>
                      <Badge tone="neutral">{mode() === "model_native" ? "模型原生" : "无音频"}</Badge>
                    </Show>
                  </div>
                  <div class="mt-0.5 line-clamp-1 text-[10.5px] text-faint">{shot.narration || shot.description || "（没有台词）"}</div>
                </div>
                <Show when={audio()?.path}>
                  <audio controls preload="none" src={mediaUrl(audio()!.path!) ?? undefined} class="h-8 w-[220px] max-w-full" />
                </Show>
                <span class="w-12 text-right font-mono text-[9.5px] text-faint">
                  {audio()?.duration_s ? `${Number(audio()!.duration_s).toFixed(1)}s` : ""}
                </span>
                <Show when={mode() === "external_tts"}>
                  <Button size="sm" variant="secondary" onClick={() => void startAudio([shot.id], Boolean(audio()?.path))}>
                    {audio()?.status === "ready" ? "重新配音" : "生成配音"}
                  </Button>
                </Show>
              </div>
            );
          }}
        </For>
      </div>
    );
  }

  return (
    <div class="h-full overflow-auto p-4 sm:p-5">
      <div class="mx-auto w-full max-w-[1180px]">
        <div class="mb-4 flex flex-wrap items-end gap-2">
          <div>
            <div class="flex items-center gap-2">
              <h1 class="text-[16px] font-semibold text-text">素材</h1>
              <Badge tone={approved() ? "ok" : "accent"}>{approved() ? "已确认" : "准备中"}</Badge>
            </div>
            <p class="mt-1 text-[11.5px] text-faint">
              {local() ? "本地动效路线以程序化画面为主；这里确认每镜的画面方向和素材状态。" : "确认每个镜头的素材、来源与可用性。"}
            </p>
          </div>
          <div class="ml-auto flex items-center gap-2">
            <div class="text-right text-[10px] text-faint">
              <div>配音 {audioReady()} / {audioRequired().length} · 画面 {previewed()} / {props.production.shots.length}</div>
              <div class="mt-0.5 text-[9.5px]">
                主播 {props.production.shots.filter((shot) => shot.persona_id).length}/{props.production.shots.length}
                {" · "}
                商品 {props.production.shots.filter((shot) => shot.product_id).length}/{props.production.shots.length}
              </div>
            </div>
            <Show when={props.production.route.id !== "local_motion"}>
              <Show
                when={tab() === "audio"}
                fallback={<Button size="sm" variant="primary" loading={!!genJob() && genJob()!.status === "running"} onClick={() => void generateMissing()}>生成缺失画面</Button>}
              >
                <Button size="sm" variant="primary" loading={!!audioJob() && audioJob()!.status === "running"} onClick={() => void startAudio(undefined, false)}>生成缺失配音</Button>
              </Show>
            </Show>
          </div>
        </div>

        <div class="mb-3 inline-flex rounded-lg border border-line-soft bg-surface/50 p-0.5">
          <button
            type="button"
            class={`rounded-md px-3 py-1.5 text-[11px] ${tab() === "audio" ? "bg-accent text-white" : "text-faint hover:text-text"}`}
            onClick={() => setTab("audio")}
          >
            配音 {audioReady()}/{audioRequired().length}
          </button>
          <button
            type="button"
            class={`rounded-md px-3 py-1.5 text-[11px] ${tab() === "visual" ? "bg-accent text-white" : "text-faint hover:text-text"}`}
            onClick={() => setTab("visual")}
          >
            画面 {previewed()}/{props.production.shots.length}
          </button>
        </div>

        <Show when={error()}>
          <div class="mb-3 rounded-lg border border-bad/30 bg-bad/5 px-3 py-2 text-[11px] text-bad">{error()}</div>
        </Show>

        <Show when={audioError()}>
          <div class="mb-3 rounded-lg border border-bad/30 bg-bad/5 px-3 py-2 text-[11px] text-bad">{audioError()}</div>
        </Show>

        <Show when={genError()}>
          <div class="mb-3 rounded-lg border border-bad/30 bg-bad/5 px-3 py-2 text-[11px] text-bad">{genError()}</div>
        </Show>

        <Show when={audioJob()}>
          {(job) => (
            <div class="mb-3 flex items-center gap-2 rounded-lg border border-line-soft bg-surface/50 px-3 py-2 text-[10.5px] text-faint">
              <span class="h-1.5 w-1.5 animate-pulse rounded-full bg-accent" />
              <span>配音生成 · {job().status}</span>
              <span class="ml-auto font-mono">{Math.round(Number(job().progress || 0) * 100)}%</span>
            </div>
          )}
        </Show>

        <Show when={genJob()}>
          {(job) => (
            <div class="mb-3 flex items-center gap-2 rounded-lg border border-line-soft bg-surface/50 px-3 py-2 text-[10.5px] text-faint">
              <span class="h-1.5 w-1.5 animate-pulse rounded-full bg-accent" />
              <span>镜头生成 · {job().status}</span>
              <span class="ml-auto font-mono">{Math.round(Number(job().progress || 0) * 100)}%</span>
            </div>
          )}
        </Show>

        <Show when={tab() === "audio"} fallback={
        <div>
        <div class="mb-4 rounded-xl border border-line-soft bg-surface/50 p-3">
          <div class="flex flex-wrap items-end gap-2">
            <label class="min-w-[180px] flex-1">
              <span class="mb-1 block text-[10px] text-faint">数字人主播</span>
              <div class="flex items-center gap-2">
                <Show when={selectedPersona()?.preview_path || selectedPersona()?.source_path} fallback={<span class="grid h-9 w-9 shrink-0 place-items-center rounded-md border border-line bg-surface-2 text-[10px] text-faint">人</span>}>
                  <img
                    src={mediaUrl((selectedPersona()!.preview_path || selectedPersona()!.source_path)!)}
                    alt=""
                    class="h-9 w-9 shrink-0 rounded-md border border-line object-cover"
                  />
                </Show>
                <select
                  class="h-9 min-w-0 flex-1 rounded-md border border-line bg-surface px-2 text-[11px] text-dim outline-none focus:border-accent/60"
                  value={personaId()}
                  onChange={(event) => setPersonaId(event.currentTarget.value)}
                >
                  <option value="" selected={!personaId()}>不绑定数字人</option>
                  <For each={personas()}>{(persona) => <option value={persona.id} selected={persona.id === personaId()}>{persona.name}</option>}</For>
                </select>
              </div>
            </label>
            <label class="min-w-[150px] flex-1">
              <span class="mb-1 block text-[10px] text-faint">商品</span>
              <div class="flex items-center gap-2">
                <Show when={selectedProduct()?.hero_path} fallback={<span class="grid h-9 w-9 shrink-0 place-items-center rounded-md border border-line bg-surface-2 text-[10px] text-faint">品</span>}>
                  <img src={mediaUrl(selectedProduct()!.hero_path!)} alt="" class="h-9 w-9 shrink-0 rounded-md border border-line object-cover" />
                </Show>
                <select
                  class="h-9 min-w-0 flex-1 rounded-md border border-line bg-surface px-2 text-[11px] text-dim outline-none focus:border-accent/60"
                  value={productId()}
                  onChange={(event) => setProductId(event.currentTarget.value)}
                >
                  <option value="" selected={!productId()}>不绑定商品</option>
                  <For each={products()}>{(product) => <option value={product.id} selected={product.id === productId()}>{product.name}</option>}</For>
                </select>
              </div>
            </label>
            <Button size="sm" variant="secondary" disabled={setupBusy() || !versionId()} onClick={() => void applyToAll()}>
              {setupBusy() ? "应用中…" : "应用到全部镜头"}
            </Button>
          </div>
          <div class="mt-2 flex flex-wrap items-center gap-2">
            <p class="text-[10px] text-faint">主播和商品是上游输入；每个镜头还需要自己的画面/视频素材。</p>
            <Show when={setupMessage()}>
              <span class="ml-auto text-[10px] text-ok">{setupMessage()}</span>
            </Show>
          </div>
        </div>

        <Show
          when={props.production.shots.length > 0}
          fallback={
            <div class="rounded-xl border border-dashed border-line bg-surface/40 py-16 text-center">
              <div class="text-[12px] text-dim">还没有镜头</div>
              <div class="mt-1 text-[10.5px] text-faint">先去分镜添加镜头，再回来准备素材。</div>
              <Button class="mt-3" size="sm" onClick={() => props.onAdvanced("scene")}>去分镜</Button>
            </div>
          }
        >
          <div class="grid gap-3 pb-4 sm:grid-cols-2 xl:grid-cols-3">
            <For each={props.production.shots}>
              {(shot) => (
                <div class="overflow-hidden rounded-xl border border-line-soft bg-surface">
                  <div class="relative bg-[#0b0e15]" style={{ "aspect-ratio": "16 / 9" }}>
                    <Show
                      when={shot.preview}
                      fallback={
                        <div class="flex h-full flex-col items-center justify-center gap-1.5 text-faint">
                          <Icon name="image" size={20} />
                          <span class="text-[9.5px]">{local() ? "动效镜头，无需外部素材" : "待生成"}</span>
                        </div>
                      }
                    >
                      <Show
                        when={isVideoPath(shot.preview)}
                        fallback={<img src={mediaUrl(shot.preview) ?? undefined} alt="" class="h-full w-full object-cover" />}
                      >
                        <video
                          controls
                          playsinline
                          preload="metadata"
                          src={mediaUrl(shot.preview) ?? undefined}
                          class="h-full w-full object-contain"
                        />
                      </Show>
                    </Show>
                    <span class="absolute left-2 top-2"><Badge tone="neutral">{shot.id}</Badge></span>
                  </div>
                  <div class="p-2.5">
                    <div class="flex items-center gap-2">
                      <span class="text-[11px] text-text">{shot.role}</span>
                      <span class="ml-auto font-mono text-[9.5px] text-faint">{shot.duration_s.toFixed(1)}s</span>
                    </div>
                    <div class="mt-1 line-clamp-2 text-[10.5px] leading-5 text-faint">{shot.description || "（空描述）"}</div>
                    <Show when={shot.narration}>
                      <div class="mt-1 line-clamp-2 text-[10px] leading-4 text-dim">台词：{shot.narration}</div>
                    </Show>
                    <div class="mt-1.5 flex flex-wrap items-center gap-1.5 text-[9.5px] text-faint">
                      <span class="rounded border border-line px-1 py-px">{local() ? "动效" : "生成/素材"}</span>
                      <Show when={shot.preview}><span class="text-ok">已有预览</span></Show>
                      <Show when={shot.persona_id}>
                        <span class="rounded bg-accent/10 px-1 py-px text-accent">主播：{personaName(shot.persona_id)}</span>
                      </Show>
                      <Show when={shot.product_id}>
                        <span class="rounded bg-surface-2 px-1 py-px">商品：{productName(shot.product_id)}</span>
                      </Show>
                    </div>
                    <div class="mt-2 grid grid-cols-2 gap-1.5">
                      <select
                        class="h-6 min-w-0 rounded border border-line bg-surface px-1 text-[9px] text-dim outline-none"
                        value={shot.persona_id || ""}
                        onChange={(event) => void bindShot(shot.id, { persona_id: event.currentTarget.value || null })}
                      >
                        <option value="" selected={!shot.persona_id}>不绑定主播</option>
                        <For each={personas()}>{(persona) => <option value={persona.id} selected={persona.id === shot.persona_id}>{persona.name}</option>}</For>
                      </select>
                      <select
                        class="h-6 min-w-0 rounded border border-line bg-surface px-1 text-[9px] text-dim outline-none"
                        value={shot.product_id || ""}
                        onChange={(event) => void bindShot(shot.id, { product_id: event.currentTarget.value || null })}
                      >
                        <option value="" selected={!shot.product_id}>不绑定商品</option>
                        <For each={products()}>{(product) => <option value={product.id} selected={product.id === shot.product_id}>{product.name}</option>}</For>
                      </select>
                    </div>
                    <div class="mt-2 flex items-center gap-1.5">
                      <button
                        type="button"
                        class="h-6 rounded border border-line px-2 text-[9.5px] text-dim hover:border-accent/50 hover:text-text"
                        onClick={(event) => { event.stopPropagation(); void openAssets(shot.id); }}
                      >
                        选择素材
                      </button>
                      <Show when={!local()}>
                        <Show
                          when={!needsAudio(shot)}
                          fallback={
                            <button
                              type="button"
                              class="h-6 rounded border border-warn/40 bg-warn/5 px-2 text-[9.5px] text-warn"
                              onClick={(event) => { event.stopPropagation(); setTab("audio"); }}
                            >
                              去配音
                            </button>
                          }
                        >
                          <button
                            type="button"
                            class="h-6 rounded border border-accent/40 bg-accent/5 px-2 text-[9.5px] text-accent hover:bg-accent/10"
                            onClick={(event) => { event.stopPropagation(); void startGeneration([shot.id], Boolean(shot.preview)); }}
                          >
                            {shot.preview ? "重新生成" : "生成"}
                          </button>
                        </Show>
                      </Show>
                    </div>
                  </div>
                </div>
              )}
            </For>
          </div>
        </Show>
        </div>
        }>
          <AudioPanel />
        </Show>

        <div class="sticky bottom-0 flex flex-wrap items-center gap-2 border-t border-line-soft bg-bg/95 py-3 backdrop-blur">
          <Show when={!approved()} fallback={<Button size="sm" variant="primary" onClick={() => props.onAdvanced("compose")}>看成片</Button>}>
            <Button size="sm" variant="primary" loading={busy()} disabled={props.production.shots.length === 0 || !canApprove()} onClick={() => void approve()}>
              素材通过，开始合成
            </Button>
            <span class="text-[10px] text-faint">
              {canApprove() ? "确认后进入成片；不会自动渲染。" : "配音和画面都完成后才能确认。"}
            </span>
          </Show>
        </div>
      </div>

      <Dialog open={assetOpen()} onOpenChange={setAssetOpen} title="为镜头选择素材">
        <Show when={!assetLoading()} fallback={<div class="py-12 text-center text-[11px] text-faint">加载中…</div>}>
          <Show
            when={assetRows().length > 0}
            fallback={<div class="py-12 text-center text-[11px] text-faint">素材库里还没有图片或视频</div>}
          >
            <div class="grid max-h-[55vh] grid-cols-3 gap-2 overflow-auto sm:grid-cols-4">
              <For each={assetRows()}>
                {(asset) => (
                  <button
                    type="button"
                    class="overflow-hidden rounded-lg border border-line-soft bg-[#0b0e15] text-left hover:border-accent/60"
                    onClick={() => void bindAsset(asset)}
                  >
                    <Show
                      when={asset.kind === "video" ? `/api/thumb?path=${encodeURIComponent(asset.path)}&width=360` : mediaUrl(asset.path)}
                      fallback={<div class="grid aspect-video place-items-center text-[10px] text-faint">无预览</div>}
                    >
                      {(src) => <img src={src()} alt="" class="aspect-video w-full object-cover" loading="lazy" />}
                    </Show>
                    <div class="truncate px-1.5 py-1 text-[9.5px] text-faint">{asset.name}</div>
                  </button>
                )}
              </For>
            </div>
          </Show>
        </Show>
      </Dialog>
    </div>
  );
}
