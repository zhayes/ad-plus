import { For, Show, createSignal } from "solid-js";
import Field from "../ui/Field";
import Button from "../ui/Button";
import Spinner from "../ui/Spinner";
import { basename } from "../../lib/format";
import Icon from "../ui/Icon";

interface Attachment {
  name: string;
  path: string;
}

interface Props {
  running: boolean;
  onSend: (text: string, attachments: Attachment[]) => void;
  onStop: () => void;
}

export default function Composer(props: Props) {
  const [text, setText] = createSignal("");
  const [files, setFiles] = createSignal<Attachment[]>([]);
  const [uploading, setUploading] = createSignal(false);
  let area: HTMLTextAreaElement | undefined;
  let picker: HTMLInputElement | undefined;

  const upload = async (list: FileList | null) => {
    if (!list?.length) return;
    setUploading(true);
    try {
      for (const file of Array.from(list).slice(0, 6)) {
        const res = await fetch(`/api/upload?name=${encodeURIComponent(file.name)}`, {
          method: "POST",
          body: file,
        });
        if (!res.ok) continue;
        const data = (await res.json()) as { name: string; path: string };
        setFiles((prev) => [...prev, { name: data.name || file.name, path: data.path }]);
      }
    } finally {
      setUploading(false);
      if (picker) picker.value = "";
    }
  };

  const send = () => {
    const value = text().trim();
    if ((!value && !files().length) || props.running) return;
    props.onSend(value, files());
    setText("");
    setFiles([]);
    if (area) area.value = "";
  };

  return (
    <div class="shrink-0 px-4 pb-3">
      <div class="mx-auto w-full max-w-[760px]">
        <div class="flex items-end gap-2 rounded-xl border border-line bg-surface px-3 py-2 transition-[border-color,box-shadow] duration-150 focus-within:border-[#3a3f55] focus-within:shadow-[0_0_0_3px_rgba(224,51,138,0.10)]">
          <button
            class="mb-1 grid h-7 w-7 shrink-0 place-items-center rounded-md text-faint hover:bg-surface-2 hover:text-text"
            title="上传素材（或拖进窗口）"
            onClick={() => picker?.click()}
          >
            <svg viewBox="0 0 24 24" class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="1.8">
              <path d="M21 11.5l-8.5 8.5a5 5 0 0 1-7-7l8.5-8.5a3.5 3.5 0 0 1 5 5L10.5 18a2 2 0 0 1-3-3l7.5-7.5" />
            </svg>
          </button>

          <input
            ref={picker}
            type="file"
            multiple
            class="hidden"
            onChange={(event) => void upload(event.currentTarget.files)}
          />
          <Field
            ref={(node) => (area = node)}
            value={text()}
            onInput={(event) => setText(event.currentTarget.value)}
            onSubmit={send}
            placeholder="描述你要的广告，或直接说“再快一点 / 换个配色 / 加一版横屏”"
            class="pb-1"
          />

          <Show
            when={!props.running}
            fallback={
              <Button variant="subtle" size="sm" class="mb-1 h-8 w-8 !px-0" onClick={props.onStop} title="停止">
                <span class="block h-2.5 w-2.5 rounded-[2px] bg-text" />
              </Button>
            }
          >
            <Button
              variant="primary"
              size="sm"
              class="mb-1 h-8 w-8 !px-0"
              onClick={send}
              disabled={!text().trim()}
              title="发送"
            >
              <Icon name="arrow-up" size={16} />
            </Button>
          </Show>
        </div>

        <Show when={files().length > 0 || uploading()}>
          <div class="mt-2 flex flex-wrap items-center gap-1.5">
            <For each={files()}>
              {(file) => (
                <span class="flex items-center gap-1 rounded-md border border-line-soft bg-surface-2 px-1.5 py-0.5 text-[10.5px] text-dim">
                  {basename(file.name)}
                  <button
                    class="text-faint hover:text-bad"
                    title="移除"
                    onClick={() => setFiles((prev) => prev.filter((f) => f.path !== file.path))}
                  >
                    ×
                  </button>
                </span>
              )}
            </For>
            <Show when={uploading()}>
              <span class="inline-flex items-center gap-1.5 text-[10.5px] text-faint">
                <Spinner size={10} /> 上传中
              </span>
            </Show>
          </div>
        </Show>

        <div class="mt-2 flex items-center gap-2 text-[10.5px] text-faint">
          <Kbd>Enter</Kbd> 发送 · <Kbd>Shift</Kbd> + <Kbd>Enter</Kbd> 换行
          <Show when={props.running}>
            <span class="ml-auto inline-flex items-center gap-1.5 text-dim">
              <Spinner size={10} /> 执行中
            </span>
          </Show>
        </div>
      </div>
    </div>
  );
}

function Kbd(props: { children: string }) {
  return (
    <kbd class="rounded border border-line-soft bg-surface-2 px-1 font-mono text-[10px] text-dim">
      {props.children}
    </kbd>
  );
}
