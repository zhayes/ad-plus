import { For, Show, createMemo, createSignal, onCleanup, onMount } from "solid-js";
import { useNavigate } from "@solidjs/router";
import AppShellV2 from "../components/layout/AppShellV2";
import ProjectCard from "../components/projects/ProjectCard";
import ProjectTable from "../components/projects/ProjectTable";
import Icon from "../components/ui/Icon";
import NewProjectDialog from "../components/projects/NewProjectDialog";
import ProjectOverview from "../components/projects/ProjectOverview";
import Button from "../components/ui/Button";
import Input from "../components/ui/Input";
import Select from "../components/ui/Select";
import { endpoints } from "../lib/api";
import { platformLabel } from "../lib/projects";
import { error, loading, projects, refreshProjects } from "../stores/projects";

type Filter = "all" | "active" | "delivered";
type View = "cards" | "table";
type Sort = "updated" | "title";

const TABS: { value: Filter; label: string }[] = [
  { value: "all", label: "全部" },
  { value: "active", label: "进行中" },
  { value: "delivered", label: "已交付" },
];

const PLATFORMS = [
  { value: "all", label: "全部平台" },
  { value: "douyin", label: "抖音" },
  { value: "xiaohongshu", label: "小红书" },
  { value: "wechat_channels", label: "视频号" },
  { value: "shorts", label: "Shorts" },
  { value: "other", label: "其他" },
];

const SORTS = [
  { value: "updated", label: "最近更新" },
  { value: "title", label: "标题" },
];

interface Toast {
  text: string;
  trash?: string;
}

export default function Projects() {
  const navigate = useNavigate();
  const [filter, setFilter] = createSignal<Filter>("all");
  const [query, setQuery] = createSignal("");
  const [platform, setPlatform] = createSignal("all");
  const [sort, setSort] = createSignal<Sort>("updated");
  const [newOpen, setNewOpen] = createSignal(false);
  const [overviewId, setOverviewId] = createSignal<string | null>(null);
  const [menuId, setMenuId] = createSignal<string | null>(null);
  const [toast, setToast] = createSignal<Toast | null>(null);
  const [view, setView] = createSignal<View>((localStorage.getItem("adplus.projects.view") as View) || "cards");

  let toastTimer: ReturnType<typeof setTimeout> | undefined;

  const showToast = (text: string, trash?: string) => {
    setToast({ text, trash });
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(() => setToast(null), 8000);
  };

  const onNewProject = () => setNewOpen(true);

  const changeView = (next: View) => {
    setView(next);
    localStorage.setItem("adplus.projects.view", next);
  };

  onMount(() => {
    void refreshProjects();
    window.addEventListener("adplus-new-project", onNewProject);
  });

  onCleanup(() => {
    if (toastTimer) clearTimeout(toastTimer);
    window.removeEventListener("adplus-new-project", onNewProject);
  });

  const countFor = (value: Filter): number =>
    projects().filter((project) =>
      value === "all"
        ? true
        : value === "active"
          ? project.status !== "delivered" && project.status !== "archived"
          : project.status === "delivered",
    ).length;

  const filtered = createMemo(() => {
    const q = query().trim().toLowerCase();
    const rows = projects().filter((project) => {
      if (filter() === "active" && (project.status === "delivered" || project.status === "archived")) return false;
      if (filter() === "delivered" && project.status !== "delivered") return false;
      if (platform() !== "all" && project.platform !== platform()) return false;
      if (!q) return true;
      return (
        project.title.toLowerCase().includes(q) ||
        project.id.toLowerCase().includes(q) ||
        project.platform.toLowerCase().includes(q) ||
        platformLabel(project.platform).toLowerCase().includes(q)
      );
    });
    return rows.sort((a, b) =>
      sort() === "title" ? a.title.localeCompare(b.title, "zh") : b.updated - a.updated,
    );
  });

  const open = (id: string) => {
    setMenuId(null);
    navigate(`/studio/${id}`);
  };

  const archive = async (id: string) => {
    setMenuId(null);
    try {
      await endpoints.patchProject(id, { status: "archived" });
      await refreshProjects();
      showToast("已归档");
    } catch (err) {
      showToast(err instanceof Error ? err.message : "归档失败");
    }
  };

  const reveal = async (id: string) => {
    setMenuId(null);
    try {
      await endpoints.reveal(`projects/${id}`);
    } catch (err) {
      showToast(err instanceof Error ? err.message : "无法打开 Finder");
    }
  };

  const remove = async (id: string) => {
    setMenuId(null);
    try {
      const result = await endpoints.deleteProject(id);
      if (overviewId() === id) setOverviewId(null);
      await refreshProjects();
      showToast("已移到废纸篓", result.trash_id);
    } catch (err) {
      showToast(err instanceof Error ? err.message : "删除失败");
    }
  };

  const undo = async () => {
    const token = toast()?.trash;
    if (!token) return;
    try {
      await endpoints.restoreProject(token);
      await refreshProjects();
      showToast("已恢复");
    } catch (err) {
      showToast(err instanceof Error ? err.message : "恢复失败");
    }
  };

  return (
    <AppShellV2
      module="projects"
      context={
        <div class="flex items-center gap-2">
          <span class="text-[13px] font-semibold text-text">项目</span>
          <span class="rounded border border-line px-1 py-px font-mono text-[10px] text-faint">
            {projects().length}
          </span>
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
                <span class="font-mono text-[9.5px] text-faint">{countFor(tab.value)}</span>
              </button>
            )}
          </For>
        </div>
      }
      primary={
        <Button size="sm" variant="primary" onClick={() => setNewOpen(true)}>
          ＋ 新建项目
        </Button>
      }
      footer={<span class="text-[10px] text-faint">{projects().length} 个项目</span>}
    >
      <div class="h-full overflow-auto px-5 py-4">
        <div class="mb-3 flex flex-wrap items-center gap-2">
          <div class="w-[260px]">
            <Input
              value={query()}
              placeholder="搜索项目 / 产品 / 平台"
              onInput={(event) => setQuery(event.currentTarget.value)}
            />
          </div>
          <Select value={platform()} options={PLATFORMS} onChange={setPlatform} variant="pill" />
          <Select
            value={sort()}
            options={SORTS}
            onChange={(value) => setSort(value as Sort)}
            variant="pill"
          />
          <div class="ml-auto flex items-center gap-2">
            <span class="text-[10.5px] text-faint">{filtered().length} / {projects().length}</span>
            <div class="flex items-center rounded-md border border-line-soft bg-surface p-0.5">
              <button
                type="button"
                class={`grid h-6 w-6 place-items-center rounded ${view() === "cards" ? "bg-surface-2 text-text" : "text-faint hover:text-text"}`}
                title="卡片视图"
                onClick={() => changeView("cards")}
              >
                <Icon name="grid" size={13} />
              </button>
              <button
                type="button"
                class={`grid h-6 w-6 place-items-center rounded ${view() === "table" ? "bg-surface-2 text-text" : "text-faint hover:text-text"}`}
                title="表格视图"
                onClick={() => changeView("table")}
              >
                <Icon name="list" size={13} />
              </button>
            </div>
          </div>
        </div>

        <Show when={error()}>
          <div class="mb-3 flex items-center gap-2 rounded-lg border border-bad/30 bg-bad/5 px-3 py-2 text-[11px] text-bad">
            <span class="min-w-0 flex-1 truncate">{error()}</span>
            <button type="button" class="text-[10.5px] underline" onClick={() => void refreshProjects()}>
              重试
            </button>
          </div>
        </Show>

        <Show when={!loading() || projects().length > 0} fallback={<Skeleton />}>
          <Show
            when={projects().length > 0}
            fallback={
              <div class="grid place-items-center rounded-xl border border-dashed border-line bg-surface/40 py-20">
                <div class="max-w-[360px] text-center">
                  <div class="text-[13px] font-medium text-text">还没有项目</div>
                  <p class="mt-1.5 whitespace-nowrap text-[11px] leading-5 text-faint">
                    先确认简报、路线和报价，再开始制作。
                  </p>
                  <Button class="mt-3" size="sm" variant="primary" onClick={() => setNewOpen(true)}>
                    ＋ 新建第一个项目
                  </Button>
                </div>
              </div>
            }
          >
            <Show
              when={filtered().length > 0}
              fallback={
                <div class="grid place-items-center rounded-xl border border-dashed border-line bg-surface/30 py-16">
                  <div class="text-center">
                    <div class="text-[12px] text-dim">没有匹配的项目</div>
                    <button
                      type="button"
                      class="mt-2 text-[10.5px] text-faint underline hover:text-text"
                      onClick={() => {
                        setQuery("");
                        setPlatform("all");
                        setFilter("all");
                      }}
                    >
                      清除筛选
                    </button>
                  </div>
                </div>
              }
            >
              <Show
                when={view() === "cards"}
                fallback={
                  <ProjectTable
                    projects={filtered()}
                    onOpen={open}
                    onOverview={(id) => setOverviewId(id)}
                  />
                }
              >
              <div class="grid gap-3.5 pb-6" style={{ "grid-template-columns": "repeat(auto-fill, minmax(300px, 1fr))" }}>
                <For each={filtered()}>
                  {(project) => (
                    <ProjectCard
                      project={project}
                      menuOpen={menuId() === project.id}
                      onOpen={() => open(project.id)}
                      onOverview={() => {
                        setMenuId(null);
                        setOverviewId(project.id);
                      }}
                      onReveal={() => void reveal(project.id)}
                      onArchive={() => void archive(project.id)}
                      onDelete={() => void remove(project.id)}
                      onToggleMenu={() => setMenuId(menuId() === project.id ? null : project.id)}
                    />
                  )}
                </For>
              </div>
              </Show>
            </Show>
          </Show>
        </Show>
      </div>

      <Show when={menuId()}>
        <div class="fixed inset-0 z-10" onClick={() => setMenuId(null)} />
      </Show>

      <NewProjectDialog
        open={newOpen()}
        onOpenChange={setNewOpen}
        onCreated={(id) => navigate(`/studio/${id}`)}
      />

      <ProjectOverview
        projectId={overviewId()}
        onClose={() => setOverviewId(null)}
        onChanged={() => void refreshProjects()}
        onDelete={(id) => void remove(id)}
      />

      <Show when={toast()}>
        <div class="fixed bottom-12 left-1/2 z-50 flex -translate-x-1/2 items-center gap-3 rounded-lg border border-line bg-surface-2 px-3 py-2 shadow-2xl">
          <span class="text-[11px] text-text">{toast()!.text}</span>
          <Show when={toast()!.trash}>
            <button type="button" class="text-[11px] font-medium text-accent hover:underline" onClick={() => void undo()}>
              撤销
            </button>
          </Show>
          <button
            type="button"
            class="text-[13px] leading-none text-faint hover:text-text"
            aria-label="关闭"
            onClick={() => setToast(null)}
          >
            ×
          </button>
        </div>
      </Show>
    </AppShellV2>
  );
}

function Skeleton() {
  return (
    <div class="grid gap-3.5" style={{ "grid-template-columns": "repeat(auto-fill, minmax(300px, 1fr))" }}>
      <For each={[0, 1, 2, 3, 4, 5]}>
        {() => <div class="aspect-[4/3] animate-pulse rounded-xl border border-line-soft bg-surface" />}
      </For>
    </div>
  );
}
