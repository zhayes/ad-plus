import { For, Show, createMemo, createSignal, onCleanup, onMount } from "solid-js";
import AppShellV2 from "../components/layout/AppShellV2";
import Badge from "../components/ui/Badge";
import Button from "../components/ui/Button";
import Select from "../components/ui/Select";
import { endpoints } from "../lib/api";
import { fmtUsd } from "../lib/format";
import { projects, refreshProjects } from "../stores/projects";
import type { AppConfig, Job } from "../lib/types";

type Filter = "all" | "running" | "failed";

const TABS: { value: Filter; label: string }[] = [
  { value: "all", label: "全部" },
  { value: "running", label: "进行中" },
  { value: "failed", label: "失败" },
];

const STATUS: Record<string, { label: string; tone: "neutral" | "ok" | "warn" | "bad" | "accent" }> = {
  queued: { label: "排队中", tone: "neutral" },
  running: { label: "运行中", tone: "accent" },
  done: { label: "完成", tone: "ok" },
  failed: { label: "失败", tone: "bad" },
  interrupted: { label: "已中断", tone: "warn" },
  cancelled: { label: "已取消", tone: "neutral" },
};

const KIND: Record<string, string> = {
  render: "渲染",
  preview: "预览",
  tool: "工具",
};

export default function Tasks() {
  const [jobs, setJobs] = createSignal<Job[]>([]);
  const [config, setConfig] = createSignal<AppConfig | null>(null);
  const [loading, setLoading] = createSignal(true);
  const [error, setError] = createSignal("");
  const [filter, setFilter] = createSignal<Filter>("all");
  const [projectFilter, setProjectFilter] = createSignal("all");
  const [expanded, setExpanded] = createSignal<string | null>(null);
  const [busy, setBusy] = createSignal<string | null>(null);
  const [notice, setNotice] = createSignal("");

  let timer: ReturnType<typeof setTimeout> | undefined;
  let noticeTimer: ReturnType<typeof setTimeout> | undefined;

  const showNotice = (text: string) => {
    setNotice(text);
    if (noticeTimer) clearTimeout(noticeTimer);
    noticeTimer = setTimeout(() => setNotice(""), 3500);
  };

  const load = async (silent = false) => {
    if (!silent) setLoading(true);
    setError("");
    try {
      const pid = projectFilter() === "all" ? undefined : projectFilter();
      const [data, cfg] = await Promise.all([endpoints.jobs(pid), endpoints.config().catch(() => null)]);
      setJobs(data.jobs ?? []);
      if (cfg) setConfig(cfg);
    } catch (err) {
      setError(err instanceof Error ? err.message : "任务加载失败");
    } finally {
      if (!silent) setLoading(false);
    }
  };

  const schedule = () => {
    if (timer) clearTimeout(timer);
    const running = jobs().some((job) => job.status === "running" || job.status === "queued");
    timer = setTimeout(async () => {
      await load(true);
      schedule();
    }, running ? 1500 : 5000);
  };

  onMount(async () => {
    void refreshProjects();
    await load();
    schedule();
  });

  onCleanup(() => {
    if (timer) clearTimeout(timer);
    if (noticeTimer) clearTimeout(noticeTimer);
  });

  const projectOptions = () => [
    { value: "all", label: "全部项目" },
    ...projects().map((project) => ({ value: project.id, label: project.title })),
  ];

  const filtered = createMemo(() => {
    const rows = jobs();
    if (filter() === "running") return rows.filter((job) => job.status === "running" || job.status === "queued");
    if (filter() === "failed") return rows.filter((job) => job.status === "failed" || job.status === "interrupted");
    return rows;
  });

  const count = (value: Filter): number => {
    if (value === "running") return jobs().filter((job) => job.status === "running" || job.status === "queued").length;
    if (value === "failed") return jobs().filter((job) => job.status === "failed" || job.status === "interrupted").length;
    return jobs().length;
  };

  const today = () => new Date().toISOString().slice(0, 10);
  const todayJobs = () => jobs().filter((job) => String(job.started_at || "").slice(0, 10) === today());
  const costToday = () => todayJobs().reduce((sum, job) => sum + Number(job.cost_usd || 0), 0);
  const budget = () => Number(config()?.daily_budget_usd ?? 2);
  const remaining = () => Math.max(0, budget() - costToday());

  const retry = async (job: Job) => {
    setBusy(job.id);
    try {
      await endpoints.retryJob(job.id, job.project_id);
      showNotice("已排队，等待 agent 接单");
      await load(true);
    } catch (err) {
      showNotice(err instanceof Error ? err.message : "重试失败");
    } finally {
      setBusy(null);
    }
  };

  const cancel = async (job: Job) => {
    setBusy(job.id);
    try {
      await endpoints.cancelJob(job.id, job.project_id);
      showNotice("已请求取消");
      await load(true);
    } catch (err) {
      showNotice(err instanceof Error ? err.message : "取消失败");
    } finally {
      setBusy(null);
    }
  };

  const reveal = async (path?: string | null) => {
    if (!path) return;
    try {
      await endpoints.reveal(path);
    } catch (err) {
      showNotice(err instanceof Error ? err.message : "无法打开 Finder");
    }
  };

  const copy = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      showNotice("已复制");
    } catch {
      showNotice("复制失败");
    }
  };

  const time = (job: Job) => {
    if (job.elapsed_seconds) return `${Math.round(job.elapsed_seconds)}s`;
    if (job.started_at && job.finished_at) {
      const seconds = (Date.parse(job.finished_at) - Date.parse(job.started_at)) / 1000;
      if (Number.isFinite(seconds) && seconds > 0) return `${Math.round(seconds)}s`;
    }
    return job.started_at?.slice(11, 16) ?? "—";
  };

  return (
    <AppShellV2
      module="tasks"
      context={
        <div class="flex items-center gap-2">
          <span class="text-[13px] font-semibold text-text">任务</span>
          <span class="rounded border border-line px-1 py-px font-mono text-[10px] text-faint">{jobs().length}</span>
        </div>
      }
      subTabs={
        <div class="flex items-center gap-0.5 rounded-lg border border-line-soft bg-surface p-0.5">
          <For each={TABS}>
            {(tab) => (
              <button
                type="button"
                class={`flex h-6 items-center gap-1 rounded-md px-2.5 text-[11px] transition-colors ${
                  filter() === tab.value ? "bg-surface-2 text-text" : "text-faint hover:text-text"
                }`}
                onClick={() => setFilter(tab.value)}
              >
                {tab.label}
                <span class="font-mono text-[9.5px] text-faint">{count(tab.value)}</span>
              </button>
            )}
          </For>
        </div>
      }
      footer={<span class="text-[10px] text-faint">{jobs().some((job) => job.status === "running") ? "实时刷新" : "5s 刷新"}</span>}
    >
      <div class="h-full overflow-auto px-5 py-4">
        <div class="mb-3 grid grid-cols-2 gap-2 lg:grid-cols-4">
          <div class="rounded-lg border border-line-soft bg-surface px-3 py-2">
            <div class="text-[10px] text-faint">进行中</div>
            <div class="mt-1 text-[17px] font-semibold text-text">{count("running")}</div>
          </div>
          <div class="rounded-lg border border-line-soft bg-surface px-3 py-2">
            <div class="text-[10px] text-faint">失败 / 中断</div>
            <div class="mt-1 text-[17px] font-semibold text-bad">{count("failed")}</div>
          </div>
          <div class="rounded-lg border border-line-soft bg-surface px-3 py-2">
            <div class="text-[10px] text-faint">今日已花</div>
            <div class="mt-1 text-[17px] font-semibold text-text">${costToday().toFixed(2)}</div>
          </div>
          <div class="rounded-lg border border-line-soft bg-surface px-3 py-2">
            <div class="text-[10px] text-faint">预算 · 剩余</div>
            <div class="mt-1 text-[17px] font-semibold text-text">
              ${budget().toFixed(2)} <span class="text-[11px] font-normal text-faint">· ${remaining().toFixed(2)}</span>
            </div>
          </div>
        </div>

        <div class="mb-3 flex flex-wrap items-center gap-2">
          <Select value={projectFilter()} options={projectOptions()} onChange={(value) => { setProjectFilter(value); void load(); }} variant="pill" />
          <button type="button" class="text-[10.5px] text-faint underline hover:text-text" onClick={() => void load()}>
            刷新
          </button>
          <div class="ml-auto text-[10.5px] text-faint">{filtered().length} / {jobs().length}</div>
        </div>

        <Show when={error()}>
          <div class="mb-3 flex items-center gap-2 rounded-lg border border-bad/30 bg-bad/5 px-3 py-2 text-[11px] text-bad">
            <span class="min-w-0 flex-1 truncate">{error()}</span>
            <button type="button" class="text-[10.5px] underline" onClick={() => void load()}>
              重试
            </button>
          </div>
        </Show>

        <Show when={!loading()} fallback={<div class="py-12 text-center text-[11px] text-faint">任务加载中…</div>}>
          <Show
            when={filtered().length > 0}
            fallback={
              <div class="grid place-items-center rounded-xl border border-dashed border-line bg-surface/40 py-16">
                <div class="text-center">
                  <div class="text-[12px] text-dim">没有任务</div>
                  <p class="mt-1 text-[10.5px] text-faint">生成、预览、工具调用会出现在这里。</p>
                </div>
              </div>
            }
          >
            <div class="space-y-1.5">
              <For each={filtered()}>
                {(job) => {
                  const state = STATUS[job.status] ?? { label: job.status, tone: "neutral" as const };
                  const progress = Math.max(0, Math.min(100, Math.round(Number(job.progress || 0) * 100)));
                  const open = () => expanded() === job.id;
                  const canExpand = job.status !== "running" && job.status !== "queued";
                  return (
                    <div class={`rounded-lg border bg-surface ${job.status === "failed" || job.status === "interrupted" ? "border-bad/25" : "border-line-soft"}`}>
                      <div class="flex items-center gap-2 px-3 py-2">
                        <button
                          type="button"
                          class="flex min-w-0 flex-1 items-center gap-2 text-left"
                          onClick={() => canExpand && setExpanded(open() ? null : job.id)}
                        >
                          <Badge tone={state.tone}>{state.label}</Badge>
                          <span class="w-[66px] shrink-0 text-[10.5px] text-dim">{KIND[job.kind] ?? job.kind}</span>
                          <span class="min-w-0 flex-1 truncate text-[10.5px] text-faint">{job.project_id}</span>
                          <Show when={job.status === "running"}>
                            <div class="h-1 w-[120px] overflow-hidden rounded-full bg-surface-2">
                              <div class="h-full rounded-full bg-accent" style={{ width: `${progress}%` }} />
                            </div>
                            <span class="w-[34px] text-right font-mono text-[9.5px] text-faint">{progress}%</span>
                          </Show>
                          <Show when={job.status !== "running"}>
                            <span class="w-[54px] text-right text-[9.5px] text-faint">{time(job)}</span>
                          </Show>
                          <span class="w-[46px] text-right font-mono text-[9.5px] text-faint">
                            {(job.cost_usd ?? 0) > 0 ? fmtUsd(job.cost_usd) : "—"}
                          </span>
                          <Show when={canExpand}>
                            <span class="w-3 text-[10px] text-faint">{open() ? "▴" : "▾"}</span>
                          </Show>
                        </button>

                        <Show when={job.status === "running"}>
                          <Button size="sm" variant="ghost" loading={busy() === job.id} onClick={() => void cancel(job)}>
                            取消
                          </Button>
                        </Show>
                        <Show when={job.status === "failed" || job.status === "interrupted"}>
                          <Button size="sm" loading={busy() === job.id} onClick={() => void retry(job)}>
                            重试
                          </Button>
                        </Show>
                        <Show when={job.status === "done"}>
                          <Button size="sm" variant="ghost" onClick={() => void reveal(job.output)}>
                            打开
                          </Button>
                        </Show>
                      </div>

                      <Show when={open()}>
                        <div class="space-y-2 border-t border-line-soft px-3 py-2">
                          <Show when={job.error}>
                            <div class="rounded border border-bad/25 bg-bad/5 px-2 py-1.5 text-[10.5px] text-bad">
                              {job.error}
                            </div>
                          </Show>
                          <Show when={job.output}>
                            <div class="flex items-center gap-2 text-[10px] text-faint">
                              <span class="min-w-0 flex-1 truncate font-mono">{job.output}</span>
                              <button type="button" class="underline hover:text-text" onClick={() => void copy(String(job.output))}>
                                复制
                              </button>
                              <button type="button" class="underline hover:text-text" onClick={() => void reveal(job.output)}>
                                Finder
                              </button>
                            </div>
                          </Show>
                          <div>
                            <div class="mb-1 flex items-center gap-2">
                              <span class="text-[9.5px] text-faint">日志尾部</span>
                              <button type="button" class="ml-auto text-[9.5px] text-faint underline hover:text-text" onClick={() => void copy((job.log_tail ?? []).join("\n"))}>
                                复制日志
                              </button>
                            </div>
                            <pre class="max-h-[160px] overflow-auto rounded border border-line-soft bg-[#0b0e13] p-2 font-mono text-[9px] leading-4 text-dim">
                              {(job.log_tail ?? []).length > 0 ? (job.log_tail ?? []).slice(-40).join("\n") : "（没有日志）"}
                            </pre>
                          </div>
                          <Show when={job.retry_of}>
                            <div class="text-[9.5px] text-faint">重试自 {job.retry_of}</div>
                          </Show>
                        </div>
                      </Show>
                    </div>
                  );
                }}
              </For>
            </div>
          </Show>
        </Show>
      </div>

      <Show when={notice()}>
        <div class="fixed bottom-12 left-1/2 z-50 -translate-x-1/2 rounded-lg border border-line bg-surface-2 px-3 py-2 text-[11px] text-text shadow-2xl">
          {notice()}
        </div>
      </Show>
    </AppShellV2>
  );
}
