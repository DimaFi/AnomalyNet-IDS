import { useAppStore } from "../app/store";
import { api } from "./api";

export function useBlockIp() {
  const markBlocked = useAppStore((state) => state.markBlocked);

  return async (ip: string, eventId?: string): Promise<void> => {
    try {
      const result = await api.blockIp(ip, eventId);
      if (result.blocked || result.message) {
        markBlocked(ip);
      }
    } catch {
      // Silently fail — iptables unavailable (non-Linux or no privileges)
      markBlocked(ip); // Still mark in UI to avoid duplicate clicks
    }
  };
}
