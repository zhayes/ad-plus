import { For } from "solid-js";
import { useNavigate } from "@solidjs/router";
import Icon, { type IconName } from "../ui/Icon";
import { firstProjectId } from "../../stores/projects";

export type ModuleKey = "projects" | "studio" | "create" | "assets" | "tasks" | "settings";

interface Props {
  active: ModuleKey;
  footer?: string;
}

const ITEMS: { key: ModuleKey; label: string; icon: IconName; path: () => string }[] = [
  { key: "projects", label: "项目", icon: "folder", path: () => "/projects" },
  { key: "studio", label: "制作", icon: "clapperboard", path: () => (firstProjectId() ? `/studio/${firstProjectId()}` : "/projects") },
  { key: "create", label: "自由创作", icon: "sparkles", path: () => "/chat" },
  { key: "assets", label: "资产", icon: "library", path: () => "/assets" },
  { key: "tasks", label: "任务", icon: "list-checks", path: () => "/tasks" },
];

const UTILITIES: { key: ModuleKey; label: string; icon: IconName; path: string }[] = [
  { key: "settings", label: "设置", icon: "settings", path: "/settings" },
];

export default function ModuleDock(props: Props) {
  const navigate = useNavigate();

  const open = (item: (typeof ITEMS)[number]) => {
    if (item.key === "studio" && !firstProjectId()) {
      navigate("/projects");
      window.setTimeout(() => window.dispatchEvent(new CustomEvent("adplus-new-project")), 80);
      return;
    }
    navigate(item.path());
  };

  return (
    <nav class="flex h-12 shrink-0 items-center gap-1 border-t border-line bg-[#141a26] px-2 shadow-[0_-8px_24px_rgba(0,0,0,0.22)]">
      <For each={ITEMS}>
        {(item) => {
          const active = () => props.active === item.key;
          return (
            <button
              type="button"
              class={`relative flex h-9 items-center gap-2 rounded-md px-3 text-[12px] transition-colors ${
                active() ? "bg-[#232b3d] text-text" : "text-dim hover:bg-surface-2/70 hover:text-text"
              }`}
              title={item.key === "studio" && !firstProjectId() ? "先新建项目，再进入制作" : undefined}
              onClick={() => open(item)}
            >
              <span class={`absolute left-0 top-2 h-5 w-0.5 rounded-full ${active() ? "bg-accent" : "bg-transparent"}`} />
              <Icon name={item.icon} size={16} class={active() ? "text-accent" : "text-faint"} />
              {item.label}
            </button>
          );
        }}
      </For>
      <div class="ml-auto flex items-center gap-2">
        {props.footer ? <span class="hidden text-[10.5px] text-faint sm:inline">{props.footer}</span> : null}
        <div class="h-5 w-px bg-line" />
        <For each={UTILITIES}>
          {(item) => (
            <button
              type="button"
              class={`flex h-8 items-center gap-1.5 rounded-md px-2.5 text-[11.5px] ${
                props.active === item.key ? "bg-[#232b3d] text-text" : "text-faint hover:bg-surface-2 hover:text-text"
              }`}
              onClick={() => navigate(item.path)}
            >
              <Icon name={item.icon} size={15} />
              {item.label}
            </button>
          )}
        </For>
        <button type="button" class="grid h-8 w-8 place-items-center rounded-md text-faint hover:bg-surface-2 hover:text-text" title="帮助">
          <Icon name="help" size={15} />
        </button>
      </div>
    </nav>
  );
}
