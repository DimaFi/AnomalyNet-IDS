import { useCallback, useEffect, useRef, useState } from "react";
import { useAppStore } from "../../app/store";
import { api } from "../../lib/api";
import type { Device, DeviceAlert, DevicesWsMessage } from "../../types/device";
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

function DevicePanel({ device, onClose, onUpdate }: {
  device: Device; onClose: () => void; onUpdate: () => void;
}) {
  const [history, setHistory] = useState<DeviceAlert[]>([]);
  const [renaming, setRenaming] = useState(false);
  const [nameInput, setNameInput] = useState(device.custom_name || device.hostname || "");
  const [typeInput, setTypeInput] = useState(device.device_type);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api.getDeviceHistory(device.mac).then(setHistory).catch(() => {});
  }, [device.mac]);

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
        <button className={`${s.actionBtn} ${s.actionBtnDanger}`} onClick={handleBlock} disabled={loading}>
          🚫 Заблокировать IP
        </button>
        <button className={`${s.actionBtn} ${s.actionBtnOk}`} onClick={handleWhitelist} disabled={loading}>
          {device.is_whitelisted ? "✕ Убрать из белого списка" : "✓ В белый список"}
        </button>
        {device.is_suspicious && (
          <button className={s.actionBtn} onClick={handleReset} disabled={loading}>
            ↺ Сбросить статус
          </button>
        )}
      </div>
    </aside>
  );
}

// ── Main view ─────────────────────────────────────────────────────────────────

export default function NetworkMapView() {
  const { devices, selectedMac, deviceStats, setDevices, setSelectedMac, setDeviceStats } = useAppStore();
  const [scanning, setScanning] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

  const selected = devices.find((d) => d.mac === selectedMac) ?? null;

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
        <button className={s.scanBtn} onClick={handleScan} disabled={scanning}>
          {scanning ? "⟳ Сканирование..." : "⟳ Сканировать"}
        </button>
      </div>

      {/* Content */}
      <div className={s.root}>
        <div className={s.main}>
          <DeviceGrid
            devices={devices}
            selectedMac={selectedMac}
            onSelect={setSelectedMac}
          />
        </div>

        {selected && (
          <DevicePanel
            device={selected}
            onClose={() => setSelectedMac(null)}
            onUpdate={loadDevices}
          />
        )}
      </div>
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
      <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", color: "var(--text-muted)", fontSize: 13 }}>
        Нет данных — нажмите «Сканировать» для обнаружения устройств
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
