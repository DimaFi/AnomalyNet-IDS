import { useState } from "react";
import type { UpdateApplyResult, UpdateCheckResult } from "../../app/types";
import { api } from "../../lib/api";
import styles from "./AboutView.module.css";

const APP_VERSION = "v1.0.0";
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
          AnomalyNet — IDS с каскадной архитектурой детекции: Stage 1 (бинарный фильтр, F1=99.4%) → Stage 2/Stage 4 (многоклассовая классификация, 8 типов атак).
          Обучена на датасете CIC-IoT-2024 с дополнением из CIC-IDS-2018 и CIC-IDS-2017.
          Захват трафика через Scapy, авто-блокировка через iptables.
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
        <h2 className={styles.cardTitle}>Обновления</h2>

        <div className={styles.updateActions}>
          <button className={styles.btnPrimary} onClick={() => void handleCheck()} disabled={checking || applying}>
            {checking ? <><span className={styles.spinner} /> Проверяем...</> : "Проверить обновления"}
          </button>
          {checkResult?.has_any_update && (
            <button className={styles.btnApply} onClick={() => void handleApply()} disabled={applying}>
              {applying ? <><span className={styles.spinner} /> Обновляем...</> : "Применить обновления"}
            </button>
          )}
        </div>

        {checkError && <p className={styles.errorMsg}>{checkError}</p>}

        {checkResult && (
          <div className={styles.checkResult}>
            <RepoStatus label="GUI (приложение)" info={checkResult.gui} />
            <RepoStatus label="ML (модели)"       info={checkResult.ml} />
            {!checkResult.has_any_update && (
              <p className={styles.upToDate}>Всё актуально</p>
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

function AutoReload({ delayMs }: { delayMs: number }) {
  const [counter, setCounter] = useState(Math.ceil(delayMs / 1000));
  useState(() => {
    const iv = setInterval(() => setCounter((c) => c - 1), 1000);
    const t  = setTimeout(() => { clearInterval(iv); window.location.reload(); }, delayMs);
    return () => { clearInterval(iv); clearTimeout(t); };
  });
  return <p className={styles.reloadMsg}>Перезагрузка через {counter} сек...</p>;
}
