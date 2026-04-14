import { useEffect, useState } from "react";
import { useAppStore } from "../app/store";
import type { ModelPreset } from "../app/types";
import { api } from "../lib/api";
import styles from "./ModelPresetPicker.module.css";

const ICONS: Record<string, string> = {
  demo:     "🎭",
  binary:   "⚡",
  simple:   "🔍",
  advanced: "🧠",
};

export function ModelPresetPicker() {
  const settings    = useAppStore((s) => s.settings);
  const setSettings = useAppStore((s) => s.setSettings);

  const [open, setOpen]       = useState(false);
  const [presets, setPresets] = useState<ModelPreset[]>([]);
  const [applying, setApplying] = useState<string | null>(null);

  useEffect(() => {
    if (open && presets.length === 0) {
      api.getModelPresets()
        .then((r) => setPresets(r.presets))
        .catch(() => setPresets([]));
    }
  }, [open]);

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
      <button className={styles.trigger} onClick={() => setOpen(true)}>
        <span>🎛</span>
        Выбрать модель
      </button>

      {open && (
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
        </div>
      )}
    </>
  );
}
