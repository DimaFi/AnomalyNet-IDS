import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useAppStore } from "../../app/store";
import type { AppSettings, ModelPackageInfo, NetworkInterface, OfficialModelInfo, PlatformCapabilities, SystemStats } from "../../app/types";
import { ModelPresetPicker } from "../../components/ModelPresetPicker";
import { api } from "../../lib/api";
import styles from "../panel.module.css";
import selfStyles from "./SettingsView.module.css";

export function SettingsView() {
  const { t, i18n } = useTranslation();
  const settings = useAppStore((state) => state.settings);
  const setSettings = useAppStore((state) => state.setSettings);
  const capabilities = useAppStore((state) => state.capabilities);
  const setCapabilities = useAppStore((state) => state.setCapabilities);
  const [interfaces, setInterfaces] = useState<NetworkInterface[]>([]);
  const [blockedIps, setBlockedIps] = useState<{ ip: string; blocked_at: string }[]>([]);
  const [autostartState, setAutostartState] = useState<{ available: boolean; enabled: boolean } | null>(null);
  const [autostartLoading, setAutostartLoading] = useState(false);
  const [whitelistInput, setWhitelistInput] = useState("");
  const [showAutoBlockConfirm, setShowAutoBlockConfirm] = useState(false);
  const [confirmIp, setConfirmIp] = useState("");

  useEffect(() => {
    api.getInterfaces().then(setInterfaces).catch(() => setInterfaces([]));
    api.getAutostart().then(setAutostartState).catch(() => null);
    api.getCapabilities().then(setCapabilities).catch(() => null);
  }, [setCapabilities]);

  const refreshBlocked = useCallback(() => {
    api.getBlockedIps().then((res) => setBlockedIps(res.items)).catch(() => setBlockedIps([]));
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
    if (!list.includes(val)) patch({ whitelist_ips: [...list, val] });
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
            <select value={s.language} onChange={(e) => patch({ language: e.target.value as "ru" | "en" })}>
              <option value="ru">Русский</option>
              <option value="en">English</option>
            </select>
          </label>
          <label className={styles.field}>
            <span>{t("settings.theme")}</span>
            <select value={s.theme} onChange={(e) => patch({ theme: e.target.value as AppSettings["theme"] })}>
              <option value="dark">Dark</option>
              <option value="light">Light</option>
              <option value="gray">Gray (VS Code)</option>
            </select>
          </label>
          <label className={styles.field}>
            <span>{t("settings.runMode")}</span>
            <select value={s.run_mode} onChange={(e) => patch({ run_mode: e.target.value as AppSettings["run_mode"] })}>
              {(!capabilities || capabilities.platform === "linux") && (
                <option value="linux_live">Linux Live — Scapy + iptables</option>
              )}
              {(!capabilities || capabilities.platform === "windows") && (
                <option value="windows_live">Windows Live — Npcap + netsh</option>
              )}
            </select>
          </label>
          {capabilities && !capabilities.packet_capture &&
           (s.run_mode === "linux_live" || s.run_mode === "windows_live") && (
            <p className={styles.warnNote}>
              ⚠{" "}
              {capabilities.warnings.find(w => /npcap|admin|rights|privilege|scapy/i.test(w))
               ?? "Захват трафика недоступен. Убедитесь что приложение запущено с правами администратора."}
            </p>
          )}
          <label className={styles.field}>
            <span>{t("settings.retention")}</span>
            <input type="number" min={1} max={30} value={s.retention_days}
              onChange={(e) => patch({ retention_days: Math.min(30, Math.max(1, Number(e.target.value))) })} />
          </label>
          <label className={styles.toggleField}>
            <input type="checkbox" checked={s.capture_enabled}
              onChange={(e) => patch({ capture_enabled: e.target.checked })} />
            <span>{t("settings.capture")}</span>
          </label>
          <label className={styles.toggleField}>
            <input type="checkbox" checked={s.stream_autostart}
              onChange={(e) => patch({ stream_autostart: e.target.checked })} />
            <span>{t("settings.autostart")}</span>
          </label>
          {autostartState?.available && (
            <label className={styles.toggleField}>
              <input type="checkbox" checked={autostartState.enabled} disabled={autostartLoading}
                onChange={async (e) => {
                  setAutostartLoading(true);
                  try { const res = await api.setAutostart(e.target.checked); setAutostartState(res); }
                  catch { /* ignore */ }
                  finally { setAutostartLoading(false); }
                }} />
              <span>Запускать при старте системы{capabilities?.service_backend ? ` (${capabilities.service_backend})` : ""}</span>
            </label>
          )}
        </div>
      </div>

      {/* ── Remote access ── */}
      <div className={selfStyles.group}>
        <div className={selfStyles.groupTitle}>Сетевой доступ к панели</div>
        <div className={styles.formGrid}>
          <label className={styles.toggleField}>
            <input type="checkbox" checked={s.allow_remote_access ?? false}
              onChange={(e) => patch({ allow_remote_access: e.target.checked })} />
            <span>Разрешить доступ с других устройств в сети (0.0.0.0:8000)</span>
          </label>
          {(s.allow_remote_access) && (
            <p className={styles.warnNote}>
              ⚠ Требуется перезапуск приложения. После перезапуска панель будет доступна по адресу вашего ПК в сети, например <code>http://172.30.44.X:8000</code>
            </p>
          )}
          {!(s.allow_remote_access) && (
            <p className={styles.dimNote}>
              Сейчас панель доступна только на этом ПК (127.0.0.1:8000).
            </p>
          )}
        </div>
      </div>

      {/* ── Platform capabilities ── */}
      {capabilities && <PlatformStatusPanel caps={capabilities} />}

      {/* ── Resource monitor ── */}
      <ResourceMonitor />

      {/* ── Network capture ── */}
      <div className={selfStyles.group}>
        <div className={selfStyles.groupTitle}>{t("settings.groupCapture")}</div>
        {interfaces.length > 0 ? (
          <div className={selfStyles.ifaceList}>
            {interfaces.map((iface) => {
              const selected = (s.interface_names ?? []).includes(iface.name);
              const isSingle = s.interface_name === iface.name && !(s.interface_names ?? []).length;
              const isActive = selected || isSingle;
              return (
                <label key={iface.name} className={[selfStyles.ifaceRow, isActive ? selfStyles.ifaceRowActive : ""].filter(Boolean).join(" ")}>
                  <input type="checkbox" checked={isActive}
                    onChange={(e) => {
                      const prev = (s.interface_names ?? []).length ? s.interface_names ?? [] : s.interface_name ? [s.interface_name] : [];
                      const next = e.target.checked ? [...prev.filter(n => n !== iface.name), iface.name] : prev.filter((n) => n !== iface.name);
                      patch({ interface_names: next, interface_name: next[0] ?? "" });
                    }} />
                  <span className={selfStyles.ifaceName}>{iface.name}</span>
                  {iface.addresses[0] && <span className={selfStyles.ifaceAddr}>{iface.addresses[0]}</span>}
                  {iface.is_recommended && <span className={selfStyles.ifaceRecommended}>рекомендуется</span>}
                  {iface.is_default && !iface.is_recommended && <span className={selfStyles.ifaceDefault}>шлюз</span>}
                  {iface.bytes_total > 0 && (
                    <span className={selfStyles.ifaceTraffic} title="Всего трафика с момента загрузки">
                      {fmtTraffic(iface.bytes_total)}
                    </span>
                  )}
                  {!iface.is_up && <span className={selfStyles.ifaceDown}>выкл</span>}
                </label>
              );
            })}
            {!(s.interface_names ?? []).length && !s.interface_name && (
              <p className={selfStyles.ifaceHint}>Интерфейс определится автоматически при старте</p>
            )}
          </div>
        ) : (
          <div className={styles.formGrid}>
            <label className={styles.field}>
              <span>{t("settings.interfaceName")}</span>
              <input type="text" value={s.interface_name}
                onChange={(e) => patch({ interface_name: e.target.value })} placeholder="eth0" />
            </label>
          </div>
        )}
      </div>

      {/* ── Models ── */}
      <div className={selfStyles.group}>
        <div className={selfStyles.groupTitle}>Модели</div>

        {/* models_dir */}
        <div className={styles.formGrid}>
          <label className={styles.field} style={{ gridColumn: "1 / -1" }}>
            <span>Папка с моделями</span>
            <input type="text" value={s.models_dir ?? ""}
              placeholder="/opt/anomalynet-ml/models   или   C:/AnomalyNet-ml/models"
              onChange={(e) => patch({ models_dir: e.target.value })} />
          </label>
          <label className={styles.toggleField}>
            <input type="checkbox" checked={s.auto_download_models ?? true}
              onChange={(e) => patch({ auto_download_models: e.target.checked })} />
            <span>Скачивать официальные модели при первом запуске</span>
          </label>
          <label className={styles.toggleField}>
            <input type="checkbox" checked={s.auto_update_models ?? false}
              onChange={(e) => patch({ auto_update_models: e.target.checked })} />
            <span>Автообновление через git pull при старте</span>
          </label>
        </div>

        {/* Installed packages / catalog */}
        <ModelsSection modelsDir={s.models_dir ?? ""} onSetModelsDir={(d) => patch({ models_dir: d })} />
      </div>

      {/* ── Detection threshold + auto-block ── */}
      <div className={selfStyles.group}>
        <div className={selfStyles.groupTitle}>{t("settings.groupCatboost")}</div>
        <div className={styles.formGrid}>
          <label className={styles.field}>
            <span>
              {t("settings.catboostThreshold")}
              <span className={selfStyles.badgeValue}>{s.catboost_threshold.toFixed(2)}</span>
            </span>
            <input type="range" min={0.5} max={0.99} step={0.01} value={s.catboost_threshold}
              onChange={(e) => patch({ catboost_threshold: parseFloat(e.target.value) })} />
            <div className={selfStyles.thresholdPresets}>
              <button className={[selfStyles.presetBtn, s.catboost_threshold === 0.5 ? selfStyles.presetBtnActive : ""].join(" ")}
                onClick={() => patch({ catboost_threshold: 0.5 })} title="Максимальная чувствительность, больше ложных тревог">
                Макс. защита (0.50)
              </button>
              <button className={[selfStyles.presetBtn, s.catboost_threshold === 0.85 ? selfStyles.presetBtnActive : ""].join(" ")}
                onClick={() => patch({ catboost_threshold: 0.85 })} title="Меньше ложных тревог, только уверенные атаки">
                Мин. тревог (0.85)
              </button>
            </div>
          </label>
          <label className={styles.field}>
            <span>Режим блокировки</span>
            <div className={selfStyles.thresholdPresets}>
              <button
                className={[selfStyles.presetBtn, (s.blocking_mode ?? "pc") === "pc" ? selfStyles.presetBtnActive : ""].join(" ")}
                onClick={() => patch({ blocking_mode: "pc" })}
                title="Блокирует входящий трафик к этому компьютеру (цепочка INPUT)">
                PC Mode
              </button>
              <button
                className={[selfStyles.presetBtn, s.blocking_mode === "gateway" ? selfStyles.presetBtnActive : ""].join(" ")}
                onClick={() => patch({ blocking_mode: "gateway" })}
                title="Блокирует транзитный трафик через AnomalyNet как шлюз (цепочка FORWARD)">
                Gateway Mode
              </button>
            </div>
            <span style={{ fontSize: "11px", color: "var(--text-muted)", marginTop: "4px", display: "block" }}>
              {(s.blocking_mode ?? "pc") === "pc"
                ? "Блокирует доступ к этому компьютеру (INPUT)"
                : "Блокирует транзитный трафик через AnomalyNet как шлюз (FORWARD)"}
            </span>
          </label>
          <label className={styles.toggleField}>
            <input type="checkbox" checked={s.auto_block}
              onChange={(e) => { if (e.target.checked) setShowAutoBlockConfirm(true); else patch({ auto_block: false }); }} />
            <span>{t("settings.autoBlock")}</span>
          </label>
          <label className={styles.field}>
            <span>Уровень авто-блокировки</span>
            <select value={s.auto_block_level ?? "anomaly"} disabled={!s.auto_block}
              onChange={(e) => patch({ auto_block_level: e.target.value as "anomaly" | "warning" })}>
              <option value="anomaly">Только аномалии (score ≥ 0.85) — консервативно</option>
              <option value="warning">Предупреждения + аномалии (score ≥ 0.70) — агрессивно</option>
            </select>
          </label>
          <label className={styles.toggleField}>
            <input type="checkbox" checked={s.auto_unblock ?? false} disabled={!s.auto_block}
              onChange={(e) => patch({ auto_unblock: e.target.checked })} />
            <span>Авто-разблокировка через cooldown</span>
          </label>
          <label className={styles.field}>
            <span>Cooldown (мин)<span className={selfStyles.badgeValue}>{s.auto_unblock_cooldown_min ?? 10}</span></span>
            <input type="number" min={1} max={120} value={s.auto_unblock_cooldown_min ?? 10}
              disabled={!s.auto_block || !s.auto_unblock}
              onChange={(e) => patch({ auto_unblock_cooldown_min: Math.min(120, Math.max(1, Number(e.target.value))) })} />
          </label>
        </div>
      </div>

      {/* ── Active pipeline ── */}
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
              {s.active_model_id === "plugin:fast"     && " — Stage1 бинарный (минимальная задержка)"}
            </>
          ) : (
            <>
              <strong>Модель:</strong>{" "}
              <code style={{ background: "var(--surface-3)", borderRadius: 4, padding: "1px 6px", fontFamily: "monospace", fontSize: 11 }}>
                {s.active_model_id}
              </code>
            </>
          )}
          <span style={{ marginLeft: 8, opacity: 0.45, fontSize: 11 }}>— сменить через «Выбрать модель»</span>
        </div>
      </div>

      {/* ── IP management ── */}
      <div className={selfStyles.group}>
        <div className={selfStyles.groupTitle}>Управление IP-адресами</div>
        <div className={selfStyles.ipTableGrid}>
          <div className={selfStyles.ipColumn}>
            <div className={selfStyles.ipColumnHeader}>
              <span>Заблокированные IP</span>
              {blockedIps.length > 0 && (
                <button className={selfStyles.clearAllBtn} onClick={() => void handleUnblockAll()}>Разблокировать все</button>
              )}
            </div>
            {blockedIps.length === 0 ? (
              <p className={selfStyles.emptyList}>Нет заблокированных адресов</p>
            ) : (
              <div className={selfStyles.ipList}>
                {blockedIps.map((entry) => (
                  <div key={entry.ip} className={selfStyles.ipRow}>
                    <span className={selfStyles.ipAddr}>{entry.ip}</span>
                    <span className={selfStyles.ipMeta}>{new Date(entry.blocked_at).toLocaleTimeString("ru-RU")}</span>
                    <button className={selfStyles.ipRemoveBtn} onClick={() => void handleUnblock(entry.ip)}>×</button>
                  </div>
                ))}
              </div>
            )}
          </div>
          <div className={selfStyles.ipColumn}>
            <div className={selfStyles.ipColumnHeader}>
              <span>Белый список <span className={selfStyles.whitelistHint}>не блокируются</span></span>
              {(s.whitelist_ips ?? []).length > 0 && (
                <button className={selfStyles.clearAllBtn} onClick={() => patch({ whitelist_ips: [] })}>Очистить всё</button>
              )}
            </div>
            <div className={selfStyles.ipAddRow}>
              <input className={selfStyles.ipAddInput} type="text" value={whitelistInput}
                placeholder="Введите IP-адрес" onChange={(e) => setWhitelistInput(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") addWhitelistIp(); }} />
              <button className={selfStyles.ipAddBtn} onClick={addWhitelistIp}>Добавить</button>
            </div>
            {(s.whitelist_ips ?? []).length === 0 ? (
              <p className={selfStyles.emptyList}>Список пуст</p>
            ) : (
              <div className={selfStyles.ipList}>
                {(s.whitelist_ips ?? []).map((ip) => (
                  <div key={ip} className={selfStyles.ipRow}>
                    <span className={selfStyles.ipAddr}>{ip}</span>
                    <button className={selfStyles.ipRemoveBtn} onClick={() => removeWhitelistIp(ip)}>×</button>
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
              Система будет автоматически блокировать IP через <code>iptables</code>.
              Если ваш IP не в белом списке — вы можете заблокировать себя.
            </p>
            <div className={selfStyles.confirmIpRow}>
              <label>Добавить ваш IP в белый список (необязательно):</label>
              <input type="text" value={confirmIp} placeholder="например: 1.2.3.4"
                onChange={(e) => setConfirmIp(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") {
                  const ip = confirmIp.trim(); const list = s.whitelist_ips ?? [];
                  patch({ auto_block: true, whitelist_ips: ip && !list.includes(ip) ? [...list, ip] : list });
                  setShowAutoBlockConfirm(false); setConfirmIp("");
                }}} autoFocus />
            </div>
            <div className={selfStyles.confirmButtons}>
              <button className={selfStyles.confirmBtnSecondary} onClick={() => { setShowAutoBlockConfirm(false); setConfirmIp(""); }}>Отмена</button>
              <button className={selfStyles.confirmBtnSecondary}
                onClick={() => { patch({ auto_block: true }); setShowAutoBlockConfirm(false); setConfirmIp(""); }}>
                Включить без добавления
              </button>
              <button className={selfStyles.confirmBtnPrimary}
                onClick={() => {
                  const ip = confirmIp.trim(); const list = s.whitelist_ips ?? [];
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

// ── Models section ────────────────────────────────────────────────────────────

function ModelsSection({ modelsDir, onSetModelsDir }: { modelsDir: string; onSetModelsDir: (d: string) => void }) {
  const [packages, setPackages] = useState<ModelPackageInfo[]>([]);
  const [catalog, setCatalog] = useState<OfficialModelInfo[]>([]);
  const [open, setOpen] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [downloading, setDownloading] = useState<string | null>(null);
  const [downloadLog, setDownloadLog] = useState<string[]>([]);
  const [addInput, setAddInput] = useState("");
  const loadedRef = useRef(false);

  async function load() {
    const [pkgs, cat] = await Promise.all([
      api.listModelPackages().catch(() => [] as ModelPackageInfo[]),
      api.getModelCatalog().catch(() => [] as OfficialModelInfo[]),
    ]);
    setPackages(pkgs);
    setCatalog(cat);
    loadedRef.current = true;
  }

  function handleToggle() {
    const next = !open;
    setOpen(next);
    if (next && !loadedRef.current) void load();
  }

  async function handleScan() {
    setScanning(true);
    try { await api.scanModels(); await load(); } catch { /* ignore */ }
    finally { setScanning(false); }
  }

  async function handleAdd() {
    const path = addInput.trim();
    if (!path) return;
    try {
      await api.addModelFolder(path);
      setAddInput("");
      await load();
    } catch (e: unknown) {
      alert((e as Error).message ?? "Ошибка добавления");
    }
  }

  async function handleDownload(catalogId: string) {
    setDownloading(catalogId);
    setDownloadLog([]);
    try {
      const resp = await fetch(`/api/models-manager/download/${catalogId}`, { method: "POST" });
      if (!resp.body) return;
      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        const lines = decoder.decode(value).split("\n").filter(Boolean);
        setDownloadLog((prev) => [...prev, ...lines].slice(-30));
        if (lines.some((l) => l.startsWith("models_dir_set:"))) {
          const line = lines.find((l) => l.startsWith("models_dir_set:"))!;
          onSetModelsDir(line.replace("models_dir_set:", "").trim());
        }
      }
      await load();
    } catch { /* ignore */ }
    finally { setDownloading(null); }
  }

  const installedIds = new Set(packages.map((p) => p.id));

  return (
    <div className={selfStyles.dirViewer}>
      <button className={selfStyles.dirViewerToggle} onClick={handleToggle}>
        {open ? "▾" : "▸"} Управление моделями
        {!open && packages.length > 0 && (
          <span className={selfStyles.dirViewerHint}>{packages.length} установлено</span>
        )}
        {!open && packages.length === 0 && !modelsDir && (
          <span className={selfStyles.dirViewerHint} style={{ color: "var(--text-muted)" }}>не настроено</span>
        )}
      </button>

      {open && (
        <div className={selfStyles.dirViewerContent}>
          {/* Official catalog */}
          {catalog.length > 0 && (
            <div style={{ marginBottom: 12 }}>
              <div className={selfStyles.subBlockTitle} style={{ marginBottom: 6 }}>Официальные модели</div>
              {catalog.map((entry) => {
                const isInstalled = modelsDir !== "";
                const isDownloading = downloading === entry.id;
                return (
                  <div key={entry.id} className={selfStyles.catalogEntry}>
                    <div className={selfStyles.catalogEntryMain}>
                      <strong>{entry.name}</strong>
                      <span className={selfStyles.catalogMeta}>~{entry.size_mb} MB</span>
                      {isInstalled && <span className={selfStyles.catalogInstalled}>✓ установлено</span>}
                    </div>
                    <p className={selfStyles.catalogDesc}>{entry.description}</p>
                    <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 6 }}>
                      <button
                        className={selfStyles.catalogBtn}
                        disabled={isDownloading}
                        onClick={() => void handleDownload(entry.id)}
                      >
                        {isDownloading ? "Загрузка..." : isInstalled ? "Обновить" : "Скачать"}
                      </button>
                    </div>
                    {isDownloading && downloadLog.length > 0 && (
                      <pre className={selfStyles.downloadLog}>{downloadLog.join("\n")}</pre>
                    )}
                  </div>
                );
              })}
            </div>
          )}

          {/* Installed packages */}
          <div className={selfStyles.subBlockTitle} style={{ marginBottom: 6 }}>
            Установленные пакеты
            <button className={selfStyles.scanBtn} onClick={() => void handleScan()} disabled={scanning}>
              {scanning ? "Сканирование..." : "↻ Пересканировать"}
            </button>
          </div>
          {packages.length === 0 ? (
            <p className={selfStyles.emptyList}>
              {modelsDir ? "Пакеты не найдены в указанной папке" : "Укажите папку с моделями выше"}
            </p>
          ) : (
            <div className={selfStyles.pkgList}>
              {packages.map((pkg) => (
                <div key={pkg.id} className={[selfStyles.pkgRow, pkg.is_valid ? "" : selfStyles.pkgRowInvalid].join(" ")}>
                  <span className={selfStyles.pkgName}>{pkg.name}</span>
                  <span className={selfStyles.pkgType}>{pkg.model_type === "binary" ? "binary" : "multiclass"}</span>
                  <span className={selfStyles.pkgPreprocessor}>{pkg.preprocessor}</span>
                  {pkg.cascade_next && <span className={selfStyles.pkgCascade}>→ {pkg.cascade_next}</span>}
                  {!pkg.is_valid && <span className={selfStyles.pkgError}>{pkg.errors[0]}</span>}
                </div>
              ))}
            </div>
          )}

          {/* Add from folder */}
          <div style={{ marginTop: 10 }}>
            <div className={selfStyles.subBlockTitle} style={{ marginBottom: 4 }}>Добавить папку пакета</div>
            <div className={selfStyles.ipAddRow}>
              <input className={selfStyles.ipAddInput} type="text" value={addInput}
                placeholder="/path/to/my-model-package"
                onChange={(e) => setAddInput(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") void handleAdd(); }} />
              <button className={selfStyles.ipAddBtn} onClick={() => void handleAdd()}>Добавить</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function fmtTraffic(b: number): string {
  if (b >= 1_000_000_000) return `${(b / 1_000_000_000).toFixed(1)} GB`;
  if (b >= 1_000_000)     return `${(b / 1_000_000).toFixed(0)} MB`;
  if (b >= 1_000)         return `${(b / 1_000).toFixed(0)} KB`;
  return `${b} B`;
}

// ── Resource Monitor ──────────────────────────────────────────────────────────

function StatBar({ value, max, color }: { value: number; max: number; color: string }) {
  const pct = Math.min(100, (value / max) * 100);
  return (
    <div style={{ height: 5, borderRadius: 3, background: "var(--surface-3)", overflow: "hidden", flex: 1 }}>
      <div style={{ height: "100%", width: `${pct}%`, background: color, borderRadius: 3, transition: "width 0.5s" }} />
    </div>
  );
}

function ResourceMonitor() {
  const [stats, setStats] = useState<SystemStats | null>(null);

  useEffect(() => {
    const refresh = () => api.getSystemStats().then(setStats).catch(() => null);
    refresh();
    const iv = setInterval(refresh, 10000);
    return () => clearInterval(iv);
  }, []);

  if (!stats || !stats.available) return null;

  const cpuColor = (stats.cpu_percent ?? 0) > 80 ? "var(--danger)" : (stats.cpu_percent ?? 0) > 50 ? "var(--warn, #eab308)" : "var(--ok)";
  const ramColor = (stats.ram_percent ?? 0) > 85 ? "var(--danger)" : (stats.ram_percent ?? 0) > 65 ? "var(--warn, #eab308)" : "var(--ok)";
  const procCpuColor = (stats.process_cpu_percent ?? 0) > 30 ? "var(--warn, #eab308)" : "var(--accent)";

  return (
    <div className={selfStyles.group}>
      <div className={selfStyles.groupTitle}>Ресурсы сервера (обновляется каждые 10 сек)</div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px 24px", fontSize: 12 }}>
        {/* CPU system */}
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <div style={{ display: "flex", justifyContent: "space-between", color: "var(--text-secondary)" }}>
            <span>CPU системы</span>
            <span style={{ color: cpuColor, fontWeight: 600 }}>{stats.cpu_percent}%</span>
          </div>
          <StatBar value={stats.cpu_percent ?? 0} max={100} color={cpuColor} />
        </div>
        {/* RAM */}
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <div style={{ display: "flex", justifyContent: "space-between", color: "var(--text-secondary)" }}>
            <span>RAM ({stats.ram_used_mb} / {stats.ram_total_mb} MB)</span>
            <span style={{ color: ramColor, fontWeight: 600 }}>{stats.ram_percent}%</span>
          </div>
          <StatBar value={stats.ram_percent ?? 0} max={100} color={ramColor} />
        </div>
        {/* Process CPU */}
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <div style={{ display: "flex", justifyContent: "space-between", color: "var(--text-secondary)" }}>
            <span>AnomalyNet CPU</span>
            <span style={{ color: procCpuColor, fontWeight: 600 }}>{stats.process_cpu_percent}%</span>
          </div>
          <StatBar value={stats.process_cpu_percent ?? 0} max={100} color={procCpuColor} />
        </div>
        {/* Process RAM */}
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <div style={{ display: "flex", justifyContent: "space-between", color: "var(--text-secondary)" }}>
            <span>AnomalyNet RAM</span>
            <span style={{ color: "var(--accent)", fontWeight: 600 }}>{stats.process_ram_mb} MB</span>
          </div>
          <StatBar value={stats.process_ram_mb ?? 0} max={Math.max(500, stats.process_ram_mb ?? 0)} color="var(--accent)" />
        </div>
        {/* Network */}
        <div style={{ display: "flex", alignItems: "center", gap: 8, color: "var(--text-secondary)", gridColumn: "span 2" }}>
          <span>Сеть:</span>
          <span>↓ {stats.net_recv_kbps} KB/s</span>
          <span style={{ opacity: 0.4 }}>·</span>
          <span>↑ {stats.net_sent_kbps} KB/s</span>
        </div>
      </div>
    </div>
  );
}

// ── Platform Status Panel ─────────────────────────────────────────────────────

function StatusDot({ ok, na }: { ok: boolean; na?: boolean }) {
  const color = na ? "var(--text-muted)" : ok ? "var(--ok)" : "var(--danger)";
  return <span style={{ display: "inline-block", width: 8, height: 8, borderRadius: "50%", background: color, flexShrink: 0 }} />;
}

function PlatformStatusPanel({ caps }: { caps: PlatformCapabilities }) {
  const platformLabel = caps.platform === "windows" ? "Windows" : caps.platform === "linux" ? "Linux" : caps.platform;
  const rows: { label: string; ok: boolean; note?: string }[] = [
    { label: "Права администратора", ok: caps.current_elevated, note: caps.current_elevated ? "да" : "нет — перезапустите от имени администратора" },
    { label: "Захват пакетов", ok: caps.packet_capture, note: caps.capture_backend !== "mock" ? caps.capture_backend : "недоступен" },
    { label: "Блокировка IP", ok: caps.firewall_blocking, note: caps.firewall_backend !== "mock" ? caps.firewall_backend : "недоступна" },
    { label: "Откат правил (snapshot)", ok: caps.firewall_rollback, note: caps.firewall_rollback ? "доступен" : "нет" },
    { label: "ARP-сканирование", ok: caps.arp_scan, note: caps.arp_scan ? "доступно" : "нет" },
  ];
  return (
    <div className={selfStyles.group}>
      <div className={selfStyles.groupTitle}>
        Платформа: {platformLabel}
        {caps.platform === "windows" && <span style={{ marginLeft: 6, fontSize: 11, opacity: 0.55 }}>({caps.capture_backend} / {caps.firewall_backend})</span>}
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 6, fontSize: 12.5 }}>
        {rows.map((r) => (
          <div key={r.label} style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <StatusDot ok={r.ok} />
            <span style={{ color: "var(--text-secondary)", minWidth: 210 }}>{r.label}</span>
            <span style={{ color: r.ok ? "var(--text-primary)" : "var(--danger)", opacity: r.ok ? 0.75 : 1 }}>{r.note}</span>
          </div>
        ))}
      </div>
      {caps.warnings.length > 0 && (
        <div style={{ marginTop: 10, display: "flex", flexDirection: "column", gap: 4 }}>
          {caps.warnings.map((w, i) => (
            <div key={i} style={{ fontSize: 11.5, color: "var(--warning)", background: "rgba(var(--warning-rgb,255,165,0),0.08)", borderRadius: 6, padding: "5px 10px", lineHeight: 1.5 }}>
              ⚠ {w}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
