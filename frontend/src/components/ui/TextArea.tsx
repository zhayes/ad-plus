import type { JSX } from "solid-js";
import { splitProps } from "solid-js";

interface Props extends JSX.TextareaHTMLAttributes<HTMLTextAreaElement> {}

/** Multi-line variant of Input — same focus treatment, fixed height by default. */
export default function TextArea(props: Props) {
  const [local, rest] = splitProps(props, ["class"]);
  return (
    <textarea
      {...rest}
      class={
        "w-full resize-none rounded-lg border border-line bg-[#0b0e13] px-2.5 py-2 text-[12px] text-text outline-none " +
        "placeholder:text-faint transition-[border-color,box-shadow] duration-150 " +
        "focus:border-[#3a3f55] focus:shadow-[0_0_0_3px_rgba(224,51,138,0.10)] " +
        (local.class ?? "")
      }
    />
  );
}
