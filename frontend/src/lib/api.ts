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
    let detail = `HTTP ${response.status}`;
    try {
      const err = await response.json() as { detail?: string | { message?: string } };
      if (typeof err.detail === "string") detail = err.detail;
      else if (err.detail && typeof err.detail === "object" && err.detail.message) detail = err.detail.message;
    } catch { /* ignore parse error */ }
    throw new Error(detail);
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
  reinstall: (wipeSettings: boolean) =>
    request<import("../app/types").ReinstallResult>(`/api/update/reinstall?wipe_settings=${wipeSettings}`, { method: "POST" }),

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
    request<{ filename: string; size_bytes: number; is_example: boolean; is_model: boolean }[]>("/api/plugins/files"),
  uploadPluginFile: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<{ filename: string; size_bytes: number; discovered: number; message: string }>(
      "/api/plugins/upload", { method: "POST", body: form }
    );
  },
  deletePluginFile: (filename: string) =>
    request<{ deleted: string }>(`/api/plugins/files/${encodeURIComponent(filename)}`, { method: "DELETE" }),
  testPluginPipeline: (pipelineName: string, ignoreGates = false) =>
    request<{
      pipeline: string; ok: boolean; stages_run: number; ignore_gates: boolean;
      trace: { stage: string; preprocessor: string; model: string; is_gate: boolean;
               ok: boolean; gate_blocked?: boolean;
               feature_count?: number; schema_id?: string;
               verdict?: string; score?: number; attack_class?: string | null;
               reason?: string; error?: string }[];
      final_verdict: string | null; final_score: number | null; note: string;
    }>(`/api/plugins/pipelines/${encodeURIComponent(pipelineName)}/test?ignore_gates=${ignoreGates}`, { method: "POST" }),
  activatePluginPipeline: (pipelineName: string, currentSettings: AppSettings) =>
    request<AppSettings>("/api/settings", {
      method: "PUT",
      headers: jsonHeaders,
      body: JSON.stringify({ ...currentSettings, active_model_id: `plugin:${pipelineName}` }),
    }),
  restartService: () =>
    request<{ message: string; restart_scheduled: boolean }>("/api/update/restart", { method: "POST" }),
  getAutostart: () =>
    request<{ available: boolean; enabled: boolean; message: string }>("/api/autostart"),
  setAutostart: (enabled: boolean) =>
    request<{ available: boolean; enabled: boolean; message: string }>("/api/autostart", {
      method: "POST",
      headers: jsonHeaders,
      body: JSON.stringify({ enabled }),
    }),
  lsDir: (path: string) =>
    request<{
      path: string; exists: boolean; error?: string;
      is_file?: boolean; size_bytes?: number;
      entries: { name: string; is_dir: boolean; size_bytes: number | null }[];
    }>(`/api/fs/ls?path=${encodeURIComponent(path)}`),
};
