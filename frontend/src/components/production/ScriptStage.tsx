import { For, Show, createEffect, createSignal, on } from "solid-js";
import Badge from "../ui/Badge";
import Button from "../ui/Button";
import Icon from "../ui/Icon";
import TextArea from "../ui/TextArea";
import { endpoints } from "../../lib/api";
import type { ProductionView, StageId } from "../../lib/types";

interface Props {
  production: ProductionView;
  onChanged: () => void;
  onAdvanced: (stage: StageId) => void;
}

interface Line {
  id: string;
  text: string;
  kind?: string;
}

export default function ScriptStage(props: Props) {
  const [lines, setLines] = createSignal<Line[]>([]);
  const [busy, setBusy] = createSignal(false);
  const [error, setError] = createSignal("");
  const [saved, setSaved] = createSignal(false);

  createEffect(
    on(
      () => props.production.project.id,
      () => {
        const source = props.production.script?.lines ?? [];
        setLines(source.length ? source.map((line) => ({ id: line.id, text: line.text, kind: line.kind })) : [
          { id: "l1", text: "", kind: "voiceover" },
          { id: "l2", text: "", kind: "voiceover" },
        ]);
        setSaved(false);
      },
    ),
  );

  const approved = () => props.production.approvals?.script != null;
  const totalChars = () => lines().reduce((sum, line) => sum + line.text.length, 0);
  const estimate = () => Math.max(1, Math.round(totalChars() / 5.2));

  const update = (id: string, text: string) => {
    setSaved(false);
    setLines((previous) => previous.map((line) => line.id === id ? { ...line, text } : line));
  };

  const add = () => {
    setSaved(false);
    setLines((previous) => [...previous, { id: `l${Date.now().toString(36)}`, text: "", kind: "voiceover" }]);
  };

  const remove = (id: string) => {
    setSaved(false);
    setLines((previous) => previous.filter((line) => line.id !== id));
  };

  const save = async () => {
    await endpoints.saveScript(props.production.project.id, lines().filter((line) => line.text.trim()));
    setSaved(true);
    props.onChanged();
  };

  const saveAndApprove = async () => {
    if (!lines().some((line) => line.text.trim())) {
      setError("至少写一段脚本");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await save();
      await endpoints.approveStage(props.production.project.id, "script");
      props.onChanged();
      props.onAdvanced("scene");
    } catch (err) {
      setError(err instanceof Error ? err.message : "确认脚本失败");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div class="h-full overflow-auto p-4 sm:p-5">
      <div class="mx-auto w-full max-w-[1120px]">
        <div class="mb-4 flex flex-wrap items-end gap-2">
          <div>
            <div class="flex items-center gap-2">
              <h1 class="text-[16px] font-semibold text-text">脚本</h1>
              <Badge tone={approved() ? "ok" : "accent"}>{approved() ? "已确认" : "编辑中"}</Badge>
            </div>
            <p class="mt-1 text-[11.5px] text-faint">按时间顺序写口播/字幕；确认后进入分镜。</p>
          </div>
          <div class="ml-auto flex items-center gap-3 text-[10px] text-faint">
            <span>{totalChars()} 字</span>
            <span>约 {estimate()}s</span>
            <span>{lines().length} 段</span>
          </div>
        </div>

        <Show when={error()}>
          <div class="mb-3 rounded-lg border border-bad/30 bg-bad/5 px-3 py-2 text-[11px] text-bad">{error()}</div>
        </Show>

        <div class="grid gap-4 lg:grid-cols-[minmax(0,1fr)_300px]">
          <section class="space-y-2">
            <For each={lines()}>
              {(line, index) => (
                <div class="rounded-xl border border-line-soft bg-surface p-3">
                  <div class="mb-2 flex items-center gap-2">
                    <span class="font-mono text-[9.5px] text-faint">0{index() + 1}</span>
                    <select
                      class="rounded border border-line-soft bg-surface-2 px-1.5 py-0.5 text-[9.5px] text-dim outline-none"
                      value={line.kind ?? "voiceover"}
                      disabled={approved()}
                      onChange={(event) => {
                        const kind = event.currentTarget.value;
                        setLines((previous) => previous.map((item) => item.id === line.id ? { ...item, kind } : item));
                      }}
                    >
                      <option value="voiceover">口播</option>
                      <option value="on_screen">字幕</option>
                      <option value="both">口播 + 字幕</option>
                    </select>
                    <button
                      type="button"
                      class="ml-auto grid h-5 w-5 place-items-center rounded text-faint hover:bg-surface-2 hover:text-bad disabled:opacity-30"
                      disabled={approved() || lines().length <= 1}
                      title="删除这段"
                      onClick={() => remove(line.id)}
                    >
                      ×
                    </button>
                  </div>
                  <TextArea
                    rows={2}
                    value={line.text}
                    readOnly={approved()}
                    placeholder={index() === 0 ? "Hook：前 1.5 秒说什么" : "这一段说什么"}
                    onInput={(event) => update(line.id, event.currentTarget.value)}
                  />
                </div>
              )}
            </For>
            <Show when={!approved()}>
              <button type="button" class="flex h-9 w-full items-center justify-center gap-1.5 rounded-lg border border-dashed border-line text-[10.5px] text-faint hover:border-accent/40 hover:text-text" onClick={add}>
                <Icon name="plus" size={13} /> 添加一段
              </button>
            </Show>
          </section>

          <aside class="space-y-3">
            <div class="rounded-xl border border-line-soft bg-surface p-3">
              <div class="text-[10px] tracking-wide text-faint">脚本检查</div>
              <div class="mt-2 space-y-1.5 text-[10.5px] text-faint">
                <div class="flex justify-between"><span>总字数</span><span class="font-mono text-dim">{totalChars()}</span></div>
                <div class="flex justify-between"><span>预估时长</span><span class="font-mono text-dim">{estimate()}s</span></div>
                <div class="flex justify-between"><span>目标时长</span><span class="font-mono text-dim">{props.production.project.duration_s}s</span></div>
                <Show when={estimate() > Number(props.production.project.duration_s || 15)}>
                  <div class="text-warn">可能超时，建议精简文案。</div>
                </Show>
              </div>
            </div>
            <div class="rounded-lg border border-line-soft bg-surface px-3 py-2 text-[10px] leading-5 text-faint">
              稿子会作为分镜的文案来源；锁定后再改需要重新确认。
            </div>
            <Show when={!approved()}>
              <Button class="w-full" size="sm" variant="primary" loading={busy()} onClick={() => void saveAndApprove()}>
                确认脚本，做分镜
              </Button>
              <Button class="w-full" size="sm" variant="ghost" loading={busy()} onClick={() => void save()}>
                {saved() ? "已保存" : "只保存"}
              </Button>
            </Show>
            <Show when={approved()}>
              <Button class="w-full" size="sm" variant="primary" onClick={() => props.onAdvanced("scene")}>
                看分镜
              </Button>
            </Show>
          </aside>
        </div>
      </div>
    </div>
  );
}
