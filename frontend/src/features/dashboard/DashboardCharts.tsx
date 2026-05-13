import { useEffect, useState } from "react";
import type { DashboardTimeseries, DashboardSummary } from "../../app/types";
import { api } from "../../lib/api";
import styles from "../panel.module.css";
import s from "./DashboardCharts.module.css";

// ── Colour palette ─────────────────────────────────────────────
const C_NORMAL  = "var(--ok)";
const C_WARNING = "var(--warn)";
const C_ANOMALY = "var(--danger)";

const CLASS_COLORS: Record<string, string> = {
  DoS:         "#f97316",
  DDoS:        "#ef4444",
  Recon:       "#3b82f6",
  PortScan:    "#60a5fa",
  BruteForce:  "#22c55e",
  WebAttack:   "#a855f7",
  Bot:         "#eab308",
  Botnet:      "#eab308",
  Spoofing:    "#06b6d4",
  Infiltration:"#f43f5e",
  NEW_TLS_FINGERPRINT:       "#8b5cf6",
  TOO_MANY_TLS_FINGERPRINTS: "#ec4899",
  DGA_DOMAIN:  "#f97316",
  DNS_TUNNELING:"#ef4444",
};
const C_DEFAULT = "#6b7280";

// ── Helpers ────────────────────────────────────────────────────

function fmtTime(ts: number): string {
  return new Date(ts * 1000).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
}

// ── TimeSeriesChart ────────────────────────────────────────────

interface TimeSeriesChartProps {
  data: DashboardTimeseries;
  windowLabel: string;
}

function TimeSeriesChart({ data, windowLabel }: TimeSeriesChartProps) {
  const W = 560; const H = 120; const PAD = { t: 8, r: 12, b: 28, l: 36 };
  const chartW = W - PAD.l - PAD.r;
  const chartH = H - PAD.t - PAD.b;

  const buckets = data.buckets;
  if (!buckets.length) {
    return (
      <div className={s.chartWrap}>
        <div className={s.chartTitle}>Активность (последние {windowLabel})</div>
        <div className={s.emptyChart}>Нет данных</div>
      </div>
    );
  }

  const maxVal = Math.max(1, ...buckets.map(b => b.normal + b.warning + b.anomaly));
  const n = buckets.length;
  const barW = Math.max(2, (chartW / n) - 1);

  const bars = buckets.map((b, i) => {
    const total = b.normal + b.warning + b.anomaly;
    const x = PAD.l + (i / n) * chartW;
    const toH = (v: number) => (v / maxVal) * chartH;
    const yNormal  = PAD.t + chartH - toH(b.normal + b.warning + b.anomaly);
    const yWarning = PAD.t + chartH - toH(b.warning + b.anomaly);
    const yAnomaly = PAD.t + chartH - toH(b.anomaly);
    const hNormal  = toH(b.normal);
    const hWarning = toH(b.warning);
    const hAnomaly = toH(b.anomaly);
    return { x, yNormal, yWarning, yAnomaly, hNormal, hWarning, hAnomaly, total, b };
  });

  // Y axis labels
  const yLabels = [0, Math.round(maxVal / 2), maxVal];

  // X axis — show ~4 labels
  const xStep = Math.max(1, Math.floor(n / 4));
  const xLabels = buckets
    .map((b, i) => ({ i, ts: b.ts }))
    .filter((_, i) => i % xStep === 0 || i === n - 1);

  return (
    <div className={s.chartWrap}>
      <div className={s.chartTitle}>
        Активность сетевых событий
        <span className={s.chartSubtitle}> · последние {windowLabel}</span>
      </div>
      <svg width="100%" viewBox={`0 0 ${W} ${H}`} className={s.svg}>
        {/* Grid lines */}
        {yLabels.map(v => {
          const y = PAD.t + chartH - (v / maxVal) * chartH;
          return (
            <g key={v}>
              <line x1={PAD.l} y1={y} x2={W - PAD.r} y2={y} stroke="var(--border)" strokeDasharray="3 3" />
              <text x={PAD.l - 4} y={y + 4} textAnchor="end" fontSize={9} fill="var(--text-muted)">{v}</text>
            </g>
          );
        })}
        {/* Stacked bars */}
        {bars.map(({ x, yNormal, yWarning, yAnomaly, hNormal, hWarning, hAnomaly, total, b }, i) => (
          <g key={i}>
            {hNormal  > 0 && <rect x={x} y={yNormal}  width={barW} height={hNormal}  fill={C_NORMAL}  opacity={0.7} />}
            {hWarning > 0 && <rect x={x} y={yWarning} width={barW} height={hWarning} fill={C_WARNING} opacity={0.85} />}
            {hAnomaly > 0 && <rect x={x} y={yAnomaly} width={barW} height={hAnomaly} fill={C_ANOMALY} />}
            {total > 0 && (
              <title>{fmtTime(b.ts)}: {b.normal} норм / {b.warning} warn / {b.anomaly} anom</title>
            )}
          </g>
        ))}
        {/* X axis labels */}
        {xLabels.map(({ i, ts }) => (
          <text key={i} x={PAD.l + (i / n) * chartW + barW / 2} y={H - 6}
            textAnchor="middle" fontSize={9} fill="var(--text-muted)">
            {fmtTime(ts)}
          </text>
        ))}
        {/* Axes */}
        <line x1={PAD.l} y1={PAD.t} x2={PAD.l} y2={PAD.t + chartH} stroke="var(--border)" />
        <line x1={PAD.l} y1={PAD.t + chartH} x2={W - PAD.r} y2={PAD.t + chartH} stroke="var(--border)" />
      </svg>
      <div className={s.legend}>
        <span><span className={s.dot} style={{ background: C_NORMAL }} />Норма</span>
        <span><span className={s.dot} style={{ background: C_WARNING }} />Предупреждение</span>
        <span><span className={s.dot} style={{ background: C_ANOMALY }} />Аномалия</span>
      </div>
    </div>
  );
}

// ── DonutChart ─────────────────────────────────────────────────

interface DonutChartProps {
  data: Record<string, number>;
  title: string;
  colors?: Record<string, string>;
}

function DonutChart({ data, title, colors = CLASS_COLORS }: DonutChartProps) {
  const entries = Object.entries(data).filter(([, v]) => v > 0).sort((a, b) => b[1] - a[1]);
  const total = entries.reduce((s, [, v]) => s + v, 0);

  if (!entries.length || total === 0) {
    return (
      <div className={s.donutWrap}>
        <div className={s.chartTitle}>{title}</div>
        <div className={s.emptyChart}>Нет данных</div>
      </div>
    );
  }

  const R = 44; const cx = 60; const cy = 56;
  let startAngle = -Math.PI / 2;

  const slices = entries.map(([cls, val]) => {
    const angle = (val / total) * 2 * Math.PI;
    const x1 = cx + R * Math.cos(startAngle);
    const y1 = cy + R * Math.sin(startAngle);
    startAngle += angle;
    const x2 = cx + R * Math.cos(startAngle);
    const y2 = cy + R * Math.sin(startAngle);
    const largeArc = angle > Math.PI ? 1 : 0;
    const path = `M ${cx} ${cy} L ${x1} ${y1} A ${R} ${R} 0 ${largeArc} 1 ${x2} ${y2} Z`;
    return { cls, val, path, color: colors[cls] ?? C_DEFAULT };
  });

  const topEntries = entries.slice(0, 6);

  return (
    <div className={s.donutWrap}>
      <div className={s.chartTitle}>{title}</div>
      <div className={s.donutInner}>
        <svg width="120" height="112" viewBox="0 0 120 112" className={s.svg}>
          {slices.map(({ cls, val, path, color }) => (
            <path key={cls} d={path} fill={color} opacity={0.85} stroke="var(--bg-card)" strokeWidth={1}>
              <title>{cls}: {val} ({((val / total) * 100).toFixed(1)}%)</title>
            </path>
          ))}
          <circle cx={cx} cy={cy} r={24} fill="var(--bg-card)" />
          <text x={cx} y={cy - 4} textAnchor="middle" fontSize={14} fontWeight="bold" fill="var(--text-primary)">{total}</text>
          <text x={cx} y={cy + 10} textAnchor="middle" fontSize={8} fill="var(--text-muted)">событий</text>
        </svg>
        <ul className={s.donutLegend}>
          {topEntries.map(([cls, val]) => (
            <li key={cls}>
              <span className={s.dot} style={{ background: colors[cls] ?? C_DEFAULT }} />
              <span className={s.donutLabel}>{cls}</span>
              <span className={s.donutVal}>{val}</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

// ── Window selector ────────────────────────────────────────────

const WINDOWS = [
  { value: 15,   label: "15 мин" },
  { value: 60,   label: "1 ч" },
  { value: 1440, label: "24 ч" },
];

// ── Main component ─────────────────────────────────────────────

export function DashboardCharts() {
  const [ts, setTs] = useState<DashboardTimeseries | null>(null);
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [window, setWindow] = useState(60);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      try {
        const [tsData, sumData] = await Promise.all([
          api.getDashboardTimeseries(window),
          api.getDashboardSummary(),
        ]);
        if (!cancelled) { setTs(tsData); setSummary(sumData); }
      } catch { /* ignore */ } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void load();
    const id = setInterval(() => { void load(); }, 30_000);
    return () => { cancelled = true; clearInterval(id); };
  }, [window]);

  const windowLabel = WINDOWS.find(w => w.value === window)?.label ?? `${window} мин`;

  const attackClasses = summary ? Object.fromEntries(
    Object.entries(summary.by_class).filter(([, v]) => v > 0)
  ) : {};

  return (
    <div className={styles.streamPreview}>
      <div className={styles.subhead}>
        <h3>Аналитика</h3>
        <div className={s.windowSel}>
          {WINDOWS.map(w => (
            <button key={w.value}
              className={`${s.winBtn} ${window === w.value ? s.winActive : ""}`}
              onClick={() => setWindow(w.value)}
            >{w.label}</button>
          ))}
          {loading && <span className={s.spinner} />}
        </div>
      </div>
      <div className={s.chartsRow}>
        {ts && <TimeSeriesChart data={ts} windowLabel={windowLabel} />}
        {summary && Object.keys(attackClasses).length > 0 && (
          <DonutChart data={attackClasses} title="Классы атак" />
        )}
        {summary && (
          <DonutChart
            data={summary.by_event_type}
            title="Типы событий"
            colors={{ flow: "#3b82f6", dns: "#22c55e", tls: "#a855f7" }}
          />
        )}
      </div>
    </div>
  );
}
