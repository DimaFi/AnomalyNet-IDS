import { useEffect, useRef, useState } from "react";
import { api } from "../../lib/api";
import type { DnsAlert, DnsEntry } from "../../types/dns";
import s from "./DnsView.module.css";

const LS_DNS_FILTERS = "anomalynet_dns_filters";
const LS_DNS_EXCL    = "anomalynet_dns_exclusions";

interface DnsFilters {
  hideLocal:  boolean;
  hidePtr:    boolean;
  onlyAlerts: boolean;
}

const DEFAULT_DNS_FILTERS: DnsFilters = { hideLocal: true, hidePtr: true, onlyAlerts: false };

function loadDnsFilters(): DnsFilters {
  try {
    const raw = localStorage.getItem(LS_DNS_FILTERS);
    if (raw) return { ...DEFAULT_DNS_FILTERS, ...JSON.parse(raw) as Partial<DnsFilters> };
  } catch { /* ignore */ }
  return { ...DEFAULT_DNS_FILTERS };
}

function loadExclusions(): string[] {
  try {
    const raw = localStorage.getItem(LS_DNS_EXCL);
    if (raw) return JSON.parse(raw) as string[];
  } catch { /* ignore */ }
  return [];
}

// ── Matching helpers ──────────────────────────────────────────────────────────

function isLocal(domain: string): boolean {
  const d = domain.toLowerCase();
  return d.endsWith(".local") || d.endsWith(".lan") || d.endsWith(".internal")
    || d.endsWith(".home") || d.endsWith(".localdomain");
}

function isPtr(e: DnsEntry): boolean {
  const d = e.domain.toLowerCase();
  return d.endsWith(".in-addr.arpa") || d.endsWith(".ip6.arpa") || e.qtype === "12";
}

/** Returns true if domain matches a user exclusion pattern.
 *  Supports:  exact match, suffix (.example.com), wildcard (*.example.com) */
function matchesExclusion(domain: string, pattern: string): boolean {
  const p = pattern.toLowerCase().trim();
  const d = domain.toLowerCase();
  if (!p) return false;
  if (p.startsWith("*.")) return d === p.slice(2) || d.endsWith("." + p.slice(2));
  if (p.startsWith("."))  return d === p.slice(1)  || d.endsWith(p);
  return d === p || d.endsWith("." + p);
}

function isExcluded(domain: string, exclusions: string[]): boolean {
  return exclusions.some((ex) => matchesExclusion(domain, ex));
}

// ── Sub-components ────────────────────────────────────────────────────────────

function fmtTime(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString("ru-RU", {
      hour: "2-digit", minute: "2-digit", second: "2-digit",
    });
  } catch { return "—"; }
}

function AlertTypeBadge({ type }: { type: string | null }) {
  if (!type) return <span className={s.statusOk}>норма</span>;
  if (type === "DGA_DOMAIN")    return <span className={s.statusDanger}>DGA</span>;
  if (type === "DNS_TUNNELING") return <span className={s.statusWarn}>tunneling</span>;
  return <span className={s.statusWarn}>{type}</span>;
}

// ── Main component ────────────────────────────────────────────────────────────

export function DnsView() {
  const [tab,         setTab]         = useState<"queries" | "alerts">("queries");
  const [entries,     setEntries]     = useState<DnsEntry[]>([]);
  const [alerts,      setAlerts]      = useState<DnsAlert[]>([]);
  const [topDomains,  setTopDomains]  = useState<{ domain: string; count: number }[]>([]);
  const [available,   setAvailable]   = useState<boolean | null>(null);
  const [filterIp,    setFilterIp]    = useState("");
  const [filters,     setFilters]     = useState<DnsFilters>(loadDnsFilters);
  const [exclusions,  setExclusions]  = useState<string[]>(loadExclusions);
  const [showFilters, setShowFilters] = useState(false);
  const [newPattern,  setNewPattern]  = useState("");
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Persist settings
  useEffect(() => {
    try { localStorage.setItem(LS_DNS_FILTERS, JSON.stringify(filters)); } catch { /* ignore */ }
  }, [filters]);
  useEffect(() => {
    try { localStorage.setItem(LS_DNS_EXCL, JSON.stringify(exclusions)); } catch { /* ignore */ }
  }, [exclusions]);

  const load = () => {
    api.getDnsRecent(filterIp || undefined, 300).then((r) => {
      setAvailable(r.available);
      setEntries(r.items);
    }).catch(() => {});
    api.getDnsAlerts(100).then((r) => setAlerts(r.alerts)).catch(() => {});
    api.getDnsTop(undefined, 30).then((r) => setTopDomains(r.domains)).catch(() => {});
  };

  useEffect(() => {
    load();
    intervalRef.current = setInterval(load, 3000);
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filterIp]);

  function patch(p: Partial<DnsFilters>) { setFilters((f) => ({ ...f, ...p })); }

  function addExclusion(pattern: string) {
    const p = pattern.trim();
    if (!p || exclusions.includes(p)) return;
    setExclusions((prev) => [...prev, p]);
    setNewPattern("");
  }

  function removeExclusion(p: string) {
    setExclusions((prev) => prev.filter((x) => x !== p));
  }

  // Smart suggestions: top domains that aren't alerts and not already excluded
  const alertDomains = new Set(alerts.map((a) => a.domain));
  const suggestions = topDomains
    .filter((d) => !alertDomains.has(d.domain) && !isExcluded(d.domain, exclusions)
      && !isLocal(d.domain) && !d.domain.endsWith(".in-addr.arpa") && !d.domain.endsWith(".ip6.arpa"))
    .slice(0, 6);

  const displayed = entries.filter((e) => {
    if (filters.hideLocal  && isLocal(e.domain))              return false;
    if (filters.hidePtr    && isPtr(e))                       return false;
    if (isExcluded(e.domain, exclusions))                     return false;
    if (filters.onlyAlerts && !e.alert_type)                  return false;
    return true;
  });

  const activeCount = (filters.hideLocal ? 1 : 0) + (filters.hidePtr ? 1 : 0)
    + (filters.onlyAlerts ? 1 : 0) + exclusions.length;

  return (
    <div className={s.wrap}>
      {/* ── Toolbar ── */}
      <div className={s.toolbar}>
        <div className={s.tabs}>
          <button className={`${s.tabBtn} ${tab === "queries" ? s.tabActive : ""}`} onClick={() => setTab("queries")}>
            Запросы {entries.length > 0 && <span className={s.count}>{displayed.length}/{entries.length}</span>}
          </button>
          <button className={`${s.tabBtn} ${tab === "alerts" ? s.tabActive : ""}`} onClick={() => setTab("alerts")}>
            Аномалии {alerts.length > 0 && <span className={`${s.count} ${s.countDanger}`}>{alerts.length}</span>}
          </button>
        </div>

        {tab === "queries" && (
          <div className={s.filters}>
            <input className={s.ipInput} type="text" placeholder="IP..."
              value={filterIp} onChange={(e) => setFilterIp(e.target.value)} />
            <button
              className={`${s.filterToggleBtn} ${showFilters ? s.filterToggleActive : ""}`}
              onClick={() => setShowFilters((v) => !v)}
              title="Настройки отображения"
            >
              ⚙ Фильтры {activeCount > 0 && <span className={s.filterBadge}>{activeCount}</span>}
            </button>
          </div>
        )}
      </div>

      {/* ── Filter panel ── */}
      {tab === "queries" && showFilters && (
        <div className={s.filterPanel}>
          {/* Built-in toggles */}
          <div className={s.filterSection}>
            <div className={s.filterSectionTitle}>Встроенные</div>
            <label className={s.checkLabel}>
              <input type="checkbox" checked={filters.hideLocal}
                onChange={(e) => patch({ hideLocal: e.target.checked })} />
              Скрыть mDNS / .local
            </label>
            <label className={s.checkLabel}>
              <input type="checkbox" checked={filters.hidePtr}
                onChange={(e) => patch({ hidePtr: e.target.checked })} />
              Скрыть PTR / обратный DNS
            </label>
            <label className={s.checkLabel}>
              <input type="checkbox" checked={filters.onlyAlerts}
                onChange={(e) => patch({ onlyAlerts: e.target.checked })} />
              Только аномалии
            </label>
          </div>

          {/* Custom exclusions */}
          <div className={s.filterSection}>
            <div className={s.filterSectionTitle}>Свои исключения</div>
            <div className={s.exclInputRow}>
              <input
                className={s.exclInput}
                type="text"
                placeholder="домен, .суффикс или *.wildcard"
                value={newPattern}
                onChange={(e) => setNewPattern(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") addExclusion(newPattern); }}
              />
              <button className={s.addBtn} onClick={() => addExclusion(newPattern)}>+ Добавить</button>
            </div>
            {exclusions.length > 0 && (
              <div className={s.tagList}>
                {exclusions.map((ex) => (
                  <span key={ex} className={s.tag}>
                    {ex}
                    <button className={s.tagRemove} onClick={() => removeExclusion(ex)}>×</button>
                  </span>
                ))}
              </div>
            )}
          </div>

          {/* Smart suggestions */}
          {suggestions.length > 0 && (
            <div className={s.filterSection}>
              <div className={s.filterSectionTitle}>
                Предложения
                <span className={s.filterSectionHint}> — часто встречаются, не аномалии</span>
              </div>
              <div className={s.suggList}>
                {suggestions.map((d) => (
                  <button key={d.domain} className={s.suggChip} onClick={() => addExclusion(d.domain)}>
                    + {d.domain}
                    <span className={s.suggCount}>×{d.count}</span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {activeCount > 0 && (
            <button className={s.resetBtn} onClick={() => {
              setFilters({ ...DEFAULT_DNS_FILTERS });
              setExclusions([]);
            }}>
              × Сбросить всё
            </button>
          )}
        </div>
      )}

      {available === false && (
        <div className={s.notice}>
          DNS мониторинг доступен только в режиме <strong>linux_live</strong>.
        </div>
      )}

      {/* ── Queries table ── */}
      {tab === "queries" && (
        <div className={s.tableWrap}>
          <table className={s.table}>
            <thead>
              <tr>
                <th>Время</th>
                <th>IP устройства</th>
                <th>Домен</th>
                <th>Тип</th>
                <th>Статус</th>
              </tr>
            </thead>
            <tbody>
              {displayed.map((e, i) => (
                <tr key={i} className={e.alert_type ? s.rowAlert : ""}
                  onContextMenu={(ev) => { ev.preventDefault(); addExclusion(e.domain); }}
                  title="ПКМ — добавить домен в исключения"
                >
                  <td className={s.timeCell}>{fmtTime(e.ts)}</td>
                  <td className={s.ipCell}>{e.src_ip}</td>
                  <td className={s.domainCell} title={e.domain}>{e.domain}</td>
                  <td><span className={s.qtypeBadge}>{e.qtype}</span></td>
                  <td>
                    <AlertTypeBadge type={e.alert_type} />
                    {e.entropy != null && <span className={s.entropy}> H={e.entropy.toFixed(2)}</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {displayed.length === 0 && (
            <p className={s.empty}>
              {available === false
                ? "Данных нет — запустите захват в режиме linux_live."
                : entries.length > 0
                  ? "Все записи скрыты фильтрами."
                  : "DNS-запросов пока нет. Ожидание трафика..."}
            </p>
          )}
        </div>
      )}

      {/* ── Alerts table ── */}
      {tab === "alerts" && (
        <div className={s.tableWrap}>
          <table className={s.table}>
            <thead>
              <tr>
                <th>Время</th><th>IP</th><th>Тип</th><th>Домен</th><th>Описание</th>
              </tr>
            </thead>
            <tbody>
              {alerts.map((a, i) => (
                <tr key={i} className={a.type === "DGA_DOMAIN" ? s.rowDanger : s.rowWarn}>
                  <td className={s.timeCell}>{fmtTime(a.ts)}</td>
                  <td className={s.ipCell}>{a.src_ip}</td>
                  <td><AlertTypeBadge type={a.type} /></td>
                  <td className={s.domainCell} title={a.domain}>{a.domain}</td>
                  <td className={s.descCell}>{a.description}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {alerts.length === 0 && <p className={s.empty}>DNS-аномалий не обнаружено.</p>}
        </div>
      )}
    </div>
  );
}
