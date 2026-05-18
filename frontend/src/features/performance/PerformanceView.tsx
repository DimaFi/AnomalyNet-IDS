import { useEffect, useState } from "react";
import { api } from "../../lib/api";
import type { AppSettings, SystemStats } from "../../app/types";
import { useAppStore } from "../../app/store";
import styles from "../panel.module.css";
import s from "./PerformanceView.module.css";

function StatBar({ pct, color }: { pct: number; color: string }) {
  return (
    <div className={s.bar}>
      <div className={s.barFill} style={{ width: `${Math.min(100, pct)}%`, background: color }} />
    </div>
  );
}

function loadColor(pct: number) {
  if (pct >= 85) return "var(--danger)";
  if (pct >= 55) return "#eab308";
  return "var(--ok)";
}

function LoadGauge({ level }: { level?: string }) {
  const map: Record<string, { label: string; color: string; hint: string }> = {
    low:      { label: "Норма",    color: "var(--ok)",    hint: "Приложение работает без нагрузки" },
    medium:   { label: "Средняя",  color: "#eab308",      hint: "Умеренная нагрузка — следи за трендом" },
    high:     { label: "Высокая",  color: "#f97316",      hint: "Высокая нагрузка — рекомендуется оптимизация" },
    critical: { label: "Критично", color: "var(--danger)", hint: "Система перегружена — страница может не отвечать" },
  };
  const m = map[level ?? "low"] ?? map.low;
  return (
    <div className={s.gauge}>
      <div className={s.gaugeDot} style={{ background: m.color, boxShadow: `0 0 12px ${m.color}` }} />
      <div>
        <div className={s.gaugeLabel} style={{ color: m.color }}>{m.label}</div>
        <div className={s.gaugeHint}>{m.hint}</div>
      </div>
    </div>
  );
}

export function PerformanceView() {
  const [stats, setStats] = useState<SystemStats | null>(null);
  const settings = useAppStore((s) => s.settings);

  useEffect(() => {
    const refresh = () => api.getSystemStats().then(setStats).catch(() => null);
    refresh();
    const iv = setInterval(refresh, 5000);
    return () => clearInterval(iv);
  }, []);

  return (
    <section className={styles.panel}>
      <div className={styles.panelHeader}>
        <div>
          <h2>Производительность</h2>
          <p>Мониторинг нагрузки и рекомендации по оптимизации</p>
        </div>
      </div>

      {/* Load indicator */}
      <LoadGauge level={stats?.load_level} />

      {stats?.available && (
        <div className={s.statsGrid}>
          {/* System column */}
          <div className={s.statsCard}>
            <div className={s.cardTitle}>Система</div>
            <div className={s.statRow}>
              <span className={s.statLabel}>CPU (вся система)</span>
              <span className={s.statVal} style={{ color: loadColor(stats.cpu_percent ?? 0) }}>
                {stats.cpu_percent}%
              </span>
            </div>
            <StatBar pct={stats.cpu_percent ?? 0} color={loadColor(stats.cpu_percent ?? 0)} />

            <div className={s.statRow} style={{ marginTop: 12 }}>
              <span className={s.statLabel}>RAM ({stats.ram_used_mb} / {stats.ram_total_mb} MB)</span>
              <span className={s.statVal} style={{ color: loadColor(stats.ram_percent ?? 0) }}>
                {stats.ram_percent}%
              </span>
            </div>
            <StatBar pct={stats.ram_percent ?? 0} color={loadColor(stats.ram_percent ?? 0)} />

            <div className={s.netRow}>
              <span>↓ {stats.net_recv_kbps} KB/s</span>
              <span>↑ {stats.net_sent_kbps} KB/s</span>
            </div>
          </div>

          {/* AnomalyNet column */}
          <div className={s.statsCard}>
            <div className={s.cardTitle}>AnomalyNet процесс</div>
            <div className={s.statRow}>
              <span className={s.statLabel}>CPU процесса</span>
              <span className={s.statVal} style={{ color: loadColor(stats.process_cpu_percent ?? 0) }}>
                {stats.process_cpu_percent}%
              </span>
            </div>
            <StatBar pct={stats.process_cpu_percent ?? 0} color={loadColor(stats.process_cpu_percent ?? 0)} />

            <div className={s.statRow} style={{ marginTop: 12 }}>
              <span className={s.statLabel}>RAM процесса</span>
              <span className={s.statVal}>{stats.process_ram_mb} MB</span>
            </div>
            <StatBar pct={(stats.process_ram_mb ?? 0) / 5} color="var(--accent)" />

            {stats.events_total != null && (
              <div className={s.statsExtra}>
                <div className={s.statRow}>
                  <span className={s.statLabel}>Событий всего</span>
                  <span className={s.statVal}>{stats.events_total.toLocaleString()}</span>
                </div>
                {stats.events_anomaly != null && stats.events_anomaly > 0 && (
                  <div className={s.statRow}>
                    <span className={s.statLabel}>Аномалий</span>
                    <span className={s.statVal} style={{ color: "var(--danger)" }}>{stats.events_anomaly}</span>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Diagnostics */}
      <DiagnosticsPanel stats={stats} settings={settings} />

      {/* Why it crashes */}
      <WhyCrashingPanel />

      {/* Optimizations */}
      <OptimizationsPanel stats={stats} settings={settings} />
    </section>
  );
}

function DiagnosticsPanel({ stats, settings }: { stats: SystemStats | null; settings: AppSettings | null }) {
  if (!stats?.available) return null;
  const checks = [
    { ok: (stats.cpu_percent ?? 0) < 80, label: "CPU системы", note: (stats.cpu_percent ?? 0) >= 80 ? "Перегрузка процессора" : `${stats.cpu_percent}% — норма` },
    { ok: (stats.ram_percent ?? 0) < 80, label: "Оперативная память", note: (stats.ram_percent ?? 0) >= 80 ? "Высокое использование RAM" : `${stats.ram_percent}% — норма` },
    { ok: (stats.process_cpu_percent ?? 0) < 50, label: "CPU AnomalyNet", note: (stats.process_cpu_percent ?? 0) >= 50 ? "Python процесс перегружен — снизь нагрузку захвата" : `${stats.process_cpu_percent}% — норма` },
    { ok: (stats.process_ram_mb ?? 0) < 400, label: "RAM AnomalyNet", note: (stats.process_ram_mb ?? 0) >= 400 ? `${stats.process_ram_mb} MB — возможна утечка памяти` : `${stats.process_ram_mb} MB — норма` },
    { ok: settings?.detection_mode !== "advanced", label: "Режим детекции", note: settings?.detection_mode === "advanced" ? "Advanced — вдвое больше вычислений на событие" : "Simple — оптимально" },
  ];
  return (
    <div className={s.section}>
      <div className={s.sectionTitle}>Диагностика</div>
      <div className={s.diagList}>
        {checks.map((c) => (
          <div key={c.label} className={s.diagRow}>
            <span className={s.diagDot} style={{ background: c.ok ? "var(--ok)" : "#eab308" }} />
            <span className={s.diagLabel}>{c.label}</span>
            <span className={s.diagNote} style={{ color: c.ok ? "var(--text-muted)" : "#eab308" }}>{c.note}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function WhyCrashingPanel() {
  return (
    <div className={s.section}>
      <div className={s.sectionTitle}>Почему приложение зависает / страница не открывается</div>
      <div className={s.explainBlock}>
        <p className={s.explainText}>
          В большой сети (университет, офис — 100+ устройств) <strong>Scapy обрабатывает каждый IP-пакет в Python</strong>.
          При высоком трафике Python не успевает — процессор уходит на 100%, FastAPI перестаёт отвечать на запросы,
          страница <code>localhost:8000</code> не открывается.
        </p>
        <div className={s.symptomList}>
          <div className={s.symptom}><span className={s.symptomIcon}>🔴</span><span>Страница localhost не открывается несколько секунд</span></div>
          <div className={s.symptom}><span className={s.symptomIcon}>🔴</span><span>Поток событий останавливается (Live Stream замирает)</span></div>
          <div className={s.symptom}><span className={s.symptomIcon}>🔴</span><span>CPU Python процесса &gt; 60% при захвате</span></div>
          <div className={s.symptom}><span className={s.symptomIcon}>🟡</span><span>Много устройств (100+) в сети с активным трафиком</span></div>
        </div>
        <p className={s.explainText} style={{ marginTop: 8 }}>
          <strong>Главное решение:</strong> добавь BPF-фильтр ниже — это исключит чужой трафик до того,
          как он попадёт в Python, снизив нагрузку в 10–50 раз в университетской сети.
        </p>
      </div>
    </div>
  );
}

function OptimizationsPanel({ stats, settings }: { stats: SystemStats | null; settings: AppSettings | null }) {
  const isHighLoad = (stats?.process_cpu_percent ?? 0) > 40 || (stats?.load_level === "high") || stats?.load_level === "critical";
  const isAdvanced = settings?.detection_mode === "advanced";

  const tips = [
    {
      priority: true,
      title: "BPF фильтр (самое важное)",
      desc: "Захватывать только трафик твоего IP. Снижает нагрузку в 10–50 раз в большой сети.",
      code: `host ТВО_IP  (пример: host 172.30.44.X)`,
      detail: "В настройках (раздел «Захват трафика») есть поле BPF Filter. Введи туда выражение — Scapy отфильтрует на уровне ядра, Python не увидит чужие пакеты.",
      warn: false,
    },
    {
      priority: isAdvanced,
      title: `Режим детекции: ${isAdvanced ? "⚠ сейчас Advanced" : "Simple (уже оптимально)"}`,
      desc: "Advanced вычисляет 46 дополнительных признаков на каждый поток — вдвое дороже по CPU.",
      code: null,
      detail: "В настройках → Режим детекции переключи на Simple. Advanced нужен только когда модели Stage3 обеспечивают лучшую точность.",
      warn: isAdvanced,
    },
    {
      priority: isHighLoad,
      title: "Одиночный интерфейс",
      desc: "Убедись что захват ведётся только на одном интерфейсе, а не на нескольких.",
      code: null,
      detail: "В настройках → Интерфейс выбери только основной (Wi-Fi или Ethernet), не оба сразу.",
      warn: false,
    },
    {
      priority: false,
      title: "Таймаут потоков (агрессивный)",
      desc: "Flow Aggregator хранит неактивные потоки 120 секунд. Снижение до 30с ускорит освобождение памяти.",
      code: null,
      detail: "Пока не вынесено в UI — изменить в flow_aggregator.py константу IDLE_TIMEOUT.",
      warn: false,
    },
    {
      priority: false,
      title: "Фильтровать только подозрительный трафик",
      desc: "Добавь BPF фильтр по портам — например, только TCP и только нестандартные порты.",
      code: `ip and (tcp port 22 or tcp port 80 or tcp port 443 or tcp portrange 8000-9999)`,
      detail: "Это позволит видеть атаки на сервисы и сканирование портов, игнорируя обычный браузерный трафик.",
      warn: false,
    },
  ];

  return (
    <div className={s.section}>
      <div className={s.sectionTitle}>Оптимизация</div>
      <div className={s.tipList}>
        {tips.map((t, i) => (
          <div key={i} className={[s.tip, t.priority ? s.tipPriority : "", t.warn ? s.tipWarn : ""].filter(Boolean).join(" ")}>
            <div className={s.tipHeader}>
              <span className={s.tipTitle}>{t.title}</span>
              {t.priority && <span className={s.tipTag}>рекомендуется</span>}
            </div>
            <p className={s.tipDesc}>{t.desc}</p>
            {t.code && <code className={s.tipCode}>{t.code}</code>}
            <p className={s.tipDetail}>{t.detail}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
