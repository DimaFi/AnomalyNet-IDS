import type { AppSettings, HealthResponse, ModelsRegistry, PipelineEvent, StreamSnapshot } from "../app/types";

let counter = 1;

function nextEvent(): PipelineEvent {
  const eventId = `flow-${String(counter).padStart(6, "0")}`;
  const packetCount = 12 + (counter % 90);
  const byteCount = packetCount * (120 + (counter % 17) * 44);
  const durationMs = 150 + (counter % 13) * 180;
  const score = Math.min(0.96, byteCount / 65000 + packetCount / 170);
  const label = score > 0.8 ? "anomaly" : score > 0.45 ? "warning" : "normal";
  const reason =
    label === "anomaly"
      ? "High risk hint based on burst size and flow density."
      : label === "warning"
        ? "Medium confidence anomaly, should be reviewed."
        : "Traffic profile looks stable for the mock baseline.";

  counter += 1;

  return {
    event: {
      event_id: eventId,
      timestamp: new Date().toISOString(),
      source: ["sensor-lab", "gateway-edge", "device-cluster"][counter % 3],
      direction: ["inbound", "outbound", "lateral"][counter % 3] as "inbound" | "outbound" | "lateral",
      protocol: ["TCP", "UDP", "ICMP", "OTHER"][counter % 4] as "TCP" | "UDP" | "ICMP" | "OTHER",
      src_ip: `192.168.1.${10 + (counter % 20)}`,
      dst_ip: `10.0.0.${100 + (counter % 40)}`,
      src_port: 1000 + (counter % 30000),
      dst_port: [53, 80, 443, 1883, 502, 8080][counter % 6],
      packet_count: packetCount,
      byte_count: byteCount,
      duration_ms: durationMs,
      risk_hint: Number(score.toFixed(3))
    },
    features: {
      event_id: eventId,
      contract_version: "feature-contract.v1",
      profile_name: "production_safe_features_with_ports",
      values: {
        Protocol: ["TCP", "UDP", "ICMP", "OTHER"][counter % 4],
        "Flow Duration": durationMs,
        "Total Fwd Packet": packetCount,
        "Total Length of Fwd Packet": byteCount,
        "Flow Bytes/s": Number((byteCount / (durationMs / 1000)).toFixed(3)),
        "Flow Packets/s": Number((packetCount / (durationMs / 1000)).toFixed(3)),
        "Average Packet Size": Number((byteCount / packetCount).toFixed(3)),
        "Src Port": 1000 + (counter % 30000),
        "Dst Port": [53, 80, 443, 1883, 502, 8080][counter % 6],
        "Risk Hint": Number(score.toFixed(3))
      }
    },
    inference: {
      event_id: eventId,
      label,
      score: Number(score.toFixed(3)),
      reason,
      model_id: "mock-default",
      attack_class: null
    },
    alert:
      label === "normal"
        ? null
        : {
            alert_id: crypto.randomUUID(),
            timestamp: new Date().toISOString(),
            level: label,
            title: "Potential anomaly detected",
            details: reason,
            event_id: eventId
          }
  };
}

export const mockSettings: AppSettings = {
  language: "ru",
  theme: "dark",
  run_mode: "mock",
  retention_days: 14,
  active_model_id: "mock-default",
  capture_enabled: true,
  stream_autostart: true,
  interface_name: "eth0",
  catboost_threshold: 0.70,
  catboost_model_dir: "",
  preprocessing_artifacts_dir: "",
  auto_block: false,
  auto_block_level: "anomaly" as const,
  whitelist_ips: [],
  detection_mode: "simple",
  catboost_secondary_model_dir: "",
  catboost_secondary_artifacts_dir: ""
};

export const mockHealth: HealthResponse = {
  service: "browser-mock-runtime",
  status: "active",
  mode: "mock",
  active_model_id: "mock-default",
  retention_days: 14,
  contract_version: "feature-contract.v1"
};

export const mockModels: ModelsRegistry = {
  active_model_id: "mock-default",
  items: [
    {
      model_id: "mock-default",
      display_name: "Mock Baseline Detector",
      version: "0.1.0",
      provider: "browser-mock",
      contract_version: "feature-contract.v1",
      profile_name: "production_safe_features_with_ports",
      artifact_path: "artifacts/models/mock-default",
      supported_modes: ["mock", "windows_stub", "linux_stub"],
      is_mock: true,
      description: "Built-in browser mock used when backend is unavailable.",
      status: "active"
    }
  ]
};

export function buildMockSnapshot(size = 8): StreamSnapshot {
  return {
    status: "active",
    queue_size: size,
    items: Array.from({ length: size }, () => nextEvent()).reverse()
  };
}

export function buildMockEvent(): PipelineEvent {
  return nextEvent();
}
