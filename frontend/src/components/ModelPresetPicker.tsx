import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { useAppStore } from "../app/store";
import type { ModelPreset } from "../app/types";
import { api } from "../lib/api";
import { usePluginsStore } from "../store/pluginsStore";
import type { CreatePipelinePayload, StageConfig } from "../types/plugins";
import styles from "./ModelPresetPicker.module.css";

const ICONS: Record<string, string> = {
  binary:   "⚡",
  simple:   "🔍",
  cascade:  "🔀",
  advanced: "🧠",
};

type Tab = "presets" | "pipelines" | "plugins";

export function ModelPresetPicker({ compact = false }: { compact?: boolean }) {
  const settings    = useAppStore((s) => s.settings);
  const setSettings = useAppStore((s) => s.setSettings);

  const [open, setOpen]       = useState(false);
  const [tab, setTab]         = useState<Tab>("presets");
  const [presets, setPresets] = useState<ModelPreset[]>([]);
  const [applying, setApplying] = useState<string | null>(null);
  const [showGuide, setShowGuide] = useState(false);

  const {
    preprocessors, models, pipelines,
    loading: pluginsLoading,
    fetchAll, deletePipeline, reloadPlugins,
  } = usePluginsStore();

  const [reloadMsg, setReloadMsg] = useState("");
  const [creating, setCreating] = useState(false);
  const [newPipeline, setNewPipeline] = useState<CreatePipelinePayload>({
    name: "", description: "", entry_stage: "stage1",
    stages: {
      stage1: { preprocessor_name: "", model_name: "", threshold: 0.70, is_gate: false, next_stage: null },
    },
  });

  useEffect(() => {
    api.getModelPresets()
      .then((r) => setPresets(r.presets))
      .catch(() => setPresets([]));
  }, []);

  useEffect(() => {
    if (open && tab !== "presets") {
      fetchAll();
    }
  }, [open, tab]);

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

  async function handleReload() {
    try {
      const r = await reloadPlugins();
      setReloadMsg(r.message);
      setTimeout(() => setReloadMsg(""), 4000);
    } catch (e) {
      setReloadMsg(String(e));
    }
  }

  async function handleDeletePipeline(name: string) {
    try {
      await deletePipeline(name);
    } catch (e) {
      alert(String(e));
    }
  }

  const [activating, setActivating] = useState<string | null>(null);

  async function handleActivatePipeline(name: string) {
    if (!settings) return;
    setActivating(name);
    try {
      const saved = await api.activatePluginPipeline(name, settings);
      setSettings(saved);
      setOpen(false);
    } finally {
      setActivating(null);
    }
  }

  const activePipelineName = settings?.active_model_id?.startsWith("plugin:")
    ? settings.active_model_id.slice("plugin:".length)
    : null;

  async function handleCreatePipeline() {
    try {
      await usePluginsStore.getState().createPipeline(newPipeline);
      setCreating(false);
      setNewPipeline({
        name: "", description: "", entry_stage: "stage1",
        stages: {
          stage1: { preprocessor_name: "", model_name: "", threshold: 0.70, is_gate: false, next_stage: null },
        },
      });
    } catch (e) {
      alert(String(e));
    }
  }

  function updateStage(stageName: string, field: keyof StageConfig, value: string | number | boolean | null) {
    setNewPipeline((p) => ({
      ...p,
      stages: {
        ...p.stages,
        [stageName]: { ...p.stages[stageName], [field]: value },
      },
    }));
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
            <path d="M12 2L2 7l10 5 10-5-10-5z" />
            <path d="M2 17l10 5 10-5" />
            <path d="M2 12l10 5 10-5" />
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
                  Готовые пресеты или пользовательские plugin-пайплайны
                </p>
              </div>
              <button className={styles.closeBtn} onClick={() => setOpen(false)}>×</button>
            </div>

            {/* Tabs */}
            <div className={styles.tabs}>
              <button className={`${styles.tabBtn} ${tab === "presets"   ? styles.tabActive : ""}`} onClick={() => setTab("presets")}>Пресеты</button>
              <button className={`${styles.tabBtn} ${tab === "pipelines" ? styles.tabActive : ""}`} onClick={() => setTab("pipelines")}>Pipeline</button>
              <button className={`${styles.tabBtn} ${tab === "plugins"   ? styles.tabActive : ""}`} onClick={() => setTab("plugins")}>Плагины</button>
            </div>

            {/* Tab: Presets */}
            {tab === "presets" && (
              <div className={styles.presetList}>
                {presets.length === 0 && (
                  <p style={{ opacity: 0.5, textAlign: "center", padding: "24px 0" }}>Загрузка...</p>
                )}
                {presets.map((preset) => {
                  const isActive   = preset.id === activePresetId;
                  const isApplying = applying === preset.id;
                  return (
                    <div key={preset.id} className={`${styles.presetCard} ${isActive ? styles.active : ""}`}>
                      <div className={`${styles.presetIcon} ${styles[`icon-${preset.icon}`]}`}>
                        {ICONS[preset.icon] ?? "📦"}
                      </div>
                      <div className={styles.presetBody}>
                        <p className={styles.presetName}>{preset.name}</p>
                        <p className={styles.presetDesc}>{preset.description}</p>
                        {!isActive && (
                          <button className={styles.applyBtn} disabled={isApplying} onClick={() => handleApply(preset)}>
                            {isApplying ? "Применяется..." : "Применить"}
                          </button>
                        )}
                      </div>
                      {isActive && <span className={styles.activeBadge}>Активна</span>}
                    </div>
                  );
                })}
              </div>
            )}

            {/* Tab: Pipelines */}
            {tab === "pipelines" && (
              <div>
                <div className={styles.tabToolbar}>
                  <button className={styles.smallBtn} onClick={handleReload}>⟳ Reload plugins</button>
                  <button className={styles.smallBtnAccent} onClick={() => setCreating((v) => !v)}>
                    {creating ? "Отмена" : "+ Создать"}
                  </button>
                  {reloadMsg && <span className={styles.reloadMsg}>{reloadMsg}</span>}
                </div>

                {/* Create form */}
                {creating && (
                  <div className={styles.createForm}>
                    <h4 className={styles.createTitle}>Новый pipeline</h4>
                    <div className={styles.formRow}>
                      <label>Имя</label>
                      <input value={newPipeline.name} onChange={(e) => setNewPipeline((p) => ({ ...p, name: e.target.value }))} placeholder="my_pipeline" className={styles.formInput} />
                    </div>
                    <div className={styles.formRow}>
                      <label>Описание</label>
                      <input value={newPipeline.description} onChange={(e) => setNewPipeline((p) => ({ ...p, description: e.target.value }))} placeholder="..." className={styles.formInput} />
                    </div>
                    <h5 className={styles.stageTitle}>Стадия stage1</h5>
                    <div className={styles.formRow}>
                      <label>Препроцессор</label>
                      <select value={newPipeline.stages.stage1.preprocessor_name} onChange={(e) => updateStage("stage1", "preprocessor_name", e.target.value)} className={styles.formInput}>
                        <option value="">— выбрать —</option>
                        {preprocessors.map((p) => <option key={p.name} value={p.name}>{p.name}</option>)}
                      </select>
                    </div>
                    <div className={styles.formRow}>
                      <label>Модель</label>
                      <select value={newPipeline.stages.stage1.model_name} onChange={(e) => updateStage("stage1", "model_name", e.target.value)} className={styles.formInput}>
                        <option value="">— выбрать —</option>
                        {models.map((m) => <option key={m.name} value={m.name}>{m.name}</option>)}
                      </select>
                    </div>
                    <div className={styles.formRow}>
                      <label>Порог</label>
                      <input type="number" min={0} max={1} step={0.05} value={newPipeline.stages.stage1.threshold} onChange={(e) => updateStage("stage1", "threshold", parseFloat(e.target.value))} className={styles.formInput} />
                    </div>
                    <button className={styles.applyBtn} onClick={handleCreatePipeline}>Создать</button>
                  </div>
                )}

                {/* Pipeline list — hide auto-generated dyn_* entries (they duplicate named presets) */}
                {pluginsLoading && <p style={{ opacity: 0.5, padding: "16px 0" }}>Загрузка...</p>}
                {pipelines.filter((cfg) => !cfg.name.startsWith("dyn_")).map((cfg) => {
                  const isActive = activePipelineName === cfg.name;
                  return (
                  <div key={cfg.name} className={`${styles.pipelineCard} ${isActive ? styles.pipelineCardActive : ""}`}>
                    <div className={styles.pipelineHeader}>
                      <span className={styles.pipelineName}>{cfg.name}</span>
                      {isActive && <span className={styles.activeBadge}>Активен</span>}
                      {cfg.is_builtin && !isActive && <span className={styles.builtinBadge}>builtin</span>}
                      {!cfg.is_builtin && (
                        <button className={styles.deleteBtn} onClick={() => handleDeletePipeline(cfg.name)}>Удалить</button>
                      )}
                    </div>
                    <p className={styles.pipelineDesc}>{cfg.description}</p>
                    <div className={styles.stageList}>
                      {Object.entries(cfg.stages).map(([sName, s]) => (
                        <span key={sName} className={styles.stagePill}>
                          {sName}: {s.preprocessor_name} → {s.model_name}
                          {s.is_gate ? " [gate]" : ""}
                        </span>
                      ))}
                    </div>
                    {!isActive && (
                      <button
                        className={styles.applyBtn}
                        style={{ marginTop: 8 }}
                        disabled={activating === cfg.name}
                        onClick={() => handleActivatePipeline(cfg.name)}
                      >
                        {activating === cfg.name ? "Активируется..." : "Активировать"}
                      </button>
                    )}
                  </div>
                );})}
                {!pluginsLoading && pipelines.filter((cfg) => !cfg.name.startsWith("dyn_")).length === 0 && (
                  <p style={{ opacity: 0.5, textAlign: "center", padding: "20px 0", fontSize: 12 }}>
                    Нет пользовательских pipeline.<br/>
                    Создайте новый выше или используйте вкладку «Пресеты» для встроенных моделей.
                  </p>
                )}

                {/* Guide accordion */}
                <div className={styles.guideSection}>
                  <button className={styles.guideToggle} onClick={() => setShowGuide((v) => !v)}>
                    {showGuide ? "▾" : "▸"} Документация плагинов (PLUGIN_GUIDE.md)
                  </button>
                  {showGuide && (
                    <div className={styles.guideContent}>
                      Документация находится в файле <code>plugins/PLUGIN_GUIDE.md</code>.<br/>
                      Примеры плагинов: <code>plugins/example_preprocessor.py</code> и <code>plugins/example_model.py</code>.<br/><br/>
                      API:<br/>
                      <code>GET /api/plugins/preprocessors</code> — препроцессоры<br/>
                      <code>GET /api/plugins/models</code> — модели<br/>
                      <code>GET /api/plugins/pipelines</code> — пайплайны<br/>
                      <code>POST /api/plugins/reload</code> — перезагрузить плагины из папки
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Tab: Plugins */}
            {tab === "plugins" && (
              <div>
                <h4 className={styles.sectionTitle}>Препроцессоры ({preprocessors.length})</h4>
                {preprocessors.length === 0 && !pluginsLoading && (
                  <p className={styles.emptyNote}>Нет зарегистрированных препроцессоров</p>
                )}
                {preprocessors.map((p) => (
                  <div key={p.name} className={styles.pluginCard}>
                    <div className={styles.pluginCardHeader}>
                      <span className={styles.pluginName}>{p.name}</span>
                      <span className={styles.pluginSchema}>{p.output_schema_id}</span>
                      {p.is_builtin && <span className={styles.builtinBadge}>builtin</span>}
                    </div>
                    <p className={styles.pluginDesc}>{p.description}</p>
                    <span className={styles.pluginMeta}>{p.feature_count} признаков · v{p.version}</span>
                  </div>
                ))}

                <h4 className={styles.sectionTitle} style={{ marginTop: 18 }}>Модели ({models.length})</h4>
                {models.length === 0 && !pluginsLoading && (
                  <p className={styles.emptyNote}>Нет зарегистрированных моделей</p>
                )}
                {models.map((m) => (
                  <div key={m.name} className={styles.pluginCard}>
                    <div className={styles.pluginCardHeader}>
                      <span className={styles.pluginName}>{m.name}</span>
                      <span className={styles.pluginSchema}>{m.accepted_schema_ids.join(", ")}</span>
                      {m.is_builtin && <span className={styles.builtinBadge}>builtin</span>}
                    </div>
                    <p className={styles.pluginDesc}>{m.description}</p>
                    <span className={styles.pluginMeta}>{m.output_classes.join(" · ")} · v{m.version}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>,
        document.body
      )}
    </>
  );
}
