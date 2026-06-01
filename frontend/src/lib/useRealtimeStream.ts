import { useEffect, useRef } from "react";
import { useAppStore } from "../app/store";
import type { PipelineEvent } from "../app/types";
import { api, remoteKey } from "./api";

const POLL_INTERVAL_MS = 5000; // fallback snapshot poll every 5s

/**
 * Subscribes to the backend WebSocket (/ws/events) and keeps the stream store in sync.
 * No mock fallback — all events come from the backend (which handles mock mode itself).
 * On disconnect → exponential backoff reconnect (1s → 2s → 4s → ... → 30s max).
 * Also polls /api/snapshot every 5s as a fallback to catch any missed events.
 */
export function useRealtimeStream(): void {
  const pushStreamItem   = useAppStore((state) => state.pushStreamItem);
  const replaceStream    = useAppStore((state) => state.replaceStream);
  const addToast         = useAppStore((state) => state.addToast);
  const serviceStopped   = useAppStore((state) => state.serviceStopped);

  const socketRef    = useRef<WebSocket | null>(null);
  const retryDelay   = useRef(1000);
  const retryTimer   = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pollTimer    = useRef<ReturnType<typeof setInterval> | null>(null);
  const destroyed    = useRef(false);
  const stoppedRef   = useRef(false);

  // Sync stopped state to ref so inner callbacks can read it without stale closure
  useEffect(() => {
    stoppedRef.current = serviceStopped;
    if (serviceStopped) {
      if (retryTimer.current !== null) { clearTimeout(retryTimer.current); retryTimer.current = null; }
      if (pollTimer.current  !== null) { clearInterval(pollTimer.current);  pollTimer.current = null; }
      socketRef.current?.close();
      socketRef.current = null;
    }
  }, [serviceStopped]);

  useEffect(() => {
    destroyed.current = false;
    retryDelay.current = 1000;

    const handleItem = (item: PipelineEvent) => {
      pushStreamItem(item);
      if (item.inference.label !== "normal" && item.alert) {
        addToast({
          level:        item.inference.label,
          title:        item.alert.title,
          details:      item.inference.reason,
          src_ip:       item.event.src_ip,
          event_id:     item.event.event_id,
          attack_class: item.inference.attack_class ?? null,
        });
      }
    };

    function connect() {
      if (destroyed.current || stoppedRef.current) return;

      const protocol = window.location.protocol === "https:" ? "wss" : "ws";
      const key = remoteKey();
      const qs = key ? `?key=${encodeURIComponent(key)}` : "";
      const ws = new WebSocket(`${protocol}://${window.location.host}/ws/events${qs}`);
      socketRef.current = ws;

      ws.onmessage = (msg) => {
        retryDelay.current = 1000;
        try {
          const payload = JSON.parse(msg.data) as { type?: string; items?: PipelineEvent[]; event?: unknown };
          if (payload.type === "ping") return;
          if (Array.isArray(payload.items)) {
            replaceStream(payload.items);
          } else if (payload.event) {
            handleItem(payload as PipelineEvent);
          }
        } catch {
          // malformed JSON — skip
        }
      };

      ws.onerror = () => { /* always followed by onclose */ };

      ws.onclose = () => {
        socketRef.current = null;
        if (destroyed.current || stoppedRef.current) return;
        const delay = retryDelay.current;
        retryDelay.current = Math.min(delay * 2, 30_000);
        retryTimer.current = setTimeout(connect, delay);
      };
    }

    connect();

    pollTimer.current = setInterval(() => {
      if (destroyed.current || stoppedRef.current) return;
      api.getSnapshot().then((snap) => {
        if (!destroyed.current && !stoppedRef.current) replaceStream(snap.items);
      }).catch(() => { /* server unreachable — skip */ });
    }, POLL_INTERVAL_MS);

    return () => {
      destroyed.current = true;
      socketRef.current?.close();
      socketRef.current = null;
      if (retryTimer.current !== null) { clearTimeout(retryTimer.current); retryTimer.current = null; }
      if (pollTimer.current  !== null) { clearInterval(pollTimer.current);  pollTimer.current = null; }
    };
  }, [pushStreamItem, replaceStream, addToast]);
}

/**
 * Called by the Refresh button in StreamView.
 */
export async function refreshStreamFromSnapshot(
  replaceStream: (items: PipelineEvent[]) => void
): Promise<void> {
  try {
    const snapshot = await api.getSnapshot();
    replaceStream(snapshot.items);
  } catch {
    // backend unreachable — leave stream as is
  }
}
