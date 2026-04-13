import { useEffect, useRef } from "react";
import { useAppStore } from "../app/store";
import type { PipelineEvent } from "../app/types";
import { api } from "./api";
import { buildMockEvent, buildMockSnapshot } from "./mockRuntime";

/**
 * Subscribes to the backend WebSocket (/ws/events) and keeps the stream store in sync.
 *
 * Live mode (linux_live / linux_stub / windows_stub):
 *   – No mock data ever. On disconnect → empty stream + reconnect with exponential backoff.
 *   – On reconnect → backend sends snapshot of last 30 real events immediately.
 *
 * Mock mode:
 *   – Uses mock snapshot + polling fallback (original behaviour).
 */
export function useRealtimeStream(): void {
  const pushStreamItem = useAppStore((state) => state.pushStreamItem);
  const replaceStream  = useAppStore((state) => state.replaceStream);
  const addToast       = useAppStore((state) => state.addToast);

  // Expose a way for StreamView's Refresh button to re-fetch the snapshot
  const socketRef     = useRef<WebSocket | null>(null);
  const retryDelay    = useRef(1000);
  const retryTimer    = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mockTimer     = useRef<ReturnType<typeof setInterval> | null>(null);
  const destroyed     = useRef(false);

  useEffect(() => {
    destroyed.current = false;

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

    function isMockMode(): boolean {
      const settings = useAppStore.getState().settings;
      return !settings || settings.run_mode === "mock";
    }

    function startMockFallback() {
      if (mockTimer.current !== null) return; // already running
      replaceStream(buildMockSnapshot(8).items);
      mockTimer.current = setInterval(() => {
        handleItem(buildMockEvent());
      }, 1600);
    }

    function stopMockFallback() {
      if (mockTimer.current !== null) {
        clearInterval(mockTimer.current);
        mockTimer.current = null;
      }
    }

    function connect() {
      if (destroyed.current) return;

      if (isMockMode()) {
        startMockFallback();
        return;
      }

      // Live mode — real WebSocket, no mock
      stopMockFallback();

      const protocol = window.location.protocol === "https:" ? "wss" : "ws";
      const ws = new WebSocket(`${protocol}://${window.location.host}/ws/events`);
      socketRef.current = ws;

      ws.onmessage = (msg) => {
        retryDelay.current = 1000; // reset backoff on successful message
        try {
          const payload = JSON.parse(msg.data) as { items?: PipelineEvent[]; event?: unknown };
          if (Array.isArray(payload.items)) {
            replaceStream(payload.items);
          } else if (payload.event) {
            handleItem(payload as PipelineEvent);
          }
        } catch {
          // malformed JSON — skip
        }
      };

      ws.onerror = () => {
        // error is always followed by close, handle in onclose
      };

      ws.onclose = () => {
        socketRef.current = null;
        if (destroyed.current) return;
        // Do NOT replace stream with mock. Just schedule reconnect.
        const delay = retryDelay.current;
        retryDelay.current = Math.min(delay * 2, 30_000); // exponential backoff, max 30s
        retryTimer.current = setTimeout(connect, delay);
      };
    }

    connect();

    return () => {
      destroyed.current = true;
      socketRef.current?.close();
      socketRef.current = null;
      if (retryTimer.current !== null) {
        clearTimeout(retryTimer.current);
        retryTimer.current = null;
      }
      stopMockFallback();
    };
  }, [pushStreamItem, replaceStream, addToast]);
}

/**
 * Called by the Refresh button in StreamView.
 * Re-fetches the latest snapshot from the REST endpoint (no WS needed).
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
