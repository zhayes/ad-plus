import { Show, createEffect, createMemo, createSignal, on, onCleanup, onMount } from "solid-js";
import { For } from "solid-js";
import { useNavigate } from "@solidjs/router";
import Badge from "../ui/Badge";
import Button from "../ui/Button";
import Input from "../ui/Input";
import { endpoints } from "../../lib/api";
import { fmtUsd } from "../../lib/format";
import { platformLabel, statusInfo, tierLabel } from "../../lib/projects";
import type { ProjectDetail } from "../../lib/types";

const VERSION_STATUS: Record<string, { label: string; tone: "neutral" | "ok" | "warn" | "accent" }> = {
  draft: { label: "草稿", tone: "neutral" },
  producing: { label: "生成中", tone: "warn" },
  review: { label: "待审", tone: "warn" },
  approved: { label: "已通过", tone: "ok" },
  superseded: { label: "已替代", tone: "neutral" },
};

interface Props {
  projectId: string | null;
  onClose: () => void;
  onChanged: () => void;
  onDelete: (projectId: string) => void;
}

export default function ProjectOverview(props: Props) {
  const navigate = useNavigate();
  const [detail, setDetail] = createSignal<ProjectDetail | null>(null);
  const [loading, setLoading] = createSignal(false);
  const [error, setError] = createSignal("");
  const [editing, setEditing] = createSignal(false);
  const [titleDraft, setTitleDraft] = createSignal("");
  const [saving, setSaving] = createSignal(false);

  const project = () => detail()?.project;
  const brief = () => project()?.brief ?? {};
  const versions = () => detail()?.versions ?? [];
  const pending = () => detail()?.pending ?? [];
  const cost = createMemo(() => versions().reduce((sum, version) => sum + (version.cost_usd || 0), 0));

  const load = async () => {
    const id = props.projectId;
    if (!id) {
      setDetail(null);
      return;
    }
    setLoading(true);
    setError("");
    try {
      const data = await endpoints.project(id);
      setDetail(data);
      setTitleDraft(data.project.title);
    } catch (err) {
      setError(err instanceof Error ? err.message : "项目加载失败");
    } finally {
      setLoading(false);
    }
  };

  createEffect(
    on(
      () => props.projectId,
      () => {
        void load();
      },
    ),
  );

  onMount(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") props.onClose();
    };
    window.addEventListener("keydown", onKey);
    onCleanup(() => window.removeEventListener("keydown", onKey));
  });

  const saveTitle = async () => {
    const id = props.projectId;
    const next = titleDraft().trim();
    if (!id || !next || next === project()?.title) {
      setEditing(false);
      return;
    }
    setSaving(true);
    try {
      await endpoints.patchProject(id, { title: next });
      await load();
      props.onChanged();
      setEditing(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "改名失败");
    } finally {
      setSaving(false);
    }
  };

  const toggleArchive = async () => {
    const id = props.projectId;
    if (!id) return;
    const next = project()?.status === "archived" ? "draft" : "archived";
    try {
      await endpoints.patchProject(id, { status: next });
      await load();
      props.onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "归档失败");
    }
  };

  const reveal = async () => {
    const id = props.projectId;
    if (!id) return;
    try {
      await endpoints.reveal(`projects/${id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "无法打开 Finder");
    }
  };

  return (
    <Show when={props.projectId}>
      <div class="fixed inset-0 z-40" role="dialog" aria-modal="true">
        <div class="absolute inset-0 bg-black/30 sm:bg-transparent" onClick={props.onClose} />
        <aside class="absolute right-0 top-0 flex h-full w-[min(420px,calc(100vw-16px))] flex-col border-l border-line-soft bg-surface shadow-2xl">
          <div class="flex h-11 shrink-0 items-center gap-2 border-b border-line-soft px-3">
            <span class="text-[12px] font-semibold">项目总览</span>
            <div class="ml-auto">
              <button
                type="button"
                class="rounded-md px-2 py-1 text-[11px] text-faint hover:bg-surface-2 hover:text-text"
                onClick={props.onClose}
              >
                关闭
              </button>
            </div>
          </div>

          <div class="min-h-0 flex-1 space-y-3 overflow-auto p-3.5">
            <Show
              when={!loading()}
              fallback={<div class="py-10 text-center text-[11px] text-faint">加载中…</div>}
            >
              <Show
                when={project()}
                fallback={
                  <div class="space-y-2 py-8 text-center">
                    <div class="text-[11px] text-faint">{error() || "项目不存在"}</div>
                    <Button size="sm" onClick={() => void load()}>
                      重试
                    </Button>
                  </div>
                }
              >
                <div>
                  <Show
                    when={!editing()}
                    fallback={
                      <div class="flex items-center gap-2">
                        <Input
                          value={titleDraft()}
                          onInput={(event) => setTitleDraft(event.currentTarget.value)}
                          onKeyDown={(event) => {
                            if (event.key === "Enter") void saveTitle();
                            if (event.key === "Escape") setEditing(false);
                          }}
                        />
                        <Button size="sm" loading={saving()} onClick={() => void saveTitle()}>
                          保存
                        </Button>
                      </div>
                    }
                  >
                    <div class="flex items-start gap-2">
                      <h2 class="min-w-0 flex-1 text-[15px] font-semibold leading-6 text-text">
                        {project()?.title}
                      </h2>
                      <Button size="sm" variant="ghost" onClick={() => setEditing(true)}>
                        改名
                      </Button>
                    </div>
                  </Show>

                  <div class="mt-1.5 flex flex-wrap items-center gap-1.5">
                    <Badge tone={statusInfo(project()?.status ?? "draft").tone}>
                      {statusInfo(project()?.status ?? "draft").label}
                    </Badge>
                    <span class="text-[10.5px] text-faint">
                      {platformLabel(project()?.platform)} · {project()?.aspect} · {project()?.duration_s}s ·{" "}
                      {tierLabel(project()?.quality_tier)}
                    </span>
                  </div>
                </div>

                <div class="rounded-lg border border-line-soft bg-surface-2/30 p-3">
                  <div class="text-[10px] tracking-wide text-faint">简报</div>
                  <Show
                    when={brief().product || brief().description || brief().audience}
                    fallback={<div class="mt-1 text-[11px] leading-5 text-faint">还没填简报，制作页会引导你补全。</div>}
                  >
                    <Show when={brief().product}>
                      <div class="mt-1 text-[12px] text-text">{brief().product}</div>
                    </Show>
                    <Show when={brief().audience}>
                      <div class="mt-1 text-[10.5px] text-dim">给谁看：{brief().audience}</div>
                    </Show>
                    <Show when={brief().description}>
                      <div class="mt-1 text-[11px] leading-5 text-dim">{brief().description}</div>
                    </Show>
                  </Show>
                </div>

                <div class="rounded-lg border border-line-soft p-3">
                  <div class="flex items-center">
                    <span class="text-[10px] tracking-wide text-faint">版本</span>
                    <span class="ml-auto text-[10px] text-faint">{versions().length} 个</span>
                  </div>
                  <Show
                    when={versions().length > 0}
                    fallback={<div class="mt-1 text-[11px] text-faint">还没有版本，先做方案和分镜。</div>}
                  >
                    <div class="mt-1 divide-y divide-line-soft">
                      <For each={versions()}>
                        {(version) => {
                          const state = () => VERSION_STATUS[version.status] ?? { label: version.status, tone: "neutral" as const };
                          const current = () => project()?.current_version_id === version.id;
                          return (
                            <div class="flex items-center gap-2 py-1.5">
                              <span class={`text-[11px] ${current() ? "text-text" : "text-dim"}`}>{version.label}</span>
                              <Badge tone={state().tone}>{state().label}</Badge>
                              <Show when={current()}>
                                <span class="text-[9.5px] text-accent">当前</span>
                              </Show>
                              <span class="ml-auto text-[10px] text-faint">
                                {version.shots_count} 镜 · {version.duration_s}s
                              </span>
                            </div>
                          );
                        }}
                      </For>
                    </div>
                  </Show>
                </div>

                <div class="grid grid-cols-2 gap-2">
                  <div class="rounded-lg border border-line-soft p-3">
                    <div class="text-[10px] text-faint">待办</div>
                    <div class="mt-1 text-[15px] font-semibold">{pending().length}</div>
                    <Show when={pending().length > 0}>
                      <div class="mt-1 text-[10px] text-warn">
                        {pending()[0]?.kind === "quotes" ? "方案待确认" : pending()[0]?.stage || "审片待确认"}
                      </div>
                    </Show>
                  </div>
                  <div class="rounded-lg border border-line-soft p-3">
                    <div class="text-[10px] text-faint">已花</div>
                    <div class="mt-1 text-[15px] font-semibold">{cost() > 0 ? fmtUsd(cost()) : "—"}</div>
                    <div class="mt-1 text-[10px] text-faint">按版本累计</div>
                  </div>
                </div>

                <div class="flex flex-wrap items-center gap-1.5 border-t border-line-soft pt-3">
                  <Button
                    size="sm"
                    variant="primary"
                    onClick={() => {
                      props.onClose();
                      navigate(`/studio/${props.projectId}`);
                    }}
                  >
                    打开制作
                  </Button>
                  <Button size="sm" onClick={() => void toggleArchive()}>
                    {project()?.status === "archived" ? "取消归档" : "归档"}
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => void reveal()}>
                    在 Finder 显示
                  </Button>
                  <Button
                    size="sm"
                    variant="danger"
                    class="ml-auto"
                    onClick={() => {
                      if (props.projectId) props.onDelete(props.projectId);
                    }}
                  >
                    删除
                  </Button>
                </div>

                <Show when={error()}>
                  <div class="text-[10.5px] text-bad">{error()}</div>
                </Show>
              </Show>
            </Show>
          </div>
        </aside>
      </div>
    </Show>
  );
}
