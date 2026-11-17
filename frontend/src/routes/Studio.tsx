import { Match, Show, Switch, createEffect, createSignal, on, onCleanup, onMount } from "solid-js";
import { useNavigate, useParams } from "@solidjs/router";
import AppShellV2 from "../components/layout/AppShellV2";
import AssetsStage from "../components/production/AssetsStage";
import BriefRouteStage from "../components/production/BriefRouteStage";
import ScriptStage from "../components/production/ScriptStage";
import StageInspector from "../components/production/StageInspector";
import StageRail from "../components/production/StageRail";
import ProjectOverview from "../components/projects/ProjectOverview";
import CanvasTab from "../components/studio/CanvasTab";
import ExportDialog from "../components/studio/ExportDialog";
import Dialog from "../components/ui/Dialog";
import PlanWorkspace from "../components/studio/PlanWorkspace";
import ReviewTab from "../components/studio/ReviewTab";
import StoryboardTab from "../components/studio/StoryboardTab";
import Badge from "../components/ui/Badge";
import Button from "../components/ui/Button";
import Icon from "../components/ui/Icon";
import { endpoints } from "../lib/api";
import { moveShot, recomputeTimeline, totalDuration } from "../lib/storyboard";
import { refreshProjects } from "../stores/projects";
import type { Job, ProductionView, ProjectDetail, StageId, Version } from "../lib/types";

const ALIASES: Record<string, StageId> = {
  plan: "proposal",
  proposal: "proposal",
  canvas: "compose",
  compose: "compose",
  storyboard: "scene",
  scene: "scene",
  brief: "brief",
  script: "script",
  assets: "assets",
  review: "review",
};


export default function Studio() {
  const params = useParams();
  const navigate = useNavigate();
  const [detail, setDetail] = createSignal<ProjectDetail | null>(null);
  const [production, setProduction] = createSignal<ProductionView | null>(null);
  const [selectedId, setSelectedId] = createSignal<string | null>(null);
  const [loading, setLoading] = createSignal(true);
  const [busy, setBusy] = createSignal(false);
  const [error, setError] = createSignal("");
  const [overview, setOverview] = createSignal(false);
  const [exportOpen, setExportOpen] = createSignal(false);
  const [notice, setNotice] = createSignal("");
  const [actionBusy, setActionBusy] = createSignal(false);
  const [composeJob, setComposeJob] = createSignal<Job | null>(null);
  const [inspectorOpen, setInspectorOpen] = createSignal(false);

  let noticeTimer: ReturnType<typeof setTimeout> | undefined;
  let composeTimer: ReturnType<typeof setTimeout> | undefined;

  const projectId = () => params.projectId ?? "";
  const project = () => detail()?.project;
  const current = (): Version | null => detail()?.current_version ?? null;

  const normalize = (value?: string): StageId | null => (value ? ALIASES[value] ?? null : null);
  const stage = (): StageId => {
    const requested = normalize(params.tab);
    const prod = production();
    if (!prod) return requested ?? "brief";
    if (!requested) return prod.current_stage;
    const row = prod.stages.find((item) => item.id === requested);
    return row?.status === "locked" ? prod.current_stage : requested;
  };
  const stageRow = () => production()?.stages.find((item) => item.id === stage()) ?? null;

  const showNotice = (text: string) => {
    setNotice(text);
    if (noticeTimer) clearTimeout(noticeTimer);
    noticeTimer = setTimeout(() => setNotice(""), 3500);
  };

  const applyDetail = (data: ProjectDetail) => {
    setDetail(data);
    const shots = data.current_version?.shots ?? [];
    setSelectedId((previous) => (previous && shots.some((shot) => shot.id === previous) ? previous : shots[0]?.id ?? null));
  };

  const applyVersion = (version: Version) => {
    setDetail((previous) => {
      if (!previous) return previous;
      const versions = previous.versions.map((item) =>
        item.id === version.id
          ? {
              ...item,
              status: version.status,
              shots_count: version.shots.length,
              duration_s: version.duration_s,
              cost_usd: version.cost_usd,
              render: version.render,
            }
          : item,
      );
      return {
        ...previous,
        project: { ...previous.project, current_version_id: version.id },
        current_version: version,
        versions,
      };
    });
    setSelectedId((previous) => (previous && version.shots.some((shot) => shot.id === previous) ? previous : version.shots[0]?.id ?? null));
  };

  const load = async (silent = false) => {
    const id = params.projectId;
    if (!id) {
      setLoading(false);
      return;
    }
    if (!silent) setLoading(true);
    setError("");
    try {
      const prod = await endpoints.production(id);
      setProduction(prod);
      const data = await endpoints.project(id);
      applyDetail(data);
      const requested = normalize(params.tab);
      const target = requested ?? prod.current_stage;
      const row = prod.stages.find((item) => item.id === target);
      if (!requested || params.tab !== target || row?.status === "locked") {
        navigate(`/studio/${id}/${target}`, { replace: true });
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "项目加载失败");
    } finally {
      if (!silent) setLoading(false);
    }
  };

  createEffect(
    on(
      () => params.projectId,
      () => {
        void load();
      },
    ),
  );

  onMount(() => {
    if (!params.projectId) navigate("/projects");
    void refreshProjects();
  });

  onCleanup(() => {
    if (noticeTimer) clearTimeout(noticeTimer);
    if (composeTimer) clearTimeout(composeTimer);
  });

  const goStage = (next: StageId) => {
    if (!projectId()) return;
    navigate(`/studio/${projectId()}/${next}`);
  };

  const advance = (next: StageId) => {
    goStage(next);
    void load(true);
  };

  const mutate = async (work: () => Promise<void>) => {
    if (busy()) return;
    setBusy(true);
    try {
      await work();
    } catch (err) {
      showNotice(err instanceof Error ? err.message : "保存失败");
      await load(true);
    } finally {
      setBusy(false);
    }
  };

  const reorder = (fromId: string, toId: string, after: boolean) => {
    const version = current();
    if (!version || busy()) return;
    const moved = moveShot(version.shots, fromId, toId, after);
    if (moved === version.shots) return;
    const optimistic = recomputeTimeline(moved);
    applyVersion({ ...version, shots: optimistic, duration_s: totalDuration(optimistic), shots_count: optimistic.length });
    void mutate(async () => {
      const result = await endpoints.reorderShots(projectId(), version.id, optimistic.map((shot) => shot.id));
      applyVersion(result.version);
    });
  };

  const addShot = (afterId: string | null) => {
    const version = current();
    if (!version) {
      showNotice("还没有分镜版本；请稍后重试或从项目重新进入。");
      return;
    }
    const before = new Set(version.shots.map((shot) => shot.id));
    void mutate(async () => {
      const result = await endpoints.addShot(projectId(), version.id, {
        after_id: afterId ?? undefined,
        role: "build",
        description: "",
        duration_s: 2.5,
      });
      applyVersion(result.version);
      const added = result.version.shots.find((shot) => !before.has(shot.id));
      if (added) setSelectedId(added.id);
    });
  };

  const deleteShot = (shotId: string) => {
    const version = current();
    if (!version) return;
    void mutate(async () => {
      const result = await endpoints.deleteShot(projectId(), version.id, shotId);
      applyVersion(result.version);
    });
  };

  const updateShot = (shotId: string, fields: Record<string, unknown>) => {
    const version = current();
    if (!version) return;
    void mutate(async () => {
      const result = await endpoints.updateShot(projectId(), version.id, shotId, fields);
      applyVersion(result.version);
    });
  };

  const approveScene = async () => {
    setActionBusy(true);
    try {
      await endpoints.approveStage(projectId(), "scene");
      await load(true);
      advance("assets");
    } catch (err) {
      showNotice(err instanceof Error ? err.message : "确认分镜失败");
    } finally {
      setActionBusy(false);
    }
  };

  const pollCompose = async (jobId: string) => {
    try {
      const data = await endpoints.jobs(projectId());
      const job = data.jobs.find((item) => item.id === jobId) ?? null;
      setComposeJob(job);
      if (job && (job.status === "running" || job.status === "queued")) {
        composeTimer = setTimeout(() => void pollCompose(jobId), 1600);
        return;
      }
      await load(true);
      if (job?.status === "done") showNotice("成片已生成");
      else if (job?.status === "failed") showNotice(job.error || "渲染失败");
      setComposeJob(null);
    } catch {
      composeTimer = setTimeout(() => void pollCompose(jobId), 2400);
    }
  };

  const startCompose = async () => {
    setActionBusy(true);
    try {
      const result = await endpoints.compose(projectId());
      if (!result.job_id) throw new Error("没有创建渲染任务");
      showNotice("已开始生成本地动效成片");
      await pollCompose(result.job_id);
    } catch (err) {
      showNotice(err instanceof Error ? err.message : "启动渲染失败");
    } finally {
      setActionBusy(false);
    }
  };

  const approveCompose = async () => {
    setActionBusy(true);
    try {
      await endpoints.approveStage(projectId(), "compose");
      await load(true);
      advance("review");
    } catch (err) {
      showNotice(err instanceof Error ? err.message : "确认成片失败");
    } finally {
      setActionBusy(false);
    }
  };

  const deleteProject = async (id: string) => {
    if (!window.confirm("删除这个项目？可在项目页撤销。")) return;
    try {
      await endpoints.deleteProject(id);
      await refreshProjects();
      navigate("/projects");
    } catch (err) {
      showNotice(err instanceof Error ? err.message : "删除失败");
    }
  };

  const reviewApproved = () => Boolean(production()?.review?.status === "approved" || project()?.status === "delivered");

  const showActionBar = () => ["scene", "compose", "review"].includes(stage());

  return (
    <AppShellV2
      module="projects"
      context={
        <div class="flex min-w-0 items-center gap-2">
          <button type="button" class="grid h-7 w-7 place-items-center rounded-md text-faint hover:bg-surface-2 hover:text-text" title="返回项目" onClick={() => navigate("/projects")}>
            <Icon name="arrow-left" size={15} />
          </button>
          <button type="button" class="flex min-w-0 items-center gap-2 rounded-md px-1 py-1 text-left hover:bg-surface-2" onClick={() => setOverview(true)}>
            <span class="h-4 w-4 shrink-0 rounded bg-gradient-to-br from-violet to-accent" />
            <span class="max-w-[200px] truncate text-[12.5px] font-medium text-text">{project()?.title ?? "制作"}</span>
          </button>
          <Show when={stageRow()}>
            <Badge tone={stageRow()!.status === "approved" ? "ok" : stageRow()!.status === "review" ? "warn" : "accent"}>{stageRow()!.short}</Badge>
          </Show>
          <Show when={production()}>
            <span class="hidden items-center gap-1 rounded border border-line px-1.5 py-0.5 text-[9.5px] text-faint sm:flex">
              <Icon name="route" size={10} />
              {production()!.route.label}
            </span>
          </Show>
        </div>
      }
      primary={
        <div class="flex items-center gap-1.5">
          <span class="hidden text-[10px] text-faint sm:inline">
            预算 ${Number(production()?.budget_usd ?? 0).toFixed(2)} · 已花 ${Number(production()?.spent_usd ?? 0).toFixed(2)}
          </span>
          <Button size="sm" variant="ghost" onClick={() => setOverview(true)}>
            总览
          </Button>
        </div>
      }
      footer={<span class="text-[10px] text-faint">{stageRow()?.action ?? "制作"}</span>}
    >
      <Show when={!loading()} fallback={<div class="grid h-full place-items-center text-[11px] text-faint">加载中…</div>}>
        <Show
          when={detail() && production()}
          fallback={
            <div class="grid h-full place-items-center">
              <div class="text-center">
                <div class="text-[12px] text-dim">{error() || "项目不存在"}</div>
                <div class="mt-3 flex justify-center gap-2">
                  <Button size="sm" onClick={() => void load()}>重试</Button>
                  <Button size="sm" variant="ghost" onClick={() => navigate("/projects")}>回到项目</Button>
                </div>
              </div>
            </div>
          }
        >
          <div class="flex h-full flex-col">
            <div class="min-h-0 flex-1 overflow-auto p-3 xl:overflow-hidden">
              <div class="mx-auto flex h-full max-w-[1440px] flex-col gap-3 xl:flex-row">
                <div class="shrink-0">
                  <StageRail stages={production()!.stages} current={stage()} onSelect={goStage} />
                </div>

                <main class="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden rounded-xl border border-line-soft bg-surface">
                  <div class="flex h-9 shrink-0 items-center gap-2 border-b border-line-soft px-3">
                    <span class="text-[11px] font-medium text-text">{stageRow()?.label}</span>
                    <span class="truncate text-[10px] text-faint">{stageRow()?.summary}</span>
                    <Show when={busy()}><span class="text-[9.5px] text-faint">保存中…</span></Show>
                    <div class="ml-auto flex items-center gap-1.5">
                      <button
                        type="button"
                        class="rounded border border-line px-1.5 py-0.5 text-[10px] text-dim hover:bg-surface-2 hover:text-text xl:hidden"
                        onClick={() => setInspectorOpen(true)}
                      >
                        详情
                      </button>
                      <Show when={production()?.quote?.status === "pending"}>
                        <Badge tone="warn">报价待确认</Badge>
                      </Show>
                      <Show when={(detail()?.pending?.length ?? 0) > 0}>
                        <Badge tone="warn">{detail()!.pending.length} 待办</Badge>
                      </Show>
                    </div>
                  </div>

                  <div class="min-h-0 flex-1 overflow-hidden">
                    <Switch>
                      <Match when={stage() === "brief"}>
                        <BriefRouteStage production={production()!} onChanged={() => void load(true)} onAdvanced={advance} />
                      </Match>
                      <Match when={stage() === "proposal"}>
                        <PlanWorkspace projectId={projectId()} route={production()?.route} onChanged={() => void load(true)} onGoNext={() => advance("script")} />
                      </Match>
                      <Match when={stage() === "script"}>
                        <ScriptStage production={production()!} onChanged={() => void load(true)} onAdvanced={advance} />
                      </Match>
                      <Match when={stage() === "scene"}>
                        <div class="h-full overflow-auto p-4">
                          <Show
                            when={current()}
                            fallback={
                              <div class="rounded-xl border border-dashed border-line bg-surface/40 py-16 text-center">
                                <div class="text-[12px] text-dim">还没有分镜版本</div>
                                <div class="mt-1 text-[10.5px] text-faint">从项目重新进入后会创建版本。</div>
                                <Button class="mt-3" size="sm" onClick={() => void load()}>刷新</Button>
                              </div>
                            }
                          >
                            <StoryboardTab
                              version={current()!}
                              selectedId={selectedId()}
                              busy={busy()}
                              onSelect={setSelectedId}
                              onReorder={reorder}
                              onAdd={addShot}
                              onDelete={deleteShot}
                              onUpdate={updateShot}
                            />
                          </Show>
                        </div>
                      </Match>
                      <Match when={stage() === "assets"}>
                        <AssetsStage production={production()!} onChanged={() => void load(true)} onAdvanced={advance} />
                      </Match>
                      <Match when={stage() === "compose"}>
                        <div class="h-full overflow-auto p-4">
                          <CanvasTab version={current()} selectedId={selectedId()} onSelect={setSelectedId} />
                        </div>
                      </Match>
                      <Match when={stage() === "review"}>
                        <div class="h-full overflow-auto p-4">
                          <ReviewTab
                            projectId={projectId()}
                            version={current()}
                            onChanged={() => {
                              void load(true);
                              void refreshProjects();
                            }}
                            onExport={() => setExportOpen(true)}
                          />
                        </div>
                      </Match>
                    </Switch>
                  </div>

                  <Show when={showActionBar()}>
                    <div class="flex shrink-0 items-center gap-2 border-t border-line-soft px-3 py-2">
                      <span class="text-[10px] text-faint">
                        {stage() === "scene"
                          ? `${current()?.shots.length ?? 0} 镜 · ${current()?.duration_s ?? 0}s`
                          : stage() === "compose"
                            ? current()?.render?.path ? "已有成片" : "等待渲染"
                            : production()?.next_action}
                      </span>
                      <div class="ml-auto flex items-center gap-1.5">
                        <Show when={stage() === "scene"}>
                          <Button size="sm" variant="primary" loading={actionBusy()} disabled={!current()?.shots.length} onClick={() => void approveScene()}>
                            确认分镜，准备素材
                          </Button>
                        </Show>
                        <Show when={stage() === "compose"}>
                          <Show
                            when={current()?.render?.path}
                            fallback={
                              <Show
                                when={production()?.route.id === "local_motion"}
                                fallback={
                                  <Show
                                    when={(production()?.shots ?? []).every((shot) => Boolean(shot.preview))}
                                    fallback={
                                      <>
                                        <span class="text-[10px] text-faint">
                                          还有镜头没有素材，先在「素材」完成 {production()?.shots.length ?? 0} 个镜头
                                        </span>
                                        <Button size="sm" variant="secondary" onClick={() => advance("assets")}>
                                          回到素材
                                        </Button>
                                      </>
                                    }
                                  >
                                    <Show when={composeJob()}>
                                      <span class="font-mono text-[9.5px] text-faint">
                                        {composeJob()!.status} · {Math.round(Number(composeJob()!.progress || 0) * 100)}%
                                      </span>
                                    </Show>
                                    <Button size="sm" variant="primary" loading={actionBusy() || !!composeJob()} onClick={() => void startCompose()}>
                                      {composeJob() ? "合成中…" : "合成数字人成片"}
                                    </Button>
                                  </Show>
                                }
                              >
                                <Show when={composeJob()}>
                                  <span class="font-mono text-[9.5px] text-faint">
                                    {composeJob()!.status} · {Math.round(Number(composeJob()!.progress || 0) * 100)}%
                                  </span>
                                </Show>
                                <Button size="sm" variant="primary" loading={actionBusy() || !!composeJob()} onClick={() => void startCompose()}>
                                  {composeJob() ? "渲染中…" : "生成本地动效成片"}
                                </Button>
                              </Show>
                            }
                          >
                            <Button
                              size="sm"
                              variant="primary"
                              loading={actionBusy()}
                              disabled={production()?.approvals?.compose != null}
                              onClick={() => void approveCompose()}
                            >
                              确认成片，去审片
                            </Button>
                          </Show>
                        </Show>
                        <Show when={stage() === "review"}>
                          <Button size="sm" variant="primary" disabled={!reviewApproved()} onClick={() => setExportOpen(true)}>
                            导出交付
                          </Button>
                        </Show>
                      </div>
                    </div>
                  </Show>
                </main>

                <div class="hidden w-[280px] shrink-0 xl:block">
                  <StageInspector production={production()!} stage={stageRow()!} />
                </div>
              </div>
            </div>
          </div>

          <ProjectOverview
            projectId={overview() ? projectId() : null}
            onClose={() => setOverview(false)}
            onChanged={() => {
              void load(true);
              void refreshProjects();
            }}
            onDelete={(id) => void deleteProject(id)}
          />

          <ExportDialog
            open={exportOpen()}
            projectId={projectId()}
            version={current()}
            onClose={() => setExportOpen(false)}
            onExported={() => {
              void load(true);
              void refreshProjects();
            }}
          />

          <Dialog open={inspectorOpen()} onOpenChange={setInspectorOpen} title="阶段详情">
            <Show when={production() && stageRow()}>
              <StageInspector production={production()!} stage={stageRow()!} />
            </Show>
          </Dialog>

          <Show when={notice()}>
            <div class="fixed bottom-12 left-1/2 z-50 -translate-x-1/2 rounded-lg border border-line bg-surface-2 px-3 py-2 text-[11px] text-text shadow-2xl">
              {notice()}
            </div>
          </Show>
        </Show>
      </Show>
    </AppShellV2>
  );
}
