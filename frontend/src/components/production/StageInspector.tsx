import { Show } from "solid-js";
import Badge from "../ui/Badge";
import type { ProductionView, StageRow } from "../../lib/types";

interface Props {
  production: ProductionView;
  stage: StageRow;
}

export default function StageInspector(props: Props) {
  const usd = (value: number) => `$${Math.max(0, Number(value || 0)).toFixed(2)}`;
  const remaining = () => Math.max(0, Number(props.production.budget_usd || 0) - Number(props.production.spent_usd || 0));
  const percent = () => Math.min(100, Math.round((Number(props.production.spent_usd || 0) / Math.max(0.01, Number(props.production.budget_usd || 2))) * 100));
  return (
    <aside class="w-full space-y-3">
      <div class="rounded-xl border border-line-soft bg-surface p-3">
        <div class="flex items-center gap-2">
          <span class="text-[10px] tracking-wide text-faint">当前阶段</span>
          <Badge tone={props.stage.status === "approved" ? "ok" : props.stage.status === "review" ? "warn" : "neutral"}>
            {props.stage.status === "approved" ? "已完成" : props.stage.status === "review" ? "待确认" : "进行中"}
          </Badge>
        </div>
        <div class="mt-1 text-[13px] font-medium text-text">{props.stage.label}</div>
        <div class="mt-1 text-[10.5px] leading-5 text-faint">{props.stage.summary}</div>
        <div class="mt-2 border-t border-line-soft pt-2">
          <div class="text-[9.5px] text-faint">产物</div>
          <div class="mt-0.5 truncate font-mono text-[9.5px] text-dim">{props.stage.artifact || "—"}</div>
          <Show when={props.stage.canonical_stage}>
            <div class="mt-0.5 text-[9px] text-faint">OpenMontage · {props.stage.canonical_stage} → {props.stage.canonical_artifact || "—"}</div>
            <Show when={props.stage.checkpoint_status}>
              <div class="mt-0.5 text-[9px] text-faint">checkpoint · {props.stage.checkpoint_status}</div>
            </Show>
          </Show>
        </div>
        <div class="mt-2 text-[10.5px] text-dim">下一步：{props.stage.action}</div>
      </div>

      <div class="rounded-xl border border-line-soft bg-surface p-3">
        <div class="flex items-center gap-2">
          <span class="text-[10px] tracking-wide text-faint">制作路线</span>
          <Badge tone="accent">{props.production.route.label}</Badge>
        </div>
        <div class="mt-2 space-y-1 text-[10.5px] text-faint">
          <div>pipeline：<span class="font-mono text-dim">{props.production.route.pipeline}</span></div>
          <div>runtime：<span class="font-mono text-dim">{props.production.route.runtime}</span></div>
          <div>成本：{props.production.route.cost_hint} · ETA {props.production.route.eta_hint}</div>
        </div>
        <div class="mt-2 text-[10px] leading-5 text-faint">{props.production.route.description}</div>
      </div>

      <div class="rounded-xl border border-line-soft bg-surface p-3">
        <div class="flex items-center gap-2">
          <span class="text-[10px] tracking-wide text-faint">预算</span>
          <span class="ml-auto font-mono text-[11px] text-text">{usd(props.production.spent_usd)} / {usd(props.production.budget_usd)}</span>
        </div>
        <div class="mt-2 h-1.5 overflow-hidden rounded-full bg-surface-2">
          <div class="h-full rounded-full bg-accent" style={{ width: `${percent()}%` }} />
        </div>
        <div class="mt-1 flex justify-between text-[9.5px] text-faint">
          <span>已花</span>
          <span>剩余 {usd(remaining())}</span>
        </div>
      </div>

      <div class="rounded-lg border border-line-soft bg-surface px-3 py-2 text-[9.5px] leading-5 text-faint">
        阶段状态从项目产物派生；确认后才会推进。
      </div>
      <Show when={props.production.preview_count > 0}>
        <div class="rounded-lg border border-line-soft bg-surface px-3 py-2 text-[9.5px] text-faint">
          已有 {props.production.preview_count} 个镜头素材
        </div>
      </Show>
    </aside>
  );
}
