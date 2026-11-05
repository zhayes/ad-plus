/** One place that owns intervals, so nothing leaks when a view unmounts. */

type Task = () => void | Promise<void>;

const timers = new Map<string, number>();

export function poll(key: string, task: Task, intervalMs: number): void {
  stop(key);
  const tick = () => {
    void task();
    timers.set(key, window.setTimeout(tick, intervalMs));
  };
  tick();
}

export function stop(key: string): void {
  const id = timers.get(key);
  if (id !== undefined) {
    window.clearTimeout(id);
    timers.delete(key);
  }
}

export function stopAll(): void {
  for (const [key, id] of timers) {
    window.clearTimeout(id);
    timers.delete(key);
  }
}
