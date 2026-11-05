import { Show } from "solid-js";
import type { Turn as TurnModel } from "../../lib/types";
import { renderMarkdown } from "../../lib/markdown";
import Timeline from "./Timeline";
import Logo from "../ui/Logo";

export default function Turn(props: { turn: TurnModel }) {
  const isUser = () => props.turn.role === "user";

  return (
    <div class="flex gap-3 px-1 py-2">
      <div class="flex h-[26px] w-[26px] shrink-0 items-center justify-center rounded-[7px] text-[11px] font-medium">
        <Show
          when={isUser()}
          fallback={
            <Logo size={26} class="rounded-[7px]" />
          }
        >
          <span class="grid h-[26px] w-[26px] place-items-center rounded-[7px] border border-line bg-surface-2 text-dim">
            你
          </span>
        </Show>
      </div>

      <div class="min-w-0 flex-1">
        <Show when={isUser()}>
          <div class="whitespace-pre-wrap text-[13px] leading-relaxed text-text">{props.turn.text}</div>
        </Show>
        <Show when={!isUser()}>
          <Timeline steps={props.turn.timeline ?? []} />
          <Show when={props.turn.text}>
            <div class="md text-[13px] leading-relaxed text-text" innerHTML={renderMarkdown(props.turn.text)} />
          </Show>
        </Show>
      </div>
    </div>
  );
}
