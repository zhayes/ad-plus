import { For, Show } from "solid-js";
import Badge from "../ui/Badge";
import Button from "../ui/Button";
import { coverUrl, platformLabel, statusInfo } from "../../lib/projects";
import { fmtTime } from "../../lib/format";
import type { ProjectSummary } from "../../lib/types";

interface Props {
  projects: ProjectSummary[];
  onOpen: (id: string) => void;
  onOverview: (id: string) => void;
}

export default function ProjectTable(props: Props) {
  return (
    <div class="overflow-hidden rounded-xl border border-line-soft bg-surface">
      <table class="w-full border-collapse text-left">
        <thead class="border-b border-line-soft bg-surface-2/40">
          <tr class="text-[10px] text-faint">
            <th class="px-3 py-2 font-normal">项目</th>
            <th class="px-3 py-2 font-normal">阶段</th>
            <th class="hidden px-3 py-2 font-normal md:table-cell">平台 / 规格</th>
            <th class="hidden px-3 py-2 font-normal lg:table-cell">版本</th>
            <th class="hidden px-3 py-2 font-normal lg:table-cell">待办</th>
            <th class="hidden px-3 py-2 font-normal sm:table-cell">更新</th>
            <th class="px-3 py-2 text-right font-normal">操作</th>
          </tr>
        </thead>
        <tbody>
          <For each={props.projects}>
            {(project) => {
              const status = () => statusInfo(project.status);
              const cover = () => coverUrl(project.cover);
              return (
                <tr class="group border-b border-line-soft/70 last:border-0 hover:bg-surface-2/40">
                  <td class="max-w-[280px] px-3 py-2">
                    <button type="button" class="flex min-w-0 items-center gap-2.5 text-left" onClick={() => props.onOpen(project.id)}>
                      <span class="h-9 w-12 shrink-0 overflow-hidden rounded-md border border-line-soft bg-[#0b0e15]">
                        <Show when={cover()}>
                          <img src={cover()!} alt="" class="h-full w-full object-cover" loading="lazy" />
                        </Show>
                      </span>
                      <span class="min-w-0">
                        <span class="block truncate text-[12px] text-text">{project.title}</span>
                        <span class="mt-0.5 block truncate font-mono text-[9.5px] text-faint">{project.id}</span>
                      </span>
                    </button>
                  </td>
                  <td class="px-3 py-2">
                    <div class="flex flex-col items-start gap-1">
                      <Badge tone={status().tone}>{status().label}</Badge>
                      <span class="max-w-[120px] truncate text-[9.5px] text-faint">{project.stage_label || "—"}</span>
                    </div>
                  </td>
                  <td class="hidden px-3 py-2 text-[10.5px] text-dim md:table-cell">
                    {platformLabel(project.platform)} · {project.aspect} · {project.duration_s}s
                  </td>
                  <td class="hidden px-3 py-2 text-[10.5px] text-dim lg:table-cell">
                    {project.current_version_label ?? "—"} · {project.version_count} 版
                  </td>
                  <td class="hidden px-3 py-2 lg:table-cell">
                    <span class={project.pending_count > 0 ? "text-[10.5px] text-warn" : "text-[10.5px] text-faint"}>
                      {project.pending_count > 0 ? `${project.pending_count} 待办` : "—"}
                    </span>
                  </td>
                  <td class="hidden px-3 py-2 text-[10.5px] text-faint sm:table-cell">{fmtTime(project.updated) || "—"}</td>
                  <td class="px-3 py-2 text-right">
                    <div class="flex justify-end gap-1">
                      <Button size="sm" variant="ghost" onClick={() => props.onOverview(project.id)}>总览</Button>
                      <Button size="sm" variant="primary" onClick={() => props.onOpen(project.id)}>
                        {project.next_action || "打开"}
                      </Button>
                    </div>
                  </td>
                </tr>
              );
            }}
          </For>
        </tbody>
      </table>
    </div>
  );
}
