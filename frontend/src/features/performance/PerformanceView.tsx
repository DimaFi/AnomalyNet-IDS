import { useEffect, useState } from "react";
import { api } from "../../lib/api";
import type { AppSettings, NetworkInterface, PlatformCapabilities, SystemStats } from "../../app/types";
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
  const settings = useAppStore((st) => st.settings);
  const setSettings = useAppStore((st) => st.setSettings);
  const capabilities = useAppStore((st) => st.capabilities);
  const [interfaces, setInterfaces] = useState<NetworkInterface[]>([]);
  const [bpfInput, setBpfInput] = useState("");
  const [bpfSaved, setBpfSaved] = useState(false);

  useEffect(() => {
    const refresh = () => api.getSystemStats().then(setStats).catch(() => null);
    refresh();
    const iv = setInterval(refresh, 5000);
    return () => clearInterval(iv);
  }, []);

  useEffect(() => {
    api.getInterfaces().then(setInterfaces).catch(() => []);
  }, []);

  useEffect(() => {
    if (settings) setBpfInput(settings.bpf_filter ?? "");
  }, [settings?.bpf_filter]);

  const saveBpf = async () => {
    if (!settings) return;
    try {
      const saved = await api.updateSettings({ ...settings, bpf_filter: bpfInput.trim() });
      setSettings(saved);
      setBpfSaved(true);
      setTimeout(() => setBpfSaved(false), 2000);
    } catch { /* ignore */ }
  };

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

      {/* Interface + BPF quick-set */}
      <InterfacePanel
        interfaces={interfaces}
        settings={settings}
        capabilities={capabilities}
        bpfInput={bpfInput}
        setBpfInput={setBpfInput}
        onSaveBpf={() => void saveBpf()}
        bpfSaved={bpfSaved}
      />

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

function InterfacePanel({
  interfaces, settings, capabilities, bpfInput, setBpfInput, onSaveBpf, bpfSaved,
}: {
  interfaces: NetworkInterface[];
  settings: AppSettings | null;
  capabilities: PlatformCapabilities | null;
  bpfInput: string;
  setBpfInput: (v: string) => void;
  onSaveBpf: () => void;
  bpfSaved: boolean;
}) {
  const platform = capabilities?.platform ?? "unknown";
  const captureBackend = capabilities?.capture_backend ?? "—";
  const activeIfaces = settings?.interface_names?.length
    ? settings.interface_names
    : settings?.interface_name
    ? [settings.interface_name]
    : [];

  const recommendedIface = interfaces.find(i => i.is_recommended) ?? interfaces.find(i => i.is_default);
  const activeIfaceObjs = activeIfaces.map(name => interfaces.find(i => i.name === name)).filter(Boolean) as NetworkInterface[];
  const myIps = activeIfaceObjs.flatMap(i => i.addresses);

  return (
    <div className={s.section}>
      <div className={s.sectionTitle}>Диагностика интерфейса и BPF фильтр</div>

      {/* Platform */}
      <div className={s.diagList} style={{ marginBottom: 12 }}>
        <div className={s.diagRow}>
          <span className={s.diagDot} style={{ background: "var(--accent)" }} />
          <span className={s.diagLabel}>Платформа</span>
          <span className={s.diagNote} style={{ fontFamily: "monospace" }}>
            {platform} · {captureBackend}
          </span>
        </div>
        <div className={s.diagRow}>
          <span className={s.diagDot} style={{ background: capabilities?.packet_capture ? "var(--ok)" : "var(--danger)" }} />
          <span className={s.diagLabel}>Захват пакетов</span>
          <span className={s.diagNote} style={{ color: capabilities?.packet_capture ? "var(--ok)" : "var(--danger)" }}>
            {capabilities?.packet_capture ? "доступен" : "недоступен — нужны права администратора"}
          </span>
        </div>
      </div>

      {/* Active interfaces */}
      {interfaces.length > 0 && (
        <div style={{ marginBottom: 12 }}>
          <div style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--text-muted)", marginBottom: 6 }}>
            Сетевые интерфейсы
          </div>
          {interfaces.map(iface => {
            const isActive = activeIfaces.includes(iface.name);
            const okColor = isActive ? "var(--ok)" : "var(--text-muted)";
            return (
              <div key={iface.name} className={s.diagRow} style={{ marginBottom: 4 }}>
                <span className={s.diagDot} style={{ background: isActive ? "var(--ok)" : (iface.is_up ? "var(--accent)" : "var(--danger)") }} />
                <span className={s.diagLabel} style={{ color: okColor, fontFamily: "monospace" }}>
                  {iface.name}
                  {isActive && " ✓"}
                  {iface.is_recommended && !isActive && " (рекомендуется)"}
                </span>
                <span className={s.diagNote} style={{ fontFamily: "monospace", fontSize: 11 }}>
                  {iface.addresses.slice(0, 2).join(", ") || "нет IP"}
                </span>
              </div>
            );
          })}
          {recommendedIface && !activeIfaces.includes(recommendedIface.name) && (
            <p style={{ fontSize: 11, color: "#eab308", marginTop: 6 }}>
              ⚠ Рекомендуемый интерфейс <code>{recommendedIface.name}</code> не выбран. Перейди в Настройки → Захват трафика.
            </p>
          )}
        </div>
      )}

      {/* BPF Filter quick-set */}
      <div>
        <div style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--text-muted)", marginBottom: 6 }}>
          BPF фильтр — быстрая настройка
        </div>
        {myIps.length > 0 && (
          <div style={{ marginBottom: 8, display: "flex", flexWrap: "wrap", gap: 6 }}>
            {myIps.slice(0, 4).map(ip => (
              <button key={ip}
                style={{ fontSize: 11, padding: "3px 9px", borderRadius: 12, border: "1px solid var(--border-accent)",
                  background: "var(--surface-3)", color: "var(--accent)", cursor: "pointer", fontFamily: "monospace" }}
                onClick={() => setBpfInput(`host ${ip}`)}>
                host {ip}
              </button>
            ))}
            <button style={{ fontSize: 11, padding: "3px 9px", borderRadius: 12, border: "1px solid var(--border)",
              background: "var(--surface-3)", color: "var(--text-muted)", cursor: "pointer" }}
              onClick={() => setBpfInput("")}>
              Сбросить
            </button>
          </div>
        )}
        <div style={{ display: "flex", gap: 8, alignItems: "stretch" }}>
          <input
            style={{ flex: 1, padding: "6px 10px", borderRadius: "var(--radius-sm)",
              border: "1px solid var(--border-strong)", background: "var(--surface-3)",
              color: "var(--text-primary)", fontSize: 12, fontFamily: "monospace", outline: "none" }}
            value={bpfInput}
            onChange={e => setBpfInput(e.target.value)}
            placeholder="host 192.168.1.5   или   host 192.168.1.5 and tcp"
            onKeyDown={e => { if (e.key === "Enter") onSaveBpf(); }}
          />
          <button
            onClick={onSaveBpf}
            style={{ padding: "6px 14px", borderRadius: "var(--radius-sm)",
              border: "1px solid var(--border-accent)", background: bpfSaved ? "var(--ok)" : "var(--accent)",
              color: "#fff", fontSize: 12, fontWeight: 600, cursor: "pointer", transition: "background 0.3s", whiteSpace: "nowrap" }}>
            {bpfSaved ? "✓ Сохранено" : "Применить"}
          </button>
        </div>
        <p style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 6, lineHeight: 1.5 }}>
          Фильтр применяется на уровне ядра (BPF/Npcap) — Python видит только нужные пакеты.
          {platform === "windows" && " На Windows использует Npcap WinPcap API."}
          {platform === "linux" && " На Linux использует libpcap / BPF ядра."}
          {" "}Изменения вступают в силу после перезапуска захвата.
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
