/** Shared formatting helpers — the legacy page had three copies of these. */

export function fmtTime(seconds?: number | null): string {
  if (!seconds) return "";
  const date = new Date(seconds * 1000);
  const now = new Date();
  const hm = date.toTimeString().slice(0, 5);
  // same day → "23:42", older → "11月4日 23:42"
  return date.toDateString() === now.toDateString()
    ? hm
    : `${date.getMonth() + 1}月${date.getDate()}日 ${hm}`;
}

export function fmtBytes(n?: number | null): string {
  const value = Number(n || 0);
  if (value <= 0) return "0";
  if (value < 1024) return `${value}B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(0)}K`;
  if (value < 1024 * 1024 * 1024) return `${(value / 1024 / 1024).toFixed(1)}M`;
  return `${(value / 1024 / 1024 / 1024).toFixed(2)}G`;
}

export function fmtEta(seconds?: number | null): string {
  const minutes = Math.round(Number(seconds || 0) / 60);
  if (minutes < 60) return `${minutes} 分钟`;
  return `${Math.floor(minutes / 60)} 小时 ${minutes % 60} 分`;
}

export function fmtDur(seconds?: number | null): string {
  const s = Math.max(0, Math.round(Number(seconds || 0)));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

/** Tool/thinking durations: ms below a second, one decimal above, m:ss beyond. */
export function fmtStepTime(seconds?: number | null): string {
  if (seconds === undefined || seconds === null) return "";
  const ms = seconds * 1000;
  if (ms < 1000) return `${Math.round(ms)}ms`;
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  return fmtDur(seconds);
}

export function fmtUsd(value?: number | null): string {
  const n = Number(value || 0);
  return n > 0 ? `$${n.toFixed(2)}` : "—";
}

export function basename(path?: string | null): string {
  return (path || "").split("/").pop() || "";
}
