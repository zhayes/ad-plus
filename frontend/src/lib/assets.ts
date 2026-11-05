/** Display labels for asset inventory records. */

export function kindLabel(kind: string): string {
  if (kind === "image") return "图片";
  if (kind === "video") return "视频";
  if (kind === "audio") return "音频";
  return "文件";
}

export function sourceLabel(source: string): string {
  if (source === "upload") return "上传";
  if (source === "project") return "项目素材";
  if (source === "render") return "成片";
  return source;
}
