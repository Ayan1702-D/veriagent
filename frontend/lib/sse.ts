import { apiUrl } from "./api";
import type { StreamAuditPayload, StreamEndPayload } from "./types";

interface StreamHandlers {
  onAudit: (payload: StreamAuditPayload) => void;
  onEnd: (payload: StreamEndPayload) => void;
  onState?: (state: "connecting" | "live" | "reconnecting") => void;
  onError?: (message: string) => void;
}

export function subscribeToRun(runId: string, handlers: StreamHandlers): () => void {
  let source: EventSource | null = null;
  let retryTimer: ReturnType<typeof setTimeout> | null = null;
  let stopped = false;
  let attempts = 0;

  const connect = () => {
    if (stopped) return;
    handlers.onState?.(attempts === 0 ? "connecting" : "reconnecting");
    source = new EventSource(apiUrl(`/api/runs/${encodeURIComponent(runId)}/stream`));

    source.addEventListener("open", () => {
      attempts = 0;
      handlers.onState?.("live");
    });

    source.addEventListener("audit", (message) => {
      try {
        handlers.onAudit(JSON.parse((message as MessageEvent<string>).data));
      } catch {
        handlers.onError?.("Received an unreadable audit event.");
      }
    });

    source.addEventListener("end", (message) => {
      try {
        handlers.onEnd(JSON.parse((message as MessageEvent<string>).data));
      } catch {
        handlers.onError?.("The run ended with an unreadable response.");
      }
      stopped = true;
      source?.close();
    });

    source.onerror = () => {
      source?.close();
      if (stopped) return;
      attempts += 1;
      handlers.onState?.("reconnecting");
      const delay = Math.min(10_000, 750 * 2 ** Math.min(attempts, 4));
      retryTimer = setTimeout(connect, delay);
    };
  };

  connect();
  return () => {
    stopped = true;
    source?.close();
    if (retryTimer) clearTimeout(retryTimer);
  };
}
