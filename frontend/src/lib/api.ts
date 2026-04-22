import type {
  AppSettings,
  BlockRequest,
  BlockResponse,
  DebugStats,
  HealthResponse,
  ModelPresetsRegistry,
  ModelsRegistry,
  NetworkInterface,
  PipelineEvent,
  StreamSnapshot,
  UpdateApplyResult,
  UpdateCheckResult,
} from "../app/types";
import type {
  CreatePipelinePayload,
  ModelMeta,
  PipelineConfig,
  PreprocessorMeta,
  ValidateResponse,
} from "../types/plugins";

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
  getDebugStats: () => request<DebugStats>("/api/debug/stats"),
  getModelPresets: () => request<ModelPresetsRegistry>("/api/model-presets"),
  applyModelPreset: (presetId: string) =>
    request<AppSettings>(`/api/model-presets/apply/${presetId}`, {
      method: "POST",
      headers: jsonHeaders,
      body: "{}",
    }),
  checkUpdates: () => request<UpdateCheckResult>("/api/update/check"),
  applyUpdates: () => request<UpdateApplyResult>("/api/update/apply", { method: "POST" }),

  // ── Plugin API ─────────────────────────────────────────────────────────────
  getPluginPreprocessors: () => request<PreprocessorMeta[]>("/api/plugins/preprocessors"),
  getPluginModels: () => request<ModelMeta[]>("/api/plugins/models"),
  getPluginPipelines: () => request<PipelineConfig[]>("/api/plugins/pipelines"),
  createPluginPipeline: (payload: CreatePipelinePayload) =>
    request<PipelineConfig>("/api/plugins/pipelines", {
      method: "POST",
      headers: jsonHeaders,
      body: JSON.stringify(payload),
    }),
  deletePluginPipeline: (name: string) =>
    request<{ deleted: string }>(`/api/plugins/pipelines/${name}`, { method: "DELETE" }),
  validatePluginPipeline: (name: string) =>
    request<ValidateResponse>(`/api/plugins/pipelines/${name}/validate`, { method: "POST" }),
  reloadPlugins: () =>
    request<{ discovered: number; message: string }>("/api/plugins/reload", { method: "POST" }),
  getPluginFiles: () =>
    request<{ filename: string; size_bytes: number; is_example: boolean }[]>("/api/plugins/files"),
  uploadPluginFile: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<{ filename: string; size_bytes: number; discovered: number; message: string }>(
      "/api/plugins/upload", { method: "POST", body: form }
    );
  },
  deletePluginFile: (filename: string) =>
    request<{ deleted: string }>(`/api/plugins/files/${encodeURIComponent(filename)}`, { method: "DELETE" }),
  activatePluginPipeline: (pipelineName: string, currentSettings: AppSettings) =>
    request<AppSettings>("/api/settings", {
      method: "PUT",
      headers: jsonHeaders,
      body: JSON.stringify({ ...currentSettings, active_model_id: `plugin:${pipelineName}` }),
    }),
  restartService: () =>
    request<{ message: string; restart_scheduled: boolean }>("/api/update/restart", { method: "POST" }),
};
