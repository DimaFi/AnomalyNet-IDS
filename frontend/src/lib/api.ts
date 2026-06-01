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
  SystemStats,
  TlsStats,
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
import type { Device, DeviceStats } from "../types/device";

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
  getSystemStats: () => request<SystemStats>("/api/system/stats"),
  getAccessInfo: () => request<{ enabled: boolean; primary_ip: string; lan_ips: string[] }>("/api/system/access-info"),
  getPublicStatus: () => request<{ running: boolean; url: string; enabled: boolean; public_url: string }>("/api/remote/public/status"),
  enablePublic: () => request<{ ok: boolean; running?: boolean; url?: string; public_url?: string; key?: string; error?: string }>("/api/remote/public/enable", { method: "POST" }),
  disablePublic: () => request<{ ok: boolean }>("/api/remote/public/disable", { method: "POST" }),
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
  getHistory: () => request<{ total: number; items: PipelineEvent[] }>("/api/history?limit=200").then(r => r.items),
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
  getDashboardTimeseries: (window = 60) => request<import("../app/types").DashboardTimeseries>(`/api/dashboard/timeseries?window=${window}`),
  getDashboardSummary: () => request<import("../app/types").DashboardSummary>("/api/dashboard/summary"),
  getModelPresets: () => request<ModelPresetsRegistry>("/api/model-presets"),
  applyModelPreset: (presetId: string) =>
    request<AppSettings>(`/api/model-presets/apply/${presetId}`, {
      method: "POST",
      headers: jsonHeaders,
      body: "{}",
    }),
  checkUpdates: () => request<UpdateCheckResult>("/api/update/check"),
  applyUpdates: () => request<UpdateApplyResult>("/api/update/apply", { method: "POST" }),
  stopService: () => request<{ stopped: boolean; message: string }>("/api/update/stop", { method: "POST" }),
  reinstall: (wipeSettings: boolean) =>
    request<import("../app/types").ReinstallResult>(`/api/update/reinstall?wipe_settings=${wipeSettings}`, { method: "POST" }),
  uninstall: (keepSettings: boolean) =>
    request<import("../app/types").UninstallResult>(`/api/update/uninstall?keep_settings=${keepSettings}`, { method: "POST" }),

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
  getShortcutInfo: () =>
    request<{ platform: string; app_root: string; launcher_exists: boolean; launcher_path: string }>("/api/shortcuts/info"),
  createShortcut: (target: "desktop" | "startmenu" | "applications") =>
    request<{ ok: boolean; path: string | null; error: string | null }>("/api/shortcuts/create", {
      method: "POST",
      headers: jsonHeaders,
      body: JSON.stringify({ target }),
    }),
  lsDir: (path: string) =>
    request<{
      path: string; exists: boolean; error?: string;
      is_file?: boolean; size_bytes?: number;
      entries: { name: string; is_dir: boolean; size_bytes: number | null }[];
    }>(`/api/fs/ls?path=${encodeURIComponent(path)}`),

  // ── Device / Network Map API ───────────────────────────────────────────────
  getDevices: (suspiciousOnly = false) =>
    request<Device[]>(`/api/devices${suspiciousOnly ? "?suspicious_only=true" : ""}`),
  getDeviceStats: () => request<DeviceStats>("/api/devices/stats"),
  triggerScan: () => request<{ success: boolean; found?: number; error?: string }>("/api/devices/scan", { method: "POST" }),
  getDeviceHistory: (mac: string) =>
    request<import("../types/device").DeviceAlert[]>(`/api/devices/${encodeURIComponent(mac)}/history`),
  labelDevice: (mac: string, custom_name: string, device_type: string) =>
    request<{ success: boolean }>(`/api/devices/${encodeURIComponent(mac)}/label`, {
      method: "POST",
      headers: jsonHeaders,
      body: JSON.stringify({ custom_name, device_type }),
    }),
  whitelistDevice: (mac: string) =>
    request<{ success: boolean }>(`/api/devices/${encodeURIComponent(mac)}/whitelist`, { method: "POST" }),
  unwhitelistDevice: (mac: string) =>
    request<{ success: boolean }>(`/api/devices/${encodeURIComponent(mac)}/whitelist`, { method: "DELETE" }),
  resetDevice: (mac: string) =>
    request<{ success: boolean }>(`/api/devices/${encodeURIComponent(mac)}/reset`, { method: "POST" }),
  addDevice: (ip: string, mac: string, custom_name: string, device_type: string) =>
    request<{ success: boolean; device: Device }>("/api/devices/add", {
      method: "POST",
      headers: jsonHeaders,
      body: JSON.stringify({ ip, mac, custom_name, device_type }),
    }),
  removeDevice: (mac: string) =>
    request<{ success: boolean }>(`/api/devices/${encodeURIComponent(mac)}`, { method: "DELETE" }),
  probeDevice: (mac: string) =>
    request<{ ip: string; reachable: boolean; latency_ms: number | null; open_ports: number[] }>(
      `/api/devices/${encodeURIComponent(mac)}/probe`, { method: "POST" }
    ),
  inspectDevice: (mac: string) =>
    request<{
      ip: string;
      os_guess: string | null;
      services: { port: number; protocol: string; title?: string; server?: string; banner?: string; status?: number }[];
      web_urls: string[];
      rtsp_url: string | null;
    }>(`/api/devices/${encodeURIComponent(mac)}/inspect`, { method: "POST" }),

  // ── TLS Monitoring ────────────────────────────────────────────────────────
  getTlsStats: () => request<TlsStats>("/api/tls/stats"),
  getTlsProfiles: (srcIp?: string) =>
    request<{ available: boolean; profiles: Record<string, Record<string, { count: number; first_seen: string; last_seen: string }>>; total_ips?: number }>(
      `/api/tls/profiles${srcIp ? `?src_ip=${encodeURIComponent(srcIp)}` : ""}`
    ),

  // ── DNS Monitoring ─────────────────────────────────────────────────────────
  getDnsRecent: (srcIp?: string, limit = 50) =>
    request<{ items: import("../types/dns").DnsEntry[]; available: boolean }>(
      `/api/dns/recent?limit=${limit}${srcIp ? `&src_ip=${encodeURIComponent(srcIp)}` : ""}`
    ),
  getDnsTop: (srcIp?: string, limit = 20) =>
    request<{ domains: { domain: string; count: number }[]; available: boolean }>(
      `/api/dns/top?limit=${limit}${srcIp ? `&src_ip=${encodeURIComponent(srcIp)}` : ""}`
    ),
  getDnsAlerts: (limit = 50) =>
    request<{ alerts: import("../types/dns").DnsAlert[]; available: boolean }>(
      `/api/dns/alerts?limit=${limit}`
    ),
  getDeviceDnsSummary: (ip: string) =>
    request<import("../types/dns").DeviceDnsSummary>(`/api/dns/device/${encodeURIComponent(ip)}/summary`),

  // Models Manager
  listModelPackages: () =>
    request<import("../app/types").ModelPackageInfo[]>("/api/models-manager/list"),
  getModelCatalog: () =>
    request<import("../app/types").OfficialModelInfo[]>("/api/models-manager/catalog"),
  scanModels: () =>
    request<{ ok: boolean; found: number }>("/api/models-manager/scan", { method: "POST" }),
  addModelFolder: (folder_path: string) =>
    request<{ ok: boolean; id: string; name: string }>("/api/models-manager/add", {
      method: "POST",
      headers: jsonHeaders,
      body: JSON.stringify({ folder_path }),
    }),
  getDownloadDest: (catalogId: string) =>
    request<{ repo_dest: string; models_dir: string; is_installed: boolean }>(
      `/api/models-manager/download-dest/${catalogId}`
    ),

  // ── GeoIP ──────────────────────────────────────────────────────────────────
  getGeoip: (ip: string) =>
    request<{ ip: string; is_private: boolean; country: string; flag: string; hint: string }>(
      `/api/geoip/${encodeURIComponent(ip)}`
    ),

  // ── Platform Capabilities ─────────────────────────────────────────────────
  getCapabilities: () =>
    request<import("../app/types").PlatformCapabilities>("/api/capabilities"),
};
