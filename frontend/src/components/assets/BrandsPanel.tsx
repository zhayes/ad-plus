import { For, Show, createEffect, createSignal, on, onMount } from "solid-js";
import Badge from "../ui/Badge";
import Button from "../ui/Button";
import Input from "../ui/Input";
import Select from "../ui/Select";
import { endpoints, uploadAsset } from "../../lib/api";
import { mediaUrl } from "../../lib/projects";
import { projects, refreshProjects } from "../../stores/projects";
import type { Brand } from "../../lib/types";

const DEFAULT_COLORS = ["#E0338A", "#8B2FC9", "#0B0E15", "#E9EDF5", "#F0CD83"];

function emptyBrand(): Brand {
  return {
    id: "",
    name: "",
    logo: null,
    colors: [...DEFAULT_COLORS],
    font_cn: "思源黑体",
    font_en: "Inter",
    tone: [],
    voice: {},
    banned_words: [],
    default: false,
  };
}

function fromBrand(brand: Brand): Brand {
  return {
    ...brand,
    colors: brand.colors && brand.colors.length > 0 ? [...brand.colors] : [...DEFAULT_COLORS],
    tone: [...(brand.tone ?? [])],
    banned_words: [...(brand.banned_words ?? [])],
    voice: { ...(brand.voice ?? {}) },
  };
}

function rgb(hex: string): [number, number, number] | null {
  const value = hex.replace("#", "").trim();
  const full = value.length === 3 ? value.split("").map((c) => c + c).join("") : value;
  if (!/^[0-9a-fA-F]{6}$/.test(full)) return null;
  return [parseInt(full.slice(0, 2), 16), parseInt(full.slice(2, 4), 16), parseInt(full.slice(4, 6), 16)];
}

function luminance(hex: string): number | null {
  const value = rgb(hex);
  if (!value) return null;
  const channels = value.map((channel) => {
    const c = channel / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2];
}

function contrast(a: string, b: string): number | null {
  const one = luminance(a);
  const two = luminance(b);
  if (one === null || two === null) return null;
  return (Math.max(one, two) + 0.05) / (Math.min(one, two) + 0.05);
}

interface Props {
  onPrimaryReady?: (open: () => void) => void;
}

export default function BrandsPanel(props: Props) {
  const [brands, setBrands] = createSignal<Brand[]>([]);
  const [selectedId, setSelectedId] = createSignal<string | null>(null);
  const [draft, setDraft] = createSignal<Brand>(emptyBrand());
  const [loading, setLoading] = createSignal(true);
  const [saving, setSaving] = createSignal(false);
  const [busy, setBusy] = createSignal(false);
  const [error, setError] = createSignal("");
  const [message, setMessage] = createSignal("");
  const [toneInput, setToneInput] = createSignal("");
  const [wordInput, setWordInput] = createSignal("");
  const [targetProject, setTargetProject] = createSignal("");

  let logoInput: HTMLInputElement | undefined;

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const data = await endpoints.brands();
      setBrands(data.brands ?? []);
      if (!selectedId() && data.brands?.length) selectBrand(data.brands[0]);
      if (selectedId() && !data.brands?.some((brand) => brand.id === selectedId())) {
        setSelectedId(null);
        setDraft(emptyBrand());
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "品牌加载失败");
    } finally {
      setLoading(false);
    }
  };

  const selectBrand = (brand: Brand) => {
    setSelectedId(brand.id || null);
    setDraft(fromBrand(brand));
    setMessage("");
    setError("");
  };

  const newBrand = () => {
    setSelectedId(null);
    setDraft(emptyBrand());
    setMessage("新品牌：填完后保存");
    setError("");
  };

  onMount(() => {
    void load();
    void refreshProjects();
    props.onPrimaryReady?.(newBrand);
  });

  createEffect(
    on(
      () => projects().length,
      () => {
        if (!targetProject() && projects().length > 0) setTargetProject(projects()[0].id);
      },
    ),
  );

  const update = (patch: Partial<Brand>) => setDraft((previous) => ({ ...previous, ...patch }));

  const setColor = (index: number, value: string) => {
    const colors = [...(draft().colors ?? DEFAULT_COLORS)];
    colors[index] = value;
    update({ colors });
  };

  const addColor = () => {
    const colors = draft().colors ?? [];
    if (colors.length < 5) update({ colors: [...colors, "#8B2FC9"] });
  };

  const addTone = () => {
    const value = toneInput().trim();
    if (!value) return;
    update({ tone: [...(draft().tone ?? []), value] });
    setToneInput("");
  };

  const addWord = () => {
    const value = wordInput().trim();
    if (!value) return;
    update({ banned_words: [...(draft().banned_words ?? []), value] });
    setWordInput("");
  };

  const uploadLogo = async (file: File) => {
    setBusy(true);
    setError("");
    try {
      const asset = await uploadAsset(file);
      update({ logo: asset.path });
    } catch (err) {
      setError(err instanceof Error ? err.message : "logo 上传失败");
    } finally {
      setBusy(false);
      if (logoInput) logoInput.value = "";
    }
  };

  const save = async () => {
    const name = draft().name.trim();
    if (!name) {
      setError("先给品牌起个名字");
      return;
    }
    setSaving(true);
    setError("");
    setMessage("");
    const body = {
      name,
      logo: draft().logo || null,
      colors: draft().colors ?? [],
      font_cn: draft().font_cn ?? "",
      font_en: draft().font_en ?? "",
      tone: draft().tone ?? [],
      voice: draft().voice ?? {},
      banned_words: draft().banned_words ?? [],
      default: !!draft().default,
    };
    try {
      const data = selectedId()
        ? await endpoints.patchBrand(selectedId()!, body)
        : await endpoints.createBrand(body);
      await load();
      selectBrand(data.brand);
      setMessage("已保存；新版本生成时带上品牌快照。");
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存失败");
    } finally {
      setSaving(false);
    }
  };

  const makeDefault = async () => {
    if (!selectedId()) return;
    setBusy(true);
    try {
      await endpoints.defaultBrand(selectedId()!);
      await load();
      setMessage("已设为默认品牌。");
    } catch (err) {
      setError(err instanceof Error ? err.message : "设置失败");
    } finally {
      setBusy(false);
    }
  };

  const apply = async () => {
    if (!selectedId() || !targetProject()) return;
    setBusy(true);
    setMessage("");
    try {
      await endpoints.applyBrand(selectedId()!, targetProject());
      await refreshProjects();
      setMessage(`已应用到 ${targetProject()}；新版本生效，旧版本保留原快照。`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "应用失败");
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    if (!selectedId() || !window.confirm(`删除品牌「${draft().name}」？`)) return;
    setBusy(true);
    try {
      await endpoints.deleteBrand(selectedId()!);
      setSelectedId(null);
      setDraft(emptyBrand());
      await load();
      setMessage("品牌已删除。");
    } catch (err) {
      setError(err instanceof Error ? err.message : "删除失败");
    } finally {
      setBusy(false);
    }
  };

  const logoUrl = () => (draft().logo ? mediaUrl(draft().logo) : null);
  const projectOptions = () => projects().map((project) => ({ value: project.id, label: project.title }));

  const checks = () => {
    const value = draft();
    const ratio = contrast(value.colors?.[3] ?? "#E9EDF5", value.colors?.[2] ?? "#0B0E15");
    const voice = value.voice ?? {};
    return [
      { label: "logo 已上传", status: value.logo ? "ok" : "bad", hint: value.logo ? "片头/落版可用" : "缺 logo" },
      { label: "色板 ≥ 2", status: (value.colors?.length ?? 0) >= 2 ? "ok" : "warn", hint: `${value.colors?.length ?? 0} 色` },
      {
        label: "文字对比度 AA",
        status: ratio === null ? "warn" : ratio >= 4.5 ? "ok" : "bad",
        hint: ratio ? `${ratio.toFixed(1)}:1` : "颜色不完整",
      },
      { label: "中文字体", status: value.font_cn ? "ok" : "warn", hint: value.font_cn || "未设置" },
      {
        label: "禁用词",
        status: (value.banned_words?.length ?? 0) > 0 ? "ok" : "warn",
        hint: `${(value.banned_words ?? []).length} 条 · 审片会检查`,
      },
      { label: "口播人设", status: voice.name ? "ok" : "warn", hint: voice.name ? String(voice.name) : "未绑定音色" },
    ] as const;
  };

  return (
    <div class="flex h-full">
      <aside class="w-[230px] shrink-0 overflow-auto border-r border-line-soft p-3">
        <div class="mb-2 flex items-center gap-2">
          <span class="text-[12px] font-semibold">品牌</span>
          <span class="rounded border border-line px-1 py-px font-mono text-[9.5px] text-faint">{brands().length}</span>
          <button type="button" class="ml-auto text-[13px] text-faint hover:text-text" title="新建品牌" onClick={newBrand}>
            ＋
          </button>
        </div>
        <Show
          when={brands().length > 0}
          fallback={<div class="mt-6 text-center text-[10.5px] leading-5 text-faint">还没有品牌包。<br />点右上“新建品牌”。</div>}
        >
          <div class="space-y-1">
            <For each={brands()}>
              {(brand) => (
                <button
                  type="button"
                  class={`flex w-full items-center gap-2 rounded-lg border px-2 py-1.5 text-left ${
                    selectedId() === brand.id ? "border-line bg-surface-2" : "border-transparent hover:bg-surface-2/60"
                  }`}
                  onClick={() => selectBrand(brand)}
                >
                  <span class="grid h-8 w-8 shrink-0 place-items-center overflow-hidden rounded-md bg-gradient-to-br from-violet to-accent text-[11px] font-semibold text-white">
                    <Show when={brand.logo} fallback={brand.name.slice(0, 1)}>
                      <img src={mediaUrl(brand.logo) ?? undefined} alt="" class="h-full w-full object-cover" />
                    </Show>
                  </span>
                  <div class="min-w-0 flex-1">
                    <div class="truncate text-[11px] text-text">{brand.name}</div>
                    <div class="mt-0.5 flex items-center gap-1">
                      <For each={(brand.colors ?? []).slice(0, 4)}>
                        {(color) => <i class="h-1.5 w-1.5 rounded-full" style={{ background: color }} />}
                      </For>
                      <Show when={brand.default}>
                        <span class="ml-1 text-[8.5px] text-ok">默认</span>
                      </Show>
                    </div>
                  </div>
                </button>
              )}
            </For>
          </div>
        </Show>
      </aside>

      <div class="min-w-0 flex-1 overflow-auto p-4">
        <div class="mb-3 flex items-center gap-2">
          <span class="text-[13px] font-semibold text-text">{selectedId() ? draft().name : "新建品牌"}</span>
          <Show when={draft().default}>
            <Badge tone="ok">默认</Badge>
          </Show>
          <div class="ml-auto flex items-center gap-1.5">
            <Button size="sm" variant="primary" loading={saving()} onClick={() => void save()}>
              保存
            </Button>
            <Show when={selectedId()}>
              <Button size="sm" variant="ghost" loading={busy()} onClick={() => void makeDefault()}>
                设为默认
              </Button>
              <Button size="sm" variant="danger" loading={busy()} onClick={() => void remove()}>
                删除
              </Button>
            </Show>
          </div>
        </div>

        <Show when={error()}>
          <div class="mb-3 text-[10.5px] text-bad">{error()}</div>
        </Show>
        <Show when={message()}>
          <div class="mb-3 text-[10.5px] text-ok">{message()}</div>
        </Show>

        <Show when={!loading()} fallback={<div class="py-12 text-center text-[11px] text-faint">品牌加载中…</div>}>
          <div class="space-y-3">
            <div class="flex items-start gap-3">
              <input
                ref={logoInput}
                type="file"
                accept="image/*"
                class="hidden"
                onChange={(event) => {
                  const file = event.currentTarget.files?.[0];
                  if (file) void uploadLogo(file);
                }}
              />
              <button
                type="button"
                class="grid h-[72px] w-[72px] shrink-0 place-items-center overflow-hidden rounded-lg border border-dashed border-line bg-[#0b0e15] text-faint hover:border-accent/50"
                onClick={() => logoInput?.click()}
              >
                <Show when={logoUrl()} fallback={<span class="text-[10px]">上传 logo</span>}>
                  <img src={logoUrl()!} alt="" class="h-full w-full object-contain" />
                </Show>
              </button>
              <div class="min-w-0 flex-1">
                <label class="mb-1 block text-[10px] text-faint">品牌名</label>
                <Input value={draft().name} placeholder="例：红薯铺" onInput={(event) => update({ name: event.currentTarget.value })} />
                <div class="mt-1 text-[9.5px] text-faint">logo 建议 SVG/PNG，≥512px；深色背景上也要能看清。</div>
              </div>
            </div>

            <div>
              <label class="mb-1 block text-[10px] text-faint">色板（≤5）</label>
              <div class="flex items-center gap-1.5">
                <For each={draft().colors ?? []}>
                  {(color, index) => (
                    <input
                      type="color"
                      value={color}
                      class="h-8 w-8 cursor-pointer rounded-md border border-line bg-transparent p-0.5"
                      onInput={(event) => setColor(index(), event.currentTarget.value)}
                    />
                  )}
                </For>
                <Show when={(draft().colors?.length ?? 0) < 5}>
                  <button type="button" class="grid h-8 w-8 place-items-center rounded-md border border-dashed border-line text-faint hover:text-text" onClick={addColor}>
                    ＋
                  </button>
                </Show>
                <span class="ml-1 text-[9.5px] text-faint">主色 · 辅色 · 背景 · 文字 · 强调</span>
              </div>
            </div>

            <div class="grid grid-cols-2 gap-2">
              <div>
                <label class="mb-1 block text-[10px] text-faint">中文字体</label>
                <Input value={draft().font_cn ?? ""} onInput={(event) => update({ font_cn: event.currentTarget.value })} />
              </div>
              <div>
                <label class="mb-1 block text-[10px] text-faint">英文字体</label>
                <Input value={draft().font_en ?? ""} onInput={(event) => update({ font_en: event.currentTarget.value })} />
              </div>
            </div>

            <div>
              <label class="mb-1 block text-[10px] text-faint">调性</label>
              <div class="flex flex-wrap items-center gap-1">
                <For each={draft().tone ?? []}>
                  {(tone) => (
                    <span class="inline-flex items-center gap-1 rounded border border-line px-1.5 py-0.5 text-[9.5px] text-dim">
                      {tone}
                      <button type="button" class="text-faint hover:text-bad" onClick={() => update({ tone: (draft().tone ?? []).filter((item) => item !== tone) })}>
                        ×
                      </button>
                    </span>
                  )}
                </For>
                <input
                  value={toneInput()}
                  placeholder="＋ 添加"
                  class="h-6 w-[92px] rounded border border-dashed border-line bg-transparent px-1.5 text-[9.5px] text-dim outline-none placeholder:text-faint focus:border-accent/50"
                  onInput={(event) => setToneInput(event.currentTarget.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") {
                      event.preventDefault();
                      addTone();
                    }
                  }}
                />
              </div>
            </div>

            <div class="grid grid-cols-2 gap-2">
              <div>
                <label class="mb-1 block text-[10px] text-faint">口播人设 · 供应商</label>
                <Input
                  value={String((draft().voice ?? {}).provider ?? "")}
                  placeholder="ElevenLabs / 本地"
                  onInput={(event) => update({ voice: { ...(draft().voice ?? {}), provider: event.currentTarget.value } })}
                />
              </div>
              <div>
                <label class="mb-1 block text-[10px] text-faint">音色名</label>
                <Input
                  value={String((draft().voice ?? {}).name ?? "")}
                  placeholder="阿岚 · 女声"
                  onInput={(event) => update({ voice: { ...(draft().voice ?? {}), name: event.currentTarget.value } })}
                />
              </div>
            </div>

            <div>
              <label class="mb-1 block text-[10px] text-faint">禁用词 · 审片合规</label>
              <div class="flex flex-wrap items-center gap-1">
                <For each={draft().banned_words ?? []}>
                  {(word) => (
                    <span class="inline-flex items-center gap-1 rounded border border-bad/30 px-1.5 py-0.5 text-[9.5px] text-bad">
                      {word}
                      <button type="button" class="hover:text-text" onClick={() => update({ banned_words: (draft().banned_words ?? []).filter((item) => item !== word) })}>
                        ×
                      </button>
                    </span>
                  )}
                </For>
                <input
                  value={wordInput()}
                  placeholder="＋ 添加"
                  class="h-6 w-[92px] rounded border border-dashed border-line bg-transparent px-1.5 text-[9.5px] text-dim outline-none placeholder:text-faint focus:border-accent/50"
                  onInput={(event) => setWordInput(event.currentTarget.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") {
                      event.preventDefault();
                      addWord();
                    }
                  }}
                />
              </div>
              <div class="mt-1 text-[9.5px] text-faint">命中禁用词时，审片 QA 会 fail。</div>
            </div>

            <div class="flex items-center gap-2 border-t border-line-soft pt-3">
              <span class="text-[10px] text-faint">默认品牌</span>
              <button
                type="button"
                class={`rounded border px-1.5 py-0.5 text-[9.5px] ${draft().default ? "border-ok/40 text-ok" : "border-line text-faint"}`}
                onClick={() => update({ default: !draft().default })}
              >
                {draft().default ? "开" : "关"}
              </button>
              <div class="ml-auto flex items-center gap-1.5">
                <Select value={targetProject()} options={projectOptions()} onChange={setTargetProject} variant="pill" placeholder="选项目" />
                <Button size="sm" loading={busy()} disabled={!selectedId() || !targetProject()} onClick={() => void apply()}>
                  应用到项目
                </Button>
              </div>
            </div>
            <div class="text-[9.5px] text-faint">保存后只影响以后生成的版本；已交付版本保留原品牌快照。</div>
          </div>
        </Show>
      </div>

      <aside class="hidden w-[220px] shrink-0 overflow-auto border-l border-line-soft p-3 xl:block">
        <div class="text-[10px] tracking-wide text-faint">品牌检查</div>
        <div class="mt-1 space-y-1.5">
          <For each={checks()}>
            {(check) => (
              <div class="rounded-md border border-line-soft px-2 py-1.5">
                <div class="flex items-center gap-1.5">
                  <span class={`h-1.5 w-1.5 rounded-full ${check.status === "ok" ? "bg-ok" : check.status === "bad" ? "bg-bad" : "bg-warn"}`} />
                  <span class="text-[10px] text-dim">{check.label}</span>
                </div>
                <div class="mt-0.5 text-[9px] text-faint">{check.hint}</div>
              </div>
            )}
          </For>
        </div>
      </aside>

      <aside class="hidden w-[240px] shrink-0 border-l border-line-soft p-3 lg:block">
        <div class="text-[10px] tracking-wide text-faint">应用预览</div>
        <div class="relative mx-auto mt-2 overflow-hidden rounded-xl border border-line bg-[#0b0e15]" style={{ "aspect-ratio": "9 / 16", width: "160px" }}>
          <div class="grid h-full place-items-center">
            <div class="text-center">
              <Show
                when={logoUrl()}
                fallback={
                  <div class="mx-auto grid h-10 w-10 place-items-center rounded-lg bg-gradient-to-br from-violet to-accent text-[15px] font-semibold text-white">
                    {draft().name.slice(0, 1) || "A"}
                  </div>
                }
              >
                <img src={logoUrl()!} alt="" class="mx-auto h-10 w-10 object-contain" />
              </Show>
              <div class="mt-3 text-[13px] font-semibold text-text">{draft().name || "品牌名"}</div>
              <div class="mt-1 text-[9.5px] text-faint">{draft().tone?.[0] ?? "品牌片头"}</div>
            </div>
          </div>
          <div class="absolute inset-x-2 bottom-2 h-1 rounded-full" style={{ background: `linear-gradient(90deg, ${(draft().colors ?? [])[0] ?? "#E0338A"}, ${(draft().colors ?? [])[1] ?? "#8B2FC9"})` }} />
        </div>
        <div class="mt-2 flex justify-center gap-1">
          <For each={(draft().colors ?? []).slice(0, 5)}>
            {(color) => <i class="h-3 w-3 rounded-full border border-line" style={{ background: color }} />}
          </For>
        </div>
        <div class="mt-2 text-[9px] leading-4 text-faint">片头 logo、字幕字体、主色/强调色、口播音色、合规禁用词。</div>
      </aside>
    </div>
  );
}
