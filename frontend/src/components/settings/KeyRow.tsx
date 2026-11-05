import { For, Show, createSignal } from "solid-js";
import type { KeyInfo } from "../../lib/types";
import Button from "../ui/Button";
import Badge from "../ui/Badge";
import Input from "../ui/Input";

export interface RowModel {
  name: string;
  label?: string;
  configured: boolean;
  masked?: string;
  meta?: string;
  caps?: string[];
}

interface Props {
  item: RowModel;
  onSave: (name: string, value: string) => Promise<void>;
  onClear: (name: string) => Promise<void>;
}

/** One credential row — the shape both 模型 and 媒体服务 use. */
export default function KeyRow(props: Props) {
  const [editing, setEditing] = createSignal(false);
  const [value, setValue] = createSignal("");
  const [busy, setBusy] = createSignal(false);

  const save = async () => {
    if (!value().trim()) return;
    setBusy(true);
    try {
      await props.onSave(props.item.name, value().trim());
      setValue("");
      setEditing(false);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div class="border-b border-line-soft py-2.5 last:border-0">
      <div class="flex items-start gap-2.5">
        <span
          class="mt-1.5 block h-1.5 w-1.5 shrink-0 rounded-full"
          classList={{ "bg-ok": props.item.configured, "bg-line": !props.item.configured }}
        />
        <div class="min-w-0 flex-1">
          <div class="flex items-center gap-2">
            <span class="text-[12.5px] text-text">{props.item.label ?? props.item.name}</span>
            <Show when={!props.item.configured}>
              <Badge>未配置</Badge>
            </Show>
          </div>
          <Show when={props.item.meta}>
            <div class="text-[10.5px] text-faint">{props.item.meta}</div>
          </Show>
          <Show when={(props.item.caps ?? []).length > 0}>
            <div class="mt-1 flex flex-wrap gap-1">
              <For each={props.item.caps!.slice(0, 6)}>
                {(cap) => (
                  <span class="rounded border border-line-soft px-1 py-px text-[9.5px] text-faint">{cap}</span>
                )}
              </For>
            </div>
          </Show>
          <Show when={props.item.configured && props.item.masked}>
            <div class="mt-1 font-mono text-[10px] text-faint">{props.item.masked}</div>
          </Show>
        </div>

        <div class="flex shrink-0 items-center gap-1.5">
          <Button size="sm" onClick={() => setEditing((v) => !v)}>
            {props.item.configured ? "更换" : "接入"}
          </Button>
          <Show when={props.item.configured}>
            <Button size="sm" variant="ghost" onClick={() => void props.onClear(props.item.name)}>
              清除
            </Button>
          </Show>
        </div>
      </div>

      <Show when={editing()}>
        <div class="mt-2 flex gap-2 pl-4">
          <Input
            type="password"
            tone="password"
            class="flex-1"
            placeholder={`粘贴 ${props.item.name}`}
            value={value()}
            onInput={(event) => setValue(event.currentTarget.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") void save();
              if (event.key === "Escape") setEditing(false);
            }}
          />
          <Button size="sm" variant="primary" loading={busy()} onClick={() => void save()}>
            保存
          </Button>
          <Button size="sm" variant="ghost" onClick={() => setEditing(false)}>
            取消
          </Button>
        </div>
      </Show>
    </div>
  );
}

export type { KeyInfo };
