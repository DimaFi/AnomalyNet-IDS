import type { StatusLevel, VerdictLabel } from "../app/types";

export function formatBytes(value: number): string {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / (1024 * 1024)).toFixed(2)} MB`;
}

export function statusTone(status: StatusLevel | VerdictLabel): "ok" | "warn" | "danger" | "info" {
  if (status === "active" || status === "normal") return "ok";
  if (status === "warning") return "warn";
  if (status === "anomaly" || status === "error") return "danger";
  return "info";
}

