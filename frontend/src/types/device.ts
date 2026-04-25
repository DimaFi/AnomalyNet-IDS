export interface Device {
  mac: string;
  ip: string;
  vendor: string;
  device_type: string;
  device_label: string;
  device_emoji: string;
  display_name: string;
  hostname: string;
  custom_name: string;
  first_seen: string | null;
  last_seen: string | null;
  is_online: boolean;
  is_suspicious: boolean;
  is_whitelisted: boolean;
  alert_count: number;
  bytes_in: number;
  bytes_out: number;
  last_alert_type: string | null;
  last_alert_score: number | null;
  last_alert_time: string | null;
  open_ports: number[];
  risk_score: number;
  risk_label: "low" | "medium" | "high" | "critical";
}

export interface DeviceAlert {
  ts: string;
  label: string;
  attack_class: string | null;
  score: number | null;
  src_ip: string;
  dst_ip: string | null;
}

export interface DeviceStats {
  total: number;
  online: number;
  offline: number;
  suspicious: number;
  whitelisted: number;
  by_type: Record<string, number>;
  last_scan: string | null;
}

export interface DevicesWsMessage {
  type: "devices_update" | "ping";
  devices?: Device[];
  stats?: DeviceStats;
}
