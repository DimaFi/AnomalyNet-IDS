import React, { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useAppStore } from "../../app/store";
import type { PipelineEvent, Priority, VerdictLabel } from "../../app/types";
import { StatusPill } from "../../components/StatusPill";
import { formatBytes } from "../../lib/format";
import { api } from "../../lib/api";
import { useBlockIp } from "../../lib/useBlockIp";
import { refreshStreamFromSnapshot } from "../../lib/useRealtimeStream";
import { deviceEmoji } from "../../lib/deviceTypes";
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

// ── Export helpers ────────────────────────────────────────────────────────────

const QUICK_RANGES = [
  { label: "1 час",   hours: 1  },
  { label: "6 часов", hours: 6  },
  { label: "24 часа", hours: 24 },
  { label: "7 дней",  hours: 168 },
] as const;

const PRIORITY_OPTIONS = [
  { value: "all",      label: "Все" },
  { value: "info",     label: "Info+" },
  { value: "medium",   label: "Medium+" },
  { value: "high",     label: "High+" },
  { value: "critical", label: "Critical" },
] as const;

function buildExportUrl(format: "eve" | "csv", fromTs: number, toTs: number, minPriority: string) {
  const params = new URLSearchParams({
    from_ts: String(fromTs),
    to_ts:   String(toTs),
    min_priority: minPriority,
  });
  return `/api/export/${format}?${params.toString()}`;
}

function ExportMenu({ onExportCurrentCsv }: { onExportCurrentCsv: () => void }) {
  const [open,   setOpen]   = useState(false);
  const [modal,  setModal]  = useState(false);
  const wrapRef = React.useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onDoc(e: MouseEvent) {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);
  const [fromDt, setFromDt] = useState(() => {
    const d = new Date(Date.now() - 86400_000);
    return d.toISOString().slice(0, 16);
  });
  const [toDt,   setToDt]   = useState(() => new Date().toISOString().slice(0, 16));
  const [prio,   setPrio]   = useState("all");

  function download(format: "eve" | "csv", hours: number | null, customFrom?: string, customTo?: string, customPrio?: string) {
    const now = Date.now() / 1000;
    const fromTs = hours !== null ? now - hours * 3600 : new Date(customFrom!).getTime() / 1000;
    const toTs   = hours !== null ? now                : new Date(customTo!).getTime()   / 1000;
    window.location.href = buildExportUrl(format, fromTs, toTs, customPrio ?? "all");
  }

  return (
    <div className={s.exportWrap} ref={wrapRef}>
      <button className={s.refreshBtn} onClick={() => setOpen((v) => !v)} title="Экспорт логов">
        ↓ Экспорт
      </button>

      {open && (
        <div className={s.exportDropdown}>
          <div className={s.exportSection}>Экспорт текущего вида</div>
          <button className={s.exportItem} onClick={() => { onExportCurrentCsv(); setOpen(false); }}>
            ↓ CSV (отфильтрованные события)
          </button>

          <div className={s.exportSection}>EVE JSON</div>
          {QUICK_RANGES.map((r) => (
            <button key={r.hours} className={s.exportItem}
              onClick={() => { download("eve", r.hours); setOpen(false); }}>
              ↓ EVE JSON — {r.label}
            </button>
          ))}

          <div className={s.exportSection}>CSV</div>
          {QUICK_RANGES.map((r) => (
            <button key={r.hours} className={s.exportItem}
              onClick={() => { download("csv", r.hours); setOpen(false); }}>
              ↓ CSV — {r.label}
            </button>
          ))}

          <div className={s.exportDivider} />
          <button className={s.exportItem} onClick={() => { setModal(true); setOpen(false); }}>
            ⚙ За период...
          </button>
        </div>
      )}

      {modal && (
        <div className={s.exportOverlay} onClick={(e) => e.target === e.currentTarget && setModal(false)}>
          <div className={s.exportModal}>
            <div className={s.exportModalHeader}>
              <span>Экспорт за период</span>
              <button className={s.exportModalClose} onClick={() => setModal(false)}>×</button>
            </div>
            <div className={s.exportModalBody}>
              <label className={s.exportModalRow}>
                <span>С</span>
                <input type="datetime-local" className={s.exportInput} value={fromDt} onChange={(e) => setFromDt(e.target.value)} />
              </label>
              <label className={s.exportModalRow}>
                <span>По</span>
                <input type="datetime-local" className={s.exportInput} value={toDt} onChange={(e) => setToDt(e.target.value)} />
              </label>
              <label className={s.exportModalRow}>
                <span>Приоритет</span>
                <select className={s.exportInput} value={prio} onChange={(e) => setPrio(e.target.value)}>
                  {PRIORITY_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                </select>
              </label>
            </div>
            <div className={s.exportModalFooter}>
              <button className={s.exportDlBtn} onClick={() => download("eve", null, fromDt, toDt, prio)}>
                ↓ EVE JSON
              </button>
              <button className={s.exportDlBtn} onClick={() => download("csv", null, fromDt, toDt, prio)}>
                ↓ CSV
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

const PRIORITY_WEIGHT: Record<string, number> = { critical: 4, high: 3, medium: 2, info: 1 };
const PRIORITY_BORDER: Record<string, string> = {
  critical: "3px solid #ef4444",
  high:     "3px solid #f97316",
  medium:   "3px solid #eab308",
  info:     "",
};

function isInternalIp(ip: string): boolean {
  return /^(10\.|172\.(1[6-9]|2\d|3[01])\.|192\.168\.)/.test(ip);
}

type SortKey = "time" | "priority" | "score" | "attack_class" | "verdict" | "src_ip" | "dst_ip";

const LS_KEY = "anomalynet_stream_filters";

interface FilterState {
  verdict:    "all" | VerdictLabel;
  cls:        string;
  protocol:   string;
  ip:         string;
  priority:   "all" | Priority;
  timeRange:  0 | 5 | 15 | 60;
  scoreMin:   number;
  scoreMax:   number;
  lanOnly:    boolean;
}

const DEFAULT_FILTERS: FilterState = {
  verdict: "all", cls: "all", protocol: "all", ip: "",
  priority: "all", timeRange: 0, scoreMin: 0, scoreMax: 1, lanOnly: false,
};

function loadFilters(): FilterState {
  try {
    const raw = localStorage.getItem(LS_KEY);
    if (raw) return { ...DEFAULT_FILTERS, ...JSON.parse(raw) as Partial<FilterState> };
  } catch { /* ignore */ }
  return { ...DEFAULT_FILTERS };
}

export function StreamView() {
  const { t } = useTranslation();
  const stream        = useAppStore((state) => state.stream);
  const blockedIps    = useAppStore((state) => state.blockedIps);
  const replaceStream = useAppStore((state) => state.replaceStream);
  const markUnblocked = useAppStore((state) => state.markUnblocked);
  const blockIp       = useBlockIp();
  const [refreshing, setRefreshing] = useState(false);

  const [filters, setFilters] = useState<FilterState>(loadFilters);
  const [page, setPage] = useState(0);
  const [sortKey,  setSortKey]  = useState<SortKey | null>("time");
  const [sortDir,  setSortDir]  = useState<"asc" | "desc">("desc");
  const [pageSize, setPageSize] = useState<number>(() => {
    try { return parseInt(localStorage.getItem("anomalynet_page_size") ?? "100") || 100; } catch { return 100; }
  });

  // Persist filters and page size to localStorage
  useEffect(() => {
    try { localStorage.setItem(LS_KEY, JSON.stringify(filters)); } catch { /* ignore */ }
  }, [filters]);
  useEffect(() => {
    try { localStorage.setItem("anomalynet_page_size", String(pageSize)); } catch { /* ignore */ }
  }, [pageSize]);

  function patchFilters(patch: Partial<FilterState>) {
    setFilters((f) => ({ ...f, ...patch }));
    // Don't reset page — safePage clamping handles out-of-bounds automatically
  }

  function resetFilters() {
    setFilters({ ...DEFAULT_FILTERS });
    setPage(0);
  }

  function handleSort(key: SortKey) {
    if (sortKey === key) setSortDir((d) => d === "asc" ? "desc" : "asc");
    else { setSortKey(key); setSortDir("desc"); }
    // Don't reset page on sort — safePage handles clamping
  }

  async function handleUnblock(ip: string) {
    try { await api.unblockIp(ip); } catch { /* best effort */ }
    markUnblocked(ip);
  }

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

  const now = Date.now();

  const filtered = useMemo(() => {
    const ipQ = filters.ip.trim().toLowerCase();
    return stream.filter((item) => {
      if (filters.verdict !== "all" && item.inference.label !== filters.verdict) return false;
      if (filters.cls !== "all") {
        if (filters.cls === "none" && item.inference.attack_class) return false;
        if (filters.cls !== "none" && item.inference.attack_class !== filters.cls) return false;
      }
      if (filters.protocol !== "all" && item.event.protocol !== filters.protocol) return false;
      if (ipQ && !item.event.src_ip.includes(ipQ) && !item.event.dst_ip.includes(ipQ)) return false;
      if (filters.priority !== "all" && (item.priority ?? "info") !== filters.priority) return false;
      if (filters.timeRange > 0) {
        const age = (now - new Date(item.event.timestamp).getTime()) / 60_000;
        if (age > filters.timeRange) return false;
      }
      if (item.inference.score < filters.scoreMin || item.inference.score > filters.scoreMax) return false;
      if (filters.lanOnly && !isInternalIp(item.event.src_ip)) return false;
      return true;
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stream, filters, now]);

  const sorted = useMemo(() => {
    if (!sortKey) return filtered;
    return [...filtered].sort((a, b) => {
      let va: number | string = 0;
      let vb: number | string = 0;
      if (sortKey === "time")         { va = a.event.timestamp; vb = b.event.timestamp; }
      else if (sortKey === "score")   { va = a.inference.score; vb = b.inference.score; }
      else if (sortKey === "verdict") { va = a.inference.label; vb = b.inference.label; }
      else if (sortKey === "attack_class") { va = a.inference.attack_class ?? ""; vb = b.inference.attack_class ?? ""; }
      else if (sortKey === "src_ip")  { va = a.event.src_ip; vb = b.event.src_ip; }
      else if (sortKey === "dst_ip")  { va = a.event.dst_ip; vb = b.event.dst_ip; }
      else if (sortKey === "priority") {
        va = PRIORITY_WEIGHT[a.priority ?? "info"] ?? 1;
        vb = PRIORITY_WEIGHT[b.priority ?? "info"] ?? 1;
      }
      if (va < vb) return sortDir === "asc" ? -1 : 1;
      if (va > vb) return sortDir === "asc" ? 1 : -1;
      return 0;
    });
  }, [filtered, sortKey, sortDir]);

  const hasFilters = filters.verdict !== "all" || filters.cls !== "all" || filters.protocol !== "all"
    || !!filters.ip || filters.priority !== "all" || filters.timeRange > 0
    || filters.scoreMin > 0 || filters.scoreMax < 1 || filters.lanOnly;

  // Freeze sorted array while user is on any page > 0 so live updates
  // don't shift content or change the page counter under their hands.
  const frozenSorted = React.useRef(sorted);
  useEffect(() => {
    if (page === 0) frozenSorted.current = sorted;
  }, [sorted, page]);
  const stableSorted = page === 0 ? sorted : frozenSorted.current;

  const totalPages = Math.max(1, Math.ceil(stableSorted.length / pageSize));
  const safePage   = Math.min(page, totalPages - 1);
  const paginated  = stableSorted.slice(safePage * pageSize, (safePage + 1) * pageSize);

  function SortIcon({ col }: { col: SortKey }) {
    if (sortKey !== col) return <span className={s.sortNeutral}>⇅</span>;
    return <span className={s.sortActive}>{sortDir === "asc" ? "↑" : "↓"}</span>;
  }

  return (
    <section className={`${styles.panel} ${s.streamPanel}`}>
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
            {stream.length >= 500 && <span className={s.counterMax} title="Буфер заполнен"> max</span>}
          </span>
          <div className={s.pagination}>
            <button className={s.pageBtn} disabled={safePage === 0} onClick={() => setPage(0)}>«</button>
            <button className={s.pageBtn} disabled={safePage === 0} onClick={() => setPage(p => Math.max(0, p - 1))}>‹</button>
            <span className={s.pageInfo}>{safePage + 1} / {totalPages}</span>
            <button className={s.pageBtn} disabled={safePage >= totalPages - 1} onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))}>›</button>
            <button className={s.pageBtn} disabled={safePage >= totalPages - 1} onClick={() => setPage(totalPages - 1)}>»</button>
            <select
              className={s.pageSizeSelect}
              value={pageSize}
              onChange={(e) => { setPageSize(Number(e.target.value)); setPage(0); }}
              title="Строк на странице"
            >
              {[25, 50, 100, 250].map((n) => (
                <option key={n} value={n}>{n}</option>
              ))}
            </select>
          </div>
          <ExportMenu onExportCurrentCsv={() => void exportCsv(filtered)} />
          <button className={s.refreshBtn} onClick={() => void handleRefresh()} disabled={refreshing} title="Обновить из снапшота">
            {refreshing ? "..." : "↺"}
          </button>
        </div>
      </div>

      {/* ── Filter bar ── */}
      <div className={s.filterBar}>
        {/* Row 1: existing filters */}
        <div className={s.filterRow}>
          <label className={s.filterItem}>
            <span>IP</span>
            <input
              className={`${s.ipSearchInput} ${filters.ip ? s.filterActive : ""}`}
              type="text"
              placeholder="src / dst..."
              value={filters.ip}
              onChange={(e) => patchFilters({ ip: e.target.value })}
            />
          </label>
          <label className={s.filterItem}>
            <span>Вердикт</span>
            <select
              className={filters.verdict !== "all" ? s.filterActive : ""}
              value={filters.verdict}
              onChange={(e) => patchFilters({ verdict: e.target.value as FilterState["verdict"] })}
            >
              <option value="all">Все</option>
              <option value="anomaly">Аномалия</option>
              <option value="warning">Предупреждение</option>
              <option value="normal">Норма</option>
            </select>
          </label>
          <label className={s.filterItem}>
            <span>Тип</span>
            <select
              className={filters.cls !== "all" ? s.filterActive : ""}
              value={filters.cls}
              onChange={(e) => patchFilters({ cls: e.target.value })}
            >
              <option value="all">Все</option>
              {allClasses.map((c) => <option key={c} value={c}>{c}</option>)}
              <option value="none">—</option>
            </select>
          </label>
          <label className={s.filterItem}>
            <span>Протокол</span>
            <select
              className={filters.protocol !== "all" ? s.filterActive : ""}
              value={filters.protocol}
              onChange={(e) => patchFilters({ protocol: e.target.value })}
            >
              <option value="all">Все</option>
              {allProtocols.map((p) => <option key={p} value={p}>{p}</option>)}
            </select>
          </label>
        </div>

        {/* Row 2: new filters */}
        <div className={s.filterRow}>
          <label className={s.filterItem}>
            <span>Приоритет</span>
            <select
              className={filters.priority !== "all" ? s.filterActive : ""}
              value={filters.priority}
              onChange={(e) => patchFilters({ priority: e.target.value as FilterState["priority"] })}
            >
              <option value="all">Все</option>
              <option value="critical">Critical</option>
              <option value="high">High</option>
              <option value="medium">Medium</option>
              <option value="info">Info</option>
            </select>
          </label>
          <label className={s.filterItem}>
            <span>Период</span>
            <div className={s.timeRangeBtns}>
              {([5, 15, 60, 0] as const).map((m) => (
                <button
                  key={m}
                  className={`${s.timeBtn} ${filters.timeRange === m ? s.timeBtnActive : ""}`}
                  onClick={() => patchFilters({ timeRange: m })}
                >
                  {m === 0 ? "Всё" : m === 60 ? "1ч" : `${m}м`}
                </button>
              ))}
            </div>
          </label>
          <label className={s.filterItem}>
            <span>Score</span>
            <div className={s.scoreRange}>
              <input
                type="number" min={0} max={1} step={0.05}
                className={`${s.scoreInput} ${filters.scoreMin > 0 ? s.filterActive : ""}`}
                value={filters.scoreMin}
                onChange={(e) => patchFilters({ scoreMin: parseFloat(e.target.value) || 0 })}
              />
              <span>—</span>
              <input
                type="number" min={0} max={1} step={0.05}
                className={`${s.scoreInput} ${filters.scoreMax < 1 ? s.filterActive : ""}`}
                value={filters.scoreMax}
                onChange={(e) => patchFilters({ scoreMax: parseFloat(e.target.value) || 1 })}
              />
            </div>
          </label>
          <label className={`${s.filterItem} ${s.filterItemInline}`}>
            <input
              type="checkbox"
              checked={filters.lanOnly}
              onChange={(e) => patchFilters({ lanOnly: e.target.checked })}
            />
            <span className={filters.lanOnly ? s.filterActive : ""}>Только LAN</span>
          </label>
          {hasFilters && (
            <button className={s.clearFiltersBtn} onClick={resetFilters}>
              × Сбросить
            </button>
          )}
        </div>

        {/* Counter */}
        {filtered.length !== stream.length && (
          <p className={s.filterCounter}>Показано: {filtered.length} из {stream.length}</p>
        )}
      </div>

      {/* ── Desktop: table ── */}
      <div className={s.desktopTable}>
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th style={{ width: 72 }} className={s.sortable} onClick={() => handleSort("time")}>{t("stream.time", "Время")} <SortIcon col="time" /></th>
                <th className={s.sortable} onClick={() => handleSort("src_ip")}>{t("stream.route", "Маршрут")} <SortIcon col="src_ip" /></th>
                <th style={{ width: 90 }} className={s.colDevice}>{t("stream.device", "Устройство")}</th>
                <th style={{ width: 60 }}>Proto</th>
                <th style={{ width: 80 }}>Пакеты</th>
                <th style={{ width: 100 }} className={s.sortable} onClick={() => handleSort("score")}>Score <SortIcon col="score" /></th>
                <th style={{ width: 110 }} className={s.sortable} onClick={() => handleSort("verdict")}>{t("stream.verdict", "Вердикт")} <SortIcon col="verdict" /></th>
                <th style={{ minWidth: 90 }} className={s.sortable} onClick={() => handleSort("attack_class")}>{t("stream.attack_class", "Класс")} <SortIcon col="attack_class" /></th>
                <th style={{ width: 60 }} className={s.sortable} onClick={() => handleSort("priority")}>P <SortIcon col="priority" /></th>
                <th style={{ width: 130 }}>{t("stream.actions", "Действия")}</th>
              </tr>
            </thead>
            <tbody>
              {paginated.map((item) => {
                const isAttack  = item.inference.label !== "normal";
                const isBlocked = blockedIps.has(item.event.src_ip);
                const prio      = item.priority ?? "info";
                const prioBorder = PRIORITY_BORDER[prio];
                return (
                  <tr
                    key={item.event.event_id}
                    className={`${isAttack ? s.attackRow : ""} ${prio === "info" ? s.rowInfo : ""}`}
                    style={prioBorder ? { borderLeft: prioBorder } : undefined}
                  >
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
                    <td className={s.colDevice}>
                      <span
                        className={s.deviceCell}
                        title={[item.device_type, item.pipeline_used ? `via ${item.pipeline_used}` : null].filter(Boolean).join(" · ")}
                      >
                        <span className={s.deviceEmoji}>{deviceEmoji(item.device_type)}</span>
                        {item.device_name && <span className={s.deviceName}>{item.device_name}</span>}
                      </span>
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
                        ? (
                          <span className={getAttackClassStyle(item.inference.attack_class)}>
                            {item.inference.attack_class}
                            {item.mitre && (
                              <a
                                className={s.mitreBadge}
                                href={`https://attack.mitre.org/techniques/${item.mitre.id}/`}
                                target="_blank"
                                rel="noopener noreferrer"
                                title={`${item.mitre.id} · ${item.mitre.name} · ${item.mitre.tactic}`}
                                onClick={(e) => e.stopPropagation()}
                              >
                                {item.mitre.id} · {item.mitre.tactic}
                              </a>
                            )}
                          </span>
                        )
                        : <span className={s.noClass}>—</span>}
                    </td>
                    <td>
                      <span className={`${s.prioBadge} ${s[`prio-${prio}`]}`} title={prio}>
                        {prio === "critical" ? "!!!" : prio === "high" ? "!!" : prio === "medium" ? "!" : "·"}
                      </span>
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
                      {item.mitre && (
                        <a
                          className={s.mitreBadge}
                          href={`https://attack.mitre.org/techniques/${item.mitre.id}/`}
                          target="_blank"
                          rel="noopener noreferrer"
                          title={`${item.mitre.id} · ${item.mitre.name} · ${item.mitre.tactic}`}
                          onClick={(e) => e.stopPropagation()}
                        >
                          {item.mitre.id} · {item.mitre.tactic}
                        </a>
                      )}
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
