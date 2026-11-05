import { Dialog as KDialog } from "@kobalte/core/dialog";
import type { JSX } from "solid-js";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title?: string;
  children: JSX.Element;
}

/** Kobalte stays behind this file — the business layer never imports it. */
export default function Dialog(props: Props) {
  return (
    <KDialog open={props.open} onOpenChange={props.onOpenChange}>
      <KDialog.Portal>
        <KDialog.Overlay class="fixed inset-0 z-40 bg-black/70 backdrop-blur-sm" />
        <div class="fixed inset-0 z-50 grid place-items-center p-6">
          <KDialog.Content class="w-full max-w-3xl rounded-xl border border-line-soft bg-surface p-4 shadow-2xl outline-none">
            <div class="mb-2 flex items-center gap-2">
              <KDialog.Title class="text-[13px] font-semibold text-text">{props.title}</KDialog.Title>
              <KDialog.CloseButton class="ml-auto rounded-md px-2 py-1 text-[11px] text-faint outline-none hover:text-text focus-visible:ring-1 focus-visible:ring-accent/60">
                关闭
              </KDialog.CloseButton>
            </div>
            {props.children}
          </KDialog.Content>
        </div>
      </KDialog.Portal>
    </KDialog>
  );
}
