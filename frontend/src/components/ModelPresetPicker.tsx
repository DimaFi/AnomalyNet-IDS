import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { useAppStore } from "../app/store";
import type { ModelPreset } from "../app/types";
import { api } from "../lib/api";
import styles from "./ModelPresetPicker.module.css";

const ICONS: Record<string, string> = {
  binary:   "⚡",
  simple:   "🔍",
  cascade:  "🔀",
  advanced: "🧠",
};

export function ModelPresetPicker({ compact = false }: { compact?: boolean }) {
  const settings    = useAppStore((s) => s.settings);
  const setSettings = useAppStore((s) => s.setSettings);

  const [open, setOpen]       = useState(false);
  const [presets, setPresets] = useState<ModelPreset[]>([]);
  const [applying, setApplying] = useState<string | null>(null);

  // Pre-fetch presets on mount so dialog opens instantly
  useEffect(() => {
    api.getModelPresets()
      .then((r) => setPresets(r.presets))
      .catch(() => setPresets([]));
  }, []);

  async function handleApply(preset: ModelPreset) {
    setApplying(preset.id);
    try {
      const saved = await api.applyModelPreset(preset.id);
      setSettings(saved);
      setOpen(false);
    } catch {
      // ignore
    } finally {
      setApplying(null);
    }
  }

  const activePresetId = presets.find(
    (p) =>
      p.active_model_id === settings?.active_model_id &&
      p.detection_mode  === (settings?.detection_mode ?? "simple")
  )?.id;

  return (
    <>
      <button
        className={compact ? styles.triggerCompact : styles.trigger}
        onClick={() => setOpen(true)}
        title="Выбрать конфигурацию модели"
      >
        {compact ? (
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="3" />
            <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
          </svg>
        ) : (
          <>
            <span>🎛</span>
            Выбрать модель
          </>
        )}
      </button>

      {open && createPortal(
        <div className={styles.overlay} onClick={(e) => e.target === e.currentTarget && setOpen(false)}>
          <div className={styles.dialog}>
            <div className={styles.dialogHeader}>
              <div>
                <h3 className={styles.dialogTitle}>Конфигурации модели</h3>
                <p className={styles.dialogSub}>
                  Выберите готовую конфигурацию — все пути и параметры установятся автоматически
                </p>
              </div>
              <button className={styles.closeBtn} onClick={() => setOpen(false)}>×</button>
            </div>

            <div className={styles.presetList}>
              {presets.length === 0 && (
                <p style={{ opacity: 0.5, textAlign: "center", padding: "24px 0" }}>
                  Загрузка пресетов...
                </p>
              )}
              {presets.map((preset) => {
                const isActive = preset.id === activePresetId;
                const isApplying = applying === preset.id;

                return (
                  <div
                    key={preset.id}
                    className={`${styles.presetCard} ${isActive ? styles.active : ""}`}
                  >
                    <div className={`${styles.presetIcon} ${styles[`icon-${preset.icon}`]}`}>
                      {ICONS[preset.icon] ?? "📦"}
                    </div>
                    <div className={styles.presetBody}>
                      <p className={styles.presetName}>{preset.name}</p>
                      <p className={styles.presetDesc}>{preset.description}</p>
                      {!isActive && (
                        <button
                          className={styles.applyBtn}
                          disabled={isApplying}
                          onClick={() => handleApply(preset)}
                        >
                          {isApplying ? "Применяется..." : "Применить"}
                        </button>
                      )}
                    </div>
                    {isActive && (
                      <span className={styles.activeBadge}>Активна</span>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        </div>,
        document.body
      )}
    </>
  );
}
