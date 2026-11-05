import { For, Show, createMemo, createSignal, onMount } from "solid-js";
import { useNavigate } from "@solidjs/router";
import KeyRow, { type RowModel } from "../components/settings/KeyRow";
import Button from "../components/ui/Button";
import Logo from "../components/ui/Logo";
import ModuleDock from "../components/layout/ModuleDock";
import Input from "../components/ui/Input";
import Select from "../components/ui/Select";
import { api } from "../lib/api";
import type { AppConfig, BootstrapInfo, CapabilityRow, KeyInfo, PiIntegration, PiStatus, ProviderEntry } from "../lib/types";

type Tab = "model" | "media" | "storage" | "notifications" | "shortcuts" | "advanced" | "about";

interface Snapshot {
  keys: KeyInfo[];
  pi: { providers: ProviderEntry[] };
  matrix: { runtimes: Record<string, boolean>; capabilities: CapabilityRow[] };
  app_data: string;
  keychain: boolean;
}

const EXPOSURES = ["direct", "codemode", "deferred", "hidden"];

const SHORTCUTS = [
  { keys: "⌘K", label: "命令面板" },
  { keys: "⌘N", label: "新建项目" },
  { keys: "⌘O", label: "打开项目" },
  { keys: "⌘,", label: "设置" },
  { keys: "Esc", label: "关闭面板 / 抽屉" },
];

export default function Settings() {
  const navigate = useNavigate();
  const [tab, setTab] = createSignal<Tab>("model");
  const [state, setState] = createSignal<Snapshot | null>(null);
  const [integration, setIntegration] = createSignal<PiIntegration | null>(null);
  const [status, setStatus] = createSignal<PiStatus | null>(null);
  const [config, setConfig] = createSignal<AppConfig | null>(null);
  const [outputDir, setOutputDir] = createSignal("");
  const [version, setVersion] = createSignal("0.1.0");
  const [exposure, setExposure] = createSignal("direct");
  const [query, setQuery] = createSignal("");
  const [toast, setToast] = createSignal<{ text: string; error?: boolean } | null>(null);
  const [loading, setLoading] = createSignal(true);

  const notify = (text: string, error = false) => {
    setToast({ text, error });
    window.setTimeout(() => setToast(null), 3000);
  };

  const reload = async () => {
    try {
      const [snapshot, integ, boot, cfg] = await Promise.all([
        api.get<Snapshot>("/api/state"),
        api.get<PiIntegration>("/api/pi/integration").catch(() => null),
        api.get<BootstrapInfo>("/api/bootstrap").catch(() => null),
        api.get<AppConfig>("/api/config").catch(() => null),
      ]);
      setState(snapshot);
      setIntegration(integ);
      if (boot?.version) setVersion(boot.version);
      if (cfg) {
        setConfig(cfg);
        setOutputDir(cfg.output_dir);
      }
      const server = integ?.servers?.find((s) => s.name === "openmontage");
      if (server) setExposure(server.exposure ?? "direct");
    } catch (err) {
      notify(`加载失败：${String(err)}`, true);
    } finally {
      setLoading(false);
    }
  };

  onMount(() => {
    void reload();
    void api
      .get<PiStatus>("/api/pi/status")
      .then(setStatus)
      .catch(() => undefined);
  });

  const saveKey = async (name: string, value: string) => {
    try {
      const result = await api.post<{ state: Snapshot }>("/api/keys", { name, value });
      setState(result.state);
      notify("已保存");
    } catch (err) {
      notify(String(err), true);
    }
  };

  const clearKey = async (name: string) => {
    try {
      const result = await api.del<{ state: Snapshot }>(`/api/keys/${encodeURIComponent(name)}`);
      setState(result.state);
      notify("已清除");
    } catch (err) {
      notify(String(err), true);
    }
  };

  const modelRows = createMemo<RowModel[]>(() =>
    (state()?.pi?.providers ?? []).map((provider) => ({
      name: provider.env,
      label: provider.label,
      configured: provider.configured,
      masked: provider.masked,
      meta: `${provider.provider} · ${provider.env}`,
    })),
  );

  const mediaRows = createMemo<RowModel[]>(() => {
    const q = query().trim().toLowerCase();
    return (state()?.keys ?? [])
      .filter(
        (key) =>
          !q ||
          key.name.toLowerCase().includes(q) ||
          (key.capabilities ?? []).join(" ").toLowerCase().includes(q),
      )
      .map((key) => ({
        name: key.name,
        label: key.label,
        configured: key.configured,
        masked: key.masked,
        meta: `解锁 ${key.unlocks} 个工具`,
        caps: key.capabilities,
      }));
  });

  const modelCount = () => {
    const rows = modelRows();
    return `${rows.filter((r) => r.configured).length}/${rows.length}`;
  };
  const mediaCount = () => {
    const keys = state()?.keys ?? [];
    return `${keys.filter((k) => k.configured).length}/${keys.length}`;
  };

  const saveConfig = async (patch: Record<string, unknown>) => {
    const data = await api.post<AppConfig>("/api/config", patch);
    setConfig(data);
    setOutputDir(data.output_dir);
    return data;
  };

  const saveOutput = async (value?: string) => {
    try {
      await saveConfig({ output_dir: value ?? outputDir() });
      notify("已保存输出目录");
    } catch (err) {
      notify(String(err), true);
    }
  };

  const useDefaultOutput = () => {
    const fallback = config()?.default_output_dir;
    if (!fallback) return;
    setOutputDir(fallback);
    void saveOutput(fallback);
  };

  const revealPath = async (path?: string) => {
    if (!path) return;
    try {
      await api.post("/api/reveal", { path });
    } catch (err) {
      notify(String(err), true);
    }
  };

  const toggleNotification = async (key: "approvals" | "done" | "failed") => {
    const current = config()?.notifications;
    if (!current) return;
    try {
      await saveConfig({ [`notify_${key}`]: !current[key] });
      notify("通知设置已保存");
    } catch (err) {
      notify(String(err), true);
    }
  };

  const testNotification = async () => {
    try {
      await api.post("/api/notify", { title: "Ad+", body: "系统通知已开启。" });
      notify("已发送系统通知");
    } catch (err) {
      notify(String(err), true);
    }
  };

  const recheck = async () => {
    try {
      await api.post("/api/recheck");
      await reload();
      notify("已重新检查环境");
    } catch (err) {
      notify(String(err), true);
    }
  };

  const logPath = () => `${config()?.app_data ?? state()?.app_data ?? ""}/app.log`;

  const saveExposure = async () => {
    try {
      await api.post("/api/pi/integration", { exposure: exposure() });
      notify("已保存，重启会话后生效");
    } catch (err) {
      notify(String(err), true);
    }
  };

  const runtimes = () => {
    const r = state()?.matrix?.runtimes ?? {};
    return ["ffmpeg", "remotion", "hyperframes"].map((name) => `${name} ${r[name] ? "✓" : "✗"}`).join(" · ");
  };

  const caps = () => {
    const rows = (state()?.matrix?.capabilities ?? []).filter((c) =>
      ["image_generation", "video_generation", "tts", "music_generation"].includes(c.capability),
    );
    return rows.map((c) => `${c.capability} ${c.configured}/${c.total}`).join(" · ") || "—";
  };

  const piLine = () => {
    const v = status()?.version;
    const models = (status()?.models?.stdout ?? "")
      .split("\n")
      .filter((line) => line.trim()).length;
    const mcp = status()?.mcp?.stdout ?? "";
    return `pi ${v?.available ? v.stdout : "未安装"} · 模型 ${Math.max(0, models - 1)} 个 · MCP ${
      mcp.includes("connected") ? "已连接" : "未连接"
    }`;
  };

  return (
    <div class="flex h-full flex-col bg-bg text-text">
      <header class="flex h-11 shrink-0 items-center gap-2 border-b border-line-soft px-3">
        <Logo size={22} />
        <span class="text-[13px] font-semibold">设置</span>
        <Button size="sm" class="ml-auto" onClick={() => navigate("/projects")}>
          ← 回到项目
        </Button>
      </header>

      <div class="flex min-h-0 flex-1">
        <nav class="w-[200px] shrink-0 border-r border-line-soft p-2">
          <For
            each={[
              { id: "model" as Tab, label: "模型", count: modelCount },
              { id: "media" as Tab, label: "媒体服务", count: mediaCount },
              { id: "storage" as Tab, label: "输出与存储", count: () => "" },
              { id: "notifications" as Tab, label: "通知", count: () => "" },
              { id: "shortcuts" as Tab, label: "快捷键", count: () => "" },
              { id: "advanced" as Tab, label: "高级", count: () => "" },
              { id: "about" as Tab, label: "关于", count: () => "" },
            ]}
          >
            {(item) => (
              <button
                class="mb-0.5 flex h-8 w-full items-center gap-2 rounded-md px-2.5 text-left text-[12px]"
                classList={{
                  "bg-surface-2 text-text": tab() === item.id,
                  "text-dim hover:bg-surface-2": tab() !== item.id,
                }}
                onClick={() => setTab(item.id)}
              >
                {item.label}
                <Show when={item.count()}>
                  <span class="ml-auto font-mono text-[10.5px] text-faint">{item.count()}</span>
                </Show>
              </button>
            )}
          </For>
        </nav>

        <main class="min-w-0 flex-1 overflow-auto">
          <div class="mx-auto w-full max-w-[720px] px-6 py-7">
            <Show when={tab() === "model"}>
              <h2 class="text-[14px] font-semibold">模型</h2>
              <p class="mt-1 text-[11.5px] text-faint">
                驱动 agent 的 LLM。key 存在 macOS 钥匙串，保存后立即生效。
              </p>
              <Show when={loading()}>
                <p class="mt-3 text-[11.5px] text-faint">读取中…</p>
              </Show>
              <div class="mt-3">
                <For each={modelRows()}>
                  {(row) => <KeyRow item={row} onSave={saveKey} onClear={clearKey} />}
                </For>
              </div>
            </Show>

            <Show when={tab() === "media"}>
              <h2 class="text-[14px] font-semibold">媒体服务</h2>
              <p class="mt-1 text-[11.5px] text-faint">
                图像 / 视频 / 语音 / 音乐 / 素材。按「解锁工具数」排序，同一个 key 解锁越多越值得先配。
              </p>
              <Input
                class="mt-3"
                placeholder="搜索 key 或能力"
                value={query()}
                onInput={(event) => setQuery(event.currentTarget.value)}
              />
              <div class="mt-2">
                <For each={mediaRows()}>
                  {(row) => <KeyRow item={row} onSave={saveKey} onClear={clearKey} />}
                </For>
              </div>
              <Show when={mediaRows().length === 0}>
                <p class="mt-3 text-[11.5px] text-faint">没有匹配「{query()}」的 key</p>
              </Show>
            </Show>

            <Show when={tab() === "storage"}>
              <h2 class="text-[14px] font-semibold">输出与存储</h2>
              <p class="mt-1 text-[11.5px] text-faint">
                成片、项目与下载素材的落盘位置。改目录只影响新任务，旧项目不搬家。
              </p>

              <div class="mt-4 rounded-lg border border-line-soft p-3">
                <label class="mb-1.5 block text-[10.5px] text-faint">项目输出目录</label>
                <Input value={outputDir()} onInput={(event) => setOutputDir(event.currentTarget.value)} />
                <div class="mt-1 break-all text-[9.5px] text-faint">默认：{config()?.default_output_dir ?? "—"}</div>
                <div class="mt-2 flex flex-wrap items-center gap-1.5">
                  <Button size="sm" variant="primary" onClick={() => void saveOutput()}>
                    保存
                  </Button>
                  <Button size="sm" variant="ghost" onClick={useDefaultOutput}>
                    使用默认
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => void revealPath(config()?.app_data)}>
                    在 Finder 显示数据目录
                  </Button>
                </div>
              </div>

              <div class="mt-3 rounded-lg border border-line-soft p-3">
                <div class="text-[10.5px] text-faint">应用数据</div>
                <div class="mt-1 break-all font-mono text-[10px] text-dim">{config()?.app_data ?? state()?.app_data ?? "—"}</div>
                <div class="mt-2 text-[10.5px] text-faint">日志</div>
                <div class="mt-1 flex items-center gap-2">
                  <code class="min-w-0 flex-1 truncate text-[9.5px] text-faint">{logPath()}</code>
                  <Button size="sm" variant="ghost" onClick={() => void revealPath(logPath())}>
                    打开
                  </Button>
                </div>
              </div>
            </Show>

            <Show when={tab() === "notifications"}>
              <h2 class="text-[14px] font-semibold">通知</h2>
              <p class="mt-1 text-[11.5px] text-faint">
                待确认、完成、失败时发 macOS 系统通知；不弹窗打断当前操作。
              </p>

              <div class="mt-4 divide-y divide-line-soft rounded-lg border border-line-soft">
                <For
                  each={[
                    { key: "approvals" as const, label: "待确认", desc: "方案 / 审片 / 报价" },
                    { key: "done" as const, label: "完成", desc: "渲染 / 预览完成" },
                    { key: "failed" as const, label: "失败", desc: "任务失败或中断" },
                  ]}
                >
                  {(item) => (
                    <div class="flex items-center gap-3 px-3 py-2.5">
                      <div class="min-w-0 flex-1">
                        <div class="text-[11.5px] text-text">{item.label}</div>
                        <div class="mt-0.5 text-[10px] text-faint">{item.desc}</div>
                      </div>
                      <button
                        type="button"
                        class={`rounded border px-2 py-0.5 text-[10px] ${
                          config()?.notifications?.[item.key] ? "border-ok/40 text-ok" : "border-line text-faint"
                        }`}
                        onClick={() => void toggleNotification(item.key)}
                      >
                        {config()?.notifications?.[item.key] ? "开" : "关"}
                      </button>
                    </div>
                  )}
                </For>
              </div>

              <div class="mt-3 flex items-center gap-2">
                <Button size="sm" onClick={() => void testNotification()}>
                  发送测试通知
                </Button>
                <span class="text-[10px] text-faint">通过 macOS 通知中心；首次使用可能需要在系统设置里允许。</span>
              </div>
            </Show>

            <Show when={tab() === "shortcuts"}>
              <h2 class="text-[14px] font-semibold">快捷键</h2>
              <p class="mt-1 text-[11.5px] text-faint">全局快捷键在应用任何页面生效；输入框聚焦时 ⌘K 仍然可用。</p>
              <div class="mt-4 divide-y divide-line-soft rounded-lg border border-line-soft">
                <For each={SHORTCUTS}>
                  {(item) => (
                    <div class="flex items-center gap-3 px-3 py-2.5">
                      <span class="text-[11.5px] text-dim">{item.label}</span>
                      <kbd class="ml-auto rounded border border-line bg-surface-2 px-2 py-0.5 font-mono text-[10px] text-text">
                        {item.keys}
                      </kbd>
                    </div>
                  )}
                </For>
              </div>
            </Show>

            <Show when={tab() === "advanced"}>
              <h2 class="text-[14px] font-semibold">高级</h2>
              <p class="mt-1 text-[11.5px] text-faint">Pi 集成、工具暴露方式、日志与环境检查。</p>

              <div class="mt-4 flex items-start gap-3 border-b border-line-soft pb-3">
                <div class="min-w-0 flex-1">
                  <div class="text-[12.5px]">工具暴露方式</div>
                  <div class="mt-0.5 text-[10.5px] leading-relaxed text-faint">
                    direct：工具直接声明给模型，行为可预测；codemode：模型写 JS 调用，省上下文但更难调试
                  </div>
                </div>
                <Select
                  variant="pill"
                  value={exposure()}
                  onChange={setExposure}
                  options={EXPOSURES.map((value) => ({ value, label: value }))}
                />
                <Button size="sm" variant="primary" onClick={() => void saveExposure()}>
                  保存
                </Button>
              </div>

              <div class="flex items-start gap-3 border-b border-line-soft py-3">
                <div class="min-w-0 flex-1">
                  <div class="text-[12.5px]">会话信任</div>
                  <div class="mt-0.5 text-[10.5px] text-faint">{integration()?.trust?.note ?? "—"}</div>
                </div>
              </div>

              <div class="flex items-start gap-3 border-b border-line-soft py-3">
                <div class="min-w-0 flex-1">
                  <div class="text-[12.5px]">运行时</div>
                  <div class="mt-0.5 text-[10.5px] text-faint">{piLine()}</div>
                </div>
                <Button size="sm" variant="ghost" onClick={() => void recheck()}>
                  重新检查
                </Button>
              </div>

              <div class="py-3">
                <div class="flex items-center gap-2">
                  <div class="min-w-0 flex-1">
                    <div class="text-[12.5px]">日志</div>
                    <div class="mt-0.5 break-all font-mono text-[9.5px] text-faint">{logPath()}</div>
                  </div>
                  <Button size="sm" variant="ghost" onClick={() => void revealPath(logPath())}>
                    在 Finder 显示
                  </Button>
                </div>
                <p class="mt-2 text-[10px] leading-5 text-faint">
                  后端日志、Pi 启动错误和 MCP 连接问题都在这里。任务失败时先看任务详情里的日志尾部。
                </p>
              </div>
            </Show>

            <Show when={tab() === "about"}>
              <h2 class="text-[14px] font-semibold">关于</h2>
              <p class="mt-1 text-[11.5px] text-faint">本机环境与存储位置。</p>
              <dl class="mt-4 grid grid-cols-[92px_1fr] gap-x-4 gap-y-2 text-[11.5px]">
                <dt class="text-faint">版本</dt>
                <dd class="font-mono">{version()}</dd>
                <dt class="text-faint">数据目录</dt>
                <dd class="break-all font-mono">{state()?.app_data ?? "—"}</dd>
                <dt class="text-faint">密钥存储</dt>
                <dd class="font-mono">
                  {state()?.keychain ? "macOS 钥匙串（0600 镜像供子进程读取）" : "加密文件（钥匙串不可用）"}
                </dd>
                <dt class="text-faint">合成运行时</dt>
                <dd class="font-mono">{runtimes()}</dd>
                <dt class="text-faint">能力</dt>
                <dd class="font-mono">{caps()}</dd>
                <dt class="text-faint">已配媒体 key</dt>
                <dd class="font-mono">{(state()?.keys ?? []).filter((k) => k.configured).length} 个</dd>
              </dl>
            </Show>
          </div>
        </main>
      </div>

      <ModuleDock active="settings" footer="本机设置" />

      <Show when={toast()}>
        {(message) => (
          <div
            class="fixed bottom-5 left-1/2 -translate-x-1/2 rounded-lg border border-line bg-surface px-3 py-2 text-[11.5px]"
            classList={{ "text-bad": message().error, "text-text": !message().error }}
          >
            {message().text}
          </div>
        )}
      </Show>
    </div>
  );
}
