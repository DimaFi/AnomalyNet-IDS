import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { ToastContainer } from "../components/ToastContainer";
import { ModelPresetPicker } from "../components/ModelPresetPicker";
import { AboutView } from "../features/about/AboutView";
import { AlertsView } from "../features/alerts/AlertsView";
import { DashboardView } from "../features/dashboard/DashboardView";
import NetworkMapView from "../features/network/NetworkMapView";
import { PerformanceView } from "../features/performance/PerformanceView";
import { PluginsView } from "../features/plugins/PluginsView";
import { SettingsView } from "../features/settings/SettingsView";
import { StreamView } from "../features/stream/StreamView";
import { api } from "../lib/api";
import { useRealtimeStream } from "../lib/useRealtimeStream";
import { useAppStore } from "./store";
import type { AppSettings, ModelPreset, SystemStats } from "./types";
import styles from "./App.module.css";

type ViewKey = "dashboard" | "stream" | "alerts" | "network" | "plugins" | "settings" | "about" | "performance";

const viewMap: Record<ViewKey, React.ComponentType> = {
  dashboard:   DashboardView,
  stream:      StreamView,
  alerts:      AlertsView,
  network:     NetworkMapView,
  plugins:     PluginsView,
  settings:    SettingsView,
  about:       AboutView,
  performance: PerformanceView,
};

/* ── Inline SVG icons ─────────────────────────────────────── */
function IconDashboard() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="3" width="7" height="7" rx="1" />
      <rect x="14" y="3" width="7" height="7" rx="1" />
      <rect x="3" y="14" width="7" height="7" rx="1" />
      <rect x="14" y="14" width="7" height="7" rx="1" />
    </svg>
  );
}

function IconStream() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
    </svg>
  );
}


function IconAlerts() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
      <line x1="12" y1="9" x2="12" y2="13" />
      <line x1="12" y1="17" x2="12.01" y2="17" />
    </svg>
  );
}

function IconNetwork() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="5" r="2" />
      <circle cx="4" cy="19" r="2" />
      <circle cx="20" cy="19" r="2" />
      <line x1="12" y1="7" x2="4" y2="17" />
      <line x1="12" y1="7" x2="20" y2="17" />
      <line x1="4" y1="19" x2="20" y2="19" />
    </svg>
  );
}

function IconPlugins() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 2L2 7l10 5 10-5-10-5z" />
      <path d="M2 17l10 5 10-5" />
      <path d="M2 12l10 5 10-5" />
    </svg>
  );
}

function IconSettings() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
    </svg>
  );
}

function IconAbout() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10" />
      <line x1="12" y1="8" x2="12" y2="12" />
      <line x1="12" y1="16" x2="12.01" y2="16" />
    </svg>
  );
}

const NAV_ITEMS: { key: ViewKey; Icon: React.ComponentType; label: string }[] = [
  { key: "dashboard", Icon: IconDashboard, label: "Dashboard" },
  { key: "stream",    Icon: IconStream,    label: "Stream" },
  { key: "alerts",    Icon: IconAlerts,    label: "Инциденты" },
  { key: "network",   Icon: IconNetwork,   label: "Карта сети" },
  { key: "plugins",   Icon: IconPlugins,   label: "Plugins" },
  { key: "settings",  Icon: IconSettings,  label: "Settings" },
  { key: "about",     Icon: IconAbout,     label: "About" },
];

const PAGE_TITLES: Record<ViewKey, string> = {
  dashboard:   "Dashboard",
  stream:      "Live Stream",
  alerts:      "Инциденты",
  network:     "Карта сети",
  plugins:     "Плагины",
  settings:    "Settings",
  about:       "О программе",
  performance: "Производительность",
};

type ThemeName = "dark" | "light" | "gray";

const THEME_CYCLE: ThemeName[] = ["dark", "light", "gray"];
const THEME_ICON: Record<ThemeName, string> = { dark: "🌙", light: "☀️", gray: "◑" };
const THEME_LABEL: Record<ThemeName, string> = { dark: "Тёмная", light: "Светлая", gray: "Серая" };

function nextTheme(current: string | undefined): ThemeName {
  const idx = THEME_CYCLE.indexOf((current ?? "dark") as ThemeName);
  return THEME_CYCLE[(idx + 1) % THEME_CYCLE.length];
}

const KNOWN_MODEL_LABELS: Record<string, string> = {
  "catboost-iot-v1":          "Быстрый",
  "catboost-cascade-simple":  "Simple",
  "catboost-cascade-advanced":"Advanced",
  "catboost-cascade-routed":  "Cascade",
};

function getActiveModelLabel(settings: AppSettings, presets: ModelPreset[]): { label: string; full: string } {
  const id = settings.active_model_id ?? "";

  if (id.startsWith("plugin:")) {
    const name = id.slice("plugin:".length);
    return { label: name, full: `Plugin pipeline: ${name}` };
  }

  const preset = presets.find(
    (p) => p.active_model_id === id &&
           (p.detection_mode ?? "simple") === (settings.detection_mode ?? "simple")
  );
  if (preset) {
    const short = preset.name.split(/[\s—–-]/)[0];
    return { label: short, full: preset.name };
  }

  const known = KNOWN_MODEL_LABELS[id];
  if (known) return { label: known, full: id };

  return { label: id, full: id };
}

function ActiveModelBadge({ settings, presets }: { settings: AppSettings; presets: ModelPreset[] }) {
  const { label, full } = getActiveModelLabel(settings, presets);
  const isAdvanced = settings.detection_mode === "advanced" || label.toLowerCase() === "advanced";
  const isPlugin = settings.active_model_id?.startsWith("plugin:");
  const cls = [
    styles.modeBadge,
    isAdvanced ? styles.modeBadgeAdvanced : "",
    isPlugin   ? styles.modeBadgePlugin   : "",
  ].filter(Boolean).join(" ");
  return <span className={cls} title={full}>{label}</span>;
}

export function App() {
  const { i18n } = useTranslation();
  const view           = useAppStore((state) => state.view);
  const setView        = useAppStore((state) => state.setView);
  const health         = useAppStore((state) => state.health);
  const settings       = useAppStore((state) => state.settings);
  const setHealth      = useAppStore((state) => state.setHealth);
  const setSettings    = useAppStore((state) => state.setSettings);
  const setModels      = useAppStore((state) => state.setModels);
  const presets        = useAppStore((state) => state.presets);
  const setPresets     = useAppStore((state) => state.setPresets);
  const capabilities      = useAppStore((state) => state.capabilities);
  const setCapabilities   = useAppStore((state) => state.setCapabilities);
  const serviceStopped    = useAppStore((state) => state.serviceStopped);
  const setServiceStopped = useAppStore((state) => state.setServiceStopped);

  useRealtimeStream();

  const [refreshing, setRefreshing] = useState(false);
  const [loadLevel, setLoadLevel] = useState<string>("low");

  useEffect(() => {
    const refresh = () => api.getSystemStats().then((s: SystemStats) => {
      if (s.load_level) setLoadLevel(s.load_level);
    }).catch(() => null);
    refresh();
    const iv = setInterval(refresh, 5000);
    return () => clearInterval(iv);
  }, []);

  const bootstrap = useCallback(async () => {
    setRefreshing(true);
    try {
      const [healthRes, settingsRes, modelsRes, presetsRes, capsRes] = await Promise.all([
        api.getHealth(),
        api.getSettings(),
        api.getModels(),
        api.getModelPresets(),
        api.getCapabilities().catch(() => null),
      ]);
      setHealth(healthRes);
      setSettings(settingsRes);
      setModels(modelsRes);
      setPresets(presetsRes.presets);
      if (capsRes) setCapabilities(capsRes);
      document.documentElement.dataset.theme = settingsRes.theme;
      await i18n.changeLanguage(settingsRes.language);
    } catch {
      // Backend unreachable — leave state empty, UI shows loading/empty state
    } finally {
      setRefreshing(false);
    }
  }, [i18n, setCapabilities, setHealth, setModels, setPresets, setSettings]);

  useEffect(() => { void bootstrap(); }, [bootstrap]);

  const [showShieldConfirm, setShowShieldConfirm] = useState(false);
  const [shieldIp, setShieldIp] = useState("");

  const toggleProtection = useCallback(async () => {
    if (!settings) return;
    if (!settings.auto_block) {
      // Turning ON → show confirm dialog
      setShowShieldConfirm(true);
    } else {
      // Turning OFF → immediate
      try {
        const saved = await api.updateSettings({ ...settings, auto_block: false });
        setSettings(saved);
      } catch {
        setSettings({ ...settings, auto_block: false });
      }
    }
  }, [settings, setSettings]);

  const handleThemeToggle = useCallback(async () => {
    if (!settings) return;
    const theme = nextTheme(settings.theme);
    document.documentElement.dataset.theme = theme;
    const next = { ...settings, theme };
    try { setSettings(await api.updateSettings(next)); }
    catch { setSettings(next); }
  }, [settings, setSettings]);

  const confirmShield = useCallback(async (addIp: boolean) => {
    if (!settings) return;
    const ip = shieldIp.trim();
    const list = settings.whitelist_ips ?? [];
    const nextList = addIp && ip && !list.includes(ip) ? [...list, ip] : list;
    const next = { ...settings, auto_block: true, whitelist_ips: nextList };
    // Close dialog immediately — don't wait for slow server
    setShowShieldConfirm(false);
    setShieldIp("");
    try {
      const saved = await api.updateSettings(next);
      setSettings(saved);
    } catch {
      setSettings(next);
    }
  }, [settings, setSettings, shieldIp]);

  const CurrentView = viewMap[view];

  const statusDotClass = [
    styles.statusDot,
    health?.status === "active"  ? styles.statusDotActive  : "",
    health?.status === "warning" ? styles.statusDotWarning : "",
    health?.status === "error"   ? styles.statusDotError   : "",
  ].filter(Boolean).join(" ");

  return (
    <div className={styles.shell}>
      {/* ── Narrow icon sidebar ── */}
      <aside className={styles.sidebar}>
        {/* Logo — power/stop button */}
        <button
          className={[styles.logo, styles.logoPowerBtn].filter(Boolean).join(" ")}
          onClick={async () => {
            if (!confirm("Выключить AnomalyNet IDS?\n\nСервис полностью завершит работу. Чтобы запустить снова — откройте launch.bat (Windows) или launch.sh (Linux).")) return;
            try { await api.stopService(); } catch { /* server closes before response */ }
            setServiceStopped(true);
          }}
          title="Выключить сервис AnomalyNet"
          aria-label="Выключить сервис"
        >
          <img src="/logo.png" alt="AnomalyNet" className={styles.logoImg} />
        </button>

        {/* Nav buttons */}
        <nav className={styles.nav}>
          {NAV_ITEMS.map(({ key, Icon, label }) => (
            <button
              key={key}
              className={[styles.navBtn, view === key ? styles.navBtnActive : ""].filter(Boolean).join(" ")}
              onClick={() => setView(key)}
              data-label={label}
              aria-label={label}
            >
              <Icon />
            </button>
          ))}
        </nav>

        <div className={styles.navSpacer} />

        {/* Status indicator */}
        <div className={statusDotClass} title={health?.status ?? "unknown"} />
      </aside>

      {/* ── Main content ── */}
      <div className={styles.content}>
        <div className={styles.topbar}>
          <span className={styles.topbarTitle}>{PAGE_TITLES[view]}</span>
          <div className={styles.topbarMeta}>
            {settings?.run_mode && (
              <span className={styles.modeBadge}>
                {(() => {
                  const isLive = settings.run_mode === "linux_live" || settings.run_mode === "windows_live";
                  if (!isLive) return settings.run_mode;
                  const plat = capabilities?.platform;
                  if (plat === "windows") return "Live (Windows)";
                  if (plat === "linux")   return "Live (Linux)";
                  // Fallback to run_mode name if capabilities not loaded yet
                  return settings.run_mode === "windows_live" ? "Live (Windows)" : "Live (Linux)";
                })()}
              </span>
            )}
            {settings && (
              <ActiveModelBadge settings={settings} presets={presets} />
            )}
            {/* Warning: live mode + mock model */}
            {(settings?.run_mode === "linux_live" || settings?.run_mode === "windows_live") && settings?.active_model_id === "mock-default" && (
              <span className={styles.mockWarningBadge} title="Активирована demo-модель — выберите реальный детектор">
                ⚠ Demo-модель
              </span>
            )}
            {/* Warning: packet capture unavailable in live mode */}
            {capabilities && !capabilities.packet_capture &&
             (settings?.run_mode === "linux_live" || settings?.run_mode === "windows_live") && (
              <span className={styles.mockWarningBadge} title={
                capabilities.warnings.find(w => /npcap|admin|rights|privilege|scapy/i.test(w))
                ?? "Захват трафика недоступен"
              }>
                ⚠ Нет захвата
              </span>
            )}
            {/* Warning: no firewall available */}
            {capabilities && !capabilities.firewall_blocking && (
              <span className={styles.mockWarningBadge} title={capabilities.warnings[0] ?? "Блокировка IP недоступна"}>
                ⚠ Нет фаервола
              </span>
            )}
            {settings && (
              <button
                className={[styles.shieldBtn, settings.auto_block ? styles.shieldActive : "", capabilities && !capabilities.firewall_blocking ? styles.shieldDisabled : ""].filter(Boolean).join(" ")}
                onClick={toggleProtection}
                disabled={capabilities != null && !capabilities.firewall_blocking}
                title={
                  capabilities && !capabilities.firewall_blocking
                    ? (capabilities.warnings[0] ?? "Блокировка IP недоступна на этой платформе")
                    : settings.auto_block ? "Защита включена — нажми чтобы выключить" : "Включить авто-блокировку атак"
                }
              >
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
                </svg>
                {settings.auto_block ? "Защита ВКЛ" : "Защита ВЫКЛ"}
              </button>
            )}
            <button
              className={styles.loadBtn}
              onClick={() => setView("performance" as ViewKey)}
              title="Производительность системы"
              style={{
                "--load-color": loadLevel === "critical" ? "var(--danger)" :
                                loadLevel === "high"     ? "#f97316" :
                                loadLevel === "medium"   ? "#eab308" : "var(--ok)",
              } as React.CSSProperties}
            >
              <span className={styles.loadDot} />
              Нагрузка
            </button>
            <ModelPresetPicker compact />
            {settings && (
              <button
                className={styles.themeBtn}
                onClick={() => void handleThemeToggle()}
                title={`Тема: ${THEME_LABEL[settings.theme as ThemeName ?? "dark"]} → ${THEME_LABEL[nextTheme(settings.theme)]}`}
              >
                {THEME_ICON[(settings.theme as ThemeName) ?? "dark"]}
              </button>
            )}
            <button
              className={styles.refreshBtn}
              onClick={() => void bootstrap()}
              disabled={refreshing}
              title="Обновить данные без перезагрузки страницы"
            >
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="23 4 23 10 17 10" />
                <polyline points="1 20 1 14 7 14" />
                <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
              </svg>
            </button>
          </div>
        </div>

        <main className={`${styles.mainPanel} mainPanelZoom`}>
          <CurrentView />
        </main>
      </div>

      <ToastContainer />

      {/* Stopped overlay */}
      {serviceStopped && (
        <div className={styles.stoppedOverlay}>
          <div className={styles.stoppedCard}>
            <img src="/AnomalyNet-logo_turn_off.png" alt="AnomalyNet" className={styles.stoppedLogo} />
            <h2 className={styles.stoppedTitle}>Сервис выключен</h2>
            <p className={styles.stoppedHint}>
              Для повторного запуска откройте <code>launch.bat</code> (Windows) или <code>launch.sh</code> (Linux)
            </p>
          </div>
        </div>
      )}

      {/* Shield confirm dialog */}
      {showShieldConfirm && (
        <div className={styles.confirmOverlay}>
          <div className={styles.confirmDialog}>
            <h3>⚠ Включить авто-блокировку?</h3>
            <p>
              Система будет блокировать IP-адреса через <code>iptables</code> при обнаружении атак.
              Если ваш IP не в белом списке — вы можете заблокировать сами себя.
            </p>
            <div className={styles.confirmIpRow}>
              <label>Добавить ваш IP в белый список (необязательно):</label>
              <input
                type="text"
                value={shieldIp}
                placeholder="например: 1.2.3.4"
                onChange={(e) => setShieldIp(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") void confirmShield(true); }}
                autoFocus
              />
            </div>
            <div className={styles.confirmButtons}>
              <button className={styles.confirmBtnSecondary}
                onClick={() => { setShowShieldConfirm(false); setShieldIp(""); }}>
                Отмена
              </button>
              <button className={styles.confirmBtnSecondary}
                onClick={() => void confirmShield(false)}>
                Включить без добавления
              </button>
              <button className={styles.confirmBtnPrimary}
                onClick={() => void confirmShield(true)}>
                {shieldIp.trim() ? "Добавить IP и включить" : "Включить"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
