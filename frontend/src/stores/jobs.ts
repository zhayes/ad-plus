/** Render/preview jobs, polled fast while something is running. */

import { createSignal } from "solid-js";
import { endpoints } from "../lib/api";
import { poll, stop } from "../lib/poller";
import type { Job } from "../lib/types";

const [jobs, setJobs] = createSignal<Job[]>([]);

export { jobs };

export function runningJobs(): Job[] {
  return jobs().filter((job) => job.status === "running");
}

export async function refreshJobs(): Promise<void> {
  try {
    const data = await endpoints.jobs();
    setJobs(data.jobs ?? []);
    const interval = (data.running ?? 0) > 0 ? 1200 : 4000;
    // re-arm with the right cadence; poll() replaces the previous timer
    poll("jobs", refreshJobs, interval);
  } catch {
    stop("jobs");
  }
}

export function watchJobs(): void {
  void refreshJobs();
}
