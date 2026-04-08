export type ThemeMode = "dark" | "light";
export type LanguageCode = "ru" | "en";
export type RunMode = "mock" | "windows_stub" | "linux_stub" | "linux_live";
export type StatusLevel = "idle" | "active" | "warning" | "error";
export type VerdictLabel = "normal" | "warning" | "anomaly";
export type AppView = "dashboard" | "stream" | "models" | "settings";

export interface AppSettings {
  language: LanguageCode;
  theme: ThemeMode;
  run_mode: RunMode;
  retention_days: number;
  active_model_id: string;
  capture_enabled: boolean;
  stream_autostart: boolean;
  // Network capture
  interface_name: string;
  // CatBoost
  catboost_threshold: number;
  catboost_model_dir: string;
  preprocessing_artifacts_dir: string;
  auto_block: boolean;
}

export interface ModelDescriptor {
  model_id: string;
  display_name: string;
  version: string;
  provider: string;
  contract_version: string;
  profile_name: string;
  artifact_path: string;
  supported_modes: RunMode[];
  is_mock: boolean;
  description: string;
  status: StatusLevel;
}

export interface ModelsRegistry {
  active_model_id: string;
  items: ModelDescriptor[];
}

export interface NormalizedFlowEvent {
  event_id: string;
  timestamp: string;
  source: string;
  direction: "inbound" | "outbound" | "lateral";
  protocol: "TCP" | "UDP" | "ICMP" | "OTHER";
  src_ip: string;
  dst_ip: string;
  src_port: number;
  dst_port: number;
  packet_count: number;
  byte_count: number;
  duration_ms: number;
  risk_hint: number;
}

export interface FeatureVector {
  event_id: string;
  contract_version: string;
  profile_name: string;
  values: Record<string, string | number>;
}

export interface InferenceResult {
  event_id: string;
  label: VerdictLabel;
  score: number;
  reason: string;
  model_id: string;
  attack_class: string | null;   // "DoS", "DDoS", etc. — только в multiclass
}

export interface AlertRecord {
  alert_id: string;
  timestamp: string;
  level: VerdictLabel;
  title: string;
  details: string;
  event_id: string;
}

export interface PipelineEvent {
  event: NormalizedFlowEvent;
  features: FeatureVector;
  inference: InferenceResult;
  alert: AlertRecord | null;
}

export interface StreamSnapshot {
  status: StatusLevel;
  queue_size: number;
  items: PipelineEvent[];
}

export interface HealthResponse {
  service: string;
  status: StatusLevel;
  mode: RunMode;
  active_model_id: string;
  retention_days: number;
  contract_version: string;
}

export interface NetworkInterface {
  name: string;
  addresses: string[];
}

export interface BlockRequest {
  ip_address: string;
  event_id?: string;
}

export interface BlockResponse {
  ip_address: string;
  blocked: boolean;
  message: string;
}

// Toast notification
export interface ToastItem {
  id: string;
  level: VerdictLabel;
  title: string;
  details: string;
  src_ip: string;
  event_id: string;
  timestamp: number;
  attack_class: string | null;
}
