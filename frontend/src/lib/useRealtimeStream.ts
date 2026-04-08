import { useEffect } from "react";
import { useAppStore } from "../app/store";
import type { PipelineEvent } from "../app/types";
import { buildMockEvent, buildMockSnapshot } from "./mockRuntime";

export function useRealtimeStream(): void {
  const pushStreamItem = useAppStore((state) => state.pushStreamItem);
  const replaceStream  = useAppStore((state) => state.replaceStream);
  const addToast       = useAppStore((state) => state.addToast);

  useEffect(() => {
    const protocol = window.location.protocol === "https:" ? "wss" : "ws";
    const socket = new WebSocket(`${protocol}://${window.location.host}/ws/events`);
    let fallbackTimer: number | null = null;

    const handleItem = (item: PipelineEvent) => {
      pushStreamItem(item);
      // Show toast for non-normal events
      if (item.inference.label !== "normal" && item.alert) {
        addToast({
          level: item.inference.label,
          title: item.alert.title,
          details: item.inference.reason,
          src_ip: item.event.src_ip,
          event_id: item.event.event_id,
          attack_class: item.inference.attack_class ?? null,
        });
      }
    };

    const startFallback = () => {
      replaceStream(buildMockSnapshot(8).items);
      if (fallbackTimer === null) {
        fallbackTimer = window.setInterval(() => {
          const evt = buildMockEvent();
          handleItem(evt);
        }, 1600);
      }
    };

    socket.onmessage = (message) => {
      const payload = JSON.parse(message.data) as { items?: PipelineEvent[]; event?: unknown };
      if (Array.isArray(payload.items)) {
        replaceStream(payload.items);
      } else if (payload.event) {
        handleItem(payload as PipelineEvent);
      }
    };
    socket.onerror = () => startFallback();
    socket.onclose = () => startFallback();

    return () => {
      socket.close();
      if (fallbackTimer !== null) {
        window.clearInterval(fallbackTimer);
      }
    };
  }, [pushStreamItem, replaceStream, addToast]);
}
