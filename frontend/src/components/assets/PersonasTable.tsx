import { For, Show, createMemo, createSignal, onMount } from "solid-js";
import { useNavigate } from "@solidjs/router";
import Badge from "../ui/Badge";
import Button from "../ui/Button";
import Input from "../ui/Input";
import { endpoints } from "../../lib/api";
import { mediaUrl } from "../../lib/projects";
import type { Persona } from "../../lib/types";

export default function PersonasTable() {
  const navigate = useNavigate();
  const [rows, setRows] = createSignal<Persona[]>([]);
  const [query, setQuery] = createSignal("");
  const [loading, setLoading] = createSignal(true);
  const [error, setError] = createSignal("");

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const data = await endpoints.personas();
      setRows(data.personas ?? []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "数字人加载失败");
    } finally {
      setLoading(false);
    }
  };
  onMount(() => void load());

  const filtered = createMemo(() => {
    const q = query().trim().toLowerCase();
    if (!q) return rows();
    return rows().filter((row) => `${row.name} ${row.description} ${(row.tags ?? []).join(" ")}`.toLowerCase().includes(q));
  });

  const cover = (persona: Persona) => persona.base_videos?.[0]?.path ?? persona.preview_path ?? persona.source_path ?? null;

  return (
    <div class="h-full overflow-auto px-5 py-4">
      <div class="mb-3 flex flex-wrap items-center gap-2">
        <div class="w-[260px]">
          <Input value={query()} placeholder="搜索数字人" onInput={(event) => setQuery(event.currentTarget.value)} />
        </div>
        <span class="text-[10.5px] text-faint">{filtered().length} 个数字人</span>
        <Button class="ml-auto" size="sm" variant="secondary" onClick={() => void load()}>刷新</Button>
      </div>

      <Show when={error()}>
        <div class="mb-3 rounded-lg border border-bad/30 bg-bad/5 px-3 py-2 text-[11px] text-bad">{error()}</div>
      </Show>

      <Show when={!loading()} fallback={<div class="py-16 text-center text-[11px] text-faint">加载中…</div>}>
        <Show when={filtered().length > 0} fallback={
          <div class="grid place-items-center rounded-xl border border-dashed border-line bg-surface/40 py-20 text-center">
            <div>
              <div class="text-[12px] text-dim">还没有数字人</div>
              <div class="mt-1 text-[10.5px] text-faint">先上传一张人像，再生成形象视频。</div>
              <Button class="mt-3" size="sm" variant="primary" onClick={() => navigate("/personas/new")}>新建数字人</Button>
            </div>
          </div>
        }>
          <div class="overflow-hidden rounded-xl border border-line-soft bg-surface">
            <table class="w-full text-left text-[11px]">
              <thead class="border-b border-line-soft text-[10px] text-faint">
                <tr>
                  <th class="px-3 py-2 font-normal">形象</th>
                  <th class="px-3 py-2 font-normal">数字人</th>
                  <th class="px-3 py-2 font-normal">形象视频</th>
                  <th class="px-3 py-2 font-normal">声音</th>
                  <th class="px-3 py-2 font-normal">状态</th>
                  <th class="px-3 py-2 font-normal">更新时间</th>
                  <th class="px-3 py-2 font-normal"></th>
                </tr>
              </thead>
              <tbody class="divide-y divide-line-soft">
                <For each={filtered()}>
                  {(persona) => (
                    <tr class="cursor-pointer transition-colors hover:bg-surface-2/60" onClick={() => navigate(`/personas/${persona.id}`)}>
                      <td class="px-3 py-2">
                        <Show when={cover(persona)} fallback={<span class="grid h-10 w-10 place-items-center rounded-md border border-line bg-surface-2 text-[10px] text-faint">人</span>}>
                          <img src={mediaUrl(cover(persona)) ?? undefined} alt="" class="h-10 w-10 rounded-md border border-line object-cover" />
                        </Show>
                      </td>
                      <td class="px-3 py-2">
                        <div class="font-medium text-text">{persona.name}</div>
                        <div class="mt-0.5 line-clamp-1 text-[9.5px] text-faint">{persona.description || persona.kind}</div>
                      </td>
                      <td class="px-3 py-2">
                        <Show when={(persona.base_videos ?? []).length > 0} fallback={<span class="text-[10px] text-warn">未生成</span>}>
                          <Badge tone="ok">{(persona.base_videos ?? []).length} 条</Badge>
                        </Show>
                      </td>
                      <td class="px-3 py-2 text-dim">{persona.voice?.voice_id || persona.voice?.provider || "—"}</td>
                      <td class="px-3 py-2"><Badge tone={persona.status === "ready" ? "ok" : "neutral"}>{persona.status === "ready" ? "可用" : persona.status}</Badge></td>
                      <td class="px-3 py-2 text-[10px] text-faint">{persona.updated_at?.slice(0, 16) ?? "—"}</td>
                      <td class="px-3 py-2 text-right">
                        <Button size="sm" variant="ghost" onClick={(event) => { event.stopPropagation(); navigate(`/personas/${persona.id}`); }}>编辑</Button>
                      </td>
                    </tr>
                  )}
                </For>
              </tbody>
            </table>
          </div>
        </Show>
      </Show>
    </div>
  );
}
