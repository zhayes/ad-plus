import { Tabs as KTabs } from "@kobalte/core/tabs";
import type { JSX } from "solid-js";

interface Props {
  value: string;
  onChange: (value: string) => void;
  tabs: { value: string; label: string }[];
  children: JSX.Element;
}

export default function Tabs(props: Props) {
  return (
    <KTabs value={props.value} onChange={props.onChange} class="flex h-full flex-col">
      <KTabs.List class="flex gap-1 border-b border-line-soft px-2">
        {props.tabs.map((tab) => (
          <KTabs.Trigger
            value={tab.value}
            class="rounded-t-md px-2.5 py-1.5 text-[11.5px] text-faint outline-none data-[selected]:text-text data-[selected]:shadow-[inset_0_-2px_0_var(--color-accent)]"
          >
            {tab.label}
          </KTabs.Trigger>
        ))}
      </KTabs.List>
      <KTabs.Content value={props.value} class="flex-1 overflow-auto">
        {props.children}
      </KTabs.Content>
    </KTabs>
  );
}
