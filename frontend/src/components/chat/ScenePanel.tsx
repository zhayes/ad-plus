import { For, Show, createSignal, onCleanup, onMount } from "solid-js";
import { useNavigate } from "@solidjs/router";
import Button from "../ui/Button";
import { endpoints, uploadAsset } from "../../lib/api";
import type { RecreateDetail } from "../../lib/types";

type Role = "user" | "assistant";
interface Message {
  role: Role;
  text: string;
  kind?: "text" | "result";
}

const STEP_LABELS: Record<string, string> = {
  analyze: "解析参考片",
  gag: "抽梗",
  script: "改脚本",
  board: "出分镜",
  shots: "生成画面",
  finish: "装配字幕",
};

const mediaUrl = (path?: string | null) => (path ? `/api/media?path=${encodeURIComponent(path)}` : "");

export default function ScenePanel() {
  const navigate = useNavigate();
  const [stage, setStage] = createSignal<"form" | "chat">("form");
  const [messages, setMessages] = createSignal<Message[]>([]);
  const [path, setPath] = createSignal("");
  const [videoName, setVideoName] = createSignal("");
  const [productImage, setProductImage] = createSignal("");
  const [productImageName, setProductImageName] = createSignal("");
  const [brief, setBrief] = createSignal("");
  const [duration, setDuration] = createSignal<"source" | "10" | "15">("source");
  const [resolution, setResolution] = createSignal<"480p" | "720p">("480p");
  const [fidelity, setFidelity] = createSignal<"effect" | "structure">("effect");
  const [gender, setGender] = createSignal<"male" | "female" | "mixed">("male");
  const [age, setAge] = createSignal<"young" | "middle" | "senior">("middle");
  const [build, setBuild] = createSignal<"slim" | "normal" | "sturdy">("normal");
  const [projectId, setProjectId] = createSignal("");
  const [detail, setDetail] = createSignal<RecreateDetail | null>(null);
  const [draft, setDraft] = createSignal("");
  const [busy, setBusy] = createSignal(false);
  const [error, setError] = createSignal("");
  let timer: number | undefined;

  const stopPolling = () => {
    if (timer) window.clearInterval(timer);
    timer = undefined;
  };
  onCleanup(stopPolling);

  const say = (text: string, kind: Message["kind"] = "text") =>
    setMessages((prev) => [...prev, { role: "assistant", text, kind }]);

  const parseProduct = (text: string) => {
    const amounts = [...text.matchAll(/(\d+(?:\.\d+)?)\s*元?/g)].map((m) => m[1]);
    const price = amounts[0] ?? "39.9";
    const promo = amounts[1] ?? "19.9";
    const firstLine = text.split(/[\n。；;]/)[0]?.trim() || "";
    const name = firstLine.length <= 14 ? firstLine : firstLine.slice(0, 14);
    return {
      name: name || "商品",
      price,
      promo_price: promo,
      brief: text.trim(),
    };
  };

  const upload = async (file: File, kind: "video" | "product") => {
    setError("");
    try {
      const asset = await uploadAsset(file);
      if (kind === "video") {
        setPath(asset.path);
        setVideoName(file.name);
      } else {
        setProductImage(asset.path);
        setProductImageName(file.name);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "上传失败");
    }
  };

  const poll = (id: string) => {
    stopPolling();
    let lastStage = "";
    timer = window.setInterval(async () => {
      try {
        const data = await endpoints.recreate(id);
        setDetail(data);
        const done = Object.entries(data.steps ?? {}).filter(([, step]) => step.status === "done").map(([key]) => key);
        const newest = done[done.length - 1];
        if (newest && newest !== lastStage) {
          lastStage = newest;
          say(`${STEP_LABELS[newest] ?? newest}完成`);
        }
        const states = Object.values(data.steps ?? {});
        if (states.length && states.every((step) => step.status === "done" || step.status === "failed")) {
          stopPolling();
          setBusy(false);
          if (states.some((step) => step.status === "failed")) {
            say("有一步失败了。点「查看详情」看卡在哪，也可以说「重来」再跑一次。");
          } else {
            say("成片好了。", "result");
          }
        }
      } catch {
        /* transient */
      }
    }, 3000);
  };

  const submit = async () => {
    if (!path()) {
      setError("先拖一条参考视频进来");
      return;
    }
    const parsed = parseProduct(brief() || "");
    setBusy(true);
    setError("");
    setStage("chat");
    setMessages([
      { role: "user", text: brief().trim() || `商品：${parsed.name}` },
      { role: "assistant", text: "开始跑：解析 → 抽梗 → 脚本 → 分镜 → 生成 → 装配。" },
    ]);
    try {
      const created = await endpoints.createRecreate({ path: path(), title: parsed.name, rights_confirmed: true });
      const id = created.recreate.project.project_id;
      setProjectId(id);
      setDetail(created.recreate);
      await endpoints.recreateOnetake(id, {
        product: {
          name: parsed.name,
          category: "零食",
          price: parsed.price,
          promo_price: parsed.promo_price,
          selling_points: ["追剧零食", "酥脆不油"],
          tone: "生活化",
          brief: parsed.brief,
          image: productImage() || undefined,
          cast_spec: { gender: gender(), age: age(), build: build(), count: 4 },
        },
        preset: {
          native_audio: true,
          resolution: resolution(),
          fidelity: fidelity(),
          duration: duration() === "source" ? undefined : Number(duration()),
        },
      });
      poll(id);
    } catch (err) {
      say(err instanceof Error ? err.message : "启动失败");
      setBusy(false);
    }
  };

  const rerun = async (text: string) => {
    if (!projectId()) return;
    setBusy(true);
    const parsed = parseProduct(text);
    const previous = () => {
      const base = detail()?.product ?? {};
      return { ...base, name: parsed.name, price: parsed.price, promo_price: parsed.promo_price, brief: parsed.brief };
    };
    try {
      await endpoints.recreateOnetake(projectId(), {
        product: previous(),
        preset: { native_audio: true, resolution: resolution(), fidelity: fidelity() },
      });
      poll(projectId());
    } catch (err) {
      say(err instanceof Error ? err.message : "重跑失败");
      setBusy(false);
    }
  };

  const send = async () => {
    const text = draft().trim();
    if (!text) return;
    setMessages((prev) => [...prev, { role: "user", text }]);
    setDraft("");
    if (/重来|再来|重跑/.test(text)) {
      void rerun(text);
      return;
    }
    say("目前支持「重来」重跑；改价格/换商品请在开始前填在输入框里。");
  };

  onMount(async () => {
    const pid = new URLSearchParams(window.location.search).get("project");
    if (!pid) return;
    try {
      const data = await endpoints.recreate(pid);
      setProjectId(pid);
      setDetail(data);
      setStage("chat");
      setMessages([{ role: "assistant", text: "这是这条任务的进度，成片在下面。" }]);
      const states = Object.values(data.steps ?? {});
      if (states.length && states.every((step) => step.status === "done" || step.status === "failed")) {
        say("成片好了。", "result");
      } else {
        setBusy(true);
        poll(pid);
      }
    } catch {
      /* ignore stale links */
    }
  });

  return (
    <div class="flex h-full min-h-0 flex-col">
      <Show when={stage() === "form"}>
        <div class="mx-auto w-full max-w-[760px] overflow-auto px-5 py-5">
          <div class="text-center">
            <div class="text-[15px] font-medium text-text">先选场景 · 爆款复刻</div>
            <div class="mt-1 text-[11px] text-faint">给一条参考片和商品，我直接出一条可投放的短视频</div>
          </div>

          <div class="mt-4 rounded-2xl border border-line bg-surface p-4">
            <div class="grid grid-cols-2 gap-3">
              <label class="flex h-[88px] cursor-pointer flex-col items-center justify-center rounded-xl border border-dashed border-line bg-surface-2 text-center hover:border-accent/60">
                <input type="file" accept="video/mp4,video/quicktime,video/webm" class="hidden" onChange={(e) => { const f = e.currentTarget.files?.[0]; if (f) void upload(f, "video"); e.currentTarget.value = ""; }} />
                <Show when={path()} fallback={<><span class="text-[18px] text-faint">＋</span><span class="text-[10.5px] text-faint">参考视频</span></>}>
                  <span class="text-[10.5px] text-ok">✓ {videoName().slice(0, 16)}</span>
                </Show>
              </label>
              <label class="flex h-[88px] cursor-pointer flex-col items-center justify-center rounded-xl border border-dashed border-line bg-surface-2 text-center hover:border-accent/60">
                <input type="file" accept="image/png,image/jpeg,image/webp" class="hidden" onChange={(e) => { const f = e.currentTarget.files?.[0]; if (f) void upload(f, "product"); e.currentTarget.value = ""; }} />
                <Show when={productImage()} fallback={<><span class="text-[18px] text-faint">＋</span><span class="text-[10.5px] text-faint">商品图（可选）</span></>}>
                  <span class="text-[10.5px] text-ok">✓ {productImageName().slice(0, 16)}</span>
                </Show>
              </label>
            </div>

            <textarea
              class="mt-3 h-[110px] w-full resize-none rounded-xl border border-line bg-surface-2 px-3 py-2 text-[12.5px] text-text outline-none focus:border-accent/60"
              placeholder="请输入产品信息、卖点、价格及修改要求，例如：原味鹰嘴豆，透明袋装，39.9 两袋 19.9，追剧零食，不要广告腔"
              value={brief()}
              onInput={(e) => setBrief(e.currentTarget.value)}
            />

            <div class="mt-3 flex flex-wrap items-center gap-2 text-[10.5px] text-faint">
              <select class="rounded-md border border-line bg-surface-2 px-2 py-1 text-text" value={duration()} onChange={(e) => setDuration(e.currentTarget.value as "source" | "10" | "15")}>
                <option value="source">时长跟随原片</option>
                <option value="10">10s</option>
                <option value="15">15s</option>
              </select>
              <select class="rounded-md border border-line bg-surface-2 px-2 py-1 text-text" value={resolution()} onChange={(e) => setResolution(e.currentTarget.value as "480p" | "720p")}>
                <option value="480p">480p 测试</option>
                <option value="720p">720p 交付</option>
              </select>
              <select class="rounded-md border border-line bg-surface-2 px-2 py-1 text-text" value={fidelity()} onChange={(e) => setFidelity(e.currentTarget.value as "effect" | "structure")}>
                <option value="effect">还原度：效果优先</option>
                <option value="structure">还原度：结构优先</option>
              </select>
              <label class="flex items-center gap-1">
                模特
                <select class="rounded-md border border-line bg-surface-2 px-1.5 py-1 text-text" value={gender()} onChange={(e) => setGender(e.currentTarget.value as "male" | "female" | "mixed")}>
                  <option value="male">男</option>
                  <option value="female">女</option>
                  <option value="mixed">男女混合</option>
                </select>
                <select class="rounded-md border border-line bg-surface-2 px-1.5 py-1 text-text" value={age()} onChange={(e) => setAge(e.currentTarget.value as "young" | "middle" | "senior")}>
                  <option value="young">青年</option>
                  <option value="middle">中年</option>
                  <option value="senior">老年</option>
                </select>
                <select class="rounded-md border border-line bg-surface-2 px-1.5 py-1 text-text" value={build()} onChange={(e) => setBuild(e.currentTarget.value as "slim" | "normal" | "sturdy")}>
                  <option value="slim">偏瘦</option>
                  <option value="normal">标准</option>
                  <option value="sturdy">偏壮</option>
                </select>
              </label>
              <div class="flex-1" />
              <Button size="sm" variant="primary" loading={busy()} onClick={() => void submit()}>开始复刻</Button>
            </div>
            <Show when={error()}>
              <div class="mt-2 text-[11px] text-bad">{error()}</div>
            </Show>
          </div>
        </div>
      </Show>

      <Show when={stage() === "chat"}>
        <div class="min-h-0 flex-1 space-y-3 overflow-auto px-4 py-4">
          <For each={messages()}>
            {(message) => (
              <div class={`flex ${message.role === "user" ? "justify-end" : "justify-start"}`}>
                <div class={`max-w-[78%] rounded-2xl px-3.5 py-2 text-[12.5px] leading-relaxed ${message.role === "user" ? "bg-accent text-white" : "border border-line bg-surface text-dim"}`}>
                  <div>{message.text}</div>
                  <Show when={message.kind === "result" && detail()?.files?.final}>
                    <div class="mt-2 w-[280px]">
                      <video class="w-full rounded-lg border border-line" src={mediaUrl(detail()?.files?.final)} controls preload="metadata" />
                      <div class="mt-2 flex gap-2">
                        <Button size="sm" variant="subtle" onClick={() => navigate(`/recreate/${projectId()}`)}>查看详情</Button>
                        <Button size="sm" variant="primary" onClick={() => window.open(mediaUrl(detail()?.files?.final) || "", "_blank")}>下载</Button>
                      </div>
                    </div>
                  </Show>
                </div>
              </div>
            )}
          </For>
          <Show when={busy()}>
            <div class="flex items-center gap-2 text-[11px] text-faint">
              <span class="h-1.5 w-1.5 animate-pulse rounded-full bg-warn" />
              后台在跑，可以在这里等
            </div>
          </Show>
        </div>
        <div class="shrink-0 px-4 pb-4">
          <div class="flex items-center gap-2">
            <input
              class="h-9 flex-1 rounded-xl border border-line bg-surface px-3 text-[12.5px] text-text outline-none focus:border-accent/60"
              placeholder="说「重来」再跑一次"
              value={draft()}
              onInput={(e) => setDraft(e.currentTarget.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  void send();
                }
              }}
            />
            <Button size="sm" variant="primary" onClick={() => void send()} loading={busy()}>发送</Button>
          </div>
        </div>
      </Show>
    </div>
  );
}
