import type { JSX } from "solid-js";
import { splitProps } from "solid-js";

interface Props extends JSX.HTMLAttributes<HTMLDivElement> {
  tone?: "plain" | "accent";
}

export default function Card(props: Props) {
  const [local, rest] = splitProps(props, ["tone", "class", "children"]);
  const tone =
    local.tone === "accent"
      ? "border-[#33304a] bg-gradient-to-b from-[#161327] to-[#111318]"
      : "border-line-soft bg-surface";
  return (
    <div {...rest} class={`rounded-xl border ${tone} ${local.class ?? ""}`}>
      {local.children}
    </div>
  );
}
