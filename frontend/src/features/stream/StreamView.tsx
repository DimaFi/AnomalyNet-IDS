import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useAppStore } from "../../app/store";
import type { PipelineEvent, VerdictLabel } from "../../app/types";
import { StatusPill } from "../../components/StatusPill";
import { formatBytes } from "../../lib/format";
import { useBlockIp } from "../../lib/useBlockIp";
import { refreshStreamFromSnapshot } from "../../lib/useRealtimeStream";
import styles from "../panel.module.css";
import blockStyles from "./StreamView.module.css";

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString("ru-RU", {
      hour: "2-digit", minute: "2-digit", second: "2-digit"
    });
  } catch {
    return "—";
  }
}

function exportCsv(rows: PipelineEvent[]) {
  const headers = ["time", "src_ip", "src_port", "dst_ip", "dst_port", "protocol",
    "packets", "bytes", "score", "verdict", "attack_class"];
  const lines = rows.map((item) => [
    item.event.timestamp,
    item.event.src_ip,
    item.event.src_port,
    item.event.dst_ip,
    item.event.dst_port,
    item.event.protocol,
    item.event.packet_count,
    item.event.byte_count,
    item.inference.score.toFixed(4),
    item.inference.label,
    item.inference.attack_class ?? "",
  ].join(","));
  const csv = [headers.join(","), ...lines].join("\n");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `anomalynet_stream_${new Date().toISOString().slice(0, 19).replace(/:/g, "-")}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

export function StreamView() {
  const { t } = useTranslation();
  const stream        = useAppStore((state) => state.stream);
  const blockedIps    = useAppStore((state) => state.blockedIps);
  const replaceStream = useAppStore((state) => state.replaceStream);
  const blockIp       = useBlockIp();
  const [refreshing, setRefreshing] = useState(false);

  const [filterVerdict,  setFilterVerdict]  = useState<"all" | VerdictLabel>("all");
  const [filterClass,    setFilterClass]    = useState("all");
  const [filterProtocol, setFilterProtocol] = useState("all");

  async function handleRefresh() {
    setRefreshing(true);
    await refreshStreamFromSnapshot(replaceStream);
    setRefreshing(false);
  }

  const allClasses = useMemo(() => {
    const s = new Set<string>();
    for (const item of stream) {
      if (item.inference.attack_class) s.add(item.inference.attack_class);
    }
    return Array.from(s).sort();
  }, [stream]);

  const allProtocols = useMemo(() => {
    const s = new Set<string>();
    for (const item of stream) s.add(item.event.protocol);
    return Array.from(s).sort();
  }, [stream]);

  const filtered = useMemo(() => stream.filter((item) => {
    if (filterVerdict !== "all" && item.inference.label !== filterVerdict) return false;
    if (filterClass !== "all") {
      if (filterClass === "none" && item.inference.attack_class) return false;
      if (filterClass !== "none" && item.inference.attack_class !== filterClass) return false;
    }
    if (filterProtocol !== "all" && item.event.protocol !== filterProtocol) return false;
    return true;
  }), [stream, filterVerdict, filterClass, filterProtocol]);

  const hasFilters = filterVerdict !== "all" || filterClass !== "all" || filterProtocol !== "all";

  return (
    <section className={styles.panel}>
      <div className={styles.panelHeader}>
        <div>
          <h2>{t("stream.title")}</h2>
          <p className={styles.panelSubtitle}>
            {t("stream.subtitle", "Потоки в реальном времени — признаки, предсказания, статус")}
          </p>
        </div>
        <div className={blockStyles.headerRight}>
          <span className={blockStyles.counter}>
            {filtered.length !== stream.length
              ? `${filtered.length} / ${stream.length} ${t("stream.events", "событий")}`
              : `${stream.length} ${t("stream.events", "событий")}`}
          </span>
          <button
            className={blockStyles.refreshBtn}
            onClick={() => void exportCsv(filtered)}
            title="Экспорт в CSV"
          >
            ↓ CSV
          </button>
          <button
            className={blockStyles.refreshBtn}
            onClick={() => void handleRefresh()}
            disabled={refreshing}
            title="Обновить из последнего снапшота"
          >
            {refreshing ? "..." : "↺ Обновить"}
          </button>
        </div>
      </div>

      {/* ── Filter bar ── */}
      <div className={blockStyles.filterBar}>
        <label className={blockStyles.filterItem}>
          <span>Вердикт</span>
          <select value={filterVerdict} onChange={(e) => setFilterVerdict(e.target.value as "all" | VerdictLabel)}>
            <option value="all">Все</option>
            <option value="anomaly">Аномалия</option>
            <option value="warning">Предупреждение</option>
            <option value="normal">Норма</option>
          </select>
        </label>
        <label className={blockStyles.filterItem}>
          <span>Тип атаки</span>
          <select value={filterClass} onChange={(e) => setFilterClass(e.target.value)}>
            <option value="all">Все</option>
            {allClasses.map((c) => <option key={c} value={c}>{c}</option>)}
            <option value="none">— (без класса)</option>
          </select>
        </label>
        <label className={blockStyles.filterItem}>
          <span>Протокол</span>
          <select value={filterProtocol} onChange={(e) => setFilterProtocol(e.target.value)}>
            <option value="all">Все</option>
            {allProtocols.map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
        </label>
        {hasFilters && (
          <button className={blockStyles.clearFiltersBtn}
            onClick={() => { setFilterVerdict("all"); setFilterClass("all"); setFilterProtocol("all"); }}>
            × Сбросить
          </button>
        )}
      </div>

      <div className={styles.tableWrap}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th style={{ width: 70 }}>{t("stream.time", "Время")}</th>
              <th>{t("stream.source")}</th>
              <th>{t("stream.route")}</th>
              <th>{t("stream.protocol")}</th>
              <th>{t("stream.volume")}</th>
              <th style={{ minWidth: 80 }}>Score</th>
              <th>{t("stream.verdict")}</th>
              <th style={{ minWidth: 90 }}>{t("stream.attack_class", "Тип атаки")}</th>
              <th style={{ width: 120 }}>{t("stream.actions", "Действия")}</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((item) => {
              const isAttack  = item.inference.label !== "normal";
              const isBlocked = blockedIps.has(item.event.src_ip);

              return (
                <tr
                  key={item.event.event_id}
                  className={isAttack ? blockStyles.attackRow : ""}
                >
                  <td className={blockStyles.timeCell}>{formatTime(item.event.timestamp)}</td>
                  <td>{item.event.source}</td>
                  <td className={blockStyles.route}>
                    <span className={blockStyles.ip}>{item.event.src_ip}</span>
                    <span className={blockStyles.port}>:{item.event.src_port}</span>
                    <span className={blockStyles.arrow}>→</span>
                    <span className={blockStyles.ip}>{item.event.dst_ip}</span>
                    <span className={blockStyles.port}>:{item.event.dst_port}</span>
                  </td>
                  <td>{item.event.protocol}</td>
                  <td>
                    {item.event.packet_count} / {formatBytes(item.event.byte_count)}
                  </td>
                  <td className={blockStyles.scoreCell}>
                    <span
                      className={[
                        blockStyles.score,
                        item.inference.score >= 0.85 ? blockStyles.scoreDanger
                          : item.inference.score >= 0.7 ? blockStyles.scoreWarn
                          : blockStyles.scoreOk,
                      ].join(" ")}
                    >
                      {item.inference.score.toFixed(2)}
                    </span>
                  </td>
                  <td>
                    <StatusPill value={item.inference.label} />
                  </td>
                  <td>
                    {item.inference.attack_class ? (
                      <span className={blockStyles.attackClassBadge}>
                        {item.inference.attack_class}
                      </span>
                    ) : (
                      <span className={blockStyles.noClass}>—</span>
                    )}
                  </td>
                  <td>
                    {isAttack && (
                      isBlocked ? (
                        <span className={blockStyles.blockedBadge}>
                          Заблокирован
                        </span>
                      ) : (
                        <button
                          className={blockStyles.blockBtn}
                          onClick={() => blockIp(item.event.src_ip, item.event.event_id)}
                          title={`Заблокировать ${item.event.src_ip}`}
                        >
                          Блокировать
                        </button>
                      )
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {!filtered.length && (
          <p className={styles.emptyState}>
            {hasFilters
              ? "Нет событий по выбранным фильтрам."
              : t("stream.empty", "Нет событий. Ожидание трафика...")}
          </p>
        )}
      </div>
    </section>
  );
}
