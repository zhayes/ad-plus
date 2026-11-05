import { For, Show, createSignal, onMount } from "solid-js";
import { useNavigate } from "@solidjs/router";
import Button from "../components/ui/Button";
import Logo from "../components/ui/Logo";
import Input from "../components/ui/Input";
import Badge from "../components/ui/Badge";
import { api } from "../lib/api";
import type { BootstrapInfo, ProviderInfo } from "../lib/types";

const LABELS: Record<string, string> = {
  deepseek: "DeepSeek",
  anthropic: "Anthropic",
  openai: "OpenAI",
  google: "Google Gemini",
  openrouter: "OpenRouter",
  xai: "xAI",
  mistral: "Mistral",
  groq: "Groq",
  moonshot: "Moonshot / Kimi",
  qwen: "Qwen",
};

const HINTS: Record<string, string> = {
  deepseek: "便宜、快",
  anthropic: "最擅长长剧本与结构化产物",
  openai: "通用，也能出图与配音",
  google: "一个 key 通图像与语音",
  openrouter: "一个 key 通多家模型",
};

const ORDER = ["deepseek", "anthropic", "openai", "google", "openrouter", "xai", "mistral", "groq", "moonshot", "qwen"];

export default function Onboarding() {
  const navigate = useNavigate();
  const [providers, setProviders] = createSignal<ProviderInfo[]>([]);
  const [selected, setSelected] = createSignal<string | null>(null);
  const [canContinue, setCanContinue] = createSignal(false);
  const [error, setError] = createSignal("");

  const load = async () => {
    try {
      const data = await api.get<{ providers: ProviderInfo[] }>("/api/pi/providers");
      const sorted = (data.providers ?? []).sort((a, b) => ORDER.indexOf(a.provider) - ORDER.indexOf(b.provider));
      setProviders(sorted);
      const first = sorted.find((p) => !p.configured);
      setSelected(first?.provider ?? sorted[0]?.provider ?? null);
      const bootstrap = await api.get<BootstrapInfo>("/api/bootstrap");
      setCanContinue(!!bootstrap.has_model);
    } catch (err) {
      setError(String(err));
    }
  };

  onMount(() => void load());

  return (
    <div class="grid min-h-full place-items-center bg-bg p-6 text-text">
      <div class="w-full max-w-[560px] rounded-2xl border border-line-soft bg-surface p-6">
        <div class="flex items-center gap-2">
          <Logo size={32} />
          <span class="text-[15px] font-semibold">
            Ad<span class="text-accent">+</span>
          </span>
        </div>

        <h1 class="mt-4 text-[17px] font-semibold">先接入一个模型</h1>
        <p class="mt-1 text-[12px] leading-relaxed text-dim">
          导演、编剧、剪辑决策都由模型完成 —— 没有模型什么都跑不了。选一个你已有 key 的服务，30 秒配好。
        </p>

        <Show when={error()}>
          <p class="mt-3 rounded-lg border border-bad/40 bg-bad/10 px-3 py-2 text-[11.5px] text-bad">{error()}</p>
        </Show>

        <div class="mt-4 space-y-1.5">
          <For each={providers()}>
            {(provider) => (
              <ProviderRow
                provider={provider}
                selected={selected() === provider.provider}
                onSelect={() => setSelected(provider.provider)}
                onSaved={() => {
                  setCanContinue(true);
                  void load();
                }}
              />
            )}
          </For>
        </div>

        <div class="mt-5 flex items-center gap-3">
          <span class="text-[10.5px] text-faint">媒体服务（图 / 视频 / 配音）的 key 可以进去后再配</span>
          <Button
            class="ml-auto"
            variant="primary"
            disabled={!canContinue()}
            onClick={() => navigate("/", { replace: true })}
          >
            继续
          </Button>
        </div>
      </div>
    </div>
  );
}

function ProviderRow(props: {
  provider: ProviderInfo;
  selected: boolean;
  onSelect: () => void;
  onSaved: () => void;
}) {
  const [value, setValue] = createSignal("");
  const [message, setMessage] = createSignal<{ tone: "ok" | "bad" | "dim"; text: string } | null>(null);
  const [busy, setBusy] = createSignal(false);

  const save = async () => {
    if (!value().trim()) {
      setMessage({ tone: "bad", text: "请先粘贴 key" });
      return;
    }
    setBusy(true);
    setMessage({ tone: "dim", text: "验证中…" });
    try {
      await api.post("/api/keys", { name: props.provider.env, value: value().trim() });
      const models = await api.get<{ models?: unknown[]; error?: string }>("/api/pi/models?force=true");
      if ((models.models ?? []).length) {
        setMessage({ tone: "ok", text: `连接正常 · 可用模型 ${models.models?.length} 个` });
        props.onSaved();
      } else {
        setMessage({
          tone: "bad",
          text: `保存了，但没能列出模型${models.error ? `（${models.error}）` : ""} —— key 可能无效，或本机 pi 运行时没跑起来`,
        });
      }
    } catch (err) {
      setMessage({ tone: "bad", text: `验证失败：${String(err)}` });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      class="rounded-xl border px-3 py-2"
      classList={{
        "border-accent/50 bg-surface-2": props.selected,
        "border-line-soft": !props.selected,
      }}
      onClick={props.onSelect}
    >
      <div class="flex items-center gap-2">
        <span class="grid h-7 w-7 place-items-center rounded-md border border-line bg-surface-2 text-[10.5px] text-dim">
          {(LABELS[props.provider.provider] ?? props.provider.provider).slice(0, 2).toUpperCase()}
        </span>
        <div class="min-w-0">
          <div class="text-[12.5px] text-text">{LABELS[props.provider.provider] ?? props.provider.provider}</div>
          <div class="truncate text-[10.5px] text-faint">
            {props.provider.configured ? `已配置 · ${props.provider.masked}` : HINTS[props.provider.provider] ?? props.provider.env}
          </div>
        </div>
        <Show when={props.provider.provider === "deepseek"}>
          <Badge tone="accent" class="ml-1">推荐</Badge>
        </Show>
        <Show when={props.provider.configured}>
          <Badge tone="ok" class="ml-auto">已配置</Badge>
        </Show>
      </div>

      <Show when={props.selected && !props.provider.configured}>
        <div class="mt-2 flex gap-2">
          <Input
            type="password"
            tone="password"
            class="flex-1"
            placeholder={`粘贴 ${props.provider.env}`}
            value={value()}
            onClick={(event) => event.stopPropagation()}
            onInput={(event) => setValue(event.currentTarget.value)}
            onKeyDown={(event) => event.key === "Enter" && void save()}
          />
          <Button size="sm" variant="primary" loading={busy()} onClick={() => void save()}>
            保存并验证
          </Button>
        </div>
      </Show>

      <Show when={message()}>
        {(msg) => (
          <p
            class="mt-1.5 text-[11px]"
            classList={{
              "text-ok": msg().tone === "ok",
              "text-bad": msg().tone === "bad",
              "text-faint": msg().tone === "dim",
            }}
          >
            {msg().text}
          </p>
        )}
      </Show>
    </div>
  );
}
