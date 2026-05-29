import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useAppStore } from "../../app/store";
import { api } from "../../lib/api";
import type { Device, DeviceAlert, DevicesWsMessage } from "../../types/device";
import type { DeviceDnsSummary } from "../../types/dns";
import s from "./NetworkMapView.module.css";

// Device types are localized inline via t("network.deviceTypes.<key>")
const DEVICE_TYPE_KEYS = [
  "iot_camera","iot_sensor","iot_bulb","iot_plug","router",
  "pc_windows","pc_linux","pc_mac","phone","printer",
  "nas","game_console","tv","unknown",
] as const;

function fmtBytes(b: number): string {
  if (b < 1024) return `${b} B`;
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`;
  return `${(b / 1024 / 1024).toFixed(1)} MB`;
}

function fmtTime(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

// ── Risk helpers ─────────────────────────────────────────────────────────────

const RISK_COLORS: Record<string, string> = {
  low:      "#22c55e",
  medium:   "#eab308",
  high:     "#f97316",
  critical: "#ef4444",
};

const RISK_LABELS_RU: Record<string, string> = {
  low: "LOW", medium: "MEDIUM", high: "HIGH", critical: "CRITICAL",
};

function RiskBar({ score, label, compact = false }: { score: number; label: string; compact?: boolean }) {
  const color = RISK_COLORS[label] ?? RISK_COLORS.low;
  if (compact) {
    return (
      <div className={s.riskBarWrap} title={`Риск: ${score}/100 (${label})`}>
        <div className={s.riskBarTrack}>
          <div className={s.riskBarFill} style={{ width: `${score}%`, background: color }} />
        </div>
      </div>
    );
  }
  return (
    <div className={s.riskBlock}>
      <div className={s.riskHeader}>
        <span className={s.riskTitle}>Риск</span>
        <span className={s.riskBadge} style={{ background: `${color}22`, color, border: `1px solid ${color}55` }}>
          {RISK_LABELS_RU[label] ?? label}
        </span>
      </div>
      <div className={s.riskScoreLine}>
        <span className={s.riskScore} style={{ color }}>{score}</span>
        <span className={s.riskScoreMax}> / 100</span>
      </div>
      <div className={s.riskBarTrackFull}>
        <div className={s.riskBarFill} style={{ width: `${score}%`, background: color }} />
      </div>
    </div>
  );
}

// ── Info row helper ──────────────────────────────────────────────────────────

function InfoRow({ label, value, mono = false, ok = false, danger = false, warn = false }: {
  label: string; value: string; mono?: boolean; ok?: boolean; danger?: boolean; warn?: boolean;
}) {
  const color = ok ? "var(--ok)" : danger ? "var(--danger-strong)" : warn ? "#f97316" : undefined;
  return (
    <div className={s.infoRow}>
      <span className={s.infoLabel}>{label}</span>
      <span className={s.infoValue} style={{ fontFamily: mono ? "monospace" : undefined, fontSize: mono ? 11 : undefined, color }}>{value}</span>
    </div>
  );
}

// ── Device Card ──────────────────────────────────────────────────────────────

function DeviceCard({ device, selected, onClick }: {
  device: Device; selected: boolean; onClick: () => void;
}) {
  const cls = [
    s.deviceCard,
    selected ? s.deviceCardSelected : "",
    device.is_suspicious ? s.deviceCardSuspicious : "",
    !device.is_online ? s.deviceCardOffline : "",
    device.is_self ? s.deviceCardSelf : "",
  ].filter(Boolean).join(" ");

  return (
    <div className={cls} onClick={onClick}>
      <div className={s.cardEmoji}>{device.device_emoji}</div>
      <div className={s.cardName} title={device.display_name}>{device.display_name}</div>
      <div className={s.cardIp}>{device.ip}</div>
      <RiskBar score={device.risk_score} label={device.risk_label} compact />
      {device.is_self && (
        <div className={s.selfCardBadge}>🖥 This device</div>
      )}
      {device.is_suspicious && (
        <div className={`${s.cardBadge} ${s.cardBadgeDanger}`}>⚠ suspicious</div>
      )}
      {!device.is_online && (
        <div className={`${s.cardBadge} ${s.cardBadgeOff}`}>offline</div>
      )}
    </div>
  );
}

// ── Device Panel (tabbed modal drawer) ───────────────────────────────────────

type TabKey = "overview" | "security" | "dns" | "tls" | "recon" | "manage";
const PANEL_TAB_KEYS: { key: TabKey; labelKey: string }[] = [
  { key: "overview",  labelKey: "network.tabOverview" },
  { key: "security",  labelKey: "network.tabSecurity" },
  { key: "dns",       labelKey: "network.tabDns" },
  { key: "tls",       labelKey: "network.tabTls" },
  { key: "recon",     labelKey: "network.tabRecon" },
  { key: "manage",    labelKey: "network.tabManage" },
];

function DevicePanel({ device, onClose, onUpdate, canBlock = true }: {
  device: Device; onClose: () => void; onUpdate: () => void; canBlock?: boolean;
}) {
  const { t } = useTranslation();
  const [tab, setTab] = useState<TabKey>("overview");
  const [history, setHistory] = useState<DeviceAlert[]>([]);
  const [dnsSummary, setDnsSummary] = useState<DeviceDnsSummary | null>(null);
  const [tlsData, setTlsData] = useState<Record<string, { count: number; first_seen: string; last_seen: string }> | null>(null);
  const [renaming, setRenaming] = useState(false);
  const [nameInput, setNameInput] = useState(device.custom_name || device.hostname || "");
  const [typeInput, setTypeInput] = useState(device.device_type);
  const [loading, setLoading] = useState(false);
  const [probeResult, setProbeResult] = useState<{ reachable: boolean; latency_ms: number | null; open_ports: number[] } | null>(null);
  const [probing, setProbing] = useState(false);
  const [inspectResult, setInspectResult] = useState<{
    ip: string; os_guess: string | null;
    services: { port: number; protocol: string; title?: string; server?: string; banner?: string; status?: number }[];
    web_urls: string[]; rtsp_url: string | null;
  } | null>(null);
  const [inspecting, setInspecting] = useState(false);
  const [inspectError, setInspectError] = useState<string | null>(null);

  useEffect(() => {
    api.getDeviceHistory(device.mac).then(setHistory).catch(() => {});
    api.getDeviceDnsSummary(device.ip).then(setDnsSummary).catch(() => {});
    api.getTlsProfiles(device.ip).then(r => setTlsData(r.profiles[device.ip] ?? null)).catch(() => {});
  }, [device.mac, device.ip]);

  const handleRename = async () => {
    setLoading(true);
    try {
      await api.labelDevice(device.mac, nameInput, typeInput);
      onUpdate();
      setRenaming(false);
    } catch { /* ignore */ } finally { setLoading(false); }
  };

  const handleWhitelist = async () => {
    setLoading(true);
    try {
      if (device.is_whitelisted) await api.unwhitelistDevice(device.mac);
      else await api.whitelistDevice(device.mac);
      onUpdate();
    } catch { /* ignore */ } finally { setLoading(false); }
  };

  const handleReset = async () => {
    setLoading(true);
    try { await api.resetDevice(device.mac); onUpdate(); }
    catch { /* ignore */ } finally { setLoading(false); }
  };

  const handleBlock = async () => {
    setLoading(true);
    try { await api.blockIp(device.ip); onUpdate(); }
    catch { /* ignore */ } finally { setLoading(false); }
  };

  const handleRemove = async () => {
    if (!confirm(`Удалить устройство ${device.display_name}?`)) return;
    setLoading(true);
    try { await api.removeDevice(device.mac); onClose(); onUpdate(); }
    catch { /* ignore */ } finally { setLoading(false); }
  };

  const handleProbe = async () => {
    setProbing(true);
    setProbeResult(null);
    try {
      const r = await api.probeDevice(device.mac);
      setProbeResult(r);
    } catch { setProbeResult({ reachable: false, latency_ms: null, open_ports: [] }); }
    finally { setProbing(false); }
  };

  const handleInspect = async () => {
    setInspecting(true);
    setInspectResult(null);
    setInspectError(null);
    try {
      const r = await api.inspectDevice(device.mac);
      setInspectResult(r);
    } catch (e) {
      setInspectError(e instanceof Error ? e.message : "Ошибка подключения к устройству");
    } finally { setInspecting(false); }
  };

  return (
    <div style={{ position: "fixed", inset: 0, zIndex: 200, display: "flex", justifyContent: "flex-end" }}>
      <div style={{ position: "absolute", inset: 0, background: "rgba(0,0,0,0.5)" }} onClick={onClose} />
      <aside className={s.drawer}>

        {/* Header */}
        <div className={s.drawerHeader}>
          <span style={{ fontSize: 26, lineHeight: 1, flexShrink: 0 }}>{device.device_emoji}</span>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div className={s.drawerTitle}>{device.display_name}</div>
            <div className={s.drawerSub}>{device.device_label} · {device.vendor}</div>
          </div>
          {device.is_self && <span className={s.selfBadge}>🖥 Это устройство</span>}
          <button className={s.panelClose} onClick={onClose}>✕</button>
        </div>

        {/* Status badges */}
        <div className={s.drawerBadges}>
          <span className={s.ipMonoBadge}>{device.ip}</span>
          {device.is_suspicious && <span className={`${s.bdg} ${s.bdgWarn}`}>{t("network.isSuspicious")}</span>}
          {device.is_whitelisted && <span className={`${s.bdg} ${s.bdgOk}`}>{t("network.isWhitelisted")}</span>}
          {!device.is_online && <span className={`${s.bdg} ${s.bdgMuted}`}>{t("common.offline")}</span>}
        </div>

        {/* Risk */}
        <div style={{ padding: "4px 16px 8px" }}>
          <RiskBar score={device.risk_score} label={device.risk_label} />
        </div>

        {/* Tabs */}
        <div className={s.tabs}>
          {PANEL_TAB_KEYS.map(tabDef => (
            <button key={tabDef.key}
              className={[s.tab, tab === tabDef.key ? s.tabActive : ""].filter(Boolean).join(" ")}
              onClick={() => setTab(tabDef.key)}>
              {t(tabDef.labelKey)}
            </button>
          ))}
        </div>

        <div className={s.drawerBody}>
          {/* ── TAB: ОБЗОР ──────────────────────────────────────── */}
          {tab === "overview" && (
            <div className={s.tabContent}>
              <div className={s.infoSection}>
                <div className={s.infoSectionTitle}>{t("network.sectionNetwork")}</div>
                <InfoRow label="IP" value={device.ip} mono />
                <InfoRow label="MAC" value={device.mac} mono />
                {device.hostname && <InfoRow label={t("network.hostname")} value={device.hostname} />}
                <InfoRow label={t("network.vendor")} value={device.vendor} />
                <InfoRow label={t("network.type")} value={device.device_label} />
                <InfoRow label={t("network.status")} value={device.is_online ? t("common.online") : t("common.offline")} ok={device.is_online} danger={!device.is_online} />
                {device.first_seen && <InfoRow label={t("network.firstSeen")} value={fmtTime(device.first_seen)} />}
                {device.last_seen && <InfoRow label={t("network.lastSeen")} value={fmtTime(device.last_seen)} />}
              </div>
              <div className={s.infoSection}>
                <div className={s.infoSectionTitle}>{t("network.traffic")}</div>
                <InfoRow label={t("network.inbound")} value={fmtBytes(device.bytes_in)} />
                <InfoRow label={t("network.outbound")} value={fmtBytes(device.bytes_out)} />
              </div>
              {device.open_ports.length > 0 && (
                <div className={s.infoSection}>
                  <div className={s.infoSectionTitle}>{t("network.openPorts")}</div>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                    {device.open_ports.map(p => (
                      <span key={p} style={{ fontFamily: "monospace", fontSize: 11, padding: "2px 6px", borderRadius: 4, background: "var(--surface-3)", color: "var(--accent)" }}>
                        {p}
                      </span>
                    ))}
                  </div>
                </div>
              )}
              {!device.is_self && (
                <div className={s.gatewayNote}>
                  {t("network.gatewayNote")}
                </div>
              )}
            </div>
          )}

          {/* ── TAB: БЕЗОПАСНОСТЬ ───────────────────────────────── */}
          {tab === "security" && (
            <div className={s.tabContent}>
              <div className={s.infoSection}>
                <div className={s.infoSectionTitle}>Риск-факторы</div>
                {device.alert_count > 0 && <InfoRow label="ML алертов" value={String(device.alert_count)} danger />}
                {device.dns_alert_count > 0 && <InfoRow label="DNS аномалий" value={String(device.dns_alert_count)} warn />}
                {device.last_alert_type && <InfoRow label="Тип угрозы" value={device.last_alert_type} danger />}
                {device.last_alert_score != null && <InfoRow label="Score" value={`${(device.last_alert_score * 100).toFixed(0)}%`} danger />}
                {device.last_alert_time && <InfoRow label="Время угрозы" value={fmtTime(device.last_alert_time)} />}
                {device.alert_count === 0 && device.dns_alert_count === 0 && (
                  <div style={{ fontSize: 12, color: "var(--text-muted)", padding: "8px 0" }}>Угроз не обнаружено</div>
                )}
              </div>
              {history.length > 0 && (
                <div className={s.infoSection}>
                  <div className={s.infoSectionTitle}>История алертов ({history.length})</div>
                  {history.slice(0, 10).map((a, i) => (
                    <div key={i} className={s.alertItem}>
                      <span className={s.alertTs}>{fmtTime(a.ts)}</span>
                      <span className={s.alertLbl}>{a.attack_class || a.label}</span>
                      {a.score != null && <span className={s.alertScore}>{(a.score * 100).toFixed(0)}%</span>}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* ── TAB: DNS ────────────────────────────────────────── */}
          {tab === "dns" && (
            <div className={s.tabContent}>
              {dnsSummary && dnsSummary.available && dnsSummary.total_queries > 0 ? (
                <>
                  <div className={s.infoSection}>
                    <div className={s.infoSectionTitle}>
                      Активность
                      {dnsSummary.alert_count > 0 && (
                        <span className={`${s.bdg} ${s.bdgWarn}`} style={{ marginLeft: 8 }}>⚠ {dnsSummary.alert_count} аномалий</span>
                      )}
                    </div>
                    <InfoRow label="Всего запросов" value={String(dnsSummary.total_queries)} />
                  </div>
                  <div className={s.infoSection}>
                    <div className={s.infoSectionTitle}>Топ домены</div>
                    {dnsSummary.top_domains.map((d) => (
                      <div key={d.domain} className={s.dnsRow}>
                        <span className={s.dnsDomain} title={d.domain}>{d.domain}</span>
                        <span className={s.dnsCount}>×{d.count}</span>
                      </div>
                    ))}
                  </div>
                </>
              ) : (
                <div style={{ fontSize: 12, color: "var(--text-muted)", padding: "16px 0", textAlign: "center" }}>
                  {dnsSummary && !dnsSummary.available ? "DNS мониторинг отключён" : "DNS-запросов не обнаружено"}
                </div>
              )}
              {!device.is_self && (
                <div className={s.gatewayNote}>
                  ℹ DNS запросы других устройств видны только если AnomalyNet работает как шлюз
                </div>
              )}
            </div>
          )}

          {/* ── TAB: TLS ────────────────────────────────────────── */}
          {tab === "tls" && (
            <div className={s.tabContent}>
              {tlsData && Object.keys(tlsData).length > 0 ? (
                <div className={s.infoSection}>
                  <div className={s.infoSectionTitle}>JA4 профили ({Object.keys(tlsData).length})</div>
                  {Object.entries(tlsData).map(([ja4, info]) => (
                    <div key={ja4} className={s.ja4Row}>
                      <div style={{ fontFamily: "monospace", fontSize: 10, color: "var(--accent)", wordBreak: "break-all" }}>{ja4}</div>
                      <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 2 }}>
                        ×{info.count} · {fmtTime(info.last_seen)}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div style={{ fontSize: 12, color: "var(--text-muted)", padding: "16px 0", textAlign: "center" }}>
                  TLS fingerprints не обнаружены
                </div>
              )}
              {!device.is_self && (
                <div className={s.gatewayNote}>
                  ℹ TLS fingerprints других устройств видны только если AnomalyNet работает как шлюз
                </div>
              )}
            </div>
          )}

          {/* ── TAB: РАЗВЕДКА ───────────────────────────────────── */}
          {tab === "recon" && (
            <div className={s.tabContent}>
              <div className={s.infoSection}>
                <div className={s.infoSectionTitle}>Тест доступности</div>
                <button className={s.actionBtn} onClick={handleProbe} disabled={probing}>
                  {probing ? "⟳ Проверяю..." : "⚡ Пинг + порты"}
                </button>
                {probeResult && (
                  <div style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: 4 }}>
                    <InfoRow label="Доступен" value={probeResult.reachable ? `✓ да${probeResult.latency_ms != null ? ` (${probeResult.latency_ms} мс)` : ""}` : "✗ нет"} ok={probeResult.reachable} danger={!probeResult.reachable} />
                    {probeResult.open_ports.length > 0 && (
                      <InfoRow label="Порты" value={probeResult.open_ports.join(", ")} mono />
                    )}
                  </div>
                )}
              </div>
              <div className={s.infoSection}>
                <div className={s.infoSectionTitle}>Инспекция сервисов</div>
                <p style={{ fontSize: 11, color: "var(--text-muted)", margin: "0 0 8px" }}>
                  HTTP/HTTPS баннеры, SSH/FTP/RTSP, определение ОС по TTL
                </p>
                <button className={s.actionBtn} onClick={handleInspect} disabled={inspecting}>
                  {inspecting ? "⟳ Сканирую..." : "🔍 Инспекция"}
                </button>
                {inspectError && (
                  <div style={{ fontSize: 11, color: "var(--danger)", marginTop: 4 }}>✗ {inspectError}</div>
                )}
                {inspectResult && (
                  <div style={{ fontSize: 11, display: "flex", flexDirection: "column", gap: 4, marginTop: 6 }}>
                    {inspectResult.os_guess && <InfoRow label="ОС (TTL)" value={inspectResult.os_guess} />}
                    {inspectResult.web_urls.length > 0 && (
                      <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                        <span style={{ fontSize: 10, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.06em" }}>Веб-интерфейсы</span>
                        {inspectResult.web_urls.map(url => (
                          <a key={url} href={url} target="_blank" rel="noopener noreferrer"
                            style={{ color: "var(--accent)", fontSize: 11, wordBreak: "break-all", textDecoration: "none" }}>
                            🌐 {url}
                          </a>
                        ))}
                      </div>
                    )}
                    {inspectResult.rtsp_url && (
                      <InfoRow label="RTSP" value={inspectResult.rtsp_url} mono warn />
                    )}
                    {inspectResult.services.map((sv, i) => (
                      <div key={i} style={{ background: "var(--surface-3)", borderRadius: 4, padding: "3px 6px", fontSize: 11 }}>
                        <span style={{ color: "var(--accent)", fontFamily: "monospace" }}>:{sv.port}</span>
                        {" "}<span style={{ color: "var(--text-muted)" }}>{sv.protocol}</span>
                        {sv.title && <span style={{ marginLeft: 4 }}>{sv.title}</span>}
                        {sv.banner && <span style={{ color: "var(--text-muted)", marginLeft: 4, fontFamily: "monospace", fontSize: 10 }}>{sv.banner.slice(0, 60)}</span>}
                      </div>
                    ))}
                    {inspectResult.services.length === 0 && !inspectResult.os_guess && inspectResult.web_urls.length === 0 && (
                      <span style={{ color: "var(--text-muted)" }}>Ничего не найдено</span>
                    )}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* ── TAB: УПРАВЛЕНИЕ ─────────────────────────────────── */}
          {tab === "manage" && (
            <div className={s.tabContent}>
              <div className={s.infoSection}>
                <div className={s.infoSectionTitle}>Переименование</div>
                {renaming ? (
                  <>
                    <input
                      className={s.renameInput}
                      value={nameInput}
                      onChange={(e) => setNameInput(e.target.value)}
                      placeholder="Имя устройства"
                      onKeyDown={(e) => { if (e.key === "Enter") handleRename(); if (e.key === "Escape") setRenaming(false); }}
                      autoFocus
                    />
                    <select className={s.typeSelect} value={typeInput} onChange={(e) => setTypeInput(e.target.value)}>
                      {DEVICE_TYPE_KEYS.map((k) => <option key={k} value={k}>{t(`network.deviceTypes.${k}`)}</option>)}
                    </select>
                    <div style={{ display: "flex", gap: 6, marginTop: 4 }}>
                      <button className={s.actionBtn} style={{ flex: 1 }} onClick={handleRename} disabled={loading}>Сохранить</button>
                      <button className={s.actionBtn} style={{ flex: 1 }} onClick={() => setRenaming(false)}>Отмена</button>
                    </div>
                  </>
                ) : (
                  <button className={s.actionBtn} onClick={() => setRenaming(true)}>✏ Переименовать</button>
                )}
              </div>
              <div className={s.infoSection}>
                <div className={s.infoSectionTitle}>Действия</div>
                <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                  <button className={`${s.actionBtn} ${s.actionBtnOk}`} onClick={handleWhitelist} disabled={loading}>
                    {device.is_whitelisted ? "✕ Убрать из белого списка" : "✓ В белый список"}
                  </button>
                  {device.is_suspicious && (
                    <button className={s.actionBtn} onClick={handleReset} disabled={loading}>
                      ↺ Сбросить статус подозрительного
                    </button>
                  )}
                  {!device.is_self && canBlock && (
                    <button className={`${s.actionBtn} ${s.actionBtnDanger}`} onClick={handleBlock} disabled={loading}>
                      🚫 Заблокировать IP
                    </button>
                  )}
                  {!device.is_self && (
                    <button className={s.actionBtn} onClick={handleRemove} disabled={loading}
                      style={{ color: "var(--text-muted)", borderColor: "var(--border)" }}>
                      🗑 Удалить устройство
                    </button>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>
      </aside>
    </div>
  );
}

// ── Main view ─────────────────────────────────────────────────────────────────

function AddDeviceModal({ onClose, onAdded }: { onClose: () => void; onAdded: () => void }) {
  const { t } = useTranslation();
  const [ip, setIp] = useState("");
  const [mac, setMac] = useState("");
  const [name, setName] = useState("");
  const [type, setType] = useState("unknown");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleAdd = async () => {
    if (!ip.trim()) { setError(t("network.ipRequired")); return; }
    setLoading(true);
    setError("");
    try {
      await api.addDevice(ip.trim(), mac.trim(), name.trim(), type);
      onAdded();
      onClose();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Ошибка");
    } finally { setLoading(false); }
  };

  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.55)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000 }}>
      <div style={{ background: "var(--surface-1)", border: "1px solid var(--border)", borderRadius: "var(--radius-md)", padding: 24, width: 360, display: "flex", flexDirection: "column", gap: 12 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <span style={{ fontWeight: 700, fontSize: 14, color: "var(--text-primary)" }}>{t("network.addDevice")}</span>
          <button className={s.panelClose} onClick={onClose}>✕</button>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <div style={{ fontSize: 11, color: "var(--text-muted)" }}>IP-адрес *</div>
          <input className={s.renameInput} value={ip} onChange={e => setIp(e.target.value)}
            placeholder="192.168.1.100" autoFocus />
          <div style={{ fontSize: 11, color: "var(--text-muted)" }}>MAC-адрес (необязательно — будет определён автоматически)</div>
          <input className={s.renameInput} value={mac} onChange={e => setMac(e.target.value)}
            placeholder="AA:BB:CC:DD:EE:FF" />
          <div style={{ fontSize: 11, color: "var(--text-muted)" }}>Имя</div>
          <input className={s.renameInput} value={name} onChange={e => setName(e.target.value)}
            placeholder="Мой роутер" />
          <div style={{ fontSize: 11, color: "var(--text-muted)" }}>Тип</div>
          <select className={s.typeSelect} value={type} onChange={e => setType(e.target.value)}>
            {DEVICE_TYPE_KEYS.map((k) => <option key={k} value={k}>{t(`network.deviceTypes.${k}`)}</option>)}
          </select>
        </div>
        {error && <div style={{ fontSize: 11, color: "var(--danger-strong)" }}>{error}</div>}
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <button className={s.actionBtn} onClick={onClose}>Отмена</button>
          <button className={s.actionBtn} style={{ background: "var(--accent)", color: "#fff", border: "none" }}
            onClick={handleAdd} disabled={loading}>
            {loading ? "Добавляю..." : "Добавить"}
          </button>
        </div>
      </div>
    </div>
  );
}

const TYPE_FILTER_GROUPS: { labelKey: string; types: string[] }[] = [
  { labelKey: "network.filterAll",   types: [] },
  { labelKey: "network.filterPc",    types: ["pc_windows", "pc_linux", "pc_mac"] },
  { labelKey: "network.filterIot",   types: ["iot_camera", "iot_sensor", "iot_bulb", "iot_plug"] },
  { labelKey: "network.filterPhone", types: ["phone"] },
  { labelKey: "network.filterNet",   types: ["router", "nas"] },
  { labelKey: "network.filterOther", types: ["printer", "game_console", "tv", "unknown"] },
];

export default function NetworkMapView() {
  const { t } = useTranslation();
  const { devices, selectedMac, deviceStats, setDevices, setSelectedMac, setDeviceStats } = useAppStore();
  const capabilities = useAppStore((state) => state.capabilities);
  const canBlock = capabilities == null || capabilities.firewall_blocking;
  const [scanning, setScanning] = useState(false);
  const [showAddModal, setShowAddModal] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [typeFilter, setTypeFilter] = useState(0); // index into TYPE_FILTER_GROUPS
  const wsRef = useRef<WebSocket | null>(null);

  const selected = devices.find((d) => d.mac === selectedMac) ?? null;

  const filteredDevices = devices.filter((d) => {
    const group = TYPE_FILTER_GROUPS[typeFilter];
    if (group.types.length > 0 && !group.types.includes(d.device_type)) return false;
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      return (
        d.ip.includes(q) ||
        d.mac.toLowerCase().includes(q) ||
        d.display_name.toLowerCase().includes(q) ||
        d.hostname.toLowerCase().includes(q) ||
        d.vendor.toLowerCase().includes(q)
      );
    }
    return true;
  });

  const loadDevices = useCallback(async () => {
    try {
      const [devs, stats] = await Promise.all([api.getDevices(), api.getDeviceStats()]);
      setDevices(devs);
      setDeviceStats(stats);
    } catch { /* ignore */ }
  }, [setDevices, setDeviceStats]);

  // Initial load + WebSocket
  useEffect(() => {
    loadDevices();

    const proto = window.location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${window.location.host}/ws/devices`);
    wsRef.current = ws;

    ws.onmessage = (e) => {
      try {
        const msg: DevicesWsMessage = JSON.parse(e.data);
        if (msg.type === "devices_update" && msg.devices) {
          setDevices(msg.devices);
          if (msg.stats) setDeviceStats(msg.stats);
        }
      } catch { /* ignore */ }
    };

    return () => { ws.close(); wsRef.current = null; };
  }, [loadDevices, setDevices, setDeviceStats]);

  const handleScan = async () => {
    setScanning(true);
    try { await api.triggerScan(); }
    catch { /* ignore */ }
    finally { setScanning(false); }
  };

  // Discovery mode banner text
  const discoveryBanner = (() => {
    if (!capabilities) return null;
    if (capabilities.platform === "windows") {
      if (!capabilities.arp_scan) {
        return capabilities.current_elevated
          ? "Активное сканирование сети недоступно — Npcap не установлен. Карта строится по ARP-кэшу и наблюдаемому трафику."
          : "Активное сканирование сети недоступно (нет прав администратора). Карта строится по ARP-кэшу и наблюдаемому трафику.";
      }
    }
    return null;
  })();

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      {/* Toolbar */}
      <div className={s.toolbar}>
        <span className={s.toolbarTitle}>{t("network.title")}</span>
        {deviceStats && (
          <>
            <span className={s.statPill}>{deviceStats.total} {t("network.devices")}</span>
            <span className={`${s.statPill} ${s.statPillOk}`}>{deviceStats.online} {t("network.online")}</span>
            {deviceStats.suspicious > 0 && (
              <span className={`${s.statPill} ${s.statPillDanger}`}>⚠ {deviceStats.suspicious} {t("network.suspicious")}</span>
            )}
          </>
        )}
        <div style={{ flex: 1 }} />
        <input
          className={s.searchInput}
          type="search"
          placeholder={t("network.search")}
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
        />
        <button className={s.scanBtn} onClick={handleScan} disabled={scanning}>
          {scanning ? `⟳ ${t("network.scanning")}` : `⟳ ${t("network.scan")}`}
        </button>
        <button className={s.scanBtn} onClick={() => setShowAddModal(true)}>
          + {t("network.add")}
        </button>
      </div>

      {/* Type filter bar */}
      <div className={s.filterBar}>
        {TYPE_FILTER_GROUPS.map((g, i) => (
          <button
            key={i}
            className={[s.filterBtn, typeFilter === i ? s.filterBtnActive : ""].filter(Boolean).join(" ")}
            onClick={() => setTypeFilter(i)}
          >
            {t(g.labelKey)}
            {i === 0 && devices.length > 0 && (
              <span className={s.filterCount}>{devices.length}</span>
            )}
            {i > 0 && (
              <span className={s.filterCount}>
                {devices.filter(d => g.types.includes(d.device_type)).length}
              </span>
            )}
          </button>
        ))}
        {(searchQuery || typeFilter > 0) && filteredDevices.length !== devices.length && (
          <span className={s.filterResult}>{filteredDevices.length} из {devices.length}</span>
        )}
      </div>

      {/* Discovery capability warning */}
      {discoveryBanner && (
        <div style={{
          padding: "7px 16px", fontSize: 12, lineHeight: 1.5,
          background: "rgba(var(--warning-rgb,234,179,8),0.08)",
          borderBottom: "1px solid rgba(234,179,8,0.2)",
          color: "var(--warning, #eab308)",
        }}>
          ⚠ {discoveryBanner}
        </div>
      )}

      {/* Content */}
      <div className={s.root}>
        <div className={s.main}>
          <DeviceGrid
            devices={filteredDevices}
            selectedMac={selectedMac}
            onSelect={setSelectedMac}
          />
        </div>

        {selected && (
          <DevicePanel
            device={selected}
            onClose={() => setSelectedMac(null)}
            onUpdate={loadDevices}
            canBlock={canBlock}
          />
        )}
      </div>

      {showAddModal && (
        <AddDeviceModal onClose={() => setShowAddModal(false)} onAdded={loadDevices} />
      )}
    </div>
  );
}

// ── Device Grid (fallback, no D3 dependency) ──────────────────────────────────

function DeviceGrid({ devices, selectedMac, onSelect }: {
  devices: Device[];
  selectedMac: string | null;
  onSelect: (mac: string | null) => void;
}) {
  const { t } = useTranslation();
  if (devices.length === 0) {
    return (
      <div style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 8, color: "var(--text-muted)", fontSize: 13, padding: 24 }}>
        <span style={{ fontSize: 32 }}>🔍</span>
        <span>{t("network.noDevices")}</span>
        <span style={{ fontSize: 11, opacity: 0.65, textAlign: "center", maxWidth: 340 }}>
          {t("network.noDevicesHint")}
        </span>
      </div>
    );
  }

  return (
    <div className={s.cardGrid}>
      {devices.map((d) => (
        <DeviceCard
          key={d.mac}
          device={d}
          selected={d.mac === selectedMac}
          onClick={() => onSelect(d.mac === selectedMac ? null : d.mac)}
        />
      ))}
    </div>
  );
}
