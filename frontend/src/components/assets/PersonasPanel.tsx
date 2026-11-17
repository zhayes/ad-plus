import { For, Show, createEffect, createSignal, onMount } from "solid-js";
import Dialog from "../ui/Dialog";
import Badge from "../ui/Badge";
import Button from "../ui/Button";
import Icon from "../ui/Icon";
import Input from "../ui/Input";
import Select from "../ui/Select";
import { endpoints, uploadAsset } from "../../lib/api";
import { mediaUrl } from "../../lib/projects";
import type { Asset, Persona, PersonaCandidate, PersonaKind } from "../../lib/types";

interface Props {
  initialId?: string | null;
  hideList?: boolean;
  onClose?: () => void;
  onSaved?: (id: string) => void;
}

const KINDS: { value: PersonaKind; label: string }[] = [
  { value: "photo", label: "照片模特" },
  { value: "video", label: "视频模特" },
  { value: "avatar", label: "数字人形象" },
];

function emptyPersona(): Persona {
  return {
    id: "",
    name: "",
    kind: "photo",
    status: "draft",
    source_path: null,
    preview_path: null,
    description: "",
    gender: "",
    age_range: "",
    look: "",
    wardrobe: "",
    scene: "",
    tags: [],
    voice: { provider: "", voice_id: "", language: "zh-CN", speed: 1.0, sample_path: "" },
    base_videos: [],
    rights: { ai_allowed: false, consent: false, commercial_use: false, note: "" },
    providers: {},
  };
}

function fromPersona(persona: Persona): Persona {
  return {
    ...persona,
    tags: [...(persona.tags ?? [])],
    voice: { ...(persona.voice ?? {}) },
    base_videos: [...(persona.base_videos ?? [])],
    rights: { ...persona.rights },
    providers: { ...(persona.providers ?? {}) },
  };
}

type PersonaDraftCache = { id: string | null; draft: Persona; tags: string; creating: boolean };
let PERSONA_CACHE: PersonaDraftCache | null = null;

export default function PersonasPanel(props: Props) {
  const cached = props.initialId ? null : PERSONA_CACHE;
  const [rows, setRows] = createSignal<Persona[]>([]);
  const [selectedId, setSelectedId] = createSignal<string | null>(cached?.id ?? null);
  const [draft, setDraft] = createSignal<Persona>(cached?.draft ?? emptyPersona());
  const [creating, setCreating] = createSignal(cached?.creating ?? false);
  const [loading, setLoading] = createSignal(true);
  const [saving, setSaving] = createSignal(false);
  const [busy, setBusy] = createSignal(false);
  const [baseBusy, setBaseBusy] = createSignal(false);
  const [error, setError] = createSignal("");
  const [message, setMessage] = createSignal("");
  const [confirmDelete, setConfirmDelete] = createSignal(false);
  const [tagText, setTagText] = createSignal(cached?.tags ?? "");
  const [genBusy, setGenBusy] = createSignal(false);
  const [genOpen, setGenOpen] = createSignal(false);
  const [genTab, setGenTab] = createSignal<"text" | "reference">("text");
  const [genError, setGenError] = createSignal("");
  const [genPrompt, setGenPrompt] = createSignal("");
  const [genAspect, setGenAspect] = createSignal("3:4");
  const [genRef, setGenRef] = createSignal<string | null>(null);
  const [genCandidates, setGenCandidates] = createSignal<PersonaCandidate[]>([]);
  const [genCost, setGenCost] = createSignal(0);
  const [assetOpen, setAssetOpen] = createSignal(false);
  const [assetLoading, setAssetLoading] = createSignal(false);
  const [assetRows, setAssetRows] = createSignal<Asset[]>([]);
  const [assetQuery, setAssetQuery] = createSignal("");
  const [assetError, setAssetError] = createSignal("");
  let fileInput: HTMLInputElement | undefined;
  let genFileInput: HTMLInputElement | undefined;
  let baseVideoInput: HTMLInputElement | undefined;

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const data = await endpoints.personas();
      setRows(data.personas ?? []);
      if (props.initialId && props.initialId !== "new") {
        const target = (data.personas ?? []).find((item) => item.id === props.initialId);
        if (target) select(target);
      } else if (props.initialId === "new") {
        if (!creating()) create();
      } else if (!selectedId() && !creating() && data.personas?.length) {
        select(data.personas[0]);
      }
      if (selectedId() && !data.personas?.some((item) => item.id === selectedId())) {
        setSelectedId(null);
        setDraft(emptyPersona());
        setCreating(true);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "数字人加载失败");
    } finally {
      setLoading(false);
    }
  };

  const select = (persona: Persona) => {
    setCreating(false);
    setSelectedId(persona.id || null);
    setDraft(fromPersona(persona));
    setTagText((persona.tags ?? []).join(", "));
    setConfirmDelete(false);
    setMessage("");
    setError("");
  };

  const create = () => {
    setCreating(true);
    setSelectedId(null);
    setDraft(emptyPersona());
    setTagText("");
    setConfirmDelete(false);
    setMessage("");
    setError("");
  };

  createEffect(() => {
    PERSONA_CACHE = { id: selectedId(), draft: draft(), tags: tagText(), creating: creating() };
  });

  onMount(() => {
    void load();
  });

  const update = (patch: Partial<Persona>) => setDraft((prev) => ({ ...prev, ...patch }));

  const loadImageAssets = async () => {
    setAssetLoading(true);
    setAssetError("");
    try {
      const data = await endpoints.assets({ kind: "image" });
      setAssetRows(data.assets ?? []);
    } catch (err) {
      setAssetError(err instanceof Error ? err.message : "素材加载失败");
    } finally {
      setAssetLoading(false);
    }
  };

  const openAssetPicker = () => {
    setAssetOpen(true);
    setAssetQuery("");
    void loadImageAssets();
  };

  const filteredAssets = () => {
    const query = assetQuery().trim().toLowerCase();
    if (!query) return assetRows();
    return assetRows().filter((asset) =>
      `${asset.name} ${asset.path}`.toLowerCase().includes(query),
    );
  };

  const chooseAsset = (asset: Asset) => {
    update({ source_path: asset.path, preview_path: asset.path, status: "ready" });
    setAssetOpen(false);
    setMessage("已从素材库选入人像。");
  };

  const uploadReference = async (file: File) => {
    setGenBusy(true);
    setError("");
    try {
      const asset = await uploadAsset(file);
      setGenRef(asset.path);
      setMessage("参考图已上传；生成时会锁定同一张脸。");
    } catch (err) {
      setError(err instanceof Error ? err.message : "参考图上传失败");
    } finally {
      setGenBusy(false);
      if (genFileInput) genFileInput.value = "";
    }
  };

  const openGenerator = () => {
    setGenOpen(true);
    setGenError("");
    setGenCandidates([]);
    setGenCost(0);
  };

  const generate = async () => {
    if (genTab() === "reference" && !genRef()) {
      setGenError("先在「图片参考」里上传一张参考图");
      return;
    }
    setGenBusy(true);
    setGenError("");
    setGenCandidates([]);
    try {
      const data = await endpoints.generatePersona({
        prompt: genPrompt().trim(),
        count: 4,
        aspect_ratio: genAspect(),
        reference_path: genTab() === "reference" ? genRef() : null,
      });
      setGenCandidates(data.candidates ?? []);
      setGenCost(data.cost_usd ?? 0);
      setMessage(
        data.reference_used
          ? `参考图生成完成：${data.candidates.length} 张候选，约 $${(data.cost_usd ?? 0).toFixed(4)}`
          : `生成完成：${data.candidates.length} 张候选，约 $${(data.cost_usd ?? 0).toFixed(4)}`,
      );
    } catch (err) {
      setGenError(err instanceof Error ? err.message : "生成失败");
    } finally {
      setGenBusy(false);
    }
  };

  const useCandidate = (candidate: PersonaCandidate) => {
    update({
      source_path: candidate.path,
      preview_path: candidate.path,
      status: "ready",
      kind: "photo",
      description: draft().description || genPrompt().trim() || "AI 生成的虚构数字模特",
    });
    setMessage("已选用该候选。");
    setGenOpen(false);
  };

  const upload = async (file: File) => {
    setBusy(true);
    setError("");
    try {
      const asset = await uploadAsset(file);
      update({ source_path: asset.path, preview_path: asset.path, status: "ready" });
      setMessage("人像已上传。");
    } catch (err) {
      setError(err instanceof Error ? err.message : "上传失败");
    } finally {
      setBusy(false);
      if (fileInput) fileInput.value = "";
    }
  };

  const uploadBaseVideo = async (file: File) => {
    setBusy(true);
    setError("");
    try {
      const asset = await uploadAsset(file);
      update({
        base_videos: [...(draft().base_videos ?? []), {
          id: `bv_${Date.now()}`,
          path: asset.path,
          framing: "half_body",
          silent: true,
        }],
      });
      setMessage("基础视频已添加；建议使用无声视频，后续由 TTS 驱动口型。");
    } catch (err) {
      setError(err instanceof Error ? err.message : "基础视频上传失败");
    } finally {
      setBusy(false);
      if (baseVideoInput) baseVideoInput.value = "";
    }
  };

  const removeBaseVideo = (index: number) => {
    const rows = [...(draft().base_videos ?? [])];
    rows.splice(index, 1);
    update({ base_videos: rows });
  };

  const save = async (): Promise<Persona | null> => {
    if (!draft().name.trim()) {
      setError("先给数字模特起个名字");
      return null;
    }
    setSaving(true);
    setError("");
    setMessage("");
    const body = {
      name: draft().name.trim(),
      kind: draft().kind,
      status: draft().status,
      source_path: draft().source_path || null,
      preview_path: draft().preview_path || draft().source_path || null,
      description: draft().description ?? "",
      gender: draft().gender ?? "",
      age_range: draft().age_range ?? "",
      look: draft().look ?? "",
      wardrobe: draft().wardrobe ?? "",
      scene: draft().scene ?? "",
      tags: tagText().split(",").map((item) => item.trim()).filter(Boolean),
      voice: draft().voice ?? {},
      base_videos: draft().base_videos ?? [],
      rights: draft().rights,
      providers: draft().providers ?? {},
    };
    try {
      const data = selectedId()
        ? await endpoints.patchPersona(selectedId()!, body)
        : await endpoints.createPersona(body);
      await load();
      select(data.persona);
      setMessage("已保存，可在后续项目中直接复用。");
      props.onSaved?.(data.persona.id);
      return data.persona;
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存失败");
      return null;
    } finally {
      setSaving(false);
    }
  };

  const saveAndGenerate = async () => {
    if (!hasSourceImage()) {
      setError("先上传人像或自动生成一张人像，才能生成形象视频");
      return;
    }
    const persona = await save();
    if (!persona) return;
    setBaseBusy(true);
    setError("");
    try {
      const result = await endpoints.generatePersonaBaseVideo(persona.id, { provider: "seedance" });
      setDraft((previous) => ({ ...previous, base_videos: result.persona.base_videos ?? [] }));
      setMessage(`形象视频已生成（Seedance）${result.cost_usd ? ` · $${result.cost_usd.toFixed(2)}` : ""}`);
    } catch (err) {
      setMessage("数字人已保存；形象视频未生成。");
      setError(err instanceof Error ? err.message : "形象视频生成失败");
    } finally {
      setBaseBusy(false);
    }
  };

  const remove = async () => {
    if (!selectedId()) return;
    if (!confirmDelete()) {
      setConfirmDelete(true);
      return;
    }
    setBusy(true);
    try {
      await endpoints.deletePersona(selectedId()!);
      setSelectedId(null);
      setDraft(emptyPersona());
      setConfirmDelete(false);
      await load();
      setMessage("已删除数字模特记录。");
    } catch (err) {
      setError(err instanceof Error ? err.message : "删除失败");
    } finally {
      setBusy(false);
    }
  };

  const hasSourceImage = () => Boolean(draft().source_path || draft().preview_path);
  const canProviderGenerate = () => Boolean(selectedId()) && hasSourceImage() && !busy() && !saving() && !baseBusy();

  const generateBaseVideo = async (provider: "seedance" | "minimax" = "seedance") => {
    if (!selectedId()) {
      setError("先保存数字模特，再生成基础视频");
      return;
    }
    if (!hasSourceImage()) {
      setError("先上传人像或自动生成一张人像，才能生成形象视频");
      return;
    }
    setBaseBusy(true);
    setError("");
    try {
      const result = await endpoints.generatePersonaBaseVideo(selectedId()!, { provider });
      setRows((previous) => previous.map((item) => item.id === result.persona.id ? result.persona : item));
      setDraft((previous) => ({ ...previous, base_videos: result.persona.base_videos ?? [] }));
      setMessage(`基础视频已生成${result.cost_usd ? ` · $${result.cost_usd.toFixed(2)}` : ""}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "基础视频生成失败");
    } finally {
      setBaseBusy(false);
    }
  };

  return (
    <div class={`grid h-full min-h-0 gap-0 overflow-hidden ${props.hideList ? "grid-cols-1" : "grid-cols-[260px_minmax(0,1fr)]"}`}>
      <Show when={!props.hideList}>
      <aside class="min-h-0 overflow-auto border-r border-line-soft bg-surface/40 p-3">
        <div class="mb-2 flex items-center gap-1.5">
          <span class="text-[10.5px] uppercase tracking-wide text-faint">数字模特库</span>
          <span class="text-[10px] text-faint">{rows().length}</span>
          <button type="button" class="ml-auto rounded border border-accent/40 bg-accent/5 px-1.5 py-0.5 text-[10px] text-accent hover:bg-accent/10" onClick={create}>+ 新增</button>
        </div>
        <Show when={!loading()} fallback={<div class="py-8 text-center text-[11px] text-faint">加载中…</div>}>
          <Show
            when={rows().length > 0}
            fallback={
              <div class="rounded-lg border border-dashed border-line px-3 py-8 text-center">
                <div class="text-[12px] text-dim">还没有数字模特</div>
                <p class="mt-1 text-[10.5px] leading-5 text-faint">上传一张人像，建立可复用的主播资产。</p>
                <Button class="mt-3" size="sm" variant="primary" onClick={create}>
                  ＋ 新建
                </Button>
              </div>
            }
          >
            <div class="space-y-1.5">
              <For each={rows()}>
                {(persona) => (
                  <button
                    type="button"
                    class={`flex w-full items-center gap-2 rounded-lg border px-2 py-2 text-left transition-colors ${
                      persona.id === selectedId()
                        ? "border-accent/50 bg-accent/8"
                        : "border-transparent hover:border-line hover:bg-surface-2/60"
                    }`}
                    onClick={() => select(persona)}
                  >
                    <div class="h-11 w-9 shrink-0 overflow-hidden rounded-md bg-[#0b0e15]">
                      <Show
                        when={persona.preview_path || persona.source_path}
                        fallback={<div class="grid h-full place-items-center text-[16px] text-white/20">◉</div>}
                      >
                        <img
                          src={mediaUrl(persona.preview_path || persona.source_path!)}
                          alt=""
                          class="h-full w-full object-cover"
                        />
                      </Show>
                    </div>
                    <div class="min-w-0 flex-1">
                      <div class="truncate text-[11.5px] text-text">{persona.name}</div>
                      <div class="mt-0.5 flex items-center gap-1.5">
                        <span class="text-[9.5px] text-faint">{persona.kind === "photo" ? "照片" : persona.kind === "video" ? "视频" : "数字人"}</span>
                      </div>
                    </div>
                  </button>
                )}
              </For>
            </div>
          </Show>
        </Show>
      </aside>
      </Show>

      <section class="min-h-0 overflow-auto p-5">
        <div class="mx-auto max-w-[760px]">
          <div class="mb-4 flex items-start justify-between gap-3">
            <div class="min-w-0">
              <Show when={props.hideList && props.onClose}>
                <button type="button" class="mb-2 text-[10.5px] text-faint hover:text-text" onClick={() => props.onClose?.()}>← 返回数字人列表</button>
              </Show>
              <div class="text-[14px] font-semibold text-text">{selectedId() ? "编辑数字模特" : "新建数字模特"}</div>
              <p class="mt-1 text-[11px] leading-5 text-faint">
                一次建立，后续项目直接引用。人像与 provider id 分开管理。
              </p>
            </div>
            <Show when={selectedId()}>
              <Button size="sm" variant="ghost" disabled={busy()} onClick={() => void remove()}>
                {confirmDelete() ? "确认删除" : "删除"}
              </Button>
            </Show>
          </div>

          <Show when={error()}>
            <div class="mb-3 rounded-lg border border-bad/30 bg-bad/5 px-3 py-2 text-[11px] text-bad">{error()}</div>
          </Show>
          <Show when={message()}>
            <div class="mb-3 rounded-lg border border-good/25 bg-good/5 px-3 py-2 text-[11px] text-good">{message()}</div>
          </Show>

          <div class="grid grid-cols-[180px_minmax(0,1fr)] gap-4">
            <div>
              <div class="overflow-hidden rounded-xl border border-line-soft bg-[#0b0e15]" style={{ "aspect-ratio": "3 / 4" }}>
                <Show
                  when={draft().preview_path || draft().source_path}
                  fallback={
                    <button
                      type="button"
                      class="grid h-full w-full place-items-center text-faint hover:text-text"
                      onClick={() => fileInput?.click()}
                    >
                      <span class="text-center text-[11px] leading-5">＋<br />上传人像</span>
                    </button>
                  }
                >
                  <img
                    src={mediaUrl((draft().preview_path || draft().source_path)!)}
                    alt=""
                    class="h-full w-full object-cover"
                  />
                </Show>
              </div>
              <input
                ref={fileInput}
                type="file"
                class="hidden"
                accept="image/*"
                onChange={(event) => {
                  const file = event.currentTarget.files?.[0];
                  if (file) void upload(file);
                }}
              />
              <div class="mt-2 grid grid-cols-2 gap-2">
                <Button size="sm" variant="secondary" disabled={busy()} onClick={openAssetPicker}>
                  从素材导入
                </Button>
                <Button size="sm" variant="primary" onClick={openGenerator}>
                  自动生成
                </Button>
              </div>
            </div>

            <div class="space-y-3">
              <div class="rounded-lg border border-line-soft p-3">
                <div class="flex flex-wrap items-center gap-2">
                  <span class="text-[10.5px] text-faint">数字人形象视频</span>
                  <span class="text-[9.5px] text-faint">生成一次，后续镜头复用</span>
                  <span class="text-[9px] text-faint">Seedance 常拦截真人感图片；可换 MiniMax 或上传视频</span>
                  <Show when={(draft().base_videos ?? []).length > 0}>
                    <Badge tone="ok">已就绪</Badge>
                  </Show>
                  <Button class="ml-auto" size="sm" variant="secondary" disabled={busy()} onClick={() => baseVideoInput?.click()}>
                    上传视频
                  </Button>
                  <Button size="sm" variant="secondary" loading={baseBusy()} disabled={!canProviderGenerate()} onClick={() => void generateBaseVideo("seedance")}>
                    Seedance
                  </Button>
                  <Button size="sm" variant="secondary" loading={baseBusy()} disabled={!canProviderGenerate()} onClick={() => void generateBaseVideo("minimax")}>
                    MiniMax
                  </Button>
                </div>
                <Show when={!hasSourceImage()}>
                  <div class="mt-2 text-[9.5px] text-warn">先上传人像，Seedance / MiniMax 才会解锁。</div>
                </Show>
                <Show when={hasSourceImage() && !selectedId()}>
                  <div class="mt-2 text-[9.5px] text-faint">这是新数字人：点底部“保存并生成”，或先“只保存”再点上方生成。</div>
                </Show>
                <input
                  ref={baseVideoInput}
                  type="file"
                  class="hidden"
                  accept="video/*"
                  onChange={(event) => {
                    const file = event.currentTarget.files?.[0];
                    if (file) void uploadBaseVideo(file);
                  }}
                />
                <Show
                  when={(draft().base_videos ?? []).length > 0}
                  fallback={<div class="mt-2 rounded-md border border-dashed border-line px-2 py-3 text-center text-[10px] leading-5 text-faint">还没有形象视频。静态图 + Wav2Lip 只会动嘴，建议先上传真实表演，或用 Seedance 生成。</div>}
                >
                  <video
                    controls
                    preload="metadata"
                    src={mediaUrl((draft().base_videos ?? [])[0].path) ?? undefined}
                    class="mt-2 aspect-[9/16] max-h-[260px] w-full rounded-md bg-black object-contain"
                  />
                  <div class="mt-2 space-y-1.5">
                    <For each={draft().base_videos ?? []}>
                      {(video, index) => (
                        <div class="flex items-center gap-2 rounded-md border border-line-soft bg-surface-2/40 px-2 py-1.5">
                          <span class="text-[18px] text-faint">▣</span>
                          <span class="min-w-0 flex-1 truncate font-mono text-[9.5px] text-dim">{video.path}</span>
                          <span class="text-[9px] text-faint">{video.silent ? "无声" : "有声音"}</span>
                          <button type="button" class="text-[11px] text-faint hover:text-bad" onClick={() => removeBaseVideo(index())}>×</button>
                        </div>
                      )}
                    </For>
                  </div>
                </Show>
              </div>


              <label class="block">
                <span class="mb-1 block text-[10.5px] text-faint">名称</span>
                <Input value={draft().name} placeholder="例如：小夏 · 通勤" onInput={(event) => update({ name: event.currentTarget.value })} />
              </label>

              <div class="grid grid-cols-2 gap-3">
                <label class="block">
                  <span class="mb-1 block text-[10.5px] text-faint">类型</span>
                  <Select
                    value={draft().kind}
                    options={KINDS}
                    onChange={(value) => update({ kind: value as PersonaKind })}
                    variant="pill"
                  />
                </label>
                <label class="block">
                  <span class="mb-1 block text-[10.5px] text-faint">状态</span>
                  <Select
                    value={draft().status}
                    options={[
                      { value: "draft", label: "草稿" },
                      { value: "ready", label: "可用" },
                      { value: "archived", label: "归档" },
                    ]}
                    onChange={(value) => update({ status: value as Persona["status"] })}
                    variant="pill"
                  />
                </label>
              </div>

              <label class="block">
                <span class="mb-1 block text-[10.5px] text-faint">描述 / 气质</span>
                <textarea
                  class="min-h-[64px] w-full rounded-lg border border-line bg-surface px-3 py-2 text-[12px] text-text outline-none focus:border-accent/60"
                  value={draft().description ?? ""}
                  placeholder="例如：25 岁，干净通勤，镜头感自然"
                  onInput={(event) => update({ description: event.currentTarget.value })}
                />
              </label>

              <div class="grid grid-cols-2 gap-3">
                <label class="block">
                  <span class="mb-1 block text-[10.5px] text-faint">服装</span>
                  <Input value={draft().wardrobe ?? ""} placeholder="红裙 / 西装" onInput={(event) => update({ wardrobe: event.currentTarget.value })} />
                </label>
                <label class="block">
                  <span class="mb-1 block text-[10.5px] text-faint">场景</span>
                  <Input value={draft().scene ?? ""} placeholder="室内 / 江边" onInput={(event) => update({ scene: event.currentTarget.value })} />
                </label>
              </div>

              <label class="block">
                <span class="mb-1 block text-[10.5px] text-faint">标签（逗号分隔）</span>
                <Input value={tagText()} placeholder="clean, 通勤, 25-30" onInput={(event) => setTagText(event.currentTarget.value)} />
              </label>

              <div class="rounded-lg border border-line-soft p-3">
                <div class="flex items-center gap-2">
                  <span class="text-[10.5px] text-faint">声音</span>
                  <span class="text-[9.5px] text-faint">项目默认继承</span>
                </div>
                <div class="mt-2 grid grid-cols-2 gap-2">
                  <Select
                    value={draft().voice?.provider ?? ""}
                    options={[
                      { value: "", label: "未配置" },
                      { value: "local", label: "本地系统声音" },
                      { value: "minimax", label: "MiniMax" },
                      { value: "elevenlabs", label: "ElevenLabs" },
                      { value: "heygen", label: "HeyGen" },
                    ]}
                    onChange={(value) => update({ voice: { ...(draft().voice ?? {}), provider: value } })}
                    variant="pill"
                  />
                  <Input
                    value={draft().voice?.voice_id ?? ""}
                    placeholder="voice_id / 声音名"
                    onInput={(event) => update({ voice: { ...(draft().voice ?? {}), voice_id: event.currentTarget.value } })}
                  />
                </div>
                <div class="mt-2 flex items-center gap-2">
                  <Input
                    value={String(draft().voice?.speed ?? 1)}
                    placeholder="语速"
                    onInput={(event) => update({ voice: { ...(draft().voice ?? {}), speed: Number(event.currentTarget.value) || 1 } })}
                  />
                  <span class="text-[9.5px] text-faint">语音试听会在生成阶段使用；此处先记录默认声音。</span>
                </div>
              </div>

              <details class="rounded-lg border border-line-soft bg-surface/40 px-3 py-2">
                <summary class="cursor-pointer text-[11px] text-dim">Provider ID（可选）</summary>
                <div class="mt-2 space-y-2">
                  <Input
                    value={draft().providers?.heygen_avatar_id ?? ""}
                    placeholder="HeyGen avatar_id"
                    onInput={(event) => update({ providers: { ...(draft().providers ?? {}), heygen_avatar_id: event.currentTarget.value } })}
                  />
                  <Input
                    value={draft().providers?.kling_face_id ?? ""}
                    placeholder="Kling face_id"
                    onInput={(event) => update({ providers: { ...(draft().providers ?? {}), kling_face_id: event.currentTarget.value } })}
                  />
                </div>
              </details>

              <div class="flex items-center justify-end gap-2 pt-1">
                <Button size="sm" variant="ghost" onClick={create}>取消</Button>
                <Button size="sm" variant="secondary" disabled={saving() || baseBusy()} onClick={() => void save()}>
                  {saving() ? "保存中…" : "只保存"}
                </Button>
                <Button
                  size="sm"
                  variant="primary"
                  loading={baseBusy()}
                  disabled={saving() || !draft().name.trim() || !hasSourceImage()}
                  title={!draft().name.trim() ? "先填写名称" : !hasSourceImage() ? "先上传人像" : "保存并用 Seedance 生成形象视频"}
                  onClick={() => void saveAndGenerate()}
                >
                  保存并生成（Seedance）
                </Button>
              </div>
            </div>
          </div>
        </div>

      <Dialog open={assetOpen()} onOpenChange={setAssetOpen} title="从素材导入人像">
        <div class="space-y-3">
          <div class="flex items-center gap-2">
            <Input
              value={assetQuery()}
              placeholder="搜索图片素材"
              onInput={(event) => setAssetQuery(event.currentTarget.value)}
            />
            <Button
              size="sm"
              variant="secondary"
              class="h-9 w-9 shrink-0 !px-0"
              title="上传新图"
              aria-label="上传新图"
              onClick={() => { setAssetOpen(false); fileInput?.click(); }}
            >
              <Icon name="plus" size={16} />
            </Button>
          </div>

          <Show when={assetError()}>
            <div class="rounded-lg border border-bad/30 bg-bad/5 px-3 py-2 text-[11px] text-bad">{assetError()}</div>
          </Show>

          <Show when={!assetLoading()} fallback={<div class="py-12 text-center text-[11px] text-faint">加载中…</div>}>
            <Show
              when={filteredAssets().length > 0}
              fallback={
                <div class="rounded-lg border border-dashed border-line px-4 py-12 text-center">
                  <div class="text-[12px] text-dim">素材库里还没有图片</div>
                  <p class="mt-1 text-[10.5px] text-faint">先上传一张人像，再从这里选择。</p>
                </div>
              }
            >
              <div class="grid max-h-[55vh] grid-cols-3 gap-2 overflow-auto sm:grid-cols-4">
                <For each={filteredAssets()}>
                  {(asset) => (
                    <button
                      type="button"
                      class="overflow-hidden rounded-lg border border-line-soft bg-[#0b0e15] text-left hover:border-accent/60"
                      onClick={() => chooseAsset(asset)}
                    >
                      <img src={mediaUrl(asset.path)} alt="" class="aspect-[3/4] w-full object-cover" />
                      <div class="truncate px-1.5 py-1 text-[9.5px] text-faint">{asset.name}</div>
                    </button>
                  )}
                </For>
              </div>
            </Show>
          </Show>
        </div>
      </Dialog>

      <Dialog open={genOpen()} onOpenChange={setGenOpen} title="自动生成数字人形象">
        <div class="space-y-3">
          <div class="flex items-center gap-1 border-b border-line-soft pb-2">
            <button
              type="button"
              class={`rounded-md px-2.5 py-1.5 text-[11px] ${
                genTab() === "text" ? "bg-accent/12 text-text" : "text-faint hover:text-text"
              }`}
              onClick={() => { setGenTab("text"); setGenError(""); }}
            >
              文本生成
            </button>
            <button
              type="button"
              class={`rounded-md px-2.5 py-1.5 text-[11px] ${
                genTab() === "reference" ? "bg-accent/12 text-text" : "text-faint hover:text-text"
              }`}
              onClick={() => { setGenTab("reference"); setGenError(""); }}
            >
              图片参考
            </button>
            <span class="ml-auto text-[10px] text-faint">虚构人物 · 约 $0.0035/张</span>
          </div>

          <Show when={genError()}>
            <div class="rounded-lg border border-bad/30 bg-bad/5 px-3 py-2 text-[11px] text-bad">{genError()}</div>
          </Show>

          <Show when={genTab() === "text"}>
            <label class="block">
              <span class="mb-1 block text-[10.5px] text-faint">人物描述</span>
              <textarea
                class="min-h-[92px] w-full rounded-lg border border-line bg-surface px-3 py-2 text-[12px] text-text outline-none focus:border-accent/60"
                value={genPrompt()}
                placeholder="例如：25 岁干净通勤女生，白衬衫，室内柔光，半身肖像，镜头感自然，不要名人脸"
                onInput={(event) => setGenPrompt(event.currentTarget.value)}
              />
              <p class="mt-1 text-[10px] leading-4 text-faint">文字生成会创建一个全新的虚构人物；适合先定气质，再生成系列。</p>
            </label>
          </Show>

          <Show when={genTab() === "reference"}>
            <div class="grid grid-cols-1 gap-3 sm:grid-cols-[128px_minmax(0,1fr)]">
              <div>
                <div class="overflow-hidden rounded-lg border border-dashed border-line bg-[#0b0e15]" style={{ "aspect-ratio": "3 / 4" }}>
                  <Show
                    when={genRef()}
                    fallback={
                      <button
                        type="button"
                        class="grid h-full w-full place-items-center text-center text-[10px] leading-5 text-faint hover:text-text"
                        onClick={() => genFileInput?.click()}
                      >
                        ＋<br />上传参考图
                      </button>
                    }
                  >
                    <img src={mediaUrl(genRef()!)} alt="" class="h-full w-full object-cover" />
                  </Show>
                </div>
                <Button class="mt-2 w-full" size="sm" variant="secondary" disabled={genBusy()} onClick={() => genFileInput?.click()}>
                  {genRef() ? "更换参考图" : "选择参考图"}
                </Button>
              </div>
              <label class="block">
                <span class="mb-1 block text-[10.5px] text-faint">想让她 / 他做什么</span>
                <textarea
                  class="min-h-[92px] w-full rounded-lg border border-line bg-surface px-3 py-2 text-[12px] text-text outline-none focus:border-accent/60"
                  value={genPrompt()}
                  placeholder="例如：同一个人，换成白衬衫，在明亮室内微笑，半身肖像"
                  onInput={(event) => setGenPrompt(event.currentTarget.value)}
                />
                <p class="mt-1 text-[10px] leading-4 text-faint">参考图会锁定同一张脸；适合系列内容，但不是 100% 身份复刻。</p>
              </label>
            </div>
          </Show>

          <input
            ref={genFileInput}
            type="file"
            class="hidden"
            accept="image/*"
            onChange={(event) => {
              const file = event.currentTarget.files?.[0];
              if (file) void uploadReference(file);
            }}
          />

          <div class="flex flex-wrap items-center gap-2 border-t border-line-soft pt-2">
            <Select
              value={genAspect()}
              options={[
                { value: "3:4", label: "3:4 人像" },
                { value: "9:16", label: "9:16 竖屏" },
                { value: "1:1", label: "1:1 头像" },
              ]}
              onChange={setGenAspect}
              variant="pill"
            />
            <Show when={genCost() > 0}>
              <span class="font-mono text-[10px] text-faint">${genCost().toFixed(4)}</span>
            </Show>
            <Button class="ml-auto" size="sm" variant="primary" loading={genBusy()} onClick={() => void generate()}>
              生成 4 张候选
            </Button>
          </div>

          <Show when={genCandidates().length > 0}>
            <div class="grid grid-cols-2 gap-2 sm:grid-cols-4">
              <For each={genCandidates()}>
                {(candidate) => (
                  <button
                    type="button"
                    class="overflow-hidden rounded-lg border border-line-soft bg-[#0b0e15] text-left hover:border-accent/60"
                    onClick={() => useCandidate(candidate)}
                  >
                    <img src={mediaUrl(candidate.path)} alt="" class="aspect-[3/4] w-full object-cover" />
                    <div class="px-1.5 py-1 text-[9px] text-faint">候选 {candidate.index} · 选用</div>
                  </button>
                )}
              </For>
            </div>
          </Show>
        </div>
      </Dialog>
      </section>
    </div>
  );
}
