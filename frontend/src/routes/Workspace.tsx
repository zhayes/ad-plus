import { Show, createEffect, createSignal, on, onCleanup, onMount } from "solid-js";
import { useNavigate, useParams } from "@solidjs/router";
import AppShell from "../components/layout/AppShell";
import ModuleDock from "../components/layout/ModuleDock";
import Rail from "../components/layout/Rail";
import Transcript from "../components/chat/Transcript";
import Composer from "../components/chat/Composer";
import AskDock from "../components/chat/AskDock";
import JobsPanel from "../components/panel/JobsPanel";
import ArtifactsPanel from "../components/panel/ArtifactsPanel";
import Select from "../components/ui/Select";
import { chatSocket } from "../lib/ws";
import { loadWorkspace, workspacePath } from "../lib/env";
import { api, endpoints } from "../lib/api";
import { poll, stop } from "../lib/poller";
import { sessions, currentId, selectSession, watchSessions } from "../stores/session";
import { addUserTurn, handleEvent, hydrateTranscript, resetTranscript, running, usage } from "../stores/transcript";
import { addAsk, refreshAsks } from "../stores/asks";
import { watchJobs } from "../stores/jobs";
import type { Approval, Artifact, Quote } from "../lib/types";

interface HistoryMessage {
  role: "user" | "assistant";
  text?: string;
  blocks?: Array<{
    kind: string;
    text?: string;
    name?: string;
    args?: string;
    result?: string;
    ok?: boolean;
    durationMs?: number;
  }>;
}
import { fmtUsd } from "../lib/format";

/* cwd comes from /api/bootstrap — no host path is baked into the bundle */

/* Module scope on purpose: the route remounts on navigation, and losing these
   would start a second session and drop the prompt that was queued before it. */
const started = new Map<string, string>();   // session id → "provider/model"
let pendingPrompt: string | null = null;
let loadedPath: string | null = null;

export default function Workspace() {
  const params = useParams();
  const navigate = useNavigate();

  const [railOpen, setRailOpen] = createSignal(false);
  const [panelOpen, setPanelOpen] = createSignal(false);
  const [artifacts, setArtifacts] = createSignal<Artifact[]>([]);
  const [model, setModel] = createSignal("deepseek-flash");
  const [provider, setProvider] = createSignal("deepseek");
  const [models, setModels] = createSignal([
    { value: "deepseek/deepseek-flash", label: "deepseek-flash", hint: "deepseek · deepseek-flash" },
  ]);

  const startSession = (id: string) => {
    const [prov, ...rest] = model().split("/");
    const modelName = rest.join("/") || model();
    const signature = `${prov}/${modelName}`;
    if (started.get(id) === signature) return;
    started.set(id, signature);
    chatSocket.send({
      action: "start",
      provider: prov || provider(),
      model: modelName,
      session_id: id,
      cwd: workspacePath(),
    });
  };

  const loadModels = async () => {
    try {
      const data = await api.get<{ models: { provider: string; model: string }[] }>("/api/pi/models");
      const options = (data.models ?? []).map((m) => ({
        value: `${m.provider}/${m.model}`,
        label: m.model,
        hint: `${m.provider} · ${m.model}`,
      }));
      if (!options.length) return;
      setModels(options);
      const [first] = options;
      if (first) {
        setModel(first.value);
        setProvider(first.value.split("/")[0] || "deepseek");
      }
    } catch {
      /* keep defaults */
    }
  };

  onMount(() => {
    void loadWorkspace();
    void loadModels();
    watchSessions();
    watchJobs();
    void refreshAsks();
    poll("asks", refreshAsks, 3000);
    chatSocket.connect();

    const off = chatSocket.on((event) => {
      const type = String(event.type ?? "");
      if (type === "quote_pending") {
        const record = event.record as Quote;
        if (record) addAsk({ id: record.id, kind: "quote", quote: record, project_id: record.project_id });
        return;
      }
      if (type === "gate_pending") {
        const record = event.record as Approval;
        if (record) addAsk({ id: record.id, kind: "gate", approval: record, project_id: record.project_id });
        return;
      }
      if (type === "session" && pendingPrompt) {
        const text = pendingPrompt;
        pendingPrompt = null;
        chatSocket.send({ action: "prompt", text });
        return;
      }
      handleEvent(event);
    });

    onCleanup(() => {
      off();
      stop("asks");
      // the socket is a singleton: keep it alive across route changes
    });
  });

  // the URL is the source of truth for which session is open
  createEffect(
    on(
      () => params.sessionId,
      (id) => {
        if (!id) return;
        selectSession(id);
        startSession(id);
      },
    ),
  );

  // artifacts follow the selected session
  createEffect(
    on(
      () => sessions().find((s) => s.id === currentId())?.path,
      async (path) => {
        if (!path) {
          setArtifacts([]);
          return;
        }
        try {
          const data = await endpoints.artifacts(`path=${encodeURIComponent(path)}`);
          setArtifacts((data as unknown as { files: Artifact[] }).files ?? []);
        } catch {
          /* keep quiet */
        }
        if (loadedPath !== path && !running()) {
          loadedPath = path;
          try {
            const history = await api.get<{ messages: HistoryMessage[] }>(
              `/api/sessions/messages?path=${encodeURIComponent(path)}&limit=400`,
            );
            hydrateTranscript(history.messages ?? []);
          } catch {
            /* history is best-effort */
          }
        }
      },
    ),
  );

  const send = (text: string, attachments: { name: string; path: string }[] = []) => {
    const withFiles = attachments.length
      ? `${text || "（见附件）"}\n\n${attachments.map((f) => `- ${f.path}`).join("\n")}`
      : text;
    addUserTurn(text || `（已上传 ${attachments.length} 个素材）`);
    const id = currentId();
    if (!id) {
      const fresh = `om-${Math.random().toString(36).slice(2, 10)}`;
      selectSession(fresh);
      pendingPrompt = withFiles;       // wait for the backend's `session` event
      navigate(`/chat/${fresh}`, { replace: true });
      startSession(fresh);
      return;
    }
    if (!started.has(id)) {
      pendingPrompt = withFiles;
      startSession(id);
      return;
    }
    chatSocket.send({ action: "prompt", text: withFiles });
  };

  const stopRun = () => chatSocket.send({ action: "abort" });

  const newChat = () => {
    resetTranscript();
    loadedPath = null;
    selectSession(null);
    setArtifacts([]);
    navigate("/chat", { replace: true });
  };

  const openSession = (id: string) => {
    if (id === currentId()) return;
    resetTranscript();
    setArtifacts([]);
    selectSession(id);
    navigate(`/chat/${id}`);
  };

  return (
    <div class="flex h-full flex-col">
      <div class="min-h-0 flex-1">
    <AppShell
      railOpen={railOpen()}
      panelOpen={panelOpen()}
      onToggleRail={() => setRailOpen((v) => !v)}
      onTogglePanel={() => setPanelOpen((v) => !v)}
      topbarRight={
        <Select
          value={model()}
          options={models()}
          onChange={(value) => {
            setModel(value);
            setProvider(value.split("/")[0] || "deepseek");
            const id = currentId();
            if (id) {
              started.delete(id);
              startSession(id);
            }
          }}
        />
      }
      rail={<Rail onNew={newChat} onSelect={openSession} />}
      panel={
        <div>
          <JobsPanel artifacts={artifacts()} />
          <ArtifactsPanel artifacts={artifacts()} />
        </div>
      }
    >
      <Transcript />
      <div class="shrink-0 px-4 pb-3">
        <AskDock />
        <Composer running={running()} onSend={send} onStop={stopRun} />
        <Show when={usage()}>
          {(totals) => (
            <div class="mx-auto w-full max-w-[760px] text-right font-mono text-[10.5px] text-faint">
              ↓{totals().input} ↑{totals().output} · {fmtUsd(totals().cost)}
            </div>
          )}
        </Show>
      </div>
    </AppShell>
      </div>
      <ModuleDock active="create" />
    </div>
  );
}
