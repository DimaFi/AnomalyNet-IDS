import { useCallback, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { ToastContainer } from "../components/ToastContainer";
import { DashboardView } from "../features/dashboard/DashboardView";
import { ModelsView } from "../features/models/ModelsView";
import { SettingsView } from "../features/settings/SettingsView";
import { StreamView } from "../features/stream/StreamView";
import { api } from "../lib/api";
import { mockHealth, mockModels, mockSettings } from "../lib/mockRuntime";
import { useRealtimeStream } from "../lib/useRealtimeStream";
import { useAppStore } from "./store";
import styles from "./App.module.css";

type ViewKey = "dashboard" | "stream" | "models" | "settings";

const viewMap: Record<ViewKey, React.ComponentType> = {
  dashboard: DashboardView,
  stream: StreamView,
  models: ModelsView,
  settings: SettingsView,
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

function IconModels() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="3" />
      <circle cx="12" cy="12" r="9" />
      <line x1="12" y1="3" x2="12" y2="9" />
      <line x1="12" y1="15" x2="12" y2="21" />
      <line x1="3" y1="12" x2="9" y2="12" />
      <line x1="15" y1="12" x2="21" y2="12" />
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

const NAV_ITEMS: { key: ViewKey; Icon: React.ComponentType; label: string }[] = [
  { key: "dashboard", Icon: IconDashboard, label: "Dashboard" },
  { key: "stream",    Icon: IconStream,    label: "Stream" },
  { key: "models",    Icon: IconModels,    label: "Models" },
  { key: "settings",  Icon: IconSettings,  label: "Settings" },
];

const PAGE_TITLES: Record<ViewKey, string> = {
  dashboard: "Dashboard",
  stream:    "Live Stream",
  models:    "Models",
  settings:  "Settings",
};

export function App() {
  const { i18n } = useTranslation();
  const view       = useAppStore((state) => state.view);
  const setView    = useAppStore((state) => state.setView);
  const health     = useAppStore((state) => state.health);
  const settings   = useAppStore((state) => state.settings);
  const setHealth  = useAppStore((state) => state.setHealth);
  const setSettings = useAppStore((state) => state.setSettings);
  const setModels  = useAppStore((state) => state.setModels);

  useRealtimeStream();

  useEffect(() => {
    async function bootstrap() {
      try {
        const [healthRes, settingsRes, modelsRes] = await Promise.all([
          api.getHealth(),
          api.getSettings(),
          api.getModels(),
        ]);
        setHealth(healthRes);
        setSettings(settingsRes);
        setModels(modelsRes);
        document.documentElement.dataset.theme = settingsRes.theme;
        await i18n.changeLanguage(settingsRes.language);
      } catch {
        setHealth(mockHealth);
        setSettings(mockSettings);
        setModels(mockModels);
        document.documentElement.dataset.theme = mockSettings.theme;
        await i18n.changeLanguage(mockSettings.language);
      }
    }
    void bootstrap();
  }, [i18n, setHealth, setModels, setSettings]);

  const toggleProtection = useCallback(async () => {
    if (!settings) return;
    try {
      const saved = await api.updateSettings({ ...settings, auto_block: !settings.auto_block });
      setSettings(saved);
    } catch {
      setSettings({ ...settings, auto_block: !settings.auto_block });
    }
  }, [settings, setSettings]);

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
        {/* Logo mark */}
        <div className={styles.logo}>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
          </svg>
        </div>

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
              <span className={styles.modeBadge}>{settings.run_mode}</span>
            )}
            {settings?.active_model_id && (
              <span className={styles.modeBadge}>{settings.active_model_id}</span>
            )}
            {settings && (
              <button
                className={[styles.shieldBtn, settings.auto_block ? styles.shieldActive : ""].filter(Boolean).join(" ")}
                onClick={toggleProtection}
                title={settings.auto_block ? "Защита включена — нажми чтобы выключить" : "Включить авто-блокировку атак"}
              >
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
                </svg>
                {settings.auto_block ? "Защита ВКЛ" : "Защита ВЫКЛ"}
              </button>
            )}
          </div>
        </div>

        <main className={styles.mainPanel}>
          <CurrentView />
        </main>
      </div>

      <ToastContainer />
    </div>
  );
}
