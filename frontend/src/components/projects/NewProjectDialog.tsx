import { Show, createEffect, createSignal, on } from "solid-js";
import Dialog from "../ui/Dialog";
import Button from "../ui/Button";
import Input from "../ui/Input";
import TextArea from "../ui/TextArea";
import { endpoints } from "../../lib/api";
import { refreshProjects } from "../../stores/projects";

const PLATFORMS = [
  { value: "douyin", label: "抖音" },
  { value: "xiaohongshu", label: "小红书" },
  { value: "wechat_channels", label: "视频号" },
  { value: "shorts", label: "Shorts" },
  { value: "other", label: "其他" },
];

const DURATIONS = [6, 15, 30, 60];
const TIERS = [
  { value: "draft", label: "草稿" },
  { value: "standard", label: "标准" },
  { value: "premium", label: "精修" },
];

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated: (projectId: string) => void;
}

export default function NewProjectDialog(props: Props) {
  const [title, setTitle] = createSignal("");
  const [audience, setAudience] = createSignal("");
  const [brief, setBrief] = createSignal("");
  const [platform, setPlatform] = createSignal("douyin");
  const [duration, setDuration] = createSignal(15);
  const [tier, setTier] = createSignal("standard");
  const [busy, setBusy] = createSignal(false);
  const [error, setError] = createSignal("");

  const reset = () => {
    setTitle("");
    setAudience("");
    setBrief("");
    setPlatform("douyin");
    setDuration(15);
    setTier("standard");
    setError("");
  };

  createEffect(
    on(
      () => props.open,
      (open) => {
        if (open) reset();
      },
    ),
  );

  const submit = async (event: SubmitEvent) => {
    event.preventDefault();
    const name = title().trim();
    if (!name) {
      setError("先写一个产品 / 主题");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const data = await endpoints.createProject({
        title: name,
        brief: {
          product: name,
          audience: audience().trim(),
          description: brief().trim(),
        },
        platform: platform(),
        duration_s: duration(),
        quality_tier: tier(),
      });
      await refreshProjects();
      props.onOpenChange(false);
      props.onCreated(data.project.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "创建失败，请重试");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={props.open} onOpenChange={props.onOpenChange} title="新建项目">
      <form class="space-y-4" onSubmit={(event) => void submit(event)}>
        <div>
          <label class="mb-1.5 block text-[10.5px] text-faint">产品 / 主题</label>
          <Input
            value={title()}
            autofocus
            placeholder="例：炭火现烤红薯"
            onInput={(event) => setTitle(event.currentTarget.value)}
          />
        </div>

        <div class="grid grid-cols-[1fr_210px] gap-4">
          <div>
            <label class="mb-1.5 block text-[10.5px] text-faint">平台</label>
            <div class="flex flex-wrap gap-1.5">
              {PLATFORMS.map((item) => (
                <button
                  type="button"
                  class={`h-7 rounded-md border px-2.5 text-[11px] ${
                    platform() === item.value
                      ? "border-accent/50 bg-accent/10 text-text"
                      : "border-line text-dim hover:text-text"
                  }`}
                  onClick={() => setPlatform(item.value)}
                >
                  {item.label}
                </button>
              ))}
            </div>
          </div>
          <div>
            <label class="mb-1.5 block text-[10.5px] text-faint">时长</label>
            <div class="flex flex-wrap gap-1.5">
              {DURATIONS.map((value) => (
                <button
                  type="button"
                  class={`h-7 rounded-md border px-2.5 font-mono text-[11px] ${
                    duration() === value
                      ? "border-accent/50 bg-accent/10 text-text"
                      : "border-line text-dim hover:text-text"
                  }`}
                  onClick={() => setDuration(value)}
                >
                  {value}s
                </button>
              ))}
            </div>
          </div>
        </div>

        <div class="grid grid-cols-2 gap-4">
          <div>
            <label class="mb-1.5 block text-[10.5px] text-faint">档位</label>
            <div class="flex gap-1.5">
              {TIERS.map((item) => (
                <button
                  type="button"
                  class={`h-7 flex-1 rounded-md border text-[11px] ${
                    tier() === item.value
                      ? "border-accent/50 bg-accent/10 text-text"
                      : "border-line text-dim hover:text-text"
                  }`}
                  onClick={() => setTier(item.value)}
                >
                  {item.label}
                </button>
              ))}
            </div>
          </div>
          <div>
            <label class="mb-1.5 block text-[10.5px] text-faint">目标人群（可选）</label>
            <Input
              value={audience()}
              placeholder="例：下班想吃点热的年轻人"
              onInput={(event) => setAudience(event.currentTarget.value)}
            />
          </div>
        </div>

        <div>
          <label class="mb-1.5 block text-[10.5px] text-faint">一句话 brief（可选）</label>
          <TextArea
            rows={3}
            value={brief()}
            placeholder="想突出什么、给谁看、最后想让用户做什么"
            onInput={(event) => setBrief(event.currentTarget.value)}
          />
        </div>

        <Show when={error()}>
          <div class="text-[11px] text-bad">{error()}</div>
        </Show>

        <div class="flex items-center gap-2 border-t border-line-soft pt-3">
          <span class="text-[10px] text-faint">创建后进入制作，补全简报和路线。</span>
          <div class="ml-auto flex items-center gap-2">
            <Button type="button" variant="ghost" onClick={() => props.onOpenChange(false)}>
              取消
            </Button>
            <Button type="submit" variant="primary" loading={busy()}>
              创建并进入
            </Button>
          </div>
        </div>
      </form>
    </Dialog>
  );
}
