/** Pure storyboard math shared by optimistic UI and tests. */

export interface TimedShot {
  id: string;
  duration_s: number;
  start_s: number;
  end_s: number;
  index: number;
}

/** Move `fromId` next to `toId` (before/after), preserving every other shot. */
export function moveShot<T extends { id: string }>(
  shots: T[],
  fromId: string,
  toId: string,
  after: boolean,
): T[] {
  if (fromId === toId) return shots;
  const fromIndex = shots.findIndex((shot) => shot.id === fromId);
  const targetIndex = shots.findIndex((shot) => shot.id === toId);
  if (fromIndex < 0 || targetIndex < 0) return shots;
  const next = [...shots];
  const [item] = next.splice(fromIndex, 1);
  let insert = next.findIndex((shot) => shot.id === toId);
  if (insert < 0) insert = next.length;
  if (after) insert += 1;
  next.splice(insert, 0, item);
  return next;
}

const round = (value: number): number => Math.round(value * 1000) / 1000;

/** Rebuild index/start/end from the array order; durations are preserved. */
export function recomputeTimeline<T extends TimedShot>(shots: T[]): T[] {
  let cursor = 0;
  return shots.map((shot, index) => {
    const duration = Math.max(0.2, round(Number(shot.duration_s) || 2.5));
    const next = {
      ...shot,
      index: index + 1,
      start_s: round(cursor),
      end_s: round(cursor + duration),
      duration_s: duration,
    };
    cursor += duration;
    return next;
  });
}

export function totalDuration(shots: { duration_s: number }[]): number {
  return round(shots.reduce((sum, shot) => sum + Math.max(0.2, Number(shot.duration_s) || 0), 0));
}

export function timecode(seconds: number): string {
  const safe = Math.max(0, seconds);
  const minutes = Math.floor(safe / 60);
  const rest = (safe % 60).toFixed(1).padStart(4, "0");
  return `${minutes}:${rest}`;
}
