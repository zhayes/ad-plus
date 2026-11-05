import type { JSX } from "solid-js";
import { splitProps } from "solid-js";
import Spinner from "./Spinner";

type Variant = "primary" | "ghost" | "subtle" | "danger";
type Size = "sm" | "md";

interface Props extends JSX.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
}

const base =
  "inline-flex items-center justify-center gap-1.5 rounded-lg font-medium transition-colors " +
  "disabled:cursor-default disabled:opacity-45 focus-visible:outline-2 focus-visible:outline-offset-2 " +
  "focus-visible:outline-accent";

const variants: Record<Variant, string> = {
  primary: "bg-gradient-to-br from-violet to-accent text-white hover:brightness-110",
  ghost: "text-dim hover:text-text hover:bg-surface-2",
  subtle: "border border-line bg-surface-2 text-text hover:border-line/80 hover:brightness-110",
  danger: "border border-bad/40 text-bad hover:bg-bad/10",
};

const sizes: Record<Size, string> = {
  sm: "h-7 px-2.5 text-[11.5px]",
  md: "h-9 px-3.5 text-[12.5px]",
};

export default function Button(props: Props) {
  const [local, rest] = splitProps(props, ["variant", "size", "loading", "class", "children", "disabled"]);
  const variant = () => local.variant ?? "subtle";
  const size = () => local.size ?? "md";

  return (
    <button
      {...rest}
      class={`${base} ${variants[variant()]} ${sizes[size()]} ${local.class ?? ""}`}
      disabled={local.disabled || local.loading}
    >
      {local.loading ? <Spinner size={12} /> : null}
      {local.children}
    </button>
  );
}

