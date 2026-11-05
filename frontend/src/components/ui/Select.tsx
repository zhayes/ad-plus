import { Select as KSelect } from "@kobalte/core/select";
import Icon from "./Icon";

export interface Option {
  value: string;
  label: string;
  hint?: string;
}

interface Props {
  value: string;
  options: Option[];
  onChange: (value: string) => void;
  class?: string;
  placeholder?: string;
  /** `ghost` = text + chevron only (top bar); `pill` = bordered chip (settings). */
  variant?: "ghost" | "pill";
}

export default function Select(props: Props) {
  const current = () => props.options.find((o) => o.value === props.value);

  return (
    <KSelect
      value={current()}
      options={props.options}
      optionValue="value"
      optionTextValue="label"
      onChange={(option: Option | null) => option && props.onChange(option.value)}
      placeholder={props.placeholder ?? "选择"}
      itemComponent={(itemProps) => (
        <KSelect.Item
          item={itemProps.item}
          class="flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-[12px] text-dim outline-none data-[highlighted]:bg-surface-2 data-[selected]:text-text"
        >
          <KSelect.ItemLabel>{itemProps.item.rawValue.label}</KSelect.ItemLabel>
        </KSelect.Item>
      )}
    >
      <KSelect.Trigger
        class={`flex h-8 items-center gap-1 rounded-md px-2 text-[12px] text-dim outline-none transition-colors hover:bg-surface-2 hover:text-text focus-visible:bg-surface-2 ${props.variant === "pill" ? "border border-line bg-surface px-3" : ""} ${props.class ?? ""}`}
      >
        <KSelect.Value<Option>>
          {(state) => (
            <span class="text-text">
              {state.selectedOption()?.hint ?? state.selectedOption()?.label ?? props.placeholder}
            </span>
          )}
        </KSelect.Value>
        <KSelect.Icon class="text-faint">
          <Icon name="chevron-down" size={13} />
        </KSelect.Icon>
      </KSelect.Trigger>
      <KSelect.Portal>
        <KSelect.Content class="z-50 min-w-[180px] rounded-lg border border-line-soft bg-surface p-1 shadow-xl outline-none">
          <KSelect.Listbox />
        </KSelect.Content>
      </KSelect.Portal>
    </KSelect>
  );
}
