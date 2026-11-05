import type { JSX } from "solid-js";
import { Show } from "solid-js";
import ModuleDock, { type ModuleKey } from "./ModuleDock";

export type { ModuleKey } from "./ModuleDock";

interface Props {
  module: ModuleKey;
  context: JSX.Element;
  subTabs?: JSX.Element;
  primary?: JSX.Element;
  footer?: JSX.Element;
  children: JSX.Element;
}

/** P0 chrome: 44px context bar, centered sub-tabs, 36px module dock. */
export default function AppShellV2(props: Props) {


  return (
    <div class="flex h-full flex-col bg-bg text-text">
      <header class="relative flex h-11 shrink-0 items-center gap-2 border-b border-line-soft px-3">
        <div class="flex min-w-0 items-center gap-2">{props.context}</div>
        <Show when={props.subTabs}>
          <div class="absolute left-1/2 top-1/2 z-10 -translate-x-1/2 -translate-y-1/2">
            {props.subTabs}
          </div>
        </Show>
        <div class="ml-auto flex shrink-0 items-center gap-2">{props.primary}</div>
      </header>

      <main class="min-h-0 flex-1 overflow-hidden">{props.children}</main>

      <ModuleDock active={props.module} footer={typeof props.footer === "string" ? props.footer : undefined} />

    </div>
  );
}
