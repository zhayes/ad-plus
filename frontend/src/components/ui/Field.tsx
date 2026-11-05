import type { JSX } from "solid-js";
import { splitProps } from "solid-js";

interface Props extends JSX.TextareaHTMLAttributes<HTMLTextAreaElement> {
  onSubmit?: () => void;
}

/** Textarea that grows with its content, capped like the legacy composer. */
export default function Field(props: Props) {
  const [local, rest] = splitProps(props, ["onSubmit", "class", "onInput", "ref"]);
  let el: HTMLTextAreaElement | undefined;

  const resize = () => {
    if (!el) return;
    el.style.height = "58px";
    el.style.height = `${Math.min(220, Math.max(58, el.scrollHeight))}px`;
  };

  return (
    <textarea
      {...rest}
      ref={(node) => {
        el = node;
        resize();
        if (typeof local.ref === "function") local.ref(node);
      }}
      onInput={(event) => {
        resize();
        if (typeof local.onInput === "function") local.onInput(event);
      }}
      onKeyDown={(event) => {
        if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
          event.preventDefault();
          local.onSubmit?.();
        }
      }}
      class={`w-full resize-none bg-transparent text-[13px] leading-relaxed text-text outline-none placeholder:text-faint ${local.class ?? ""}`}
    />
  );
}
