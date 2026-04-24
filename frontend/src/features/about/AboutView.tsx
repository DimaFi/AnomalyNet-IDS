import { useState } from "react";
import type { ReinstallResult, UninstallResult, UpdateApplyResult, UpdateCheckResult } from "../../app/types";
import { api } from "../../lib/api";
import styles from "./AboutView.module.css";

const APP_VERSION = "v1.3.0";
const GUI_REPO    = "https://github.com/DimaFi/AnomalyNet-gui";
const ML_REPO     = "https://github.com/DimaFi/AnomalyNet-ml";

export function AboutView() {
  const [checking, setChecking]   = useState(false);
  const [applying, setApplying]   = useState(false);
  const [checkResult, setCheck]   = useState<UpdateCheckResult | null>(null);
  const [applyResult, setApply]   = useState<UpdateApplyResult | null>(null);
  const [checkError, setCheckErr] = useState<string | null>(null);

  async function handleCheck() {
    setChecking(true);
    setCheck(null);
    setApply(null);
    setCheckErr(null);
    try {
      const res = await api.checkUpdates();
      setCheck(res);
    } catch {
      setCheckErr("Не удалось получить информацию об обновлениях. Проверьте соединение с сервером.");
    } finally {
      setChecking(false);
    }
  }

  async function handleApply() {
    setApplying(true);
    setApply(null);
    try {
      const res = await api.applyUpdates();
      setApply(res);
    } catch {
      setApply({ gui: { ok: false }, ml: { ok: false }, dist_rebuilt: false, restart_scheduled: false, message: "Ошибка при применении обновления", errors: [] });
    } finally {
      setApplying(false);
    }
  }

  return (
    <section className={styles.wrap}>
      {/* ── Header ── */}
      <div className={styles.hero}>
        <img src="/logo.png" alt="AnomalyNet" className={styles.logo} />
        <div className={styles.heroText}>
          <h1 className={styles.appName}>AnomalyNet IDS</h1>
          <p className={styles.appSub}>Система обнаружения вторжений на основе машинного обучения</p>
          <span className={styles.versionBadge}>{APP_VERSION}</span>
        </div>
      </div>

      {/* ── Description ── */}
      <div className={styles.card}>
        <p className={styles.desc}>
          AnomalyNet — IDS, детекция по умолчанию работает на каскадной системе из нескольких моделей
          машинного обучения. Подробнее об архитектуре и обучении — на GitHub.
          В разделе <strong>Plugins</strong> можно подключить любую собственную модель и препроцессор
          признаков, соблюдая описанный контракт ввода/вывода.
        </p>
      </div>

      {/* ── Repos ── */}
      <div className={styles.card}>
        <h2 className={styles.cardTitle}>Репозитории</h2>
        <div className={styles.repoList}>
          <a className={styles.repoLink} href={GUI_REPO} target="_blank" rel="noreferrer">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M9 19c-5 1.5-5-2.5-7-3m14 6v-3.87a3.37 3.37 0 0 0-.94-2.61c3.14-.35 6.44-1.54 6.44-7A5.44 5.44 0 0 0 20 4.77 5.07 5.07 0 0 0 19.91 1S18.73.65 16 2.48a13.38 13.38 0 0 0-7 0C6.27.65 5.09 1 5.09 1A5.07 5.07 0 0 0 5 4.77a5.44 5.44 0 0 0-1.5 3.78c0 5.42 3.3 6.61 6.44 7A3.37 3.37 0 0 0 9 18.13V22" />
            </svg>
            AnomalyNet-gui
            <span className={styles.repoDesc}>Приложение (FastAPI + React)</span>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={styles.extIcon}>
              <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/>
            </svg>
          </a>
          <a className={styles.repoLink} href={ML_REPO} target="_blank" rel="noreferrer">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M9 19c-5 1.5-5-2.5-7-3m14 6v-3.87a3.37 3.37 0 0 0-.94-2.61c3.14-.35 6.44-1.54 6.44-7A5.44 5.44 0 0 0 20 4.77 5.07 5.07 0 0 0 19.91 1S18.73.65 16 2.48a13.38 13.38 0 0 0-7 0C6.27.65 5.09 1 5.09 1A5.07 5.07 0 0 0 5 4.77a5.44 5.44 0 0 0-1.5 3.78c0 5.42 3.3 6.61 6.44 7A3.37 3.37 0 0 0 9 18.13V22" />
            </svg>
            AnomalyNet-ml
            <span className={styles.repoDesc}>Модели CatBoost (Stage 1–4)</span>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={styles.extIcon}>
              <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/>
            </svg>
          </a>
        </div>
      </div>

      {/* ── Updates ── */}
      <div className={styles.card}>
        <h2 className={styles.cardTitle}>Обновления и управление</h2>

        <div className={styles.updateActions}>
          <button className={styles.btnPrimary} onClick={() => void handleCheck()} disabled={checking || applying}>
            {checking ? <><span className={styles.spinner} /> Проверяем...</> : "Проверить обновления"}
          </button>
          <RestartButton />
          <ReinstallButton />
          <UninstallButton />
        </div>

        {checkError && <p className={styles.errorMsg}>{checkError}</p>}

        {checkResult && (
          <div className={styles.checkResult}>
            <RepoStatus label="GUI (приложение)" info={checkResult.gui} />
            <RepoStatus label="ML (модели)"       info={checkResult.ml} />
            {!checkResult.has_any_update && (
              <p className={styles.upToDate}>Всё актуально</p>
            )}
            {checkResult.has_any_update && (
              <button className={styles.btnApply} onClick={() => void handleApply()} disabled={applying} style={{ marginTop: 10, alignSelf: "flex-start" }}>
                {applying ? <><span className={styles.spinner} /> Обновляем...</> : "Применить обновления"}
              </button>
            )}
          </div>
        )}

        {applyResult && (
          <div className={styles.applyResult}>
            <p className={[styles.applyMsg, applyResult.restart_scheduled ? styles.applyWarn : styles.applyOk].join(" ")}>
              {applyResult.message}
            </p>
            {applyResult.dist_rebuilt && <p className={styles.applyDetail}>Frontend пересобран</p>}
            {applyResult.restart_scheduled && <p className={styles.applyDetail}>Сервис перезапускается — страница обновится через ~5 сек</p>}
            {applyResult.errors.length > 0 && (
              <ul className={styles.errorList}>
                {applyResult.errors.map((e, i) => <li key={i}>{e}</li>)}
              </ul>
            )}
            {applyResult.restart_scheduled && <AutoReload delayMs={5000} />}
          </div>
        )}
      </div>
    </section>
  );
}

function RepoStatus({ label, info }: { label: string; info: { has_update?: boolean; current?: string; latest?: string; latest_msg?: string; available?: boolean; error?: string } }) {
  if (!info.available) {
    return (
      <div className={styles.repoStatus}>
        <span className={styles.repoStatusLabel}>{label}</span>
        <span className={styles.statusErr}>недоступен{info.error ? `: ${info.error}` : ""}</span>
      </div>
    );
  }
  return (
    <div className={styles.repoStatus}>
      <span className={styles.repoStatusLabel}>{label}</span>
      {info.has_update ? (
        <span className={styles.statusNew}>
          Доступно: <code>{info.latest}</code>
          {info.latest_msg && <span className={styles.commitMsg}> — {info.latest_msg}</span>}
        </span>
      ) : (
        <span className={styles.statusOk}>
          Актуально: <code>{info.current}</code>
        </span>
      )}
    </div>
  );
}

function RestartButton() {
  const [state, setState] = useState<"idle" | "pending" | "done" | "error">("idle");

  async function handleRestart() {
    if (!confirm("Перезапустить сервис AnomalyNet? Подключение прервётся на ~3 секунды.")) return;
    setState("pending");
    try {
      await api.restartService();
      setState("done");
      setTimeout(() => window.location.reload(), 3500);
    } catch {
      setState("error");
      setTimeout(() => setState("idle"), 4000);
    }
  }

  return (
    <button
      className={styles.btnRestart}
      onClick={() => void handleRestart()}
      disabled={state === "pending" || state === "done"}
      title="Перезапустить сервис (systemctl restart anomalynet)"
    >
      {state === "pending" ? <><span className={styles.spinner} /> Перезапускаем...</>
       : state === "done"  ? "Перезапускается..."
       : state === "error" ? "Ошибка — только Linux"
       : "↺ Перезапустить"}
    </button>
  );
}

function ReinstallButton() {
  const [phase, setPhase] = useState<"idle" | "confirm" | "running" | "done">("idle");
  const [wipe, setWipe]   = useState(false);
  const [result, setResult] = useState<ReinstallResult | null>(null);

  async function run() {
    setPhase("running");
    try {
      const r = await api.reinstall(wipe);
      setResult(r);
      setPhase("done");
    } catch {
      setResult({ steps: [], errors: ["Нет ответа от сервера"], wipe_settings: wipe, restart_scheduled: false, message: "Ошибка запроса" });
      setPhase("done");
    }
  }

  if (phase === "idle") {
    return (
      <button className={styles.btnReinstall} onClick={() => setPhase("confirm")}>
        ⟳ Переустановить
      </button>
    );
  }

  if (phase === "confirm") {
    return (
      <div className={styles.reinstallConfirm}>
        <p className={styles.reinstallConfirmTitle}>Выберите тип переустановки:</p>
        <label className={styles.reinstallOption}>
          <input type="radio" name="wipe" checked={!wipe} onChange={() => setWipe(false)} />
          <span>
            <strong>Обновить код</strong>
            <span className={styles.reinstallOptionSub}>git pull + pip install + перезапуск. Настройки сохраняются.</span>
          </span>
        </label>
        <label className={styles.reinstallOption}>
          <input type="radio" name="wipe" checked={wipe} onChange={() => setWipe(true)} />
          <span>
            <strong>Полная переустановка</strong>
            <span className={[styles.reinstallOptionSub, styles.reinstallOptionWarn].join(" ")}>
              То же + удаляет config/settings.json и data/ (история, блокировки). Настройки сбросятся на дефолт.
            </span>
          </span>
        </label>
        <div className={styles.reinstallActions}>
          <button className={styles.btnSecondary} onClick={() => setPhase("idle")}>Отмена</button>
          <button className={[styles.btnApply, wipe ? styles.btnDanger : ""].filter(Boolean).join(" ")} onClick={() => void run()}>
            {wipe ? "⚠ Переустановить со сбросом" : "Переустановить"}
          </button>
        </div>
      </div>
    );
  }

  if (phase === "running") {
    return (
      <div className={styles.reinstallRunning}>
        <span className={styles.spinner} /> Выполняется переустановка... (может занять до 2 минут)
      </div>
    );
  }

  // done
  const ok = result && result.errors.length === 0;
  return (
    <div className={styles.reinstallResult}>
      <p className={[styles.applyMsg, ok ? styles.applyOk : styles.applyWarn].join(" ")}>
        {result?.message}
      </p>
      {result?.steps.map((s, i) => (
        <div key={i} className={[styles.reinstallStep, s.ok ? styles.reinstallStepOk : styles.reinstallStepErr].join(" ")}>
          <span>{s.ok ? "✓" : "✗"}</span>
          <span>{s.name}</span>
          {!s.ok && <span className={styles.reinstallStepDetail}>{s.detail}</span>}
        </div>
      ))}
      {result?.restart_scheduled && <AutoReload delayMs={4000} />}
    </div>
  );
}

function UninstallButton() {
  const [phase, setPhase] = useState<"idle" | "confirm" | "running" | "done">("idle");
  const [keepSettings, setKeepSettings] = useState(true);
  const [result, setResult] = useState<UninstallResult | null>(null);

  async function run() {
    setPhase("running");
    try {
      const r = await api.uninstall(keepSettings);
      setResult(r);
      setPhase("done");
    } catch {
      setResult({ steps: [], errors: ["Нет ответа от сервера"], keep_settings: keepSettings, message: "Ошибка запроса" });
      setPhase("done");
    }
  }

  if (phase === "idle") {
    return (
      <button
        className={styles.btnUninstall}
        onClick={() => setPhase("confirm")}
        title="Удалить приложение"
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <polyline points="3 6 5 6 21 6" />
          <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
          <path d="M10 11v6" />
          <path d="M14 11v6" />
          <path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
        </svg>
      </button>
    );
  }

  if (phase === "confirm") {
    return (
      <div className={[styles.reinstallConfirm, styles.uninstallConfirm].join(" ")}>
        <p className={styles.reinstallConfirmTitle}>Выберите тип удаления:</p>
        <label className={styles.reinstallOption}>
          <input type="radio" name="uninstall_mode" checked={keepSettings} onChange={() => setKeepSettings(true)} />
          <span>
            <strong>Удалить приложение</strong>
            <span className={styles.reinstallOptionSub}>Останавливает сервис и удаляет код. Ваши настройки и данные сохраняются.</span>
          </span>
        </label>
        <label className={styles.reinstallOption}>
          <input type="radio" name="uninstall_mode" checked={!keepSettings} onChange={() => setKeepSettings(false)} />
          <span>
            <strong>Полное удаление</strong>
            <span className={[styles.reinstallOptionSub, styles.reinstallOptionWarn].join(" ")}>
              Удаляет сервис, код, все настройки и историю. Восстановление невозможно.
            </span>
          </span>
        </label>
        <div className={styles.reinstallActions}>
          <button className={styles.btnSecondary} onClick={() => setPhase("idle")}>Отмена</button>
          <button className={[styles.btnApply, styles.btnDanger].join(" ")} onClick={() => void run()}>
            {keepSettings ? "Удалить" : "⚠ Удалить всё"}
          </button>
        </div>
      </div>
    );
  }

  if (phase === "running") {
    return (
      <div className={styles.reinstallRunning}>
        <span className={styles.spinner} /> Удаление... подождите
      </div>
    );
  }

  // done
  const ok = result && result.errors.length === 0;
  return (
    <div className={styles.reinstallResult}>
      <p className={[styles.applyMsg, ok ? styles.applyOk : styles.applyWarn].join(" ")}>
        {result?.message}
      </p>
      {result?.steps.map((s, i) => (
        <div key={i} className={[styles.reinstallStep, s.ok ? styles.reinstallStepOk : styles.reinstallStepErr].join(" ")}>
          <span>{s.ok ? "✓" : "✗"}</span>
          <span>{s.name}</span>
          {!s.ok && <span className={styles.reinstallStepDetail}>{s.detail}</span>}
        </div>
      ))}
    </div>
  );
}

function AutoReload({ delayMs }: { delayMs: number }) {
  const [counter, setCounter] = useState(Math.ceil(delayMs / 1000));
  useState(() => {
    const iv = setInterval(() => setCounter((c) => c - 1), 1000);
    const t  = setTimeout(() => { clearInterval(iv); window.location.reload(); }, delayMs);
    return () => { clearInterval(iv); clearTimeout(t); };
  });
  return <p className={styles.reloadMsg}>Перезагрузка через {counter} сек...</p>;
}
