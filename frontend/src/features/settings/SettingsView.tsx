import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useAppStore } from "../../app/store";
import type { AppSettings, NetworkInterface } from "../../app/types";
import { ModelPresetPicker } from "../../components/ModelPresetPicker";
import { api } from "../../lib/api";
import styles from "../panel.module.css";
import selfStyles from "./SettingsView.module.css";

export function SettingsView() {
  const { t, i18n } = useTranslation();
  const settings = useAppStore((state) => state.settings);
  const setSettings = useAppStore((state) => state.setSettings);
  const [interfaces, setInterfaces] = useState<NetworkInterface[]>([]);
  const [blockedIps, setBlockedIps] = useState<{ ip: string; blocked_at: string }[]>([]);

  // Whitelist add input (local only — save on Add/Enter)
  const [whitelistInput, setWhitelistInput] = useState("");

  // Auto-block confirm dialog
  const [showAutoBlockConfirm, setShowAutoBlockConfirm] = useState(false);
  const [confirmIp, setConfirmIp] = useState("");

  useEffect(() => {
    api.getInterfaces()
      .then(setInterfaces)
      .catch(() => setInterfaces([]));
  }, []);

  const refreshBlocked = useCallback(() => {
    api.getBlockedIps()
      .then((res) => setBlockedIps(res.items))
      .catch(() => setBlockedIps([]));
  }, []);

  useEffect(() => { refreshBlocked(); }, [refreshBlocked]);

  const handleUnblock = useCallback(async (ip: string) => {
    await api.unblockIp(ip).catch(() => null);
    refreshBlocked();
  }, [refreshBlocked]);

  const handleUnblockAll = useCallback(async () => {
    await api.unblockAllIps().catch(() => null);
    refreshBlocked();
  }, [refreshBlocked]);

  if (!settings) return null;
  // settings is non-null from here — TypeScript doesn't narrow through closures
  const s = settings;

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
    const next = { ...s, ...partial } as AppSettings;
    setSettings(next);
    void persist(next);
  }

  function addWhitelistIp() {
    const val = whitelistInput.trim();
    if (!val) return;
    const list = s.whitelist_ips ?? [];
    if (!list.includes(val)) {
      patch({ whitelist_ips: [...list, val] });
    }
    setWhitelistInput("");
  }

  function removeWhitelistIp(ip: string) {
    patch({ whitelist_ips: (s.whitelist_ips ?? []).filter((x) => x !== ip) });
  }

  return (
    <section className={styles.panel}>
      <div className={styles.panelHeader}>
        <div>
          <h2>{t("settings.title")}</h2>
          <p>{t("settings.subtitle")}</p>
        </div>
        <ModelPresetPicker />
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
              <option value="linux_live">Linux Live (scapy)</option>
              <option value="mock">Demo (без захвата)</option>
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
            <div className={selfStyles.thresholdPresets}>
              <button
                className={[selfStyles.presetBtn, settings.catboost_threshold === 0.5 ? selfStyles.presetBtnActive : ""].join(" ")}
                onClick={() => patch({ catboost_threshold: 0.5 })}
                title="Минимальный порог — максимальная чувствительность, больше ложных тревог"
              >
                Макс. защита (0.50)
              </button>
              <button
                className={[selfStyles.presetBtn, settings.catboost_threshold === 0.85 ? selfStyles.presetBtnActive : ""].join(" ")}
                onClick={() => patch({ catboost_threshold: 0.85 })}
                title="Высокий порог — меньше ложных тревог, только уверенные атаки"
              >
                Мин. тревог (0.85)
              </button>
            </div>
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
            <input
              type="checkbox"
              checked={settings.auto_block}
              onChange={(e) => {
                if (e.target.checked) {
                  setShowAutoBlockConfirm(true);
                } else {
                  patch({ auto_block: false });
                }
              }}
            />
            <span>{t("settings.autoBlock")}</span>
          </label>
          <label className={styles.field}>
            <span>Уровень авто-блокировки</span>
            <select
              value={settings.auto_block_level ?? "anomaly"}
              disabled={!settings.auto_block}
              onChange={(e) => patch({ auto_block_level: e.target.value as "anomaly" | "warning" })}
            >
              <option value="anomaly">Только аномалии (score ≥ 0.85) — консервативно</option>
              <option value="warning">Предупреждения + аномалии (score ≥ 0.70) — агрессивно</option>
            </select>
          </label>
          <label className={styles.toggleField}>
            <input
              type="checkbox"
              checked={settings.auto_unblock ?? false}
              disabled={!settings.auto_block}
              onChange={(e) => patch({ auto_unblock: e.target.checked })}
            />
            <span>Авто-разблокировка через cooldown</span>
          </label>
          <label className={styles.field}>
            <span>
              Cooldown (мин)
              <span className={selfStyles.badgeValue}>{settings.auto_unblock_cooldown_min ?? 10}</span>
            </span>
            <input
              type="number" min={1} max={120}
              value={settings.auto_unblock_cooldown_min ?? 10}
              disabled={!settings.auto_block || !settings.auto_unblock}
              onChange={(e) => patch({ auto_unblock_cooldown_min: Math.min(120, Math.max(1, Number(e.target.value))) })}
            />
          </label>
        </div>
      </div>

      {/* ── Detection mode (read-only info) ── */}
      <div className={selfStyles.group}>
        <div className={selfStyles.groupTitle}>Текущий режим детекции</div>
        <div style={{ fontSize: "12.5px", color: "var(--text-secondary)", lineHeight: 1.6, padding: "4px 0" }}>
          {s.detection_mode === "advanced"
            ? <><strong>Advanced</strong> — Stage1 (бинарный, F1=99.4%) → Stage3 IoT2023 (8 классов, Macro F1=0.82). Двойной extractor: 71 + 46 признаков.</>
            : s.detection_mode === "simple"
            ? <><strong>Simple</strong> — Stage1 (бинарный, F1=99.4%) → Stage2 (8 классов, Macro F1=0.31). CICFlowMeter, 71 признак.</>
            : <><strong>Binary</strong> — только Stage1, бинарная детекция (атака/норма).</>
          }
          <span style={{ marginLeft: 8, opacity: 0.5 }}>— сменить через «Выбрать модель»</span>
        </div>
      </div>

      {/* ── IP management: two-column table ── */}
      <div className={selfStyles.group}>
        <div className={selfStyles.groupTitle}>Управление IP-адресами</div>
        <div className={selfStyles.ipTableGrid}>

          {/* Blocked IPs column */}
          <div className={selfStyles.ipColumn}>
            <div className={selfStyles.ipColumnHeader}>
              <span>Заблокированные IP</span>
              {blockedIps.length > 0 && (
                <button className={selfStyles.clearAllBtn} onClick={() => void handleUnblockAll()}>
                  Разблокировать все
                </button>
              )}
            </div>
            {blockedIps.length === 0 ? (
              <p className={selfStyles.emptyList}>Нет заблокированных адресов</p>
            ) : (
              <div className={selfStyles.ipList}>
                {blockedIps.map((entry) => (
                  <div key={entry.ip} className={selfStyles.ipRow}>
                    <span className={selfStyles.ipAddr}>{entry.ip}</span>
                    <span className={selfStyles.ipMeta}>
                      {new Date(entry.blocked_at).toLocaleTimeString("ru-RU")}
                    </span>
                    <button className={selfStyles.ipRemoveBtn} onClick={() => void handleUnblock(entry.ip)}>
                      ×
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Whitelist column */}
          <div className={selfStyles.ipColumn}>
            <div className={selfStyles.ipColumnHeader}>
              <span>Белый список <span className={selfStyles.whitelistHint}>не блокируются</span></span>
              {(settings.whitelist_ips ?? []).length > 0 && (
                <button className={selfStyles.clearAllBtn}
                  onClick={() => patch({ whitelist_ips: [] })}>
                  Очистить всё
                </button>
              )}
            </div>
            <div className={selfStyles.ipAddRow}>
              <input
                className={selfStyles.ipAddInput}
                type="text"
                value={whitelistInput}
                placeholder="Введите IP-адрес"
                onChange={(e) => setWhitelistInput(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") addWhitelistIp(); }}
              />
              <button className={selfStyles.ipAddBtn} onClick={addWhitelistIp}>
                Добавить
              </button>
            </div>
            {(settings.whitelist_ips ?? []).length === 0 ? (
              <p className={selfStyles.emptyList}>Список пуст</p>
            ) : (
              <div className={selfStyles.ipList}>
                {(settings.whitelist_ips ?? []).map((ip) => (
                  <div key={ip} className={selfStyles.ipRow}>
                    <span className={selfStyles.ipAddr}>{ip}</span>
                    <button className={selfStyles.ipRemoveBtn} onClick={() => removeWhitelistIp(ip)}>
                      ×
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>

        </div>
      </div>

      {/* Auto-block confirmation dialog */}
      {showAutoBlockConfirm && (
        <div className={selfStyles.confirmOverlay}>
          <div className={selfStyles.confirmDialog}>
            <h3>⚠ Включить авто-блокировку?</h3>
            <p>
              Система будет автоматически блокировать IP-адреса через <code>iptables</code> при
              обнаружении атак. Если ваш IP не в белом списке — вы можете заблокировать сами себя.
            </p>
            <div className={selfStyles.confirmIpRow}>
              <label>Добавить ваш IP в белый список (необязательно):</label>
              <input
                type="text"
                value={confirmIp}
                placeholder="например: 1.2.3.4"
                onChange={(e) => setConfirmIp(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") {
                  const ip = confirmIp.trim();
                  const list = settings.whitelist_ips ?? [];
                  patch({ auto_block: true, whitelist_ips: ip && !list.includes(ip) ? [...list, ip] : list });
                  setShowAutoBlockConfirm(false); setConfirmIp("");
                }}}
                autoFocus
              />
            </div>
            <div className={selfStyles.confirmButtons}>
              <button className={selfStyles.confirmBtnSecondary}
                onClick={() => { setShowAutoBlockConfirm(false); setConfirmIp(""); }}>
                Отмена
              </button>
              <button className={selfStyles.confirmBtnSecondary}
                onClick={() => { patch({ auto_block: true }); setShowAutoBlockConfirm(false); setConfirmIp(""); }}>
                Включить без добавления
              </button>
              <button className={selfStyles.confirmBtnPrimary}
                onClick={() => {
                  const ip = confirmIp.trim();
                  const list = settings.whitelist_ips ?? [];
                  patch({ auto_block: true, whitelist_ips: ip && !list.includes(ip) ? [...list, ip] : list });
                  setShowAutoBlockConfirm(false); setConfirmIp("");
                }}>
                {confirmIp.trim() ? "Добавить IP и включить" : "Включить"}
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
