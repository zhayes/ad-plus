import { For, Show, createEffect, createMemo, createSignal, onCleanup, onMount } from "solid-js";
import { useNavigate } from "@solidjs/router";
import { firstProjectId, refreshProjects } from "../../stores/projects";

interface Action {
  id: string;
  label: string;
  group: string;
  hint?: string;
  run: () => void;
}

export default function CommandPalette() {
  const navigate = useNavigate();
  const [open, setOpen] = createSignal(false);
  const [query, setQuery] = createSignal("");
  const [active, setActive] = createSignal(0);
  let input: HTMLInputElement | undefined;

  const go = (path: string) => {
    setOpen(false);
    setQuery("");
    navigate(path);
  };

  const newProject = () => {
    setOpen(false);
    setQuery("");
    navigate("/projects");
    window.setTimeout(() => window.dispatchEvent(new CustomEvent("adplus-new-project")), 80);
  };

  const actions = (): Action[] => {
    return [
      { id: "projects", label: "项目", group: "页面", hint: "⌘O", run: () => go("/projects") },
      { id: "assets", label: "资产", group: "页面", run: () => go("/assets") },
      { id: "tasks", label: "任务", group: "页面", run: () => go("/tasks") },
      { id: "settings", label: "设置", group: "页面", hint: "⌘,", run: () => go("/settings") },
      { id: "new-project", label: "新建项目", group: "动作", hint: "⌘N", run: newProject },
      {
        id: "new-brand",
        label: "新建品牌包",
        group: "动作",
        run: () => go("/assets"),
      },
      {
        id: "command-palette",
        label: "打开命令面板",
        group: "动作",
        hint: "⌘K",
        run: () => setOpen(true),
      },
    ];
  };

  const filtered = createMemo(() => {
    const q = query().trim().toLowerCase();
    if (!q) return actions();
    return actions().filter((action) =>
      `${action.label} ${action.group} ${action.hint ?? ""}`.toLowerCase().includes(q),
    );
  });

  createEffect(() => {
    if (!open()) return;
    setActive(0);
    queueMicrotask(() => input?.focus());
  });

  createEffect(() => {
    query();
    setActive(0);
  });

  const runActive = () => {
    const action = filtered()[active()];
    if (action) action.run();
  };

  const onKey = (event: KeyboardEvent) => {
    const meta = event.metaKey || event.ctrlKey;
    const key = event.key.toLowerCase();
    if (meta && key === "k") {
      event.preventDefault();
      setOpen((value) => !value);
      return;
    }
    if (meta && key === "n") {
      event.preventDefault();
      newProject();
      return;
    }
    if (meta && key === "o") {
      event.preventDefault();
      go("/projects");
      return;
    }
    if (meta && event.key === ",") {
      event.preventDefault();
      go("/settings");
      return;
    }
    if (!open()) return;
    if (event.key === "Escape") {
      event.preventDefault();
      setOpen(false);
    } else if (event.key === "ArrowDown") {
      event.preventDefault();
      setActive((value) => Math.min(value + 1, Math.max(0, filtered().length - 1)));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActive((value) => Math.max(0, value - 1));
    } else if (event.key === "Enter") {
      event.preventDefault();
      runActive();
    }
  };

  const onMenu = (event: Event) => {
    const id = String((event as CustomEvent).detail ?? "");
    if (!id) return;
    if (id === "command-palette") {
      setOpen(true);
      return;
    }
    if (id === "new-project") {
      newProject();
      return;
    }
    if (id === "open-projects") go("/projects");
    else if (id === "open-studio") go(firstProjectId() ? `/studio/${firstProjectId()}` : "/projects");
    else if (id === "open-assets") go("/assets");
    else if (id === "open-tasks") go("/tasks");
    else if (id === "open-settings" || id === "about" || id === "shortcuts") go("/settings");
    else if (id === "export") go(firstProjectId() ? `/studio/${firstProjectId()}` : "/projects");
  };

  onMount(() => {
    void refreshProjects();
    window.addEventListener("keydown", onKey);
    window.addEventListener("adplus-menu", onMenu);
  });

  onCleanup(() => {
    window.removeEventListener("keydown", onKey);
    window.removeEventListener("adplus-menu", onMenu);
  });

  return (
    <Show when={open()}>
      <div class="fixed inset-0 z-[60] flex items-start justify-center pt-[12vh]" role="dialog" aria-modal="true">
        <div class="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={() => setOpen(false)} />
        <div class="relative w-[min(620px,calc(100vw-32px))] overflow-hidden rounded-xl border border-line-soft bg-surface shadow-2xl">
          <div class="flex h-11 items-center gap-2 border-b border-line-soft px-3">
            <span class="text-[13px] text-faint">⌘</span>
            <input
              ref={input}
              value={query()}
              placeholder="搜索页面或动作…"
              class="h-full flex-1 bg-transparent text-[12px] text-text outline-none placeholder:text-faint"
              onInput={(event) => setQuery(event.currentTarget.value)}
              onKeyDown={(event) => {
                event.stopPropagation();
                onKey(event);
              }}
            />
            <span class="text-[9.5px] text-faint">esc 关闭</span>
          </div>
          <div class="max-h-[360px] overflow-auto p-1">
            <Show
              when={filtered().length > 0}
              fallback={<div class="py-10 text-center text-[11px] text-faint">没有匹配的动作</div>}
            >
              <For each={filtered()}>
                {(action, index) => (
                  <button
                    type="button"
                    class={`flex w-full items-center gap-2 rounded-md px-2 py-2 text-left ${
                      active() === index() ? "bg-surface-2" : "hover:bg-surface-2/60"
                    }`}
                    onMouseEnter={() => setActive(index())}
                    onClick={() => action.run()}
                  >
                    <span class="w-[42px] shrink-0 text-[9.5px] text-faint">{action.group}</span>
                    <span class="min-w-0 flex-1 truncate text-[11.5px] text-text">{action.label}</span>
                    <Show when={action.hint}>
                      <span class="font-mono text-[9.5px] text-faint">{action.hint}</span>
                    </Show>
                  </button>
                )}
              </For>
            </Show>
          </div>
          <div class="flex items-center gap-3 border-t border-line-soft px-3 py-1.5 text-[9px] text-faint">
            <span>↑↓ 选择</span>
            <span>↵ 执行</span>
            <span class="ml-auto">Ad+ Command</span>
          </div>
        </div>
      </div>
    </Show>
  );
}
