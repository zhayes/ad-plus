/** Project presentation helpers: labels, tones, cover URLs. */

import type { ProjectStatus, RenderInfo } from "./types";

type Tone = "neutral" | "ok" | "warn" | "bad" | "accent";

const STATUS: Record<ProjectStatus, { label: string; tone: Tone }> = {
  draft: { label: "草稿", tone: "neutral" },
  briefing: { label: "补简报", tone: "warn" },
  quoted: { label: "方案待确认", tone: "accent" },
  storyboard: { label: "分镜编辑", tone: "accent" },
  producing: { label: "生成中", tone: "warn" },
  review: { label: "待审片", tone: "warn" },
  delivered: { label: "已交付", tone: "ok" },
  archived: { label: "已归档", tone: "neutral" },
};

export function statusInfo(status: string): { label: string; tone: Tone } {
  return STATUS[status as ProjectStatus] ?? { label: status || "草稿", tone: "neutral" };
}

const PLATFORM: Record<string, string> = {
  douyin: "抖音",
  xiaohongshu: "小红书",
  wechat_channels: "视频号",
  shorts: "Shorts",
  generic: "通用",
  other: "其他",
};

export function platformLabel(platform?: string | null): string {
  return PLATFORM[platform || ""] ?? platform ?? "通用";
}

const TIER: Record<string, string> = {
  draft: "草稿",
  standard: "标准",
  premium: "精修",
};

export function tierLabel(tier?: string | null): string {
  return TIER[tier || ""] ?? tier ?? "标准";
}

export function isVideo(path?: string | null): boolean {
  return !!path && /\.(mp4|mov|webm|m4v)$/i.test(path);
}

/** Cover can be a rendered video or an image; choose the right endpoint. */
export function coverUrl(cover?: string | null): string | null {
  if (!cover) return null;
  const path = encodeURIComponent(cover);
  return isVideo(cover) ? `/api/thumb?path=${path}&width=720` : `/api/media?path=${path}`;
}

export function mediaUrl(path?: string | null): string | null {
  return path ? `/api/media?path=${encodeURIComponent(path)}` : null;
}

export function renderCover(render?: RenderInfo | null): string | null {
  if (!render) return null;
  return coverUrl(render.poster || render.path);
}
