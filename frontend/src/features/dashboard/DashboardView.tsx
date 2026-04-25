import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useAppStore } from "../../app/store";
import type { DebugStats } from "../../app/types";
import type { Device } from "../../types/device";
import { StatusPill } from "../../components/StatusPill";
import { api } from "../../lib/api";
import styles from "../panel.module.css";

const RISK_COLORS: Record<string, string> = {
  low: "#22c55e", medium: "#eab308", high: "#f97316", critical: "#ef4444",
};
const RISK_LABELS_RU: Record<string, string> = {
  low: "LOW", medium: "MED", high: "HIGH", critical: "CRIT",
};

export function DashboardView() {
  const { t } = useTranslation();
  const health   = useAppStore((state) => state.health);
  const settings = useAppStore((state) => state.settings);
  const stream   = useAppStore((state) => state.stream);
  const storeDevices = useAppStore((state) => state.devices);
  const latest   = stream.slice(0, 4);

  const [stats, setStats] = useState<DebugStats | null>(null);
  const [topRiskDevices, setTopRiskDevices] = useState<Device[]>([]);

  useEffect(() => {
    const update = () => {
      const sorted = [...storeDevices]
        .sort((a, b) => b.risk_score - a.risk_score)
        .slice(0, 3);
      setTopRiskDevices(sorted);
    };
    update();
  }, [storeDevices]);

  useEffect(() => {
    let cancelled = false;
    async function fetchStats() {
      try {
        const data = await api.getDebugStats();
        if (!cancelled) setStats(data);
      } catch { /* ignore — stats endpoint may be temporarily unavailable */ }
    }
    void fetchStats();
    const id = setInterval(() => { void fetchStats(); }, 30_000);
    return () => { cancelled = true; clearInterval(id); };
  }, []);

  const attackCount = stats
    ? (stats.events_by_label["warning"] ?? 0) + (stats.events_by_label["anomaly"] ?? 0)
    : null;

  const now24 = Date.now() - 24 * 60 * 60 * 1000;
  const criticalCount = stream.filter(
    (item) => item.priority === "critical" && new Date(item.event.timestamp).getTime() > now24
  ).length;

  const topClass = stats && Object.keys(stats.events_by_attack_class).length > 0
    ? Object.entries(stats.events_by_attack_class).sort((a, b) => b[1] - a[1])[0][0]
    : null;

  const topIp = stats && Object.keys(stats.top_src_ips).length > 0
    ? Object.entries(stats.top_src_ips).sort((a, b) => b[1] - a[1])[0][0]
    : null;

  return (
    <section className={styles.panel}>
      <div className={styles.panelHeader}>
        <div>
          <h2>{t("dashboard.title")}</h2>
          <p>Мониторинг сети в реальном времени. Обнаружение атак на основе CatBoost.</p>
        </div>
      </div>
      <div className={styles.metricsGrid}>
        <article className={styles.metricCard}>
          <span>{t("dashboard.status")}</span>
          {health ? <StatusPill value={health.status} /> : <span>...</span>}
        </article>
        <article className={styles.metricCard}>
          <span>{t("dashboard.mode")}</span>
          <strong>{settings?.run_mode ?? "mock"}</strong>
        </article>
        <article className={styles.metricCard}>
          <span>{t("dashboard.activeModel")}</span>
          <strong>{settings?.active_model_id ?? "mock-default"}</strong>
        </article>
        <article className={styles.metricCard}>
          <span>{t("dashboard.retention")}</span>
          <strong>{settings?.retention_days ?? 14} days</strong>
        </article>
        <article className={styles.metricCard}>
          <span>{t("dashboard.contract")}</span>
          <strong>{health?.contract_version ?? "feature-contract.v1"}</strong>
        </article>
        <article className={styles.metricCard}>
          <span>Всего потоков</span>
          <strong>{stats ? stats.uptime_events_total : "—"}</strong>
        </article>
        <article className={styles.metricCard}>
          <span>Атак обнаружено</span>
          <strong style={{ color: attackCount ? "var(--danger)" : undefined }}>
            {attackCount !== null ? attackCount : "—"}
            {criticalCount > 0 && (
              <span style={{ marginLeft: 6, fontSize: 11, color: "#ef4444", fontWeight: 700 }}
                title="Critical за 24ч">
                {criticalCount} critical
              </span>
            )}
          </strong>
        </article>
        <article className={styles.metricCard}>
          <span>Топ класс атак</span>
          <strong>{topClass ?? "—"}</strong>
        </article>
        <article className={styles.metricCard}>
          <span>Топ атакующий IP</span>
          <strong style={{ fontFamily: "monospace", fontSize: "12px" }}>{topIp ?? "—"}</strong>
        </article>
        <article className={styles.metricCard}>
          <span>Средний score</span>
          <strong>{stats ? stats.avg_score.toFixed(3) : "—"}</strong>
        </article>
      </div>
      <div className={styles.streamPreview}>
        <div className={styles.subhead}>
          <h3>{t("dashboard.latestVerdicts")}</h3>
        </div>
        <div className={styles.previewList}>
          {latest.map((item) => (
            <div key={item.event.event_id} className={styles.previewRow}>
              <div>
                <strong>{item.event.event_id}</strong>
                <p>
                  {item.event.src_ip}:{item.event.src_port} → {item.event.dst_ip}:{item.event.dst_port}
                </p>
              </div>
              <div className={styles.previewMeta}>
                <StatusPill value={item.inference.label} />
                <span>{item.inference.score.toFixed(3)}</span>
              </div>
            </div>
          ))}
          {!latest.length && <p className={styles.emptyState}>Нет данных. Ожидание сетевых потоков...</p>}
        </div>
      </div>

      {topRiskDevices.length > 0 && (
        <div className={styles.streamPreview}>
          <div className={styles.subhead}>
            <h3>Топ устройств по риску</h3>
          </div>
          <div className={styles.previewList}>
            {topRiskDevices.map((d) => {
              const color = RISK_COLORS[d.risk_label] ?? RISK_COLORS.low;
              const lbl   = RISK_LABELS_RU[d.risk_label] ?? d.risk_label;
              return (
                <div key={d.mac} className={styles.previewRow}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 0 }}>
                    <span style={{ fontSize: 18, lineHeight: 1 }}>{d.device_emoji}</span>
                    <div style={{ minWidth: 0 }}>
                      <strong style={{ fontSize: 12, display: "block", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {d.display_name}
                      </strong>
                      <p style={{ fontFamily: "monospace", fontSize: 11, color: "var(--text-muted)", margin: 0 }}>{d.ip}</p>
                    </div>
                  </div>
                  <div className={styles.previewMeta}>
                    <span style={{
                      fontSize: 11, fontWeight: 700, padding: "2px 8px", borderRadius: 10,
                      background: `${color}22`, color, border: `1px solid ${color}55`,
                    }}>{lbl}</span>
                    <span style={{ fontSize: 13, fontWeight: 700, color }}>{d.risk_score}</span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </section>
  );
}
