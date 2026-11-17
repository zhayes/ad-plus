import { useNavigate, useParams } from "@solidjs/router";
import AppShellV2 from "../components/layout/AppShellV2";
import PersonasPanel from "../components/assets/PersonasPanel";
import Button from "../components/ui/Button";

export default function PersonaEditor() {
  const params = useParams();
  const navigate = useNavigate();
  const personaId = params.personaId ?? "new";

  return (
    <AppShellV2
      module="assets"
      context={
        <div class="flex items-center gap-2">
          <span class="text-[13px] font-semibold text-text">数字人</span>
          <span class="rounded border border-line px-1 py-px text-[10px] text-faint">形象视频</span>
        </div>
      }
      primary={
        <Button size="sm" variant="ghost" onClick={() => navigate("/assets/personas")}>
          返回列表
        </Button>
      }
      footer={<span class="text-[10px] text-faint">数字人 · 一次生成，项目复用</span>}
    >
      <PersonasPanel
        initialId={personaId}
        hideList
        onClose={() => navigate("/assets/personas")}
      />
    </AppShellV2>
  );
}
