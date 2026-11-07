import type { JSX } from "solid-js";

export type IconName =
  | "chevron-down"
  | "chevron-left"
  | "chevron-right"
  | "play"
  | "arrow-up"
  | "arrow-left"
  | "panel-left"
  | "panel-right"
  | "file-text"
  | "lightbulb"
  | "script"
  | "layout"
  | "image"
  | "film"
  | "check"
  | "route"
  | "folder"
  | "clapperboard"
  | "library"
  | "list-checks"
  | "settings"
  | "help"
  | "plus"
  | "more-horizontal"
  | "grid"
  | "list"
  | "layers"
  | "sparkles";

const paths: Record<IconName, () => JSX.Element> = {
  "chevron-down": () => <path d="M6 9l6 6 6-6" />,
  "chevron-left": () => <path d="M15 18l-6-6 6-6" />,
  "chevron-right": () => <path d="M9 6l6 6-6 6" />,
  play: () => <path d="M9 7l9 5-9 5z" fill="currentColor" stroke="none" />,
  "arrow-up": () => <path d="M12 19V5M5 12l7-7 7 7" />,
  "panel-left": () => (
    <>
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <path d="M9 4v16" />
    </>
  ),
  "panel-right": () => (
    <>
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <path d="M15 4v16" />
    </>
  ),
  "arrow-left": () => <path d="M19 12H5M12 19l-7-7 7-7" />,
  "file-text": () => (
    <>
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <path d="M14 2v6h6M8 13h8M8 17h6" />
    </>
  ),
  lightbulb: () => (
    <>
      <path d="M9 18h6M10 22h4" />
      <path d="M12 2a7 7 0 0 0-4 12.7V17h8v-2.3A7 7 0 0 0 12 2z" />
    </>
  ),
  script: () => (
    <>
      <path d="M4 4h12l4 4v12H4z" />
      <path d="M8 9h8M8 13h8M8 17h5" />
    </>
  ),
  layout: () => (
    <>
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <path d="M3 10h18M10 10v10" />
    </>
  ),
  image: () => (
    <>
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <circle cx="9" cy="9" r="1.5" />
      <path d="M21 15l-5-5L5 21" />
    </>
  ),
  film: () => (
    <>
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <path d="M7 4v16M17 4v16M3 9h4M17 9h4M3 15h4M17 15h4" />
    </>
  ),
  check: () => <path d="M20 6L9 17l-5-5" />,
  route: () => (
    <>
      <circle cx="6" cy="19" r="2" />
      <circle cx="18" cy="5" r="2" />
      <path d="M8 19h6a3 3 0 0 0 3-3V7" />
    </>
  ),
  folder: () => <path d="M3 7a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />,
  clapperboard: () => (
    <>
      <path d="M3 8h18v12H3z" />
      <path d="M3 8l3-4 4 4 3-4 4 4 3-4" />
    </>
  ),
  library: () => (
    <>
      <rect x="4" y="3" width="4" height="18" rx="1" />
      <rect x="10" y="3" width="4" height="18" rx="1" />
      <path d="M17 4l3 1-4 16-3-1z" />
    </>
  ),
  "list-checks": () => (
    <>
      <path d="M10 6h11M10 12h11M10 18h11" />
      <path d="M3 6l1.5 1.5L7 5M3 12l1.5 1.5L7 11M3 18l1.5 1.5L7 17" />
    </>
  ),
  settings: () => (
    <>
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09a1.65 1.65 0 0 0 1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33h.09a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51h.09a1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82v.09a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
    </>
  ),
  help: () => (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M9.5 9a2.5 2.5 0 1 1 4 2c-.9.6-1.5 1.2-1.5 2.5" />
      <path d="M12 17h.01" />
    </>
  ),
  plus: () => <path d="M12 5v14M5 12h14" />,
  "more-horizontal": () => (
    <>
      <circle cx="5" cy="12" r="1" fill="currentColor" />
      <circle cx="12" cy="12" r="1" fill="currentColor" />
      <circle cx="19" cy="12" r="1" fill="currentColor" />
    </>
  ),
  grid: () => (
    <>
      <rect x="3" y="3" width="7" height="7" rx="1" />
      <rect x="14" y="3" width="7" height="7" rx="1" />
      <rect x="3" y="14" width="7" height="7" rx="1" />
      <rect x="14" y="14" width="7" height="7" rx="1" />
    </>
  ),
  list: () => <path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01" />,
  layers: () => (
    <>
      <path d="M12 2L2 7l10 5 10-5-10-5z" />
      <path d="M2 17l10 5 10-5M2 12l10 5 10-5" />
    </>
  ),
  sparkles: () => (
    <>
      <path d="M12 3l1.8 4.2L18 9l-4.2 1.8L12 15l-1.8-4.2L6 9l4.2-1.8z" />
      <path d="M19 15l.8 1.9L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-1.1z" />
    </>
  ),
};

interface Props {
  name: IconName;
  size?: number;
  class?: string;
}

/** One icon set for the whole app — no more text glyphs like "▾" standing in for icons. */
export default function Icon(props: Props) {
  const size = () => props.size ?? 14;
  return (
    <svg
      viewBox="0 0 24 24"
      width={size()}
      height={size()}
      fill="none"
      stroke="currentColor"
      stroke-width="1.9"
      stroke-linecap="round"
      stroke-linejoin="round"
      class={`shrink-0 ${props.class ?? ""}`}
      aria-hidden="true"
    >
      {paths[props.name]()}
    </svg>
  );
}
