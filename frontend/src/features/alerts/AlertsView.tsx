import { Fragment, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import type { PipelineEvent } from "../../app/types";
import { api } from "../../lib/api";
import styles from "../panel.module.css";
import s from "./AlertsView.module.css";

// ── Helpers ────────────────────────────────────────────────

function formatDateTime(iso: string): string {
  try {
    return new Date(iso).toLocaleString("ru-RU", {
      month: "2-digit", day: "2-digit",
      hour: "2-digit", minute: "2-digit", second: "2-digit",
    });
  } catch { return "—"; }
}

function severityColor(label: string): string {
  if (label === "anomaly") return "var(--danger)";
  if (label === "warning") return "var(--warn)";
  return "var(--ok)";
}

function eventTypeLabel(t: string | undefined): string {
  if (!t) return "flow";
  return t;
}

function attackClassBadge(cls: string | null | undefined): string {
  if (!cls) return s.badgeDefault;
  const l = cls.toLowerCase();
  if (l.includes("ddos"))                       return `${s.badge} ${s.badgeDdos}`;
  if (l.includes("dos"))                        return `${s.badge} ${s.badgeDos}`;
  if (l.includes("recon") || l.includes("scan"))return `${s.badge} ${s.badgeRecon}`;
  if (l.includes("brute"))                      return `${s.badge} ${s.badgeBrute}`;
  if (l.includes("web"))                        return `${s.badge} ${s.badgeWeb}`;
  if (l.includes("bot") || l.includes("mirai")) return `${s.badge} ${s.badgeBot}`;
  if (l.includes("spoof"))                      return `${s.badge} ${s.badgeSpoof}`;
  if (l.includes("tls") || l.includes("ja4"))   return `${s.badge} ${s.badgeTls}`;
  if (l.includes("dns"))                        return `${s.badge} ${s.badgeDns}`;
  return s.badge;
}

function exportCsv(rows: PipelineEvent[]) {
  const headers = [
    "time", "event_type", "src_ip", "src_port", "dst_ip", "dst_port",
    "protocol", "verdict", "score", "attack_class",
    "mitre_id", "mitre_name", "mitre_tactic", "mitre_url",
    "ja4", "sni", "priority",
  ];
  const lines = rows.map(item => {
    const m = item.mitre;
    const meta = (item.metadata ?? {}) as Record<string, unknown>;
    return [
      item.event.timestamp,
      item.event_type ?? "flow",
      item.event.src_ip,
      item.event.src_port,
      item.event.dst_ip,
      item.event.dst_port,
      item.event.protocol,
      item.inference.label,
      item.inference.score.toFixed(4),
      item.inference.attack_class ?? "",
      m?.id ?? "",
      m?.name ?? "",
      m?.tactic ?? "",
      (m as Record<string, unknown> | null | undefined)?.["url"] as string ?? "",
      (meta["ja4"] as string | undefined) ?? "",
      (meta["sni"] as string | undefined) ?? "",
      item.priority ?? "",
    ].map(v => `"${String(v).replace(/"/g, '""')}"`).join(",");
  });
  const csv = [headers.join(","), ...lines].join("\n");
  const blob = new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `anomalynet_alerts_${new Date().toISOString().slice(0, 19).replace(/:/g, "-")}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

// ── Component ──────────────────────────────────────────────

export function AlertsView() {
  const { t } = useTranslation();
  const [items, setItems]     = useState<PipelineEvent[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState<string | null>(null);

  // Filters
  const [filterVerdict, setFilterVerdict]   = useState<"all" | "warning" | "anomaly">("all");
  const [filterClass, setFilterClass]       = useState("");
  const [filterIp, setFilterIp]             = useState("");
  const [filterType, setFilterType]         = useState<"all" | "flow" | "dns" | "tls">("all");
  const [filterMitre, setFilterMitre]       = useState(false);

  // Expanded row
  const [expanded, setExpanded] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const data = await api.getHistory();
        if (!cancelled) setItems(data);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "Ошибка загрузки");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void load();
    const id = setInterval(() => { void load(); }, 30_000);
    return () => { cancelled = true; clearInterval(id); };
  }, []);

  const filtered = useMemo(() => {
    return items.filter(item => {
      if (filterVerdict !== "all" && item.inference.label !== filterVerdict) return false;
      if (filterType !== "all") {
        const et = (item.event_type ?? "flow").toLowerCase();
        if (filterType === "flow" && et !== "flow") return false;
        if (filterType === "dns"  && et !== "dns")  return false;
        if (filterType === "tls"  && et !== "tls")  return false;
      }
      if (filterClass) {
        const cls = (item.inference.attack_class ?? "").toLowerCase();
        if (!cls.includes(filterClass.toLowerCase())) return false;
      }
      if (filterIp) {
        const ip = filterIp.trim();
        if (!item.event.src_ip.includes(ip) && !item.event.dst_ip.includes(ip)) return false;
      }
      if (filterMitre && !item.mitre) return false;
      return true;
    });
  }, [items, filterVerdict, filterType, filterClass, filterIp, filterMitre]);

  const attackClasses = useMemo(() => {
    const set = new Set<string>();
    items.forEach(i => { if (i.inference.attack_class) set.add(i.inference.attack_class); });
    return Array.from(set).sort();
  }, [items]);

  const totalAnomaly = items.filter(i => i.inference.label === "anomaly").length;
  const totalWarning = items.filter(i => i.inference.label === "warning").length;

  return (
    <section className={styles.panel}>
      <div className={styles.panelHeader}>
        <div>
          <h2>{t("alerts.title")}</h2>
          <p>{t("alerts.subtitle")}</p>
        </div>
        <div className={s.headerStats}>
          <span className={s.statBadge} style={{ borderColor: "var(--danger)", color: "var(--danger)" }}>
            {totalAnomaly} {t("alerts.anomalies")}
          </span>
          <span className={s.statBadge} style={{ borderColor: "var(--warn)", color: "var(--warn)" }}>
            {totalWarning} {t("alerts.warnings")}
          </span>
          <span className={s.statBadge}>
            {items.length} {t("alerts.total")}
          </span>
        </div>
      </div>

      {/* ── Filters bar ── */}
      <div className={s.filtersBar}>
        <div className={s.filterGroup}>
          <label>{t("alerts.verdictLabel")}</label>
          <div className={s.segmented}>
            {(["all", "anomaly", "warning"] as const).map(v => (
              <button key={v}
                className={filterVerdict === v ? s.segActive : ""}
                onClick={() => setFilterVerdict(v)}>
                {v === "all" ? t("stream.filterAll") : v === "anomaly" ? t("stream.filterAnomaly") : t("stream.filterWarning")}
              </button>
            ))}
          </div>
        </div>

        <div className={s.filterGroup}>
          <label>{t("alerts.typeLabel")}</label>
          <div className={s.segmented}>
            {(["all", "flow", "dns", "tls"] as const).map(v => (
              <button key={v}
                className={filterType === v ? s.segActive : ""}
                onClick={() => setFilterType(v)}>
                {v === "all" ? "Все" : v.toUpperCase()}
              </button>
            ))}
          </div>
        </div>

        <div className={s.filterGroup}>
          <label>{t("alerts.classLabel")}</label>
          <select value={filterClass} onChange={e => setFilterClass(e.target.value)} className={s.filterSelect}>
            <option value="">{t("alerts.allClasses")}</option>
            {attackClasses.map(c => <option key={c} value={c}>{c}</option>)}
          </select>
        </div>

        <div className={s.filterGroup}>
          <label>{t("alerts.ipLabel")}</label>
          <input
            type="text"
            value={filterIp}
            onChange={e => setFilterIp(e.target.value)}
            placeholder="192.168.1.100"
            className={s.filterInput}
          />
        </div>

        <div className={s.filterGroup}>
          <label className={s.checkLabel}>
            <input type="checkbox" checked={filterMitre} onChange={e => setFilterMitre(e.target.checked)} />
            {t("alerts.mitreOnly")}
          </label>
        </div>

        <button
          className={s.exportBtn}
          onClick={() => exportCsv(filtered)}
          disabled={filtered.length === 0}
          title={`Экспорт ${filtered.length} строк в CSV`}
        >
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
            <polyline points="7 10 12 15 17 10" />
            <line x1="12" y1="15" x2="12" y2="3" />
          </svg>
          CSV ({filtered.length})
        </button>
      </div>

      {/* ── Table ── */}
      <div className={styles.tableWrap}>
        {loading && items.length === 0 && (
          <p className={styles.emptyState}>{t("alerts.loadingMsg")}</p>
        )}
        {error && (
          <p className={styles.emptyState} style={{ color: "var(--danger)" }}>{error}</p>
        )}
        {!loading && !error && filtered.length === 0 && (
          <p className={styles.emptyState}>{t("alerts.noIncidents")}</p>
        )}
        {filtered.length > 0 && (
          <table className={styles.table}>
            <thead>
              <tr>
                <th>{t("alerts.time")}</th>
                <th>{t("alerts.type")}</th>
                <th>{t("alerts.route")}</th>
                <th>{t("alerts.verdict")}</th>
                <th>Score</th>
                <th>{t("alerts.class")}</th>
                <th>{t("alerts.mitre")}</th>
                <th>{t("alerts.ja4domain")}</th>
                <th>{t("alerts.priority")}</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map(item => {
                const eid = item.event.event_id;
                const isExp = expanded === eid;
                const meta = (item.metadata ?? {}) as Record<string, unknown>;
                const ja4  = meta["ja4"]  as string | undefined;
                const sni  = meta["sni"]  as string | undefined;
                const domain = meta["domain"] as string | undefined;
                const mitreUrl = (item.mitre as (typeof item.mitre & { url?: string }) | null | undefined)?.url;
                return (
                  <Fragment key={eid}>
                    <tr
                      className={[
                        s.row,
                        item.inference.label === "anomaly" ? s.rowAnomaly : item.inference.label === "warning" ? s.rowWarning : "",
                        isExp ? s.rowExpanded : "",
                      ].filter(Boolean).join(" ")}
                      onClick={() => setExpanded(isExp ? null : eid)}
                    >
                      <td className={s.tdTime}>{formatDateTime(item.event.timestamp)}</td>
                      <td>
                        <span className={`${s.badge} ${
                          item.event_type === "tls" ? s.badgeTls :
                          item.event_type === "dns" ? s.badgeDns : s.badgeFlow
                        }`}>
                          {eventTypeLabel(item.event_type).toUpperCase()}
                        </span>
                      </td>
                      <td className={s.tdRoute}>
                        <span className={s.ip}>{item.event.src_ip}</span>
                        <span className={s.arrow}>→</span>
                        <span className={s.ip}>{item.event.dst_ip}</span>
                        {item.event.dst_port > 0 && (
                          <span className={s.port}>:{item.event.dst_port}</span>
                        )}
                      </td>
                      <td>
                        <span className={s.verdictDot} style={{ color: severityColor(item.inference.label) }}>
                          ● {item.inference.label}
                        </span>
                      </td>
                      <td className={s.tdScore} style={{ color: severityColor(item.inference.label) }}>
                        {item.inference.score.toFixed(3)}
                      </td>
                      <td>
                        {item.inference.attack_class ? (
                          <span className={attackClassBadge(item.inference.attack_class)}>
                            {item.inference.attack_class}
                          </span>
                        ) : <span className={s.muted}>—</span>}
                      </td>
                      <td className={s.tdMitre}>
                        {item.mitre ? (
                          <span className={s.mitreBadge} title={`${item.mitre.tactic}: ${item.mitre.name}`}>
                            {mitreUrl ? (
                              <a href={mitreUrl} target="_blank" rel="noopener noreferrer"
                                className={s.mitreLink} onClick={e => e.stopPropagation()}>
                                {item.mitre.id}
                              </a>
                            ) : item.mitre.id}
                          </span>
                        ) : <span className={s.muted}>—</span>}
                      </td>
                      <td className={s.tdJa4}>
                        {item.event_type === "tls" && ja4 ? (
                          <span className={s.mono} title={sni ? `SNI: ${sni}` : undefined}>{ja4.slice(0, 20)}{ja4.length > 20 ? "…" : ""}</span>
                        ) : item.event_type === "dns" && domain ? (
                          <span className={s.mono}>{domain.length > 22 ? "…" + domain.slice(-20) : domain}</span>
                        ) : <span className={s.muted}>—</span>}
                      </td>
                      <td>
                        {item.priority && item.priority !== "info" ? (
                          <span className={`${s.priorBadge} ${
                            item.priority === "critical" ? s.priorCritical :
                            item.priority === "high"     ? s.priorHigh :
                            item.priority === "medium"   ? s.priorMedium : ""
                          }`}>
                            {item.priority}
                          </span>
                        ) : <span className={s.muted}>—</span>}
                      </td>
                    </tr>
                    {isExp && (
                      <tr key={`${eid}-exp`} className={s.expandedRow}>
                        <td colSpan={9}>
                          <ExpandedDetails item={item} />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </section>
  );
}

// ── Expanded row details ───────────────────────────────────

function ExpandedDetails({ item }: { item: PipelineEvent }) {
  const { t } = useTranslation();
  const meta = (item.metadata ?? {}) as Record<string, unknown>;
  const mitreUrl = (item.mitre as (typeof item.mitre & { url?: string }) | null | undefined)?.url;
  const repInfo  = meta["ja4_reputation"] as Record<string, string> | undefined;

  return (
    <div className={s.expanded}>
      <div className={s.expandedGrid}>
        <div className={s.expandedSection}>
          <div className={s.expandedTitle}>{t("alerts.expandEvent")}</div>
          <dl className={s.dl}>
            <dt>Event ID</dt><dd className={s.mono}>{item.event.event_id}</dd>
            <dt>{t("alerts.protocol")}</dt><dd>{item.event.protocol}</dd>
            <dt>{t("alerts.packets")}</dt><dd>{item.event.packet_count}</dd>
            <dt>{t("alerts.bytes")}</dt><dd>{item.event.byte_count}</dd>
            <dt>{t("alerts.duration")}</dt><dd>{item.event.duration_ms} ms</dd>
            <dt>{t("alerts.source")}</dt><dd>{item.event.source}</dd>
            {item.pipeline_used && <><dt>Pipeline</dt><dd>{item.pipeline_used}</dd></>}
            {item.device_name  && <><dt>{t("alerts.device")}</dt><dd>{item.device_name}</dd></>}
          </dl>
        </div>
        <div className={s.expandedSection}>
          <div className={s.expandedTitle}>{t("alerts.expandVerdict")}</div>
          <dl className={s.dl}>
            <dt>{t("alerts.model")}</dt><dd className={s.mono}>{item.inference.model_id}</dd>
            <dt>{t("alerts.reason")}</dt><dd>{item.inference.reason || "—"}</dd>
            {item.mitre && (
              <>
                <dt>MITRE ID</dt>
                <dd>
                  {mitreUrl
                    ? <a href={mitreUrl} target="_blank" rel="noopener noreferrer" className={s.mitreLink}>{item.mitre.id}</a>
                    : item.mitre.id}
                </dd>
                <dt>{t("alerts.technique")}</dt><dd>{item.mitre.name}</dd>
                <dt>{t("alerts.tactic")}</dt><dd>{item.mitre.tactic}</dd>
              </>
            )}
          </dl>
        </div>
        {(item.event_type === "tls" || item.event_type === "dns") && (
          <div className={s.expandedSection}>
            <div className={s.expandedTitle}>
              {item.event_type === "tls" ? "TLS / JA4" : "DNS"}
            </div>
            <dl className={s.dl}>
              {Object.entries(meta)
                .filter(([k]) => !["ja4_reputation"].includes(k))
                .map(([k, v]) => v != null && v !== "" && (
                  <><dt key={k + "k"}>{k}</dt><dd key={k + "v"} className={s.mono}>{String(v)}</dd></>
                ))}
            </dl>
          </div>
        )}
        {repInfo && (
          <div className={s.expandedSection}>
            <div className={s.expandedTitle} style={{ color: "var(--danger)" }}>{t("alerts.reputation")}</div>
            <dl className={s.dl}>
              <dt>{t("alerts.repLabel")}</dt><dd style={{ color: "var(--danger)", fontWeight: 700 }}>{repInfo["label"]}</dd>
              <dt>{t("alerts.repSeverity")}</dt><dd>{repInfo["severity"]}</dd>
              <dt>{t("alerts.repDesc")}</dt><dd>{repInfo["description"]}</dd>
              <dt>{t("alerts.repSource")}</dt><dd>{repInfo["source"]}</dd>
            </dl>
          </div>
        )}
      </div>
    </div>
  );
}
