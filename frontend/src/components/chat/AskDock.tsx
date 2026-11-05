import { For, Show, createSignal } from "solid-js";
import { asks, index, prev, next, decide, type AskItem } from "../../stores/asks";
import { fmtEta, fmtUsd } from "../../lib/format";
import Button from "../ui/Button";
import Badge from "../ui/Badge";
import Icon from "../ui/Icon";
import TextArea from "../ui/TextArea";

/** Pinned above the composer: exactly one pending confirmation, carousel for more. */
export default function AskDock() {
  const current = () => asks()[index()];

  return (
    <Show when={asks().length > 0}>
      <div class="mx-auto mb-2 w-full max-w-[760px]">
        <Show when={asks().length > 1}>
          <div class="mb-1.5 flex items-center gap-2 px-0.5 text-[11px] text-faint">
            <span>
              待确认 {index() + 1}/{asks().length}
            </span>
            <div class="ml-auto flex items-center gap-1.5">
              <button
                class="grid h-5 w-5 place-items-center rounded border border-line text-dim disabled:opacity-35"
                disabled={index() === 0}
                onClick={prev}
              >
                <Icon name="chevron-left" size={11} />
              </button>
              <button
                class="grid h-5 w-5 place-items-center rounded border border-line text-dim disabled:opacity-35"
                disabled={index() === asks().length - 1}
                onClick={next}
              >
                <Icon name="chevron-right" size={11} />
              </button>
              <span class="ml-1 flex gap-1">
                <For each={asks()}>
                  {(_, i) => (
                    <i
                      class="block h-[5px] w-[5px] rounded-full"
                      classList={{ "bg-accent": i() === index(), "bg-line": i() !== index() }}
                    />
                  )}
                </For>
              </span>
            </div>
          </div>
        </Show>
        <Show when={current()}>{(item) => <AskCard item={item()} />}</Show>
      </div>
    </Show>
  );
}

function AskCard(props: { item: AskItem }) {
  const [rejecting, setRejecting] = createSignal(false);
  const [comment, setComment] = createSignal("");
  const [busy, setBusy] = createSignal(false);
  const [done, setDone] = createSignal<"approved" | "rejected" | null>(null);

  const quote = () => props.item.quote;
  const approval = () => props.item.approval;
  const isQuote = () => props.item.kind === "quote";

  const submit = async (approved: boolean, note = "") => {
    setBusy(true);
    try {
      await decide(props.item, approved, note);
      setDone(approved ? "approved" : "rejected");
    } catch {
      setBusy(false);
    }
  };

  return (
    <div class="overflow-hidden rounded-xl border border-[#33304a] bg-gradient-to-b from-[#161327] to-[#111318]">
      <div class="flex items-center gap-2 border-b border-line-soft px-3 py-2 text-[12px] text-dim">
        <Show when={isQuote()} fallback={<b class="font-semibold text-text">需要你确认</b>}>
          <b class="font-semibold text-text">报价确认</b>
          <span class="truncate">{quote()?.headline}</span>
          <span class="ml-auto shrink-0 font-mono text-[11.5px] text-[#e8a6d8]">
            {(quote()?.total_usd ?? 0) > 0
              ? `${fmtUsd(quote()?.low_usd)}–${fmtUsd(quote()?.high_usd)}`
              : "无付费项"}{" "}
            · {fmtEta(quote()?.eta_seconds)}
          </span>
        </Show>
        <Show when={!isQuote()}>
          <span class="truncate font-mono text-[11.5px] text-faint">{approval()?.stage}</span>
        </Show>
      </div>

      <div class="px-3 py-2">
        <Show when={isQuote()}>
          <For each={quote()?.line_items ?? []}>
            {(line) => (
              <div class="flex items-center gap-2 py-0.5 text-[11.5px] text-dim">
                <span class="truncate">{line.label || line.tool}</span>
                <Show when={line.status === "quote_required"}>
                  <Badge tone="warn">待询价</Badge>
                </Show>
                <span class="ml-auto font-mono text-[#c3cad8]">{fmtUsd(line.usd)}</span>
              </div>
            )}
          </For>
          <Show when={(quote()?.assumptions ?? []).length > 0}>
            <div class="mt-1 text-[11.5px] text-faint">假设：{quote()?.assumptions?.join(" · ")}</div>
          </Show>
        </Show>

        <Show when={!isQuote() && approval()?.note}>
          <div class="whitespace-pre-wrap text-[11.5px] text-faint">{approval()?.note}</div>
        </Show>

        <Show when={(approval()?.previews ?? []).length > 0}>
          <div class="mt-1 flex gap-1.5 overflow-x-auto pb-1">
            <For each={approval()?.previews ?? []}>
              {(path) => (
                <img
                  src={`/api/media?path=${encodeURIComponent(path)}`}
                  class="h-[132px] rounded-[7px] border border-line-soft bg-[#05060a] object-contain"
                  alt=""
                />
              )}
            </For>
          </div>
        </Show>
      </div>

      <Show when={rejecting()}>
        <div class="px-3 pb-2">
          <TextArea
            class="h-14"
            placeholder={isQuote() ? "说说要改什么（例如：预算压到 $0.3 以内）" : "哪里不对？（例如：第二个镜头太快）"}
            value={comment()}
            onInput={(event) => setComment(event.currentTarget.value)}
          />
          <div class="mt-1.5 flex justify-end gap-1.5">
            <Button size="sm" onClick={() => setRejecting(false)}>
              取消
            </Button>
            <Button size="sm" variant="primary" loading={busy()} onClick={() => submit(false, comment().trim())}>
              提交修改意见
            </Button>
          </div>
        </div>
      </Show>

      <div class="flex items-center gap-2 px-3 pb-3">
        <Button
          size="sm"
          variant="primary"
          loading={busy()}
          disabled={!!done()}
          onClick={() => submit(true)}
        >
          {isQuote() ? "开工" : "通过"}
        </Button>
        <Button size="sm" disabled={!!done()} onClick={() => setRejecting(true)}>
          {isQuote() ? "改方案" : "打回"}
        </Button>
        <Show when={done()}>
          <span
            class="ml-auto text-[11.5px]"
            classList={{ "text-ok": done() === "approved", "text-warn": done() === "rejected" }}
          >
            {done() === "approved" ? "已通过" : "已打回"}
          </span>
        </Show>
      </div>
    </div>
  );
}
