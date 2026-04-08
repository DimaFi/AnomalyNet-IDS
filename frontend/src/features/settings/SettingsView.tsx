import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useAppStore } from "../../app/store";
import type { AppSettings, NetworkInterface } from "../../app/types";
import { api } from "../../lib/api";
import styles from "../panel.module.css";
import selfStyles from "./SettingsView.module.css";

export function SettingsView() {
  const { t, i18n } = useTranslation();
  const settings = useAppStore((state) => state.settings);
  const setSettings = useAppStore((state) => state.setSettings);
  const [interfaces, setInterfaces] = useState<NetworkInterface[]>([]);

  useEffect(() => {
    api.getInterfaces()
      .then(setInterfaces)
      .catch(() => setInterfaces([]));
  }, []);

  if (!settings) return null;

  async function persist(nextSettings: AppSettings) {
    try {
      const saved = await api.updateSettings(nextSettings);
      setSettings(saved);
      await i18n.changeLanguage(saved.language);
      document.documentElement.dataset.theme = saved.theme;
    } catch {
      setSettings(nextSettings);
      await i18n.changeLanguage(nextSettings.language);
      document.documentElement.dataset.theme = nextSettings.theme;
    }
  }

  function patch(partial: Partial<AppSettings>) {
    const next = { ...settings, ...partial } as AppSettings;
    setSettings(next);
    void persist(next);
  }

  return (
    <section className={styles.panel}>
      <div className={styles.panelHeader}>
        <div>
          <h2>{t("settings.title")}</h2>
          <p>{t("settings.subtitle")}</p>
        </div>
      </div>

      {/* ── General ── */}
      <div className={selfStyles.group}>
        <div className={selfStyles.groupTitle}>{t("settings.groupGeneral")}</div>
        <div className={styles.formGrid}>
          <label className={styles.field}>
            <span>{t("settings.language")}</span>
            <select value={settings.language}
              onChange={(e) => patch({ language: e.target.value as "ru" | "en" })}>
              <option value="ru">Русский</option>
              <option value="en">English</option>
            </select>
          </label>
          <label className={styles.field}>
            <span>{t("settings.theme")}</span>
            <select value={settings.theme}
              onChange={(e) => patch({ theme: e.target.value as "dark" | "light" })}>
              <option value="dark">Dark</option>
              <option value="light">Light</option>
            </select>
          </label>
          <label className={styles.field}>
            <span>{t("settings.runMode")}</span>
            <select value={settings.run_mode}
              onChange={(e) => patch({ run_mode: e.target.value as AppSettings["run_mode"] })}>
              <option value="mock">Mock</option>
              <option value="windows_stub">Windows Stub</option>
              <option value="linux_stub">Linux Stub</option>
              <option value="linux_live">Linux Live (scapy)</option>
            </select>
          </label>
          <label className={styles.field}>
            <span>{t("settings.retention")}</span>
            <input type="number" min={1} max={30}
              value={settings.retention_days}
              onChange={(e) => patch({ retention_days: Math.min(30, Math.max(1, Number(e.target.value))) })} />
          </label>
          <label className={styles.toggleField}>
            <input type="checkbox" checked={settings.capture_enabled}
              onChange={(e) => patch({ capture_enabled: e.target.checked })} />
            <span>{t("settings.capture")}</span>
          </label>
          <label className={styles.toggleField}>
            <input type="checkbox" checked={settings.stream_autostart}
              onChange={(e) => patch({ stream_autostart: e.target.checked })} />
            <span>{t("settings.autostart")}</span>
          </label>
        </div>
      </div>

      {/* ── Network capture ── */}
      <div className={selfStyles.group}>
        <div className={selfStyles.groupTitle}>{t("settings.groupCapture")}</div>
        <div className={styles.formGrid}>
          <label className={styles.field}>
            <span>{t("settings.interfaceName")}</span>
            {interfaces.length > 0 ? (
              <select value={settings.interface_name}
                onChange={(e) => patch({ interface_name: e.target.value })}>
                {interfaces.map((iface) => (
                  <option key={iface.name} value={iface.name}>
                    {iface.name}{iface.addresses.length > 0 ? ` (${iface.addresses[0]})` : ""}
                  </option>
                ))}
              </select>
            ) : (
              <input type="text" value={settings.interface_name}
                onChange={(e) => patch({ interface_name: e.target.value })}
                placeholder="eth0" />
            )}
          </label>
        </div>
      </div>

      {/* ── CatBoost model ── */}
      <div className={selfStyles.group}>
        <div className={selfStyles.groupTitle}>{t("settings.groupCatboost")}</div>
        <div className={styles.formGrid}>
          <label className={styles.field}>
            <span>
              {t("settings.catboostThreshold")}
              <span className={selfStyles.badgeValue}>{settings.catboost_threshold.toFixed(2)}</span>
            </span>
            <input type="range" min={0.5} max={0.99} step={0.01}
              value={settings.catboost_threshold}
              onChange={(e) => patch({ catboost_threshold: parseFloat(e.target.value) })} />
          </label>
          <label className={styles.field}>
            <span>{t("settings.catboostModelDir")}</span>
            <input type="text" value={settings.catboost_model_dir}
              onChange={(e) => patch({ catboost_model_dir: e.target.value })} />
          </label>
          <label className={styles.field}>
            <span>{t("settings.preprocessingDir")}</span>
            <input type="text" value={settings.preprocessing_artifacts_dir}
              onChange={(e) => patch({ preprocessing_artifacts_dir: e.target.value })} />
          </label>
          <label className={styles.toggleField}>
            <input type="checkbox" checked={settings.auto_block}
              onChange={(e) => patch({ auto_block: e.target.checked })} />
            <span>{t("settings.autoBlock")}</span>
          </label>
        </div>
      </div>
    </section>
  );
}
