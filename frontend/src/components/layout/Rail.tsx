import { For, Show } from "solid-js";
import { sessions, currentId, loading } from "../../stores/session";
import { fmtBytes, fmtTime } from "../../lib/format";
import Spinner from "../ui/Spinner";
import { CountBadge } from "../ui/Badge";

interface Props {
  onNew: () => void;
  onSelect: (id: string) => void;
}

export default function Rail(props: Props) {
  return (
    <div class="flex h-full flex-col">
      <div class="p-3">
        <button
          class="flex h-9 w-full items-center justify-center gap-1.5 rounded-lg bg-gradient-to-br from-violet to-accent text-[12.5px] font-medium text-white hover:brightness-110"
          onClick={props.onNew}
        >
          + 新对话
        </button>
      </div>

      <div class="flex items-center px-3 pb-1 text-[10.5px] text-faint">
        <span>会话</span>
        <CountBadge value={sessions().length} class="text-[10.5px] text-faint" />
      </div>

      <div class="min-h-0 flex-1 overflow-auto px-2 pb-2">
        <Show when={!loading() && sessions().length === 0}>
          <div class="px-2 py-3 text-[11.5px] text-faint">还没有会话</div>
        </Show>
        <For each={sessions()}>
          {(session) => (
            <button
              class="mb-1 block w-full rounded-lg border px-2.5 py-2 text-left"
              classList={{
                "border-line bg-surface-2": currentId() === session.id,
                "border-transparent hover:bg-surface-2": currentId() !== session.id,
              }}
              onClick={() => props.onSelect(session.id)}
            >
              <div class="truncate text-[12.5px] text-text">{session.title}</div>
              <div class="mt-0.5 flex items-center gap-1.5 font-mono text-[10.5px] text-faint">
                <Show when={session.running}>
                  <Spinner size={9} />
                </Show>
                <span>
                  {fmtTime(session.updated)} · {fmtBytes(session.bytes)}
                </span>
              </div>
            </button>
          )}
        </For>
      </div>

    </div>
  );
}
