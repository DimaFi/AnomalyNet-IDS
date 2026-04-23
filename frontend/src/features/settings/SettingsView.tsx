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
  const [autostartState, setAutostartState] = useState<{ available: boolean; enabled: boolean } | null>(null);
  const [autostartLoading, setAutostartLoading] = useState(false);

  // Whitelist add input (local only — save on Add/Enter)
  const [whitelistInput, setWhitelistInput] = useState("");

  // Auto-block confirm dialog
  const [showAutoBlockConfirm, setShowAutoBlockConfirm] = useState(false);
  const [confirmIp, setConfirmIp] = useState("");

  useEffect(() => {
    api.getInterfaces().then(setInterfaces).catch(() => setInterfaces([]));
    api.getAutostart().then(setAutostartState).catch(() => null);
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
              onChange={(e) => patch({ theme: e.target.value as "dark" | "light" | "gray" })}>
              <option value="dark">Dark</option>
              <option value="light">Light</option>
              <option value="gray">Gray (VS Code)</option>
            </select>
          </label>
          <label className={styles.field}>
            <span>{t("settings.runMode")}</span>
            <select value={settings.run_mode}
              onChange={(e) => patch({ run_mode: e.target.value as AppSettings["run_mode"] })}>
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
          {autostartState?.available && (
            <label className={styles.toggleField}>
              <input
                type="checkbox"
                checked={autostartState.enabled}
                disabled={autostartLoading}
                onChange={async (e) => {
                  setAutostartLoading(true);
                  try {
                    const res = await api.setAutostart(e.target.checked);
                    setAutostartState(res);
                  } catch { /* ignore */ }
                  finally { setAutostartLoading(false); }
                }}
              />
              <span>Запускать при старте системы (systemctl)</span>
            </label>
          )}
        </div>
      </div>

      {/* ── Network capture ── */}
      <div className={selfStyles.group}>
        <div className={selfStyles.groupTitle}>{t("settings.groupCapture")}</div>
        {interfaces.length > 0 ? (
          <div className={selfStyles.ifaceList}>
            {interfaces.map((iface) => {
              const selected = (settings.interface_names ?? []).includes(iface.name);
              return (
                <label key={iface.name} className={selfStyles.ifaceRow}>
                  <input
                    type="checkbox"
                    checked={selected}
                    onChange={(e) => {
                      const prev = settings.interface_names ?? [];
                      const next = e.target.checked
                        ? [...prev, iface.name]
                        : prev.filter((n) => n !== iface.name);
                      patch({ interface_names: next });
                    }}
                  />
                  <span className={selfStyles.ifaceName}>{iface.name}</span>
                  {iface.addresses[0] && (
                    <span className={selfStyles.ifaceAddr}>{iface.addresses[0]}</span>
                  )}
                  {iface.is_default && (
                    <span className={selfStyles.ifaceDefault}>рекомендуется</span>
                  )}
                  {!iface.is_up && (
                    <span className={selfStyles.ifaceDown}>выкл</span>
                  )}
                </label>
              );
            })}
            {(settings.interface_names ?? []).length === 0 && (
              <p className={selfStyles.ifaceHint}>Выберите хотя бы один интерфейс</p>
            )}
          </div>
        ) : (
          <div className={styles.formGrid}>
            <label className={styles.field}>
              <span>{t("settings.interfaceName")}</span>
              <input type="text" value={settings.interface_name}
                onChange={(e) => patch({ interface_name: e.target.value })}
                placeholder="eth0" />
            </label>
          </div>
        )}
      </div>

      {/* ── Model settings ── */}
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
        </div>

        {/* Paths sub-block */}
        <div className={selfStyles.subBlock}>
          <div className={selfStyles.subBlockTitle}>Пути к файлам моделей</div>
          <div className={styles.formGrid}>
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
          </div>
        </div>

        {/* Dir viewer sub-block */}
        <ModelDirsViewer settings={settings} />

        <div className={styles.formGrid}>
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
        </div>{/* end formGrid */}
      </div>{/* end group */}

      {/* ── Active pipeline / Detection mode ── */}
      <div className={selfStyles.group}>
        <div className={selfStyles.groupTitle}>Активный pipeline</div>
        <div style={{ fontSize: "12.5px", color: "var(--text-secondary)", lineHeight: 1.7, padding: "4px 0" }}>
          {s.active_model_id?.startsWith("plugin:") ? (
            <>
              <strong style={{ color: "var(--accent)" }}>Plugin pipeline:</strong>{" "}
              <code style={{ background: "var(--surface-3)", borderRadius: 4, padding: "1px 6px", fontFamily: "monospace", fontSize: 11 }}>
                {s.active_model_id.slice("plugin:".length)}
              </code>
              {s.active_model_id === "plugin:advanced" && " — Stage1 → Stage3 IoT2023 (46 признаков, Macro F1=0.82)"}
              {s.active_model_id === "plugin:simple"   && " — Stage1 → Stage2 (71 признак, 8 классов)"}
              {s.active_model_id === "plugin:fast"     && " — Stage1 бинарный (71 признак, минимальная задержка)"}
            </>
          ) : (
            <>
              <strong>Стандартная модель:</strong>{" "}
              <code style={{ background: "var(--surface-3)", borderRadius: 4, padding: "1px 6px", fontFamily: "monospace", fontSize: 11 }}>
                {s.active_model_id}
              </code>
              {" — "}
              {s.detection_mode === "advanced"
                ? "Advanced: Stage1 → Stage3 IoT2023 (71+46 признаков)"
                : s.detection_mode === "simple"
                ? "Simple: Stage1 → Stage2 (71 признак, 8 классов)"
                : "Binary: только Stage1 (71 признак)"}
            </>
          )}
          <span style={{ marginLeft: 8, opacity: 0.45, fontSize: 11 }}>— сменить через «Выбрать модель»</span>
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

// ── Model directory browser ──────────────────────────────────────────────────

type DirEntry = { name: string; is_dir: boolean; size_bytes: number | null };
type DirResult = { path: string; exists: boolean; error?: string; entries: DirEntry[] };

function ModelDirsViewer({ settings }: { settings: AppSettings }) {
  const [open, setOpen] = useState(false);
  const [results, setResults] = useState<Record<string, DirResult>>({});
  const [loading, setLoading] = useState(false);
  const loadedRef = useRef(false);

  const dirs = [
    { label: "Stage1 модель",        path: settings.catboost_model_dir },
    { label: "Stage1 артефакты",     path: settings.preprocessing_artifacts_dir },
    { label: "Stage2 модель",        path: settings.catboost_secondary_model_dir },
    { label: "Stage3 модель",        path: settings.catboost_stage3_model_dir },
    { label: "Stage3 артефакты",     path: settings.catboost_stage3_artifacts_dir },
  ].filter((d) => d.path);

  async function loadDirs() {
    if (loadedRef.current) return;
    loadedRef.current = true;
    setLoading(true);
    const res: Record<string, DirResult> = {};
    await Promise.all(dirs.map(async (d) => {
      try { res[d.path] = await api.lsDir(d.path); }
      catch { res[d.path] = { path: d.path, exists: false, entries: [], error: "network error" }; }
    }));
    setResults(res);
    setLoading(false);
  }

  function handleToggle() {
    setOpen((v) => !v);
    if (!open) loadDirs();
  }

  return (
    <div className={selfStyles.dirViewer}>
      <button className={selfStyles.dirViewerToggle} onClick={handleToggle}>
        {open ? "▾" : "▸"} Просмотр папок моделей
        {!open && <span className={selfStyles.dirViewerHint}>проверить что файлы на месте</span>}
      </button>
      {open && (
        <div className={selfStyles.dirViewerContent}>
          {loading && <p className={selfStyles.dirLoading}>Загрузка...</p>}
          {dirs.map((d) => {
            const r = results[d.path];
            return (
              <div key={d.path} className={selfStyles.dirBlock}>
                <div className={selfStyles.dirBlockHeader}>
                  <span className={selfStyles.dirLabel}>{d.label}</span>
                  {r && (
                    <span className={r.exists ? selfStyles.dirExists : selfStyles.dirMissing}>
                      {r.exists ? "✓ найдена" : "✗ не найдена"}
                    </span>
                  )}
                </div>
                <code className={selfStyles.dirPath}>{d.path}</code>
                {r?.error && <p className={selfStyles.dirError}>{r.error}</p>}
                {r?.exists && r.entries.length > 0 && (
                  <div className={selfStyles.dirEntries}>
                    {r.entries.map((e) => (
                      <span key={e.name} className={`${selfStyles.dirEntry} ${e.is_dir ? selfStyles.dirEntryDir : selfStyles.dirEntryFile}`}>
                        {e.is_dir ? "📁" : fileIcon(e.name)}{" "}{e.name}
                        {e.size_bytes !== null && !e.is_dir && (
                          <span className={selfStyles.dirEntrySize}>{fmtSize(e.size_bytes)}</span>
                        )}
                      </span>
                    ))}
                  </div>
                )}
                {r?.exists && r.entries.length === 0 && (
                  <p className={selfStyles.dirEmpty}>Папка пуста</p>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function fileIcon(name: string): string {
  if (name.endsWith(".cbm") || name.endsWith(".pkl") || name.endsWith(".joblib")) return "🧠";
  if (name.endsWith(".json")) return "📋";
  if (name.endsWith(".png"))  return "🖼";
  return "📄";
}

function fmtSize(b: number): string {
  if (b >= 1_000_000) return `${(b / 1_000_000).toFixed(1)} MB`;
  if (b >= 1_000)     return `${(b / 1_000).toFixed(0)} KB`;
  return `${b} B`;
}
