import { For, Show, createSignal, onMount } from "solid-js";
import Badge from "../ui/Badge";
import Button from "../ui/Button";
import Dialog from "../ui/Dialog";
import Input from "../ui/Input";
import TextArea from "../ui/TextArea";
import { endpoints } from "../../lib/api";
import type { Skill } from "../../lib/types";

interface Props {
  notify: (text: string, error?: boolean) => void;
}

/** Settings → 技能. Only app-authored skills live here; bundled ones are untouched. */
export default function SkillsPanel(props: Props) {
  const [rows, setRows] = createSignal<Skill[]>([]);
  const [dir, setDir] = createSignal("");
  const [loading, setLoading] = createSignal(true);
  const [open, setOpen] = createSignal(false);
  const [editing, setEditing] = createSignal<Skill | null>(null);
  const [name, setName] = createSignal("");
  const [description, setDescription] = createSignal("");
  const [instructions, setInstructions] = createSignal("");
  const [error, setError] = createSignal("");
  const [saving, setSaving] = createSignal(false);

  const load = async () => {
    setLoading(true);
    try {
      const data = await endpoints.skills();
      setRows(data.skills ?? []);
      setDir(data.dir ?? "");
    } catch (err) {
      props.notify(err instanceof Error ? err.message : "技能加载失败", true);
    } finally {
      setLoading(false);
    }
  };

  onMount(() => void load());

  const openCreate = () => {
    setEditing(null);
    setName("");
    setDescription("");
    setInstructions("");
    setError("");
    setOpen(true);
  };

  const openEdit = (skill: Skill) => {
    setEditing(skill);
    setName(skill.name);
    setDescription(skill.description);
    setInstructions(skill.instructions);
    setError("");
    setOpen(true);
  };

  const save = async () => {
    const nextName = name().trim();
    const nextDescription = description().trim();
    if (!nextName || !nextDescription) {
      setError("技能名和描述都要填");
      return;
    }
    setSaving(true);
    setError("");
    const current = editing();
    try {
      if (current) {
        await endpoints.updateSkill(current.slug, {
          name: nextName,
          description: nextDescription,
          instructions: instructions(),
        });
      } else {
        await endpoints.createSkill({
          name: nextName,
          description: nextDescription,
          instructions: instructions(),
        });
      }
      setOpen(false);
      await load();
      props.notify(current ? "技能已保存，新会话生效" : "技能已新增，新会话生效");
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存失败");
    } finally {
      setSaving(false);
    }
  };

  const remove = async (skill: Skill) => {
    if (!window.confirm(`删除技能「${skill.name}」？文件会移到技能目录的 .trash。`)) return;
    try {
      await endpoints.deleteSkill(skill.slug);
      await load();
      props.notify("技能已删除，新会话生效");
    } catch (err) {
      props.notify(err instanceof Error ? err.message : "删除失败", true);
    }
  };

  const reveal = async () => {
    if (!dir()) return;
    try {
      await endpoints.reveal(dir());
    } catch (err) {
      props.notify(err instanceof Error ? err.message : "打开目录失败", true);
    }
  };

  return (
    <section>
      <div class="flex items-start gap-3">
        <div class="min-w-0 flex-1">
          <h2 class="text-[14px] font-semibold">技能</h2>
          <p class="mt-1 text-[11.5px] leading-5 text-faint">
            只管理你新增的技能；项目自带技能不受影响。保存后对新会话生效。
          </p>
        </div>
        <Button size="sm" variant="primary" onClick={openCreate}>
          ＋ 新增技能
        </Button>
      </div>

      <Show when={loading()}>
        <p class="mt-3 text-[11.5px] text-faint">读取中…</p>
      </Show>

      <Show when={!loading() && rows().length > 0}>
        <div class="mt-3 divide-y divide-line-soft rounded-lg border border-line-soft">
          <For each={rows()}>
            {(skill) => (
              <div class="flex items-start gap-3 px-3 py-2.5">
                <div class="min-w-0 flex-1">
                  <div class="flex flex-wrap items-center gap-2">
                    <code class="font-mono text-[11.5px] text-text">{skill.name}</code>
                    <Show when={!skill.valid}>
                      <Badge tone="warn">{skill.error || "格式不完整"}</Badge>
                    </Show>
                  </div>
                  <div class="mt-0.5 text-[10.5px] leading-4 text-faint">
                    {skill.description || "（没有描述，Pi 不会加载）"}
                  </div>
                  <div class="mt-0.5 text-[9.5px] text-faint">更新于 {skill.updated_at || "—"}</div>
                </div>
                <div class="flex shrink-0 items-center gap-1">
                  <Button size="sm" onClick={() => openEdit(skill)}>
                    编辑
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => void remove(skill)}>
                    删除
                  </Button>
                </div>
              </div>
            )}
          </For>
        </div>
      </Show>

      <Show when={!loading() && rows().length === 0}>
        <div class="mt-3 rounded-lg border border-dashed border-line-soft px-4 py-6 text-center">
          <p class="text-[11.5px] text-dim">还没有自定义技能</p>
          <p class="mt-1 text-[10.5px] text-faint">新增一个，告诉 agent 什么时候用、具体怎么做。</p>
          <Button size="sm" variant="primary" class="mt-3" onClick={openCreate}>
            ＋ 新增技能
          </Button>
        </div>
      </Show>

      <div class="mt-3 flex items-center gap-2">
        <Button size="sm" variant="ghost" disabled={!dir()} onClick={() => void reveal()}>
          在 Finder 显示
        </Button>
        <span class="min-w-0 truncate font-mono text-[9.5px] text-faint">{dir()}</span>
      </div>

      <Dialog open={open()} onOpenChange={setOpen} title={editing() ? "编辑技能" : "新增技能"}>
        <div class="space-y-3">
          <div>
            <label class="mb-1 block text-[10.5px] text-faint">技能名</label>
            <Input
              value={name()}
              placeholder="ad-hook"
              onInput={(event) => setName(event.currentTarget.value)}
            />
            <p class="mt-1 text-[9.5px] text-faint">小写字母、数字、连字符；最多 64 个字符。</p>
          </div>
          <div>
            <label class="mb-1 block text-[10.5px] text-faint">描述（何时使用）</label>
            <TextArea
              rows={2}
              value={description()}
              placeholder="当用户要写短视频开场钩子时使用"
              onInput={(event) => setDescription(event.currentTarget.value)}
            />
            <p class="mt-1 text-[9.5px] text-faint">模型只看到这段摘要，用它判断要不要加载。</p>
          </div>
          <div>
            <label class="mb-1 block text-[10.5px] text-faint">指令（Markdown）</label>
            <TextArea
              rows={14}
              value={instructions()}
              placeholder={"# 标题\n\n写清楚步骤、约束和示例。"}
              onInput={(event) => setInstructions(event.currentTarget.value)}
            />
            <p class="mt-1 text-[9.5px] text-faint">模型加载技能后读到的完整内容。</p>
          </div>
          <Show when={error()}>
            <div class="rounded-lg border border-bad/30 bg-bad/5 px-3 py-2 text-[11px] text-bad">{error()}</div>
          </Show>
          <div class="flex justify-end gap-2">
            <Button size="sm" variant="ghost" onClick={() => setOpen(false)}>
              取消
            </Button>
            <Button size="sm" variant="primary" loading={saving()} onClick={() => void save()}>
              保存
            </Button>
          </div>
        </div>
      </Dialog>
    </section>
  );
}
