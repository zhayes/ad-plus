import { For } from "solid-js";
import { useNavigate } from "@solidjs/router";
import Icon, { type IconName } from "../ui/Icon";

export type ModuleKey = "projects" | "create" | "restyle" | "recreate" | "assets" | "tasks" | "settings";

interface Props {
  active: ModuleKey;
  footer?: string;
}

const ITEMS: { key: ModuleKey; label: string; icon: IconName; path: string }[] = [
  { key: "projects", label: "项目", icon: "folder", path: "/projects" },
  { key: "create", label: "自由创作", icon: "sparkles", path: "/chat" },
  { key: "restyle", label: "改写", icon: "layers", path: "/restyle" },
  { key: "assets", label: "资产", icon: "library", path: "/assets" },
  { key: "tasks", label: "任务", icon: "list-checks", path: "/tasks" },
];

const UTILITIES: { key: ModuleKey; label: string; icon: IconName; path: string }[] = [
  { key: "settings", label: "设置", icon: "settings", path: "/settings" },
];

const ACTIVE_RAISED =
  "border border-accent/35 bg-gradient-to-b from-[#f86ab3] to-accent text-white " +
  "shadow-[inset_0_1px_0_rgba(255,255,255,0.35),0_3px_0_#8e1c5b,0_8px_16px_rgba(240,68,154,0.28)] " +
  "hover:from-[#ff7dbe] hover:to-[#f0449a] active:translate-y-px " +
  "active:shadow-[inset_0_1px_0_rgba(255,255,255,0.28),0_1px_0_#8e1c5b]";

export default function ModuleDock(props: Props) {
  const navigate = useNavigate();

  return (
    <nav class="flex h-12 shrink-0 items-center gap-1 border-t border-line bg-[#141a26] px-2 shadow-[0_-8px_24px_rgba(0,0,0,0.22)]">
      <For each={ITEMS}>
        {(item) => {
          const active = () => props.active === item.key;
          return (
            <button
              type="button"
              class={`flex h-9 items-center gap-2 rounded-lg px-3 text-[12px] transition-all duration-150 ${
                active() ? ACTIVE_RAISED : "text-dim hover:bg-surface-2/70 hover:text-text"
              }`}
              onClick={() => navigate(item.path)}
            >
              <Icon name={item.icon} size={16} class={active() ? "text-white" : "text-faint"} />
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
              class={`flex h-8 items-center gap-1.5 rounded-lg px-2.5 text-[11.5px] transition-all duration-150 ${
                props.active === item.key ? ACTIVE_RAISED : "text-faint hover:bg-surface-2 hover:text-text"
              }`}
              onClick={() => navigate(item.path)}
            >
              <Icon name={item.icon} size={15} class={props.active === item.key ? "text-white" : undefined} />
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
