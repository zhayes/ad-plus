import { For, Show, createSignal } from "solid-js";
import { useNavigate, useParams } from "@solidjs/router";
import AppShellV2 from "../components/layout/AppShellV2";
import AssetsPanel from "../components/assets/AssetsPanel";
import BrandsPanel from "../components/assets/BrandsPanel";
import PersonasTable from "../components/assets/PersonasTable";
import ProductsPanel from "../components/assets/ProductsPanel";
import Button from "../components/ui/Button";

const TABS = [
  { value: "assets", label: "素材" },
  { value: "products", label: "商品" },
  { value: "personas", label: "数字人" },
  { value: "brands", label: "品牌" },
  { value: "templates", label: "模板" },
];

export default function Assets() {
  const params = useParams();
  const navigate = useNavigate();
  const validTabs = new Set(TABS.map((item) => item.value));
  const initialTab = params.tab && validTabs.has(params.tab) ? params.tab : "assets";
  const [tab, setTab] = createSignal(initialTab);
  const [assetOpen, setAssetOpen] = createSignal<{ fn: () => void } | null>(null);
  const [brandOpen, setBrandOpen] = createSignal<{ fn: () => void } | null>(null);
  const [productOpen, setProductOpen] = createSignal<{ fn: () => void } | null>(null);

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
  const PersonasPrimary = () => (
    <Button size="sm" variant="primary" onClick={() => navigate("/personas/new")}>
      ＋ 新建数字人
    </Button>
  );
  const ProductsPrimary = () => (
    <Button size="sm" variant="primary" onClick={() => productOpen()?.fn()}>
      ＋ 新建商品
    </Button>
  );

  return (
    <AppShellV2
      module="assets"
      context={
        <div class="flex items-center gap-2">
          <span class="text-[13px] font-semibold text-text">资产</span>
          <span class="rounded border border-line px-1 py-px text-[10px] text-faint">
            {tab() === "brands" ? "品牌包" : tab() === "personas" ? "可复用" : tab() === "products" ? "锁定资产" : tab() === "templates" ? "P1" : "素材"}
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
                onClick={() => {
                  setTab(item.value);
                  navigate(`/assets/${item.value}`);
                }}
              >
                {item.label}
              </button>
            )}
          </For>
        </div>
      }
      primary={
        <Show
          when={tab() === "assets"}
          fallback={
            <Show
              when={tab() === "personas"}
              fallback={
                <Show
                  when={tab() === "products"}
                  fallback={
                    <Show
                      when={tab() === "brands"}
                  fallback={<Button size="sm" variant="primary" disabled title="模板库 P1">＋ 新建模板</Button>}
                >
                      <BrandsPrimary />
                    </Show>
                  }
                >
                  <ProductsPrimary />
                </Show>
              }
            >
              <PersonasPrimary />
            </Show>
          }
        >
          <AssetsPrimary />
        </Show>
      }
      footer={<span class="text-[10px] text-faint">素材 · 数字人 · 品牌 · 模板</span>}
    >
      <Show when={tab() === "assets"}>
        <AssetsPanel onPrimaryReady={(fn) => setAssetOpen({ fn })} />
      </Show>
      <Show when={tab() === "products"}>
        <ProductsPanel onPrimaryReady={(fn) => setProductOpen({ fn })} />
      </Show>
      <Show when={tab() === "personas"}>
        <PersonasTable />
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
