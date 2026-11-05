import type { JSX } from "solid-js";
import { splitProps } from "solid-js";

interface Props extends JSX.InputHTMLAttributes<HTMLInputElement> {
  tone?: "default" | "password";
}

/** The one input style: same focus border + pink glow as the composer. */
export default function Input(props: Props) {
  const [local, rest] = splitProps(props, ["class", "tone"]);
  return (
    <input
      {...rest}
      class={
        "h-8 w-full rounded-lg border border-line bg-[#0b0e13] px-2.5 text-[12px] text-text outline-none " +
        "placeholder:text-faint transition-[border-color,box-shadow] duration-150 " +
        "focus:border-[#3a3f55] focus:shadow-[0_0_0_3px_rgba(224,51,138,0.10)] " +
        (local.tone === "password" ? "font-mono " : "") +
        (local.class ?? "")
      }
    />
  );
}
