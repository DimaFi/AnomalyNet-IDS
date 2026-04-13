import type {
  AppSettings,
  BlockRequest,
  BlockResponse,
  HealthResponse,
  ModelPresetsRegistry,
  ModelsRegistry,
  NetworkInterface,
  PipelineEvent,
  StreamSnapshot
} from "../app/types";

const jsonHeaders = {
  "Content-Type": "application/json"
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return (await response.json()) as T;
}

export const api = {
  getHealth: () => request<HealthResponse>("/api/health"),
  getSettings: () => request<AppSettings>("/api/settings"),
  updateSettings: (payload: AppSettings) =>
    request<AppSettings>("/api/settings", {
      method: "PUT",
      headers: jsonHeaders,
      body: JSON.stringify(payload)
    }),
  getModels: () => request<ModelsRegistry>("/api/models"),
  selectModel: (modelId: string) =>
    request<ModelsRegistry>("/api/models/select", {
      method: "POST",
      headers: jsonHeaders,
      body: JSON.stringify({ model_id: modelId })
    }),
  getSnapshot: () => request<StreamSnapshot>("/api/stream/snapshot"),
  getHistory: () => request<PipelineEvent[]>("/api/history?limit=30"),
  blockIp: (ip: string, eventId?: string) =>
    request<BlockResponse>("/api/block", {
      method: "POST",
      headers: jsonHeaders,
      body: JSON.stringify({ ip_address: ip, event_id: eventId } as BlockRequest)
    }),
  getBlockedIps: () => request<{ count: number; items: { ip: string; blocked_at: string }[] }>("/api/blocked-ips"),
  unblockIp: (ip: string) => request<{ ip: string; unblocked: boolean }>(`/api/blocked-ips/${ip}`, { method: "DELETE" }),
  unblockAllIps: () => request<{ unblocked: number; message: string }>("/api/blocked-ips/all", { method: "DELETE" }),
  getInterfaces: () => request<NetworkInterface[]>("/api/interfaces"),
  getModelPresets: () => request<ModelPresetsRegistry>("/api/model-presets"),
  applyModelPreset: (presetId: string) =>
    request<AppSettings>(`/api/model-presets/apply/${presetId}`, {
      method: "POST",
      headers: jsonHeaders,
      body: "{}",
    })
};
