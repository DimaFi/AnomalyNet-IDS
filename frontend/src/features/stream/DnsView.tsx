import { useEffect, useRef, useState } from "react";
import { api } from "../../lib/api";
import type { DnsAlert, DnsEntry } from "../../types/dns";
import s from "./DnsView.module.css";

function fmtTime(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString("ru-RU", {
      hour: "2-digit", minute: "2-digit", second: "2-digit",
    });
  } catch { return "—"; }
}

function AlertTypeBadge({ type }: { type: string | null }) {
  if (!type) return <span className={s.statusOk}>норма</span>;
  if (type === "DGA_DOMAIN") return <span className={s.statusDanger}>DGA</span>;
  if (type === "DNS_TUNNELING") return <span className={s.statusWarn}>tunneling</span>;
  return <span className={s.statusWarn}>{type}</span>;
}

export function DnsView() {
  const [tab, setTab] = useState<"queries" | "alerts">("queries");
  const [entries, setEntries] = useState<DnsEntry[]>([]);
  const [alerts, setAlerts] = useState<DnsAlert[]>([]);
  const [available, setAvailable] = useState<boolean | null>(null);
  const [filterIp, setFilterIp] = useState("");
  const [showOnlyAlerts, setShowOnlyAlerts] = useState(false);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const load = () => {
    api.getDnsRecent(filterIp || undefined, 200).then((r) => {
      setAvailable(r.available);
      setEntries(r.items);
    }).catch(() => {});
    api.getDnsAlerts(100).then((r) => setAlerts(r.alerts)).catch(() => {});
  };

  useEffect(() => {
    load();
    intervalRef.current = setInterval(load, 3000);
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filterIp]);

  const displayed = showOnlyAlerts
    ? entries.filter((e) => e.alert_type !== null)
    : entries;

  return (
    <div className={s.wrap}>
      {/* ── Controls ── */}
      <div className={s.toolbar}>
        <div className={s.tabs}>
          <button className={`${s.tabBtn} ${tab === "queries" ? s.tabActive : ""}`} onClick={() => setTab("queries")}>
            Запросы {entries.length > 0 && <span className={s.count}>{entries.length}</span>}
          </button>
          <button className={`${s.tabBtn} ${tab === "alerts" ? s.tabActive : ""}`} onClick={() => setTab("alerts")}>
            Аномалии {alerts.length > 0 && <span className={`${s.count} ${s.countDanger}`}>{alerts.length}</span>}
          </button>
        </div>

        {tab === "queries" && (
          <div className={s.filters}>
            <input
              className={s.ipInput}
              type="text"
              placeholder="Фильтр по IP..."
              value={filterIp}
              onChange={(e) => setFilterIp(e.target.value)}
            />
            <label className={s.checkLabel}>
              <input
                type="checkbox"
                checked={showOnlyAlerts}
                onChange={(e) => setShowOnlyAlerts(e.target.checked)}
              />
              Только аномалии
            </label>
          </div>
        )}
      </div>

      {available === false && (
        <div className={s.notice}>
          DNS мониторинг доступен только в режиме <strong>linux_live</strong>.
          В текущем режиме DNS-запросы не захватываются.
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
                <tr key={i} className={e.alert_type ? s.rowAlert : ""}>
                  <td className={s.timeCell}>{fmtTime(e.ts)}</td>
                  <td className={s.ipCell}>{e.src_ip}</td>
                  <td className={s.domainCell} title={e.domain}>{e.domain}</td>
                  <td><span className={s.qtypeBadge}>{e.qtype}</span></td>
                  <td>
                    <AlertTypeBadge type={e.alert_type} />
                    {e.entropy != null && (
                      <span className={s.entropy}> H={e.entropy.toFixed(2)}</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {displayed.length === 0 && (
            <p className={s.empty}>
              {available === false
                ? "Данных нет — запустите захват в режиме linux_live."
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
                <th>Время</th>
                <th>IP</th>
                <th>Тип</th>
                <th>Домен</th>
                <th>Описание</th>
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
          {alerts.length === 0 && (
            <p className={s.empty}>DNS-аномалий не обнаружено.</p>
          )}
        </div>
      )}
    </div>
  );
}
