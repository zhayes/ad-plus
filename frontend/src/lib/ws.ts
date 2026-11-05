/** WebSocket client: one socket, auto-reconnect, typed fan-out. */

import type { WsEvent } from "./types";

type Handler = (event: WsEvent) => void;

/** Debug trail: window.__adws in devtools (cheap enough to keep). */
function trace(entry: Record<string, unknown>): void {
  const store = (window as unknown as { __adws?: unknown[] }).__adws ?? [];
  store.push({ t: Date.now(), ...entry });
  (window as unknown as { __adws?: unknown[] }).__adws = store.slice(-60);
}

export class ChatSocket {
  private socket: WebSocket | null = null;
  private handlers = new Set<Handler>();
  private retry = 0;
  private closed = false;
  private timer: number | undefined;

  on(handler: Handler): () => void {
    this.handlers.add(handler);
    return () => this.handlers.delete(handler);
  }

  connect(): void {
    if (this.socket && this.socket.readyState <= WebSocket.OPEN) return;
    this.closed = false;
    const url = `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/chat`;
    trace({ dir: "connect", url });
    const socket = new WebSocket(url);
    this.socket = socket;

    socket.onopen = () => {
      this.retry = 0;
      trace({ dir: "open" });
    };
    socket.onmessage = (message) => {
      let event: WsEvent;
      try {
        event = JSON.parse(message.data as string) as WsEvent;
      } catch {
        return;
      }
      for (const handler of this.handlers) handler(event);
    };
    socket.onclose = () => {
      this.socket = null;
      if (this.closed) return;
      const delay = Math.min(8000, 500 * 2 ** this.retry++);
      this.timer = window.setTimeout(() => this.connect(), delay);
    };
    socket.onerror = () => {
      trace({ dir: "error" });
      socket.close();
    };
  }

  send(payload: unknown): void {
    trace({ dir: "send-attempt", state: this.socket?.readyState ?? -1, payload });
    if (this.socket?.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify(payload));
      return;
    }
    this.connect();
    const attempt = () => {
      if (this.socket?.readyState === WebSocket.OPEN) this.socket.send(JSON.stringify(payload));
      else window.setTimeout(attempt, 250);
    };
    window.setTimeout(attempt, 250);
  }

  close(): void {
    this.closed = true;
    window.clearTimeout(this.timer);
    this.socket?.close();
    this.socket = null;
  }
}

export const chatSocket = new ChatSocket();
