import { For, Show, createSignal } from "solid-js";
import AppShellV2 from "../components/layout/AppShellV2";
import AssetsPanel from "../components/assets/AssetsPanel";
import BrandsPanel from "../components/assets/BrandsPanel";
import Button from "../components/ui/Button";

const TABS = [
  { value: "assets", label: "素材" },
  { value: "brands", label: "品牌" },
  { value: "templates", label: "模板" },
];

export default function Assets() {
  const [tab, setTab] = createSignal("assets");
  const [assetOpen, setAssetOpen] = createSignal<{ fn: () => void } | null>(null);
  const [brandOpen, setBrandOpen] = createSignal<{ fn: () => void } | null>(null);

  const AssetsPrimary = () => (
    <Button size="sm" variant="primary" onClick={() => assetOpen()?.fn()}>
      ＋ 导入素材
    </Button>
  );
  const BrandsPrimary = () => (
    <Button size="sm" variant="primary" onClick={() => brandOpen()?.fn()}>
      ＋ 新建品牌
    </Button>
  );

  return (
    <AppShellV2
      module="assets"
      context={
        <div class="flex items-center gap-2">
          <span class="text-[13px] font-semibold text-text">资产</span>
          <span class="rounded border border-line px-1 py-px text-[10px] text-faint">
            {tab() === "brands" ? "品牌包" : tab() === "templates" ? "P1" : "素材"}
          </span>
        </div>
      }
      subTabs={
        <div class="flex items-center gap-0.5 rounded-lg border border-line-soft bg-surface p-0.5">
          <For each={TABS}>
            {(item) => (
              <button
                type="button"
                class={`h-6 rounded-md px-3 text-[11px] transition-colors ${
                  tab() === item.value ? "bg-surface-2 text-text" : "text-faint hover:text-text"
                }`}
                onClick={() => setTab(item.value)}
              >
                {item.label}
              </button>
            )}
          </For>
        </div>
      }
      primary={
        <Show when={tab() === "assets"} fallback={<Show when={tab() === "brands"} fallback={<Button size="sm" variant="primary" disabled title="模板库 P1">＋ 新建模板</Button>}><BrandsPrimary /></Show>}>
          <AssetsPrimary />
        </Show>
      }
      footer={<span class="text-[10px] text-faint">素材 · 品牌 · 模板</span>}
    >
      <Show when={tab() === "assets"}>
        <AssetsPanel onPrimaryReady={(fn) => setAssetOpen({ fn })} />
      </Show>
      <Show when={tab() === "brands"}>
        <BrandsPanel onPrimaryReady={(fn) => setBrandOpen({ fn })} />
      </Show>
      <Show when={tab() === "templates"}>
        <div class="grid h-full place-items-center p-6">
          <div class="max-w-[460px] text-center">
            <div class="text-[13px] font-medium text-text">模板</div>
            <p class="mt-2 text-[11px] leading-6 text-faint">
              广告结构/风格预设，从模板新建项目。P1 上线；P0 先把素材与品牌做完。
            </p>
            <Button class="mt-4" size="sm" onClick={() => setTab("assets")}>
              回到素材
            </Button>
          </div>
        </div>
      </Show>
    </AppShellV2>
  );
}
