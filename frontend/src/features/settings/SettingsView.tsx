import { useCallback, useEffect, useRef, useState } from "react";
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

  // Whitelist tag input
  const [ipInput, setIpInput] = useState("");
  const ipInputRef = useRef<HTMLInputElement>(null);

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

  useEffect(() => {
    refreshBlocked();
  }, [refreshBlocked]);

  const handleUnblock = useCallback(async (ip: string) => {
    await api.unblockIp(ip).catch(() => null);
    refreshBlocked();
  }, [refreshBlocked]);

  const handleUnblockAll = useCallback(async () => {
    await api.unblockAllIps().catch(() => null);
    refreshBlocked();
  }, [refreshBlocked]);

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

      {/* ── CatBoost model (primary / Stage1) ── */}
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
          <div className={styles.field}>
            <span>
              Белый список IP
              <span className={selfStyles.badgeValue} style={{ marginLeft: 8, fontSize: 11 }}>
                не блокируются
              </span>
            </span>
            <div
              className={selfStyles.ipTagsWrap}
              onClick={() => ipInputRef.current?.focus()}
            >
              {(settings.whitelist_ips ?? []).map((ip) => (
                <span key={ip} className={selfStyles.ipTag}>
                  {ip}
                  <button
                    className={selfStyles.ipTagRemove}
                    onClick={(e) => {
                      e.stopPropagation();
                      patch({ whitelist_ips: (settings.whitelist_ips ?? []).filter((x) => x !== ip) });
                    }}
                  >×</button>
                </span>
              ))}
              <input
                ref={ipInputRef}
                className={selfStyles.ipTagInput}
                value={ipInput}
                placeholder={(settings.whitelist_ips ?? []).length === 0 ? "Введите IP и нажмите Enter" : ""}
                onChange={(e) => setIpInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === ",") {
                    e.preventDefault();
                    const val = ipInput.trim().replace(/,$/, "");
                    if (val && !(settings.whitelist_ips ?? []).includes(val)) {
                      patch({ whitelist_ips: [...(settings.whitelist_ips ?? []), val] });
                    }
                    setIpInput("");
                  } else if (e.key === "Backspace" && ipInput === "") {
                    const list = settings.whitelist_ips ?? [];
                    if (list.length > 0) {
                      patch({ whitelist_ips: list.slice(0, -1) });
                    }
                  }
                }}
                onBlur={() => {
                  const val = ipInput.trim();
                  if (val && !(settings.whitelist_ips ?? []).includes(val)) {
                    patch({ whitelist_ips: [...(settings.whitelist_ips ?? []), val] });
                    setIpInput("");
                  }
                }}
              />
            </div>
          </div>

          {/* Auto-block confirmation dialog */}
          {showAutoBlockConfirm && (
            <div className={selfStyles.confirmOverlay}>
              <div className={selfStyles.confirmDialog}>
                <h3>⚠ Включить авто-блокировку?</h3>
                <p>
                  Система будет автоматически добавлять правила <code>iptables</code> для
                  блокировки IP-адресов при обнаружении атак.
                  <br /><br />
                  Если ваш IP не в белом списке — вы можете заблокировать сами себя.
                </p>
                <div className={selfStyles.confirmIpRow}>
                  <label>Добавить ваш IP в белый список (необязательно):</label>
                  <input
                    type="text"
                    value={confirmIp}
                    placeholder="например: 1.2.3.4"
                    onChange={(e) => setConfirmIp(e.target.value)}
                    autoFocus
                  />
                </div>
                <div className={selfStyles.confirmButtons}>
                  <button
                    className={selfStyles.confirmBtnSecondary}
                    onClick={() => { setShowAutoBlockConfirm(false); setConfirmIp(""); }}
                  >
                    Отмена
                  </button>
                  <button
                    className={selfStyles.confirmBtnSecondary}
                    onClick={() => {
                      patch({ auto_block: true });
                      setShowAutoBlockConfirm(false);
                      setConfirmIp("");
                    }}
                  >
                    Включить без добавления
                  </button>
                  <button
                    className={selfStyles.confirmBtnPrimary}
                    onClick={() => {
                      const ip = confirmIp.trim();
                      const list = settings.whitelist_ips ?? [];
                      patch({
                        auto_block: true,
                        whitelist_ips: ip && !list.includes(ip) ? [...list, ip] : list,
                      });
                      setShowAutoBlockConfirm(false);
                      setConfirmIp("");
                    }}
                  >
                    {confirmIp.trim() ? "Добавить IP и включить" : "Включить"}
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* ── Detection mode ── */}
      <div className={selfStyles.group}>
        <div className={selfStyles.groupTitle}>Режим детекции</div>
        <div className={styles.formGrid}>
          <label className={styles.field}>
            <span>Режим</span>
            <select
              value={settings.detection_mode ?? "simple"}
              onChange={(e) => patch({ detection_mode: e.target.value as "simple" | "advanced" })}
            >
              <option value="simple">Simple — Stage1 + Stage2 (71 признак)</option>
              <option value="advanced">Advanced — Stage1 + Stage3 IoT 2023 (46 признаков, Macro F1=0.82)</option>
            </select>
          </label>
          <label className={styles.field}>
            <span>
              {settings.detection_mode === "advanced" ? "Stage3 IoT 2023 (dir)" : "Stage2 Multi-Class (dir)"}
            </span>
            <input
              type="text"
              value={settings.catboost_secondary_model_dir ?? ""}
              placeholder={
                settings.detection_mode === "advanced"
                  ? "G:/Диплом/IoT/stage3_cic2023/models/catboost"
                  : "G:/Диплом/IoT/stage2_multiclass/models/catboost"
              }
              onChange={(e) => patch({ catboost_secondary_model_dir: e.target.value })}
            />
          </label>
          {settings.detection_mode === "advanced" && (
            <label className={styles.field}>
              <span>Stage3 артефакты (dir)</span>
              <input
                type="text"
                value={settings.catboost_secondary_artifacts_dir ?? ""}
                placeholder="G:/Диплом/IoT/stage3_cic2023/artifacts"
                onChange={(e) => patch({ catboost_secondary_artifacts_dir: e.target.value })}
              />
            </label>
          )}
        </div>
        <div style={{ marginTop: "8px", fontSize: "12px", opacity: 0.6, lineHeight: 1.5 }}>
          {settings.detection_mode === "simple"
            ? "Stage1 (бинарный, F1=99.4%) → Stage2 (8 классов, Macro F1=0.31). Один feature extractor (CICFlowMeter, 71 признак)."
            : "Stage1 (бинарный, F1=99.4%) → Stage3 IoT2023 (8 классов, Macro F1=0.82). Двойной extractor: 71 + 46 признаков. Лучше для Recon, Bot, Spoofing."}
        </div>
      </div>

      {/* ── Blocked IPs ── */}
      <div className={selfStyles.group}>
        <div className={selfStyles.groupTitle}>Заблокированные IP</div>
        {blockedIps.length === 0 ? (
          <p className={selfStyles.emptyBlocked}>Нет заблокированных IP-адресов.</p>
        ) : (
          <>
            <div className={selfStyles.blockedList}>
              {blockedIps.map((entry) => (
                <div key={entry.ip} className={selfStyles.blockedRow}>
                  <span>
                    <span className={selfStyles.blockedIp}>{entry.ip}</span>
                    <span className={selfStyles.blockedAt}>
                      {new Date(entry.blocked_at).toLocaleTimeString("ru-RU")}
                    </span>
                  </span>
                  <button className={selfStyles.unblockBtn} onClick={() => void handleUnblock(entry.ip)}>
                    Разблокировать
                  </button>
                </div>
              ))}
            </div>
            <button className={selfStyles.unblockAllBtn} onClick={() => void handleUnblockAll()}>
              Разблокировать все ({blockedIps.length})
            </button>
          </>
        )}
      </div>
    </section>
  );
}
