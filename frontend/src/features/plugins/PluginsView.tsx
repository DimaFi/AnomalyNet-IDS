import { useEffect, useRef, useState } from "react";
import { useAppStore } from "../../app/store";
import type { ModelPreset } from "../../app/types";
import { api } from "../../lib/api";
import { usePluginsStore } from "../../store/pluginsStore";
import type { CreatePipelinePayload, StageConfig, ValidateResponse } from "../../types/plugins";
import styles from "./PluginsView.module.css";

type Tab = "presets" | "pipelines" | "plugins" | "files" | "test";

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

  // Test tab state
  type TestResult = Awaited<ReturnType<typeof api.testPluginPipeline>>;
  const [testPipeline,    setTestPipeline]    = useState<string>("");
  const [testRunning,     setTestRunning]     = useState<"validate" | "synthetic" | null>(null);
  const [validateResult,  setValidateResult]  = useState<ValidateResponse | null>(null);
  const [syntheticResult, setSyntheticResult] = useState<TestResult | null>(null);

  async function runValidate() {
    if (!testPipeline) return;
    setTestRunning("validate");
    setValidateResult(null);
    try {
      const r = await api.validatePluginPipeline(testPipeline);
      setValidateResult(r);
    } catch (e) {
      setValidateResult({ valid: false, errors: [String(e)] });
    } finally {
      setTestRunning(null);
    }
  }

  async function runSynthetic() {
    if (!testPipeline) return;
    setTestRunning("synthetic");
    setSyntheticResult(null);
    try {
      const r = await api.testPluginPipeline(testPipeline);
      setSyntheticResult(r);
    } catch (e) {
      setSyntheticResult({
        pipeline: testPipeline, ok: false, stages_run: 0,
        trace: [{ stage: "—", preprocessor: "—", model: "—", is_gate: false,
                  ok: false, error: String(e) }],
        final_verdict: null, final_score: null, note: "",
      });
    } finally {
      setTestRunning(null);
    }
  }

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
        <button className={`${styles.tabBtn} ${tab === "test"      ? styles.tabActive : ""}`} onClick={() => setTab("test")}>🧪 Тест</button>
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
            <div className={styles.pluginSummary}>
              <p className={styles.pluginSummaryTitle}>Как работает система плагинов</p>
              <div className={styles.pluginSummaryGrid}>
                <div className={styles.pluginSummaryCard}>
                  <div className={styles.pluginSummaryIcon}>1</div>
                  <div>
                    <strong>Препроцессор</strong> получает сырое событие с атрибутами
                    <code>.raw_features</code> (71 признак), <code>.protocol</code>,
                    <code>.src_ip</code>, <code>.byte_count</code> и т.д.
                    Возвращает вектор признаков (<code>PluginFeatureVector</code>).
                  </div>
                </div>
                <div className={styles.pluginSummaryCard}>
                  <div className={styles.pluginSummaryIcon}>2</div>
                  <div>
                    <strong>Модель</strong> получает вектор признаков и возвращает
                    вердикт: <code>normal / warning / anomaly</code>, оценку 0–1
                    и тип атаки (<code>DoS, DDoS</code> и т.д.).
                  </div>
                </div>
                <div className={styles.pluginSummaryCard}>
                  <div className={styles.pluginSummaryIcon}>3</div>
                  <div>
                    <strong>Pipeline</strong> связывает препроцессор + модель.
                    Многоступенчатые каскады: Stage1 как gate
                    (пропускает нормальный трафик), Stage2/3 определяет тип атаки.
                  </div>
                </div>
                <div className={styles.pluginSummaryCard}>
                  <div className={styles.pluginSummaryIcon}>4</div>
                  <div>
                    <strong>Активация</strong>: в табе <strong>Pipeline</strong> нажми
                    «Активировать» — сервис начнёт использовать этот pipeline
                    для анализа трафика вместо стандартного.
                  </div>
                </div>
              </div>
              <div className={styles.pluginSummaryHint}>
                <strong>Как написать свою модель:</strong> загрузи <code>.py</code> файл
                в таб «Файлы». Наследуй от <code>BaseModel</code>, реализуй
                <code>predict(features: PluginFeatureVector) → PluginVerdict</code>.
                Если хочешь использовать 71 CICFlowMeter признак — укажи
                <code>get_accepted_schema_ids() → ["cicflowmeter_71"]</code> и создай
                pipeline с препроцессором <code>cicflowmeter_71</code>.
                Примеры: <code>plugins/example_model.py</code>, <code>plugins/example_preprocessor.py</code>.
              </div>
            </div>

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
              Можно загружать как <strong>модели</strong>, так и <strong>препроцессоры признаков</strong> — любой класс,
              унаследованный от <code>BaseModel</code> или <code>BasePreprocessor</code>, регистрируется автоматически.<br/>
              После загрузки перейди в таб <strong>Плагины</strong> — новый плагин появится в списке.<br/>
              Затем в табе <strong>Pipeline</strong> создай pipeline (препроцессор + модель) и нажми <strong>Активировать</strong>.<br/>
              Если что-то пошло не так — нажми <strong>Reload plugins</strong> в табе Pipeline.
            </p>
          </div>
        )}

        {/* ── Тест ─────────────────────────────────────────── */}
        {tab === "test" && (
          <div className={styles.testTab}>

            {/* Pipeline selector */}
            <div className={styles.testSelector}>
              <label className={styles.testSelectorLabel}>Pipeline для тестирования:</label>
              <select
                className={styles.testSelect}
                value={testPipeline}
                onChange={(e) => { setTestPipeline(e.target.value); setValidateResult(null); setSyntheticResult(null); }}
              >
                <option value="">— выберите pipeline —</option>
                {pipelines.map((p) => (
                  <option key={p.name} value={p.name}>
                    {p.name}{p.is_builtin ? " (builtin)" : ""}
                  </option>
                ))}
              </select>
              {!testPipeline && pipelines.length === 0 && (
                <p className={styles.testHintSmall}>Нет доступных pipeline. Проверьте пути к моделям в Настройках.</p>
              )}
            </div>

            {/* Test actions */}
            <div className={styles.testActions}>
              <div className={styles.testCheck}>
                <div className={styles.testCheckHeader}>
                  <span className={styles.testCheckNum}>1</span>
                  <div>
                    <strong>Валидация конфигурации</strong>
                    <p>Проверяет что все препроцессоры и модели pipeline зарегистрированы корректно.</p>
                  </div>
                </div>
                <button
                  className={styles.testRunBtn}
                  disabled={!testPipeline || testRunning !== null}
                  onClick={() => void runValidate()}
                >
                  {testRunning === "validate" ? <><span className={styles.testSpinner} /> Проверяем...</> : "Запустить"}
                </button>
                {validateResult && (
                  <div className={`${styles.testResult} ${validateResult.valid ? styles.testResultOk : styles.testResultErr}`}>
                    <span className={styles.testResultIcon}>{validateResult.valid ? "✓" : "✗"}</span>
                    <div>
                      <strong>{validateResult.valid ? "Конфигурация корректна" : "Обнаружены ошибки"}</strong>
                      {validateResult.errors.length > 0 && (
                        <ul className={styles.testErrorList}>
                          {validateResult.errors.map((e, i) => <li key={i}>{e}</li>)}
                        </ul>
                      )}
                    </div>
                  </div>
                )}
              </div>

              <div className={styles.testCheck}>
                <div className={styles.testCheckHeader}>
                  <span className={styles.testCheckNum}>2</span>
                  <div>
                    <strong>Синтетический прогон (нулевые признаки)</strong>
                    <p>
                      Создаёт тестовое событие с нулевыми значениями всех признаков и прогоняет через все стадии pipeline.
                      Показывает пошаговую трассировку: какой препроцессор, сколько признаков, какой вердикт.
                      Не отражает реальную детекцию — проверяет что плагин подключён и данные проходят.
                    </p>
                  </div>
                </div>
                <button
                  className={styles.testRunBtn}
                  disabled={!testPipeline || testRunning !== null}
                  onClick={() => void runSynthetic()}
                >
                  {testRunning === "synthetic" ? <><span className={styles.testSpinner} /> Тестируем...</> : "Запустить"}
                </button>
                {syntheticResult && (
                  <div className={styles.testTraceWrap}>
                    <div className={`${styles.testResult} ${syntheticResult.ok ? styles.testResultOk : styles.testResultErr}`}>
                      <span className={styles.testResultIcon}>{syntheticResult.ok ? "✓" : "✗"}</span>
                      <div>
                        <strong>
                          {syntheticResult.ok ? "Все стадии пройдены" : "Ошибка в одной из стадий"}
                        </strong>
                        {" — "}стадий выполнено: {syntheticResult.stages_run}
                        {syntheticResult.final_verdict && (
                          <span className={styles.testFinalVerdict} data-verdict={syntheticResult.final_verdict}>
                            Итог: {syntheticResult.final_verdict}
                            {syntheticResult.final_score !== null && ` (${(syntheticResult.final_score * 100).toFixed(1)}%)`}
                          </span>
                        )}
                      </div>
                    </div>

                    <table className={styles.traceTable}>
                      <thead>
                        <tr>
                          <th>Стадия</th>
                          <th>Препроцессор</th>
                          <th>Модель</th>
                          <th>Gate</th>
                          <th>Признаков</th>
                          <th>Schema</th>
                          <th>Вердикт</th>
                          <th>Score</th>
                          <th>Тип атаки</th>
                          <th>Ошибка / причина</th>
                        </tr>
                      </thead>
                      <tbody>
                        {syntheticResult.trace.map((row, i) => (
                          <tr key={i} className={row.ok ? styles.traceRowOk : styles.traceRowErr}>
                            <td><code>{row.stage}</code></td>
                            <td><code>{row.preprocessor}</code></td>
                            <td><code>{row.model}</code></td>
                            <td>{row.is_gate ? "да" : "—"}</td>
                            <td>{row.feature_count ?? "—"}</td>
                            <td>{row.schema_id ? <code>{row.schema_id}</code> : "—"}</td>
                            <td>
                              {row.verdict ? (
                                <span className={styles.verdictBadge} data-verdict={row.verdict}>{row.verdict}</span>
                              ) : "—"}
                            </td>
                            <td>{row.score !== undefined ? `${(row.score * 100).toFixed(1)}%` : "—"}</td>
                            <td>{row.attack_class ?? "—"}</td>
                            <td className={styles.traceReason}>
                              {row.error
                                ? <span className={styles.traceError}>{row.error}</span>
                                : (row.reason ?? "—")}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>

                    {syntheticResult.note && (
                      <p className={styles.testNote}>{syntheticResult.note}</p>
                    )}
                  </div>
                )}
              </div>
            </div>

            {/* How to write test files */}
            <div className={styles.testGuide}>
              <p className={styles.testGuideTitle}>📄 Как написать свой плагин для тестирования</p>
              <p className={styles.testGuideIntro}>
                Загрузи <code>.py</code> файл в таб <strong>Файлы</strong>, затем нажми <strong>Reload plugins</strong> в табе Pipeline.
                Ниже — минимальные шаблоны препроцессора и модели:
              </p>
              <div className={styles.testCodeGrid}>
                <div className={styles.testCodeBlock}>
                  <p className={styles.testCodeTitle}>Препроцессор (my_preprocessor.py)</p>
                  <pre className={styles.testCode}>{`from app.plugins import BasePreprocessor, PluginFeatureVector

class MyPreprocessor(BasePreprocessor):
    def get_name(self) -> str:
        return "my_preprocessor"   # уникальное имя

    def get_output_schema_id(self) -> str:
        return "my_schema_v1"      # совпадает с accepted_schema_ids модели

    def get_feature_names(self) -> list[str]:
        # Имена признаков, которые вернёт transform()
        return ["byte_count", "packet_count", "duration_ms"]

    def transform(self, raw_input) -> PluginFeatureVector:
        # raw_input — NormalizedFlowEvent
        # Атрибуты: .raw_features (dict 71 признак),
        #           .byte_count, .packet_count, .duration_ms,
        #           .src_ip, .dst_ip, .protocol
        features = {
            "byte_count":   float(raw_input.byte_count   or 0),
            "packet_count": float(raw_input.packet_count or 0),
            "duration_ms":  float(raw_input.duration_ms  or 0),
        }
        return PluginFeatureVector(
            schema_id="my_schema_v1",
            features=features,
        )`}</pre>
                </div>
                <div className={styles.testCodeBlock}>
                  <p className={styles.testCodeTitle}>Модель (my_model.py)</p>
                  <pre className={styles.testCode}>{`from app.plugins import BaseModel, PluginFeatureVector, PluginVerdict

class MyModel(BaseModel):
    def get_name(self) -> str:
        return "my_model"          # уникальное имя

    def get_accepted_schema_ids(self) -> list[str]:
        return ["my_schema_v1"]    # совпадает с output_schema_id препроцессора

    def get_output_classes(self) -> list[str]:
        return ["normal", "anomaly"]

    def predict(self, features: PluginFeatureVector) -> PluginVerdict:
        f = features.features
        score = min(f.get("byte_count", 0) / 100_000, 1.0)
        if score >= 0.85:
            return PluginVerdict(verdict="anomaly", score=score,
                                 attack_class="DoS", reason="высокий объём трафика")
        elif score >= 0.5:
            return PluginVerdict(verdict="warning", score=score)
        return PluginVerdict(verdict="normal", score=score)`}</pre>
                </div>
              </div>
              <div className={styles.testGuideSteps}>
                <p><strong>Шаги после написания плагина:</strong></p>
                <ol>
                  <li>Загрузи оба файла в таб <strong>Файлы</strong></li>
                  <li>Перейди в таб <strong>Pipeline</strong> → нажми <strong>⟳ Reload plugins</strong></li>
                  <li>Убедись что препроцессор и модель появились в табе <strong>Плагины</strong></li>
                  <li>В табе <strong>Pipeline</strong> нажми <strong>+ Создать pipeline</strong>, выбери свой препроцессор и модель</li>
                  <li>Вернись в таб <strong>🧪 Тест</strong>, выбери созданный pipeline и запусти оба теста</li>
                  <li>Если всё зелёное — нажми <strong>Активировать</strong> в табе Pipeline</li>
                </ol>
              </div>
            </div>

          </div>
        )}

      </div>
    </div>
  );
}
