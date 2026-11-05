import { For, Show, createEffect, onMount } from "solid-js";
import { turns, running } from "../../stores/transcript";
import Turn from "./Turn";

export default function Transcript() {
  let box: HTMLDivElement | undefined;

  const stick = () => {
    if (!box) return;
    box.scrollTop = box.scrollHeight;
  };

  onMount(stick);
  createEffect(() => {
    // read the reactive value so the effect re-runs as text streams in
    void turns().length;
    void running();
    queueMicrotask(stick);
  });

  return (
    <div ref={box} class="flex-1 overflow-auto px-4">
      <div class="mx-auto w-full max-w-[760px] py-4">
        <Show when={turns().length === 0}>
          <div class="px-1 pt-8 pb-6">
            <div class="text-[10px] font-mono tracking-[0.18em] text-accent">FREE CREATE / BETA</div>
            <h2 class="mt-2 text-[22px] font-semibold tracking-tight text-text">直接描述，生成一段视频</h2>
            <p class="mt-2 max-w-[560px] text-[12.5px] leading-6 text-dim">
              这里不先建项目，也不经过简报和 gate。适合试探想法、做概念片或让导演自由发挥。
              需要报价、逐镜确认和交付管理时，回到「制作」用七阶段流程。
            </p>
            <div class="mt-5 flex flex-wrap gap-1.5">
              <For each={["15 秒产品广告", "品牌概念片", "口播 + 字幕", "一个视觉实验"]}>
                {(item) => (
                  <span class="rounded-full border border-line bg-surface px-2.5 py-1 text-[10.5px] text-dim">{item}</span>
                )}
              </For>
            </div>
            <div class="mt-6 rounded-lg border border-line-soft bg-surface/60 px-3 py-2.5 text-[10.5px] leading-5 text-faint">
              生成结果会出现在右侧「产物 / 任务」；要把它变成可管理项目，先记录关键设定，再到「项目 → 新建项目」。
            </div>
          </div>
        </Show>
        <For each={turns()}>{(turn) => <Turn turn={turn} />}</For>
      </div>
    </div>
  );
}
