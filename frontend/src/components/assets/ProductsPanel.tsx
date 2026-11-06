import { For, Show, createSignal, onMount } from "solid-js";
import Badge from "../ui/Badge";
import Button from "../ui/Button";
import Input from "../ui/Input";
import Select from "../ui/Select";
import { endpoints, uploadAsset } from "../../lib/api";
import { mediaUrl } from "../../lib/projects";
import type { Product } from "../../lib/types";

interface Props {
  onPrimaryReady?: (open: () => void) => void;
}

function emptyProduct(): Product {
  return {
    id: "",
    name: "",
    sku: "",
    brand: "",
    label_text: "",
    category: "",
    hero_path: null,
    detail_paths: [],
    tags: [],
    status: "draft",
    locked: false,
    rights: { commercial_use: false, ai_reference_allowed: false, note: "" },
  };
}

function fromProduct(product: Product): Product {
  return {
    ...product,
    detail_paths: [...(product.detail_paths ?? [])],
    tags: [...(product.tags ?? [])],
    rights: { ...product.rights },
  };
}

export default function ProductsPanel(props: Props) {
  const [rows, setRows] = createSignal<Product[]>([]);
  const [selectedId, setSelectedId] = createSignal<string | null>(null);
  const [draft, setDraft] = createSignal<Product>(emptyProduct());
  const [loading, setLoading] = createSignal(true);
  const [saving, setSaving] = createSignal(false);
  const [busy, setBusy] = createSignal(false);
  const [error, setError] = createSignal("");
  const [message, setMessage] = createSignal("");
  const [tagText, setTagText] = createSignal("");
  const [confirmDelete, setConfirmDelete] = createSignal(false);
  let fileInput: HTMLInputElement | undefined;

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const data = await endpoints.products();
      setRows(data.products ?? []);
      if (!selectedId() && data.products?.length) select(data.products[0]);
      if (selectedId() && !data.products?.some((item) => item.id === selectedId())) {
        setSelectedId(null);
        setDraft(emptyProduct());
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "商品加载失败");
    } finally {
      setLoading(false);
    }
  };

  const select = (product: Product) => {
    setSelectedId(product.id || null);
    setDraft(fromProduct(product));
    setTagText((product.tags ?? []).join(", "));
    setConfirmDelete(false);
    setMessage("");
    setError("");
  };

  const create = () => {
    setSelectedId(null);
    setDraft(emptyProduct());
    setTagText("");
    setConfirmDelete(false);
    setMessage("新商品：上传真实商品图，锁定后作为镜头参考。");
    setError("");
  };

  onMount(() => {
    void load();
    props.onPrimaryReady?.(create);
  });

  const update = (patch: Partial<Product>) => setDraft((prev) => ({ ...prev, ...patch }));

  const uploadHero = async (file: File) => {
    setBusy(true);
    setError("");
    try {
      const asset = await uploadAsset(file);
      update({ hero_path: asset.path, status: "locked", locked: true });
      setMessage("商品主图已上传，默认锁定。");
    } catch (err) {
      setError(err instanceof Error ? err.message : "上传失败");
    } finally {
      setBusy(false);
      if (fileInput) fileInput.value = "";
    }
  };

  const save = async () => {
    if (!draft().name.trim()) {
      setError("先给商品起个名字");
      return;
    }
    if (draft().locked && !draft().hero_path) {
      setError("锁定商品必须有真实主图");
      return;
    }
    setSaving(true);
    setError("");
    setMessage("");
    const body = {
      name: draft().name.trim(),
      sku: draft().sku ?? "",
      brand: draft().brand ?? "",
      label_text: draft().label_text ?? "",
      category: draft().category ?? "",
      hero_path: draft().hero_path || null,
      detail_paths: draft().detail_paths ?? [],
      tags: tagText().split(",").map((item) => item.trim()).filter(Boolean),
      status: draft().status,
      locked: draft().locked,
      rights: draft().rights,
    };
    try {
      const data = selectedId()
        ? await endpoints.patchProduct(selectedId()!, body)
        : await endpoints.createProduct(body);
      await load();
      select(data.product);
      setMessage("商品已保存；后续镜头可以绑定这个真实商品。");
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存失败");
    } finally {
      setSaving(false);
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
      await endpoints.deleteProduct(selectedId()!);
      setSelectedId(null);
      setDraft(emptyProduct());
      setConfirmDelete(false);
      await load();
      setMessage("已删除商品。");
    } catch (err) {
      setError(err instanceof Error ? err.message : "删除失败");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div class="grid h-full min-h-0 grid-cols-[260px_minmax(0,1fr)] gap-0 overflow-hidden">
      <aside class="min-h-0 overflow-auto border-r border-line-soft bg-surface/40 p-3">
        <div class="mb-2 flex items-center justify-between">
          <span class="text-[10.5px] uppercase tracking-wide text-faint">商品资产</span>
          <span class="text-[10px] text-faint">{rows().length}</span>
        </div>
        <Show when={!loading()} fallback={<div class="py-8 text-center text-[11px] text-faint">加载中…</div>}>
          <Show
            when={rows().length > 0}
            fallback={
              <div class="rounded-lg border border-dashed border-line px-3 py-8 text-center">
                <div class="text-[12px] text-dim">还没有锁定商品</div>
                <p class="mt-1 text-[10.5px] leading-5 text-faint">真实商品图是带货广告的主锚点，模型不能替代。</p>
                <Button class="mt-3" size="sm" variant="primary" onClick={create}>＋ 新建</Button>
              </div>
            }
          >
            <div class="space-y-1.5">
              <For each={rows()}>
                {(product) => (
                  <button
                    type="button"
                    class={`flex w-full items-center gap-2 rounded-lg border px-2 py-2 text-left transition-colors ${
                      product.id === selectedId() ? "border-accent/50 bg-accent/8" : "border-transparent hover:border-line hover:bg-surface-2/60"
                    }`}
                    onClick={() => select(product)}
                  >
                    <div class="h-11 w-9 shrink-0 overflow-hidden rounded-md bg-[#0b0e15]">
                      <Show when={product.hero_path} fallback={<div class="grid h-full place-items-center text-[16px] text-white/20">▣</div>}>
                        <img src={mediaUrl(product.hero_path!)} alt="" class="h-full w-full object-cover" />
                      </Show>
                    </div>
                    <div class="min-w-0 flex-1">
                      <div class="truncate text-[11.5px] text-text">{product.name}</div>
                      <div class="mt-0.5 flex items-center gap-1.5">
                        <span class="text-[9.5px] text-faint">{product.sku || "无 SKU"}</span>
                        <Show when={product.locked}><Badge tone="good">已锁定</Badge></Show>
                      </div>
                    </div>
                  </button>
                )}
              </For>
            </div>
          </Show>
        </Show>
      </aside>

      <section class="min-h-0 overflow-auto p-5">
        <div class="mx-auto max-w-[760px]">
          <div class="mb-4 flex items-start justify-between gap-3">
            <div>
              <div class="text-[14px] font-semibold text-text">{selectedId() ? "编辑商品" : "新建商品"}</div>
              <p class="mt-1 text-[11px] leading-5 text-faint">锁定真实商品图、SKU 与授权；镜头只引用，不让模型重画包装文字。</p>
            </div>
            <Show when={selectedId()}>
              <Button size="sm" variant="ghost" disabled={busy()} onClick={() => void remove()}>
                {confirmDelete() ? "确认删除" : "删除"}
              </Button>
            </Show>
          </div>

          <Show when={error()}><div class="mb-3 rounded-lg border border-bad/30 bg-bad/5 px-3 py-2 text-[11px] text-bad">{error()}</div></Show>
          <Show when={message()}><div class="mb-3 rounded-lg border border-good/25 bg-good/5 px-3 py-2 text-[11px] text-good">{message()}</div></Show>

          <div class="grid grid-cols-[180px_minmax(0,1fr)] gap-4">
            <div>
              <div class="overflow-hidden rounded-xl border border-line-soft bg-[#0b0e15]" style={{ "aspect-ratio": "3 / 4" }}>
                <Show when={draft().hero_path} fallback={
                  <button type="button" class="grid h-full w-full place-items-center text-faint hover:text-text" onClick={() => fileInput?.click()}>
                    <span class="text-center text-[11px] leading-5">＋<br />上传商品图</span>
                  </button>
                }>
                  <img src={mediaUrl(draft().hero_path!)} alt="" class="h-full w-full object-cover" />
                </Show>
              </div>
              <input ref={fileInput} type="file" class="hidden" accept="image/*" onChange={(event) => {
                const file = event.currentTarget.files?.[0];
                if (file) void uploadHero(file);
              }} />
              <Button class="mt-2 w-full" size="sm" variant="secondary" disabled={busy()} onClick={() => fileInput?.click()}>
                {busy() ? "上传中…" : "更换商品图"}
              </Button>
            </div>

            <div class="space-y-3">
              <label class="block">
                <span class="mb-1 block text-[10.5px] text-faint">商品名</span>
                <Input value={draft().name} placeholder="例如：YACHEL 冰丝无痕背心" onInput={(event) => update({ name: event.currentTarget.value })} />
              </label>
              <div class="grid grid-cols-2 gap-3">
                <label class="block"><span class="mb-1 block text-[10.5px] text-faint">SKU</span><Input value={draft().sku ?? ""} placeholder="SKU-001" onInput={(event) => update({ sku: event.currentTarget.value })} /></label>
                <label class="block"><span class="mb-1 block text-[10.5px] text-faint">品牌</span><Input value={draft().brand ?? ""} placeholder="YACHEL" onInput={(event) => update({ brand: event.currentTarget.value })} /></label>
              </div>
              <div class="grid grid-cols-2 gap-3">
                <label class="block"><span class="mb-1 block text-[10.5px] text-faint">类目</span><Input value={draft().category ?? ""} placeholder="服饰 / 内衣" onInput={(event) => update({ category: event.currentTarget.value })} /></label>
                <label class="block"><span class="mb-1 block text-[10.5px] text-faint">状态</span>
                  <Select value={draft().status} options={[{ value: "draft", label: "草稿" }, { value: "locked", label: "锁定" }, { value: "archived", label: "归档" }]} onChange={(value) => update({ status: value })} variant="pill" />
                </label>
              </div>
              <label class="block">
                <span class="mb-1 block text-[10.5px] text-faint">包装/领标文字</span>
                <Input value={draft().label_text ?? ""} placeholder="YACHEL" onInput={(event) => update({ label_text: event.currentTarget.value })} />
              </label>
              <label class="block">
                <span class="mb-1 block text-[10.5px] text-faint">标签（逗号分隔）</span>
                <Input value={tagText()} placeholder="无痕, 冰丝, 通勤" onInput={(event) => setTagText(event.currentTarget.value)} />
              </label>
              <div class="rounded-lg border border-line-soft bg-surface/50 p-3">
                <div class="mb-2 text-[10.5px] text-faint">锁定与授权</div>
                <label class="flex items-center gap-2 text-[11px] text-dim">
                  <input type="checkbox" checked={draft().locked} onChange={(event) => update({ locked: event.currentTarget.checked, status: event.currentTarget.checked ? "locked" : "draft" })} />
                  锁定为真实商品（镜头不得重画标签）
                </label>
                <div class="mt-2 grid grid-cols-2 gap-2">
                  <label class="flex items-center gap-2 text-[11px] text-dim">
                    <input type="checkbox" checked={draft().rights.ai_reference_allowed} onChange={(event) => update({ rights: { ...draft().rights, ai_reference_allowed: event.currentTarget.checked } })} />
                    AI 参考允许
                  </label>
                  <label class="flex items-center gap-2 text-[11px] text-dim">
                    <input type="checkbox" checked={draft().rights.commercial_use} onChange={(event) => update({ rights: { ...draft().rights, commercial_use: event.currentTarget.checked } })} />
                    商用
                  </label>
                </div>
              </div>
              <div class="flex justify-end gap-2 pt-1">
                <Button size="sm" variant="ghost" onClick={create}>取消</Button>
                <Button size="sm" variant="primary" disabled={saving()} onClick={() => void save()}>{saving() ? "保存中…" : "保存商品"}</Button>
              </div>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
