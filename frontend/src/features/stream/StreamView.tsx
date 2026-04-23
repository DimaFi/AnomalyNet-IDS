import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useAppStore } from "../../app/store";
import type { PipelineEvent, VerdictLabel } from "../../app/types";
import { StatusPill } from "../../components/StatusPill";
import { formatBytes } from "../../lib/format";
import { api } from "../../lib/api";
import { useBlockIp } from "../../lib/useBlockIp";
import { refreshStreamFromSnapshot } from "../../lib/useRealtimeStream";
import styles from "../panel.module.css";
import s from "./StreamView.module.css";

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

function getScoreClass(score: number): string {
  if (score >= 0.85) return s.scoreDanger;
  if (score >= 0.70) return s.scoreWarn;
  return s.scoreOk;
}

function getScoreColor(score: number): string {
  if (score >= 0.85) return "var(--danger)";
  if (score >= 0.70) return "var(--warn)";
  return "var(--ok)";
}

function getAttackClassStyle(cls: string | null | undefined): string {
  if (!cls) return s.attackClassBadge;
  const lower = cls.toLowerCase();
  if (lower.includes("ddos"))                               return `${s.attackClassBadge} ${s.classDdos}`;
  if (lower.includes("dos"))                                return `${s.attackClassBadge} ${s.classDos}`;
  if (lower.includes("recon") || lower.includes("scan"))    return `${s.attackClassBadge} ${s.classRecon}`;
  if (lower.includes("brute"))                              return `${s.attackClassBadge} ${s.classBrute}`;
  if (lower.includes("web") || lower.includes("sql") || lower.includes("xss")) return `${s.attackClassBadge} ${s.classWeb}`;
  if (lower.includes("bot")  || lower.includes("mirai"))    return `${s.attackClassBadge} ${s.classBot}`;
  if (lower.includes("spoof"))                              return `${s.attackClassBadge} ${s.classSpoof}`;
  return s.attackClassBadge;
}

function ScoreBar({ score }: { score: number }) {
  return (
    <div className={s.scoreWrap}>
      <span className={`${s.score} ${getScoreClass(score)}`}>{score.toFixed(2)}</span>
      <div
        className={s.scoreBar}
        style={{ "--bar-w": `${Math.round(score * 100)}%`, "--bar-c": getScoreColor(score) } as React.CSSProperties}
      />
    </div>
  );
}

export function StreamView() {
  const { t } = useTranslation();
  const stream        = useAppStore((state) => state.stream);
  const blockedIps    = useAppStore((state) => state.blockedIps);
  const replaceStream = useAppStore((state) => state.replaceStream);
  const markUnblocked = useAppStore((state) => state.markUnblocked);
  const blockIp       = useBlockIp();
  const [refreshing, setRefreshing] = useState(false);

  const [filterVerdict,  setFilterVerdict]  = useState<"all" | VerdictLabel>("all");
  const [filterClass,    setFilterClass]    = useState("all");
  const [filterProtocol, setFilterProtocol] = useState("all");
  const [filterIp,       setFilterIp]       = useState("");
  const [page, setPage] = useState(0);

  async function handleUnblock(ip: string) {
    try { await api.unblockIp(ip); } catch { /* best effort */ }
    markUnblocked(ip);
  }

  const PAGE_SIZE = 100;

  async function handleRefresh() {
    setRefreshing(true);
    await refreshStreamFromSnapshot(replaceStream);
    setRefreshing(false);
  }

  const allClasses = useMemo(() => {
    const set = new Set<string>();
    for (const item of stream) {
      if (item.inference.attack_class) set.add(item.inference.attack_class);
    }
    return Array.from(set).sort();
  }, [stream]);

  const allProtocols = useMemo(() => {
    const set = new Set<string>();
    for (const item of stream) set.add(item.event.protocol);
    return Array.from(set).sort();
  }, [stream]);

  const ipQuery = filterIp.trim().toLowerCase();

  const filtered = useMemo(() => stream.filter((item) => {
    if (filterVerdict !== "all" && item.inference.label !== filterVerdict) return false;
    if (filterClass !== "all") {
      if (filterClass === "none" && item.inference.attack_class) return false;
      if (filterClass !== "none" && item.inference.attack_class !== filterClass) return false;
    }
    if (filterProtocol !== "all" && item.event.protocol !== filterProtocol) return false;
    if (ipQuery && !item.event.src_ip.includes(ipQuery) && !item.event.dst_ip.includes(ipQuery)) return false;
    return true;
  }), [stream, filterVerdict, filterClass, filterProtocol, ipQuery]);

  const hasFilters = filterVerdict !== "all" || filterClass !== "all" || filterProtocol !== "all" || !!ipQuery;
  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const safePage   = Math.min(page, totalPages - 1);
  const paginated  = filtered.slice(safePage * PAGE_SIZE, (safePage + 1) * PAGE_SIZE);

  return (
    <section className={styles.panel}>
      {/* ── Header ── */}
      <div className={styles.panelHeader}>
        <div>
          <h2>{t("stream.title")}</h2>
          <p className={styles.panelSubtitle}>
            {t("stream.subtitle", "Потоки в реальном времени — признаки, предсказания, статус")}
          </p>
        </div>
        <div className={s.headerRight}>
          <span className={s.counter}>
            {filtered.length !== stream.length
              ? `${filtered.length} / ${stream.length}`
              : `${stream.length}`}
          </span>
          {totalPages > 1 && (
            <div className={s.pagination}>
              <button className={s.pageBtn} disabled={safePage === 0} onClick={() => setPage(0)}>«</button>
              <button className={s.pageBtn} disabled={safePage === 0} onClick={() => setPage(p => Math.max(0, p - 1))}>‹</button>
              <span className={s.pageInfo}>{safePage + 1} / {totalPages}</span>
              <button className={s.pageBtn} disabled={safePage >= totalPages - 1} onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))}>›</button>
              <button className={s.pageBtn} disabled={safePage >= totalPages - 1} onClick={() => setPage(totalPages - 1)}>»</button>
            </div>
          )}
          <button className={s.refreshBtn} onClick={() => void exportCsv(filtered)} title="Экспорт в CSV">
            ↓ CSV
          </button>
          <button className={s.refreshBtn} onClick={() => void handleRefresh()} disabled={refreshing} title="Обновить из снапшота">
            {refreshing ? "..." : "↺"}
          </button>
        </div>
      </div>

      {/* ── Filter bar ── */}
      <div className={s.filterBar}>
        <label className={s.filterItem}>
          <span>IP</span>
          <input
            className={s.ipSearchInput}
            type="text"
            placeholder="Поиск по IP..."
            value={filterIp}
            onChange={(e) => { setFilterIp(e.target.value); setPage(0); }}
          />
        </label>
        <label className={s.filterItem}>
          <span>Вердикт</span>
          <select value={filterVerdict} onChange={(e) => { setFilterVerdict(e.target.value as "all" | VerdictLabel); setPage(0); }}>
            <option value="all">Все</option>
            <option value="anomaly">Аномалия</option>
            <option value="warning">Предупреждение</option>
            <option value="normal">Норма</option>
          </select>
        </label>
        <label className={s.filterItem}>
          <span>Тип</span>
          <select value={filterClass} onChange={(e) => { setFilterClass(e.target.value); setPage(0); }}>
            <option value="all">Все</option>
            {allClasses.map((c) => <option key={c} value={c}>{c}</option>)}
            <option value="none">—</option>
          </select>
        </label>
        <label className={s.filterItem}>
          <span>Протокол</span>
          <select value={filterProtocol} onChange={(e) => { setFilterProtocol(e.target.value); setPage(0); }}>
            <option value="all">Все</option>
            {allProtocols.map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
        </label>
        {hasFilters && (
          <button className={s.clearFiltersBtn}
            onClick={() => { setFilterVerdict("all"); setFilterClass("all"); setFilterProtocol("all"); setFilterIp(""); setPage(0); }}>
            × Сбросить
          </button>
        )}
      </div>

      {/* ── Desktop: table ── */}
      <div className={s.desktopTable}>
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th style={{ width: 72 }}>{t("stream.time", "Время")}</th>
                <th>{t("stream.route", "Маршрут")}</th>
                <th style={{ width: 60 }}>Proto</th>
                <th style={{ width: 80 }}>Пакеты</th>
                <th style={{ width: 100 }}>Score</th>
                <th style={{ width: 110 }}>{t("stream.verdict", "Вердикт")}</th>
                <th style={{ minWidth: 90 }}>{t("stream.attack_class", "Класс")}</th>
                <th style={{ width: 130 }}>{t("stream.actions", "Действия")}</th>
              </tr>
            </thead>
            <tbody>
              {paginated.map((item) => {
                const isAttack  = item.inference.label !== "normal";
                const isBlocked = blockedIps.has(item.event.src_ip);
                return (
                  <tr key={item.event.event_id} className={isAttack ? s.attackRow : ""}>
                    <td className={s.timeCell}>{formatTime(item.event.timestamp)}</td>
                    <td>
                      <div className={s.route}>
                        <span className={s.ip}>{item.event.src_ip}</span>
                        <span className={s.port}>:{item.event.src_port}</span>
                        <span className={s.arrow}>→</span>
                        <span className={s.ip}>{item.event.dst_ip}</span>
                        <span className={s.port}>:{item.event.dst_port}</span>
                      </div>
                    </td>
                    <td><span className={s.protoBadge}>{item.event.protocol}</span></td>
                    <td className={s.volumeCell}>
                      <span>{item.event.packet_count}</span>
                      <span className={s.volumeSub}>{formatBytes(item.event.byte_count)}</span>
                    </td>
                    <td><ScoreBar score={item.inference.score} /></td>
                    <td><StatusPill value={item.inference.label} /></td>
                    <td>
                      {item.inference.attack_class
                        ? <span className={getAttackClassStyle(item.inference.attack_class)}>{item.inference.attack_class}</span>
                        : <span className={s.noClass}>—</span>}
                    </td>
                    <td>
                      <div className={s.actionsCell}>
                        {isAttack && !isBlocked && (
                          <button className={s.blockBtn}
                            onClick={() => blockIp(item.event.src_ip, item.event.event_id)}
                            title={`Заблокировать ${item.event.src_ip}`}>
                            Блок
                          </button>
                        )}
                        {isBlocked && (
                          <button className={s.unblockBtn}
                            onClick={() => void handleUnblock(item.event.src_ip)}>
                            Разблок
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {!filtered.length && (
            <p className={styles.emptyState}>
              {hasFilters ? "Нет событий по выбранным фильтрам." : t("stream.empty", "Нет событий. Ожидание трафика...")}
            </p>
          )}
        </div>
      </div>

      {/* ── Mobile: event cards ── */}
      <div className={s.mobileCards}>
        {paginated.map((item) => {
          const isAttack  = item.inference.label !== "normal";
          const isBlocked = blockedIps.has(item.event.src_ip);
          return (
            <div key={item.event.event_id} className={`${s.eventCard} ${isAttack ? s.eventCardAttack : ""}`}>
              <div className={s.cardHead}>
                <div className={s.cardBadges}>
                  <StatusPill value={item.inference.label} />
                  {item.inference.attack_class && (
                    <span className={getAttackClassStyle(item.inference.attack_class)}>
                      {item.inference.attack_class}
                    </span>
                  )}
                </div>
                <span className={s.timeCell}>{formatTime(item.event.timestamp)}</span>
              </div>
              <div className={s.cardRoute}>
                <span className={s.ip}>{item.event.src_ip}</span>
                <span className={s.port}>:{item.event.src_port}</span>
                <span className={s.arrow}>→</span>
                <span className={s.ip}>{item.event.dst_ip}</span>
                <span className={s.port}>:{item.event.dst_port}</span>
              </div>
              <div className={s.cardMeta}>
                <span className={s.protoBadge}>{item.event.protocol}</span>
                <span className={s.cardMetaText}>{item.event.packet_count} pkt · {formatBytes(item.event.byte_count)}</span>
                <ScoreBar score={item.inference.score} />
              </div>
              {(isAttack || isBlocked) && (
                <div className={s.cardAction}>
                  {isAttack && !isBlocked && (
                    <button className={s.blockBtn}
                      onClick={() => blockIp(item.event.src_ip, item.event.event_id)}>
                      Заблокировать {item.event.src_ip}
                    </button>
                  )}
                  {isBlocked && (
                    <button className={s.unblockBtn}
                      onClick={() => void handleUnblock(item.event.src_ip)}>
                      Разблокировать
                    </button>
                  )}
                </div>
              )}
            </div>
          );
        })}
        {!filtered.length && (
          <p className={styles.emptyState}>
            {hasFilters ? "Нет событий по выбранным фильтрам." : t("stream.empty", "Нет событий. Ожидание трафика...")}
          </p>
        )}
      </div>
    </section>
  );
}
