import type { JSX } from "solid-js";
import { Show } from "solid-js";
import Logo from "../ui/Logo";
import Icon from "../ui/Icon";

interface Props {
  railOpen: boolean;
  panelOpen: boolean;
  rail: JSX.Element;
  panel?: JSX.Element;
  topbarRight?: JSX.Element;
  title?: JSX.Element;
  children: JSX.Element;
  onToggleRail: () => void;
  onTogglePanel: () => void;
}

/** Fixed chrome: top bar, collapsible rail, content, optional right panel. */
export default function AppShell(props: Props) {
  return (
    <div class="flex h-full flex-col bg-bg text-text">
      <header class="flex h-11 shrink-0 items-center gap-2 border-b border-line-soft px-3">
        <button
          class="grid h-7 w-7 place-items-center rounded-md text-faint hover:bg-surface-2 hover:text-text"
          title={props.railOpen ? "收起侧栏" : "展开侧栏"}
          onClick={props.onToggleRail}
        >
          <Icon name="panel-left" size={16} />
        </button>
        <Show
          when={props.title}
          fallback={
            <div class="flex items-center gap-2">
              <Logo size={22} />
              <span class="text-[14px] font-semibold leading-none">
                Ad<span class="text-accent">+</span>
              </span>
            </div>
          }
        >
          {props.title}
        </Show>
        <div class="ml-auto flex items-center gap-2">{props.topbarRight}</div>
        <button
          class="grid h-7 w-7 place-items-center rounded-md text-faint hover:bg-surface-2 hover:text-text"
          title={props.panelOpen ? "隐藏右栏" : "显示右栏"}
          onClick={props.onTogglePanel}
        >
          <Icon name="panel-right" size={16} />
        </button>
      </header>

      <div class="flex min-h-0 flex-1">
        <Show when={props.railOpen}>
          <aside class="w-[244px] shrink-0 border-r border-line-soft bg-surface">{props.rail}</aside>
        </Show>
        <main class="flex min-w-0 flex-1 flex-col">{props.children}</main>
        <Show when={props.panelOpen && props.panel}>
          <aside class="w-[288px] shrink-0 overflow-auto border-l border-line-soft bg-surface">
            {props.panel}
          </aside>
        </Show>
      </div>
    </div>
  );
}
