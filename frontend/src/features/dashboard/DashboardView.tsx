import { useTranslation } from "react-i18next";
import { useAppStore } from "../../app/store";
import { StatusPill } from "../../components/StatusPill";
import styles from "../panel.module.css";

export function DashboardView() {
  const { t } = useTranslation();
  const health = useAppStore((state) => state.health);
  const settings = useAppStore((state) => state.settings);
  const stream = useAppStore((state) => state.stream);
  const latest = stream.slice(0, 4);

  return (
    <section className={styles.panel}>
      <div className={styles.panelHeader}>
        <div>
          <h2>{t("dashboard.title")}</h2>
          <p>Mock-ready console with contracts, local API and stream visualization.</p>
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
          {!latest.length && <p className={styles.emptyState}>Waiting for mock flow events...</p>}
        </div>
      </div>
    </section>
  );
}

