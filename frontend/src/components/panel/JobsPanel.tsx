import { For, Show, createMemo } from "solid-js";
import { jobs, runningJobs } from "../../stores/jobs";
import { endpoints } from "../../lib/api";
import { basename, fmtDur } from "../../lib/format";
import type { Artifact } from "../../lib/types";
import Button from "../ui/Button";
import { CountBadge } from "../ui/Badge";

interface Props {
  /** Files this session actually produced; used to keep the panel scoped. */
  artifacts?: Artifact[];
}

/** Only this session's work: running jobs, plus finished ones whose output it owns. */
export default function JobsPanel(props: Props) {
  const rows = createMemo(() => {
    const owned = new Set((props.artifacts ?? []).map((a) => a.path));
    const running = runningJobs();
    const finished = jobs()
      .filter((job) => job.status !== "running")
      .filter((job) => !!job.output && owned.has(job.output))
      .slice(0, 2);
    return [...running, ...finished].slice(0, 4);
  });

  return (
    <Show when={rows().length > 0}>
      <div class="px-2 pt-3">
        <div class="flex items-center px-1 pb-1 text-[11px] text-dim">
          <b class="font-semibold">任务</b>
          <CountBadge value={rows().length} />
        </div>
        <For each={rows()}>
          {(job) => (
            <div class="mb-2 rounded-[10px] border border-line-soft bg-surface-2 p-2">
              <div class="flex items-center gap-2 text-[11.5px] text-dim">
                <span class="truncate font-mono text-text">{basename(job.output) || job.composition || job.kind}</span>
                <span class="ml-auto shrink-0 font-mono text-[10.5px] text-faint">
                  {job.status === "running" ? `${Math.round((job.progress || 0) * 100)}%` : job.status}
                </span>
              </div>
              <div class="my-1.5 h-1 overflow-hidden rounded bg-[#1b2030]">
                <i
                  class="block h-full bg-gradient-to-r from-violet to-accent transition-[width] duration-500"
                  classList={{
                    "bg-ok/80": job.status === "done",
                    "bg-bad/80": job.status === "failed",
                  }}
                  style={{ width: `${Math.round((job.progress || 0) * 100)}%` }}
                />
              </div>
              <div class="flex items-center gap-2 font-mono text-[10.5px] text-faint">
                <span>
                  {job.frames_done}/{job.frames_total || "?"} 帧
                </span>
                <span>{fmtDur(job.elapsed_seconds)}</span>
                <Show when={job.status === "running"}>
                  <Button
                    size="sm"
                    class="ml-auto !h-5 !px-1.5 !text-[10.5px]"
                    onClick={() => void endpoints.cancelJob(job.id, job.project_id)}
                  >
                    取消
                  </Button>
                </Show>
              </div>
            </div>
          )}
        </For>
      </div>
    </Show>
  );
}
