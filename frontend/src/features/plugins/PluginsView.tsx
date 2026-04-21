import { useEffect, useRef, useState } from "react";
import { useAppStore } from "../../app/store";
import type { ModelPreset } from "../../app/types";
import { api } from "../../lib/api";
import { usePluginsStore } from "../../store/pluginsStore";
import type { CreatePipelinePayload, StageConfig } from "../../types/plugins";
import styles from "./PluginsView.module.css";

type Tab = "presets" | "pipelines" | "plugins" | "files";

type PluginFile = { filename: string; size_bytes: number; is_example: boolean };

const ICONS: Record<string, string> = {
  binary:   "⚡",
  simple:   "🔍",
  cascade:  "🔀",
  advanced: "🧠",
};

export function PluginsView() {
  const settings    = useAppStore((s) => s.settings);
  const setSettings = useAppStore((s) => s.setSettings);

  const [tab, setTab]           = useState<Tab>("presets");
  const [presets, setPresets]   = useState<ModelPreset[]>([]);
  const [applying, setApplying] = useState<string | null>(null);
  const [showGuide, setShowGuide] = useState(false);
  const [reloadMsg, setReloadMsg] = useState("");
  const [creating, setCreating] = useState(false);

  // Files tab state
  const [pluginFiles, setPluginFiles] = useState<PluginFile[]>([]);
  const [filesLoading, setFilesLoading] = useState(false);
  const [uploadMsg, setUploadMsg] = useState("");
  const [uploadError, setUploadError] = useState("");
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [newPipeline, setNewPipeline] = useState<CreatePipelinePayload>({
    name: "", description: "", entry_stage: "stage1",
    stages: {
      stage1: { preprocessor_name: "", model_name: "", threshold: 0.70, is_gate: false, next_stage: null },
    },
  });

  const {
    preprocessors, models, pipelines, loading,
    fetchAll, deletePipeline, reloadPlugins,
  } = usePluginsStore();

  useEffect(() => {
    api.getModelPresets().then((r) => setPresets(r.presets)).catch(() => setPresets([]));
  }, []);

  useEffect(() => {
    if (tab === "presets" || tab === "pipelines" || tab === "plugins") fetchAll();
    if (tab === "files") loadFiles();
  }, [tab]);

  async function loadFiles() {
    setFilesLoading(true);
    try { setPluginFiles(await api.getPluginFiles()); }
    catch { setPluginFiles([]); }
    finally { setFilesLoading(false); }
  }

  async function handleUpload(file: File) {
    setUploadMsg(""); setUploadError("");
    try {
      const r = await api.uploadPluginFile(file);
      setUploadMsg(r.message);
      await loadFiles();
      await fetchAll();
      setTimeout(() => setUploadMsg(""), 5000);
    } catch (e) {
      setUploadError(String(e));
    }
  }

  async function handleDeleteFile(filename: string) {
    if (!confirm(`Удалить файл «${filename}»?`)) return;
    try {
      await api.deletePluginFile(filename);
      setPluginFiles((f) => f.filter((x) => x.filename !== filename));
    } catch (e) { alert(String(e)); }
  }

  function onDrop(e: React.DragEvent) {
    e.preventDefault(); setDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file) handleUpload(file);
  }

  const activePresetId = presets.find(
    (p) =>
      p.active_model_id === settings?.active_model_id &&
      p.detection_mode  === (settings?.detection_mode ?? "simple"),
  )?.id;

  async function handleApply(preset: ModelPreset) {
    setApplying(preset.id);
    try {
      const saved = await api.applyModelPreset(preset.id);
      setSettings(saved);
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
    if (!confirm(`Удалить pipeline «${name}»?`)) return;
    try { await deletePipeline(name); } catch (e) { alert(String(e)); }
  }

  const [activating, setActivating] = useState<string | null>(null);

  async function handleActivatePipeline(name: string) {
    if (!settings) return;
    setActivating(name);
    try {
      const saved = await api.activatePluginPipeline(name, settings);
      setSettings(saved);
    } finally {
      setActivating(null);
    }
  }

  const activePipelineName = settings?.active_model_id?.startsWith("plugin:")
    ? settings.active_model_id.slice("plugin:".length)
    : null;

  async function handleCreate() {
    try {
      await usePluginsStore.getState().createPipeline(newPipeline);
      setCreating(false);
      setNewPipeline({
        name: "", description: "", entry_stage: "stage1",
        stages: { stage1: { preprocessor_name: "", model_name: "", threshold: 0.70, is_gate: false, next_stage: null } },
      });
    } catch (e) { alert(String(e)); }
  }

  function updateStage(field: keyof StageConfig, value: string | number | boolean | null) {
    setNewPipeline((p) => ({ ...p, stages: { ...p.stages, stage1: { ...p.stages.stage1, [field]: value } } }));
  }

  return (
    <div className={styles.root}>
      {/* Tabs */}
      <div className={styles.tabs}>
        <button className={`${styles.tabBtn} ${tab === "presets"   ? styles.tabActive : ""}`} onClick={() => setTab("presets")}>Пресеты</button>
        <button className={`${styles.tabBtn} ${tab === "pipelines" ? styles.tabActive : ""}`} onClick={() => setTab("pipelines")}>Pipeline</button>
        <button className={`${styles.tabBtn} ${tab === "plugins"   ? styles.tabActive : ""}`} onClick={() => setTab("plugins")}>Плагины</button>
        <button className={`${styles.tabBtn} ${tab === "files"     ? styles.tabActive : ""}`} onClick={() => setTab("files")}>Файлы</button>
      </div>

      <div className={styles.tabContent}>

        {/* ── Пресеты ─────────────────────────────────────────── */}
        {tab === "presets" && (
          <div className={styles.presetGrid}>
            {presets.length === 0 && (
              <p style={{ opacity: 0.4, fontSize: 13 }}>Загрузка пресетов...</p>
            )}
            {presets.map((preset) => {
              const isActive   = preset.id === activePresetId;
              const isApplying = applying === preset.id;
              return (
                <div key={preset.id} className={`${styles.presetCard} ${isActive ? styles.active : ""}`}>
                  <div className={`${styles.presetIcon} ${styles[`icon-${preset.icon}`] ?? ""}`}>
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

        {/* ── Pipeline ─────────────────────────────────────────── */}
        {tab === "pipelines" && (
          <div>
            <div className={styles.toolbar}>
              <button className={styles.btnOutline} onClick={handleReload}>⟳ Reload plugins</button>
              <button className={styles.btnAccent} onClick={() => setCreating((v) => !v)}>
                {creating ? "Отмена" : "+ Создать pipeline"}
              </button>
              {reloadMsg && <span className={styles.reloadMsg}>{reloadMsg}</span>}
            </div>

            {creating && (
              <div className={styles.createForm}>
                <p className={styles.createFormTitle}>Новый pipeline</p>
                <div className={styles.formRow}>
                  <label>Имя</label>
                  <input className={styles.formInput} value={newPipeline.name} placeholder="my_pipeline"
                    onChange={(e) => setNewPipeline((p) => ({ ...p, name: e.target.value }))} />
                </div>
                <div className={styles.formRow}>
                  <label>Описание</label>
                  <input className={styles.formInput} value={newPipeline.description} placeholder="..."
                    onChange={(e) => setNewPipeline((p) => ({ ...p, description: e.target.value }))} />
                </div>
                <p className={styles.stageHeader}>Стадия stage1</p>
                <div className={styles.formRow}>
                  <label>Препроцессор</label>
                  <select className={styles.formInput} value={newPipeline.stages.stage1.preprocessor_name}
                    onChange={(e) => updateStage("preprocessor_name", e.target.value)}>
                    <option value="">— выбрать —</option>
                    {preprocessors.map((p) => <option key={p.name} value={p.name}>{p.name} ({p.output_schema_id})</option>)}
                  </select>
                </div>
                <div className={styles.formRow}>
                  <label>Модель</label>
                  <select className={styles.formInput} value={newPipeline.stages.stage1.model_name}
                    onChange={(e) => updateStage("model_name", e.target.value)}>
                    <option value="">— выбрать —</option>
                    {models.map((m) => <option key={m.name} value={m.name}>{m.name} ({m.accepted_schema_ids.join(",")})</option>)}
                  </select>
                </div>
                <div className={styles.formRow}>
                  <label>Порог</label>
                  <input className={styles.formInput} type="number" min={0} max={1} step={0.05}
                    value={newPipeline.stages.stage1.threshold}
                    onChange={(e) => updateStage("threshold", parseFloat(e.target.value))} />
                </div>
                <button className={styles.applyBtn} onClick={handleCreate}>Создать</button>
              </div>
            )}

            {loading && <p style={{ opacity: 0.4, fontSize: 13 }}>Загрузка...</p>}

            <div className={styles.pipelineList}>
              {pipelines.map((cfg) => {
                const isActive = activePipelineName === cfg.name;
                return (
                <div key={cfg.name} className={`${styles.pipelineCard} ${isActive ? styles.pipelineCardActive : ""}`}>
                  <div className={styles.pipelineCardHeader}>
                    <span className={styles.pipelineName}>{cfg.name}</span>
                    {isActive && <span className={styles.activeBadge}>Активен</span>}
                    {cfg.is_builtin && !isActive && <span className={styles.builtinBadge}>builtin</span>}
                    {!cfg.is_builtin && (
                      <button className={styles.deleteBtn} onClick={() => handleDeletePipeline(cfg.name)}>Удалить</button>
                    )}
                  </div>
                  <p className={styles.pipelineDesc}>{cfg.description}</p>
                  <div className={styles.stageList}>
                    {Object.entries(cfg.stages).map(([sname, s]) => (
                      <span key={sname} className={styles.stagePill}>
                        {sname}: {s.preprocessor_name} → {s.model_name}{s.is_gate ? " [gate]" : ""}
                      </span>
                    ))}
                  </div>
                  {!isActive && (
                    <button
                      className={styles.applyBtn}
                      style={{ marginTop: 10 }}
                      disabled={activating === cfg.name}
                      onClick={() => handleActivatePipeline(cfg.name)}
                    >
                      {activating === cfg.name ? "Активируется..." : "Активировать"}
                    </button>
                  )}
                </div>
              );})}
            </div>

            {!loading && pipelines.length === 0 && (
              <p className={styles.emptyNote}>
                Нет зарегистрированных pipeline.<br/>
                Задайте пути к моделям в Настройках для активации builtin пресетов.
              </p>
            )}

            <div className={styles.guideSection}>
              <button className={styles.guideToggle} onClick={() => setShowGuide((v) => !v)}>
                {showGuide ? "▾" : "▸"} Документация плагинов
              </button>
              {showGuide && (
                <div className={styles.guideContent}>
                  Положи <code>.py</code> файл в папку <code>plugins/</code> (в корне приложения).<br/>
                  Класс унаследуй от <code>BasePreprocessor</code> или <code>BaseModel</code> из <code>app.plugins</code>.<br/>
                  После сохранения нажми <strong>Reload plugins</strong> или перезапусти сервис.<br/><br/>
                  Примеры: <code>plugins/example_preprocessor.py</code>, <code>plugins/example_model.py</code><br/>
                  Полная документация: <code>plugins/PLUGIN_GUIDE.md</code><br/><br/>
                  API:<br/>
                  <code>GET  /api/plugins/preprocessors</code> — список препроцессоров<br/>
                  <code>GET  /api/plugins/models</code> — список моделей<br/>
                  <code>POST /api/plugins/pipelines</code> — создать pipeline<br/>
                  <code>POST /api/plugins/reload</code> — перезагрузить папку plugins/
                </div>
              )}
            </div>
          </div>
        )}

        {/* ── Плагины ─────────────────────────────────────────── */}
        {tab === "plugins" && (
          <div>
            <p className={styles.sectionTitle}>Препроцессоры ({preprocessors.length})</p>
            {preprocessors.length === 0 && !loading && (
              <p className={styles.emptyNote}>Нет зарегистрированных препроцессоров</p>
            )}
            <div className={styles.pluginGrid}>
              {preprocessors.map((p) => (
                <div key={p.name} className={styles.pluginCard}>
                  <div className={styles.pluginCardHeader}>
                    <span className={styles.pluginName}>{p.name}</span>
                    <span className={styles.pluginSchema}>{p.output_schema_id}</span>
                    {p.is_builtin && <span className={styles.pluginBuiltinBadge}>builtin</span>}
                  </div>
                  <p className={styles.pluginDesc}>{p.description}</p>
                  <span className={styles.pluginMeta}>{p.feature_count} признаков · v{p.version}</span>
                </div>
              ))}
            </div>

            <p className={styles.sectionTitle}>Модели ({models.length})</p>
            {models.length === 0 && !loading && (
              <p className={styles.emptyNote}>Нет зарегистрированных моделей</p>
            )}
            <div className={styles.pluginGrid}>
              {models.map((m) => (
                <div key={m.name} className={styles.pluginCard}>
                  <div className={styles.pluginCardHeader}>
                    <span className={styles.pluginName}>{m.name}</span>
                    <span className={styles.pluginSchema}>{m.accepted_schema_ids.join(", ")}</span>
                    {m.is_builtin && <span className={styles.pluginBuiltinBadge}>builtin</span>}
                  </div>
                  <p className={styles.pluginDesc}>{m.description}</p>
                  <span className={styles.pluginMeta}>{m.output_classes.join(" · ")} · v{m.version}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* ── Файлы ─────────────────────────────────────────── */}
        {tab === "files" && (
          <div>
            <div
              className={`${styles.dropZone} ${dragOver ? styles.dropZoneOver : ""}`}
              onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
              onDragLeave={() => setDragOver(false)}
              onDrop={onDrop}
              onClick={() => fileInputRef.current?.click()}
            >
              <div className={styles.dropIcon}>📦</div>
              <p className={styles.dropText}>Перетащи <code>.py</code> файл сюда или нажми для выбора</p>
              <p className={styles.dropSub}>Файл сохранится в <code>plugins/</code> и загрузится автоматически</p>
              <input
                ref={fileInputRef}
                type="file"
                accept=".py"
                style={{ display: "none" }}
                onChange={(e) => { const f = e.target.files?.[0]; if (f) handleUpload(f); e.target.value = ""; }}
              />
            </div>

            {uploadMsg   && <p className={styles.uploadOk}>✓ {uploadMsg}</p>}
            {uploadError && <p className={styles.uploadErr}>✗ {uploadError}</p>}

            <div className={styles.fileList}>
              {filesLoading && <p style={{ opacity: 0.4, fontSize: 13 }}>Загрузка...</p>}
              {!filesLoading && pluginFiles.length === 0 && (
                <p className={styles.emptyNote}>Нет загруженных файлов плагинов</p>
              )}
              {pluginFiles.map((f) => (
                <div key={f.filename} className={styles.fileRow}>
                  <span className={styles.fileIcon}>🐍</span>
                  <span className={styles.fileName}>{f.filename}</span>
                  <span className={styles.fileSize}>{(f.size_bytes / 1024).toFixed(1)} KB</span>
                  {f.is_example && <span className={styles.exampleBadge}>example</span>}
                  <button
                    className={styles.fileDeleteBtn}
                    onClick={() => handleDeleteFile(f.filename)}
                    disabled={f.is_example}
                    title={f.is_example ? "Пример нельзя удалить" : "Удалить файл"}
                  >✕</button>
                </div>
              ))}
            </div>

            <p className={styles.fileHint}>
              После загрузки плагины регистрируются автоматически.<br/>
              Если что-то пошло не так — перейди на таб <strong>Pipeline</strong> и нажми <strong>Reload plugins</strong>.
            </p>
          </div>
        )}

      </div>
    </div>
  );
}
