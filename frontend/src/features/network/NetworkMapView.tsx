import { useCallback, useEffect, useRef, useState } from "react";
import { useAppStore } from "../../app/store";
import { api } from "../../lib/api";
import type { Device, DeviceAlert, DevicesWsMessage } from "../../types/device";
import type { DeviceDnsSummary } from "../../types/dns";
import s from "./NetworkMapView.module.css";

const DEVICE_TYPES: Record<string, string> = {
  iot_camera: "IP-камера", iot_sensor: "IoT датчик", iot_bulb: "Умная лампа",
  iot_plug: "Умная розетка", router: "Роутер/шлюз", pc_windows: "Windows ПК",
  pc_linux: "Linux сервер", pc_mac: "Mac", phone: "Смартфон", printer: "Принтер",
  nas: "NAS хранилище", game_console: "Игровая консоль", tv: "Смарт ТВ",
  unknown: "Неизвестно",
};

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

// ── Device Card ──────────────────────────────────────────────────────────────

function DeviceCard({ device, selected, onClick }: {
  device: Device; selected: boolean; onClick: () => void;
}) {
  const cls = [
    s.deviceCard,
    selected ? s.deviceCardSelected : "",
    device.is_suspicious ? s.deviceCardSuspicious : "",
    !device.is_online ? s.deviceCardOffline : "",
  ].filter(Boolean).join(" ");

  return (
    <div className={cls} onClick={onClick}>
      <div className={s.cardEmoji}>{device.device_emoji}</div>
      <div className={s.cardName} title={device.display_name}>{device.display_name}</div>
      <div className={s.cardIp}>{device.ip}</div>
      <RiskBar score={device.risk_score} label={device.risk_label} compact />
      {device.is_suspicious && (
        <div className={`${s.cardBadge} ${s.cardBadgeDanger}`}>⚠ подозрительный</div>
      )}
      {!device.is_online && (
        <div className={`${s.cardBadge} ${s.cardBadgeOff}`}>офлайн</div>
      )}
    </div>
  );
}

// ── Device Panel ─────────────────────────────────────────────────────────────

function DevicePanel({ device, onClose, onUpdate, canBlock = true }: {
  device: Device; onClose: () => void; onUpdate: () => void; canBlock?: boolean;
}) {
  const [history, setHistory] = useState<DeviceAlert[]>([]);
  const [dnsSummary, setDnsSummary] = useState<DeviceDnsSummary | null>(null);
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

  useEffect(() => {
    api.getDeviceHistory(device.mac).then(setHistory).catch(() => {});
    api.getDeviceDnsSummary(device.ip).then(setDnsSummary).catch(() => {});
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
    try {
      const r = await api.inspectDevice(device.mac);
      setInspectResult(r);
    } catch { /* ignore */ }
    finally { setInspecting(false); }
  };

  return (
    <aside className={s.panel}>
      <div className={s.panelHeader}>
        <span className={s.panelEmoji}>{device.device_emoji}</span>
        <div className={s.panelTitleBlock}>
          <div className={s.panelName}>{device.display_name}</div>
          <div className={s.panelSub}>{device.device_label} · {device.vendor}</div>
        </div>
        <button className={s.panelClose} onClick={onClose}>✕</button>
      </div>

      <div className={s.panelBody}>
        {/* Badges */}
        <div style={{ display: "flex", gap: 5, flexWrap: "wrap" }}>
          {device.is_suspicious && <span className={`${s.badge} ${s.badgeSuspicious}`}>⚠ подозрительный</span>}
          {device.is_whitelisted && <span className={`${s.badge} ${s.badgeWhitelisted}`}>✓ белый список</span>}
          {!device.is_online && <span className={`${s.badge} ${s.badgeOffline}`}>офлайн</span>}
        </div>

        {/* Risk score */}
        <RiskBar score={device.risk_score} label={device.risk_label} />
        {device.risk_score > 0 && (
          <div className={s.riskExplain}>
            {device.alert_count > 0 && `${device.alert_count} ML · `}
            {device.dns_alert_count > 0 && (
              <span style={{ color: device.dns_alert_count >= 3 ? "#f97316" : "#eab308" }}>
                {device.dns_alert_count} DNS ·{" "}
              </span>
            )}
            {device.last_alert_score != null && `Score ${device.last_alert_score.toFixed(2)} · `}
            {device.device_label}
          </div>
        )}

        {/* Info */}
        <div className={s.panelSection}>
          <div className={s.panelSectionTitle}>Сеть</div>
          <div className={s.infoRow}>
            <span className={s.infoLabel}>IP</span>
            <span className={s.infoValue}>{device.ip}</span>
          </div>
          <div className={s.infoRow}>
            <span className={s.infoLabel}>MAC</span>
            <span className={s.infoValue}>{device.mac}</span>
          </div>
          {device.hostname && (
            <div className={s.infoRow}>
              <span className={s.infoLabel}>Хостнейм</span>
              <span className={s.infoValue}>{device.hostname}</span>
            </div>
          )}
        </div>

        {/* Traffic */}
        <div className={s.panelSection}>
          <div className={s.panelSectionTitle}>Трафик (всего)</div>
          <div className={s.trafficRow}>
            <span className={s.trafficLabel}>↓ Входящий</span>
            <span className={s.trafficValue}>{fmtBytes(device.bytes_in)}</span>
          </div>
          <div className={s.trafficRow}>
            <span className={s.trafficLabel}>↑ Исходящий</span>
            <span className={s.trafficValue}>{fmtBytes(device.bytes_out)}</span>
          </div>
        </div>

        {/* Alerts */}
        {device.alert_count > 0 && (
          <div className={s.panelSection}>
            <div className={s.panelSectionTitle}>Алерты ({device.alert_count})</div>
            {history.slice(0, 5).map((a, i) => (
              <div key={i} className={`${s.alertItem} ${s.alertItemDanger}`}>
                <div className={s.alertTs}>{fmtTime(a.ts)}</div>
                <div className={s.alertLabel}>{a.attack_class || a.label} {a.score != null ? `(${(a.score * 100).toFixed(0)}%)` : ""}</div>
              </div>
            ))}
            {history.length === 0 && device.last_alert_type && (
              <div className={`${s.alertItem} ${s.alertItemDanger}`}>
                <div className={s.alertTs}>{fmtTime(device.last_alert_time)}</div>
                <div className={s.alertLabel}>{device.last_alert_type} {device.last_alert_score != null ? `(${(device.last_alert_score * 100).toFixed(0)}%)` : ""}</div>
              </div>
            )}
          </div>
        )}

        {/* DNS activity */}
        {dnsSummary && dnsSummary.available && dnsSummary.total_queries > 0 && (
          <div className={s.panelSection}>
            <div className={s.panelSectionTitle}>
              DNS активность
              {dnsSummary.alert_count > 0 && (
                <span style={{ marginLeft: 6, fontSize: 10, fontWeight: 700,
                  padding: "1px 6px", borderRadius: 4,
                  background: "rgba(var(--warn-rgb,234,179,8),0.15)",
                  color: "var(--warn)", border: "1px solid rgba(234,179,8,0.3)" }}>
                  ⚠ {dnsSummary.alert_count} аном.
                </span>
              )}
            </div>
            <div className={s.infoRow}>
              <span className={s.infoLabel}>Запросов</span>
              <span className={s.infoValue}>{dnsSummary.total_queries}</span>
            </div>
            {dnsSummary.top_domains.map((d) => (
              <div key={d.domain} className={s.infoRow}>
                <span className={s.infoValue} style={{ fontFamily: "monospace", fontSize: 11,
                  overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                  maxWidth: 180 }} title={d.domain}>{d.domain}</span>
                <span className={s.infoLabel} style={{ marginLeft: "auto", flexShrink: 0 }}>×{d.count}</span>
              </div>
            ))}
          </div>
        )}

        {/* Probe */}
        <div className={s.panelSection}>
          <div className={s.panelSectionTitle}>Тест доступности</div>
          <button className={s.actionBtn} onClick={handleProbe} disabled={probing}>
            {probing ? "⟳ Проверяю..." : "⚡ Отправить запрос"}
          </button>
          {probeResult && (
            <div style={{ fontSize: 11, display: "flex", flexDirection: "column", gap: 3, marginTop: 4 }}>
              <div className={s.infoRow}>
                <span className={s.infoLabel}>Доступен</span>
                <span className={s.infoValue} style={{ color: probeResult.reachable ? "var(--ok)" : "var(--danger-strong)" }}>
                  {probeResult.reachable ? `✓ да${probeResult.latency_ms != null ? ` (${probeResult.latency_ms} мс)` : ""}` : "✗ нет"}
                </span>
              </div>
              {probeResult.open_ports.length > 0 && (
                <div className={s.infoRow}>
                  <span className={s.infoLabel}>Открытые порты</span>
                  <span className={s.infoValue}>{probeResult.open_ports.join(", ")}</span>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Full Inspect */}
        <div className={s.panelSection}>
          <div className={s.panelSectionTitle}>Разведка устройства</div>
          <button className={s.actionBtn} onClick={handleInspect} disabled={inspecting}>
            {inspecting ? "⟳ Сканирую..." : "🔍 Инспекция сервисов"}
          </button>
          {inspectResult && (
            <div style={{ fontSize: 11, display: "flex", flexDirection: "column", gap: 4, marginTop: 6 }}>
              {inspectResult.os_guess && (
                <div className={s.infoRow}>
                  <span className={s.infoLabel}>ОС (TTL)</span>
                  <span className={s.infoValue}>{inspectResult.os_guess}</span>
                </div>
              )}
              {inspectResult.web_urls.length > 0 && (
                <div style={{ display: "flex", flexDirection: "column", gap: 2, marginTop: 2 }}>
                  <span className={s.infoLabel} style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: "0.06em" }}>Веб-интерфейсы</span>
                  {inspectResult.web_urls.map(url => (
                    <a key={url} href={url} target="_blank" rel="noopener noreferrer"
                      style={{ color: "var(--accent)", fontSize: 11, wordBreak: "break-all", textDecoration: "none" }}>
                      🌐 {url}
                    </a>
                  ))}
                </div>
              )}
              {inspectResult.rtsp_url && (
                <div className={s.infoRow}>
                  <span className={s.infoLabel}>RTSP камера</span>
                  <span className={s.infoValue} style={{ color: "#f97316", fontFamily: "monospace", fontSize: 10 }}>
                    {inspectResult.rtsp_url}
                  </span>
                </div>
              )}
              {inspectResult.services.length > 0 && (
                <div style={{ display: "flex", flexDirection: "column", gap: 3, marginTop: 2 }}>
                  <span className={s.infoLabel} style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: "0.06em" }}>Сервисы</span>
                  {inspectResult.services.map((sv, i) => (
                    <div key={i} style={{ background: "var(--surface-3)", borderRadius: 4, padding: "3px 6px", fontSize: 11 }}>
                      <span style={{ color: "var(--accent)", fontFamily: "monospace" }}>:{sv.port}</span>
                      {" "}<span style={{ color: "var(--text-muted)" }}>{sv.protocol}</span>
                      {sv.title && <span style={{ color: "var(--text-secondary)", marginLeft: 4 }}>{sv.title}</span>}
                      {sv.banner && <span style={{ color: "var(--text-muted)", marginLeft: 4, fontFamily: "monospace", fontSize: 10 }}>{sv.banner.slice(0, 60)}</span>}
                    </div>
                  ))}
                </div>
              )}
              {inspectResult.services.length === 0 && !inspectResult.os_guess && inspectResult.web_urls.length === 0 && (
                <span style={{ color: "var(--text-muted)" }}>Ничего не найдено — устройство не отвечает</span>
              )}
            </div>
          )}
        </div>

        {/* Rename */}
        <div className={s.panelSection}>
          <div className={s.panelSectionTitle}>Настройки</div>
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
                {Object.entries(DEVICE_TYPES).map(([k, v]) => (
                  <option key={k} value={k}>{v}</option>
                ))}
              </select>
              <div style={{ display: "flex", gap: 6 }}>
                <button className={s.actionBtn} style={{ flex: 1 }} onClick={handleRename} disabled={loading}>Сохранить</button>
                <button className={s.actionBtn} style={{ flex: 1 }} onClick={() => setRenaming(false)}>Отмена</button>
              </div>
            </>
          ) : (
            <button className={s.actionBtn} onClick={() => setRenaming(true)}>✏ Переименовать</button>
          )}
        </div>
      </div>

      <div className={s.panelActions}>
        {canBlock && (
          <button className={`${s.actionBtn} ${s.actionBtnDanger}`} onClick={handleBlock} disabled={loading}>
            🚫 Заблокировать IP
          </button>
        )}
        <button className={`${s.actionBtn} ${s.actionBtnOk}`} onClick={handleWhitelist} disabled={loading}>
          {device.is_whitelisted ? "✕ Убрать из белого списка" : "✓ В белый список"}
        </button>
        {device.is_suspicious && (
          <button className={s.actionBtn} onClick={handleReset} disabled={loading}>
            ↺ Сбросить статус
          </button>
        )}
        <button className={`${s.actionBtn}`} onClick={handleRemove} disabled={loading}
          style={{ color: "var(--text-muted)", borderColor: "var(--border)" }}>
          🗑 Удалить устройство
        </button>
      </div>
    </aside>
  );
}

// ── Main view ─────────────────────────────────────────────────────────────────

function AddDeviceModal({ onClose, onAdded }: { onClose: () => void; onAdded: () => void }) {
  const [ip, setIp] = useState("");
  const [mac, setMac] = useState("");
  const [name, setName] = useState("");
  const [type, setType] = useState("unknown");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleAdd = async () => {
    if (!ip.trim()) { setError("IP обязателен"); return; }
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
          <span style={{ fontWeight: 700, fontSize: 14, color: "var(--text-primary)" }}>Добавить устройство</span>
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
            {Object.entries(DEVICE_TYPES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
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

const TYPE_FILTER_GROUPS: { label: string; types: string[] }[] = [
  { label: "Все",     types: [] },
  { label: "ПК",      types: ["pc_windows", "pc_linux", "pc_mac"] },
  { label: "IoT",     types: ["iot_camera", "iot_sensor", "iot_bulb", "iot_plug"] },
  { label: "Телефон", types: ["phone"] },
  { label: "Сеть",    types: ["router", "nas"] },
  { label: "Другое",  types: ["printer", "game_console", "tv", "unknown"] },
];

export default function NetworkMapView() {
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
        <span className={s.toolbarTitle}>Карта сети</span>
        {deviceStats && (
          <>
            <span className={s.statPill}>{deviceStats.total} устройств</span>
            <span className={`${s.statPill} ${s.statPillOk}`}>{deviceStats.online} онлайн</span>
            {deviceStats.suspicious > 0 && (
              <span className={`${s.statPill} ${s.statPillDanger}`}>⚠ {deviceStats.suspicious} подозрительных</span>
            )}
          </>
        )}
        <div style={{ flex: 1 }} />
        <input
          className={s.searchInput}
          type="search"
          placeholder="Поиск по IP, MAC, имени..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
        />
        <button className={s.scanBtn} onClick={handleScan} disabled={scanning}>
          {scanning ? "⟳ Сканирование..." : "⟳ Сканировать"}
        </button>
        <button className={s.scanBtn} onClick={() => setShowAddModal(true)}>
          + Добавить
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
            {g.label}
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
  if (devices.length === 0) {
    return (
      <div style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 8, color: "var(--text-muted)", fontSize: 13, padding: 24 }}>
        <span style={{ fontSize: 32 }}>🔍</span>
        <span>Устройства не обнаружены</span>
        <span style={{ fontSize: 11, opacity: 0.65, textAlign: "center", maxWidth: 340 }}>
          Нажмите «⟳ Сканировать» для поиска устройств в сети.<br/>
          Если сканирование недоступно, устройства появятся по мере наблюдения трафика.
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
