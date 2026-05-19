import { useEffect, useState } from "react";
import { useAppStore } from "../../app/store";
import { api } from "../../lib/api";
import type { AppSettings } from "../../app/types";
import s from "./SetupWizard.module.css";

// ─── Types ────────────────────────────────────────────────────
type DeviceType = "pc" | "server";
type RunMode    = "windows_live" | "linux_live";
type StepId     = "welcome" | "device" | "remote" | "os" | "iface" | "autoblock" | "sensitivity" | "done";

const PC_STEPS:     StepId[] = ["welcome", "device", "os", "iface", "autoblock", "sensitivity", "done"];
const SERVER_STEPS: StepId[] = ["welcome", "device", "remote", "os", "iface", "autoblock", "sensitivity", "done"];

const THEME_CYCLE = ["dark", "light", "gray"] as const;
const THEME_ICONS: Record<string, string> = { dark: "🌙", light: "☀️", gray: "◑" };

// Sensitivity → threshold mapping
const SENSITIVITY_MAP: Record<string, number> = {
  conservative: 0.85,
  balanced:     0.70,
  aggressive:   0.55,
};
type Sensitivity = keyof typeof SENSITIVITY_MAP;

function detectOS(): RunMode {
  return /win/i.test(navigator.platform) ? "windows_live" : "linux_live";
}

function nextTheme(t: string): typeof THEME_CYCLE[number] {
  const i = THEME_CYCLE.indexOf(t as typeof THEME_CYCLE[number]);
  return THEME_CYCLE[(i + 1) % 3];
}

// ─── Shared sub-components ────────────────────────────────────
function Opt({
  selected, onClick, label, hint, isDefault,
}: { selected: boolean; onClick: () => void; label: string; hint?: string; isDefault?: boolean }) {
  return (
    <button
      type="button"
      className={[s.option, selected ? s.optionSelected : ""].join(" ")}
      onClick={onClick}
    >
      <span className={s.radio} />
      <span>
        <span className={s.optLabel}>
          {label}
          {isDefault && <span className={s.defaultBadge}>по умолчанию</span>}
        </span>
        {hint && <div className={s.optHint}>{hint}</div>}
      </span>
    </button>
  );
}

function Dots({ total, current }: { total: number; current: number }) {
  return (
    <div className={s.dots}>
      {Array.from({ length: total }, (_, i) => (
        <span
          key={i}
          className={[s.dot, i === current ? s.dotActive : i < current ? s.dotDone : ""].join(" ")}
        />
      ))}
    </div>
  );
}

// ─── Steps ───────────────────────────────────────────────────
function WelcomeStep() {
  return (
    <>
      <img src="/logo.png" alt="AnomalyNet" className={s.logo} />
      <h2 className={s.title}>Добро пожаловать!</h2>
      <p className={s.subtitle}>
        Давайте настроим AnomalyNet IDS под вашу систему.<br />
        Это займёт меньше минуты.
      </p>
    </>
  );
}

function DeviceStep({ value, onChange }: { value: DeviceType; onChange: (v: DeviceType) => void }) {
  return (
    <>
      <h2 className={s.title}>Тип устройства</h2>
      <p className={s.subtitle}>Где установлен AnomalyNet?</p>
      <div className={s.opts}>
        <Opt selected={value === "pc"} onClick={() => onChange("pc")}
          label="Персональный компьютер" isDefault
          hint="Мониторинг домашней или рабочей сети с этого ПК" />
        <Opt selected={value === "server"} onClick={() => onChange("server")}
          label="Сервер / сетевое устройство"
          hint="Выделенный сервер, VPS или сетевой шлюз" />
      </div>
    </>
  );
}

function RemoteStep({ value, onChange }: { value: boolean; onChange: (v: boolean) => void }) {
  return (
    <>
      <h2 className={s.title}>Удалённый доступ к панели</h2>
      <p className={s.subtitle}>С каких адресов разрешить доступ к веб-интерфейсу?</p>
      <div className={s.opts}>
        <Opt selected={!value} onClick={() => onChange(false)}
          label="Только с этого сервера" isDefault
          hint="Доступ по localhost:8000 — рекомендуется для безопасности" />
        <Opt selected={value} onClick={() => onChange(true)}
          label="С любого IP в сети"
          hint="Открыть панель по IP сервера из любого браузера в сети" />
      </div>
    </>
  );
}

function OSStep({ value, onChange }: { value: RunMode; onChange: (v: RunMode) => void }) {
  return (
    <>
      <h2 className={s.title}>Операционная система</h2>
      <p className={s.subtitle}>На какой ОС работает AnomalyNet?</p>
      <div className={s.opts}>
        <Opt selected={value === "windows_live"} onClick={() => onChange("windows_live")}
          label="Windows"
          hint="Windows 10/11 · Windows Server 2019/2022" />
        <Opt selected={value === "linux_live"} onClick={() => onChange("linux_live")}
          label="Linux"
          hint="Ubuntu · Debian · RHEL · Alt Linux · любой дистрибутив" />
      </div>
    </>
  );
}

function IfaceStep({
  value, onChange, interfaces,
}: { value: string; onChange: (v: string) => void; interfaces: { name: string }[] }) {
  return (
    <>
      <h2 className={s.title}>Сетевой интерфейс</h2>
      <p className={s.subtitle}>Какой интерфейс анализировать на предмет угроз?</p>
      <select className={s.select} value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">Авто — выбрать автоматически (рекомендуется)</option>
        {interfaces.map((iface) => (
          <option key={iface.name} value={iface.name}>{iface.name}</option>
        ))}
      </select>
      <p className={s.selectHint}>
        Если список пустой — выберите «Авто». Интерфейс можно сменить в Settings позже.
      </p>
    </>
  );
}

function AutoblockStep({ value, onChange }: { value: boolean; onChange: (v: boolean) => void }) {
  return (
    <>
      <h2 className={s.title}>Автоматическая блокировка</h2>
      <p className={s.subtitle}>
        Блокировать атакующие IP-адреса автоматически?
      </p>
      <div className={s.opts}>
        <Opt selected={!value} onClick={() => onChange(false)}
          label="Только оповещения" isDefault
          hint="Обнаруживать атаки и уведомлять — без блокировки (рекомендуется для начала)" />
        <Opt selected={value} onClick={() => onChange(true)}
          label="Блокировать автоматически"
          hint="Мгновенно блокировать IP через iptables/Windows Firewall при обнаружении атаки" />
      </div>
      {value && (
        <div className={s.warn}>
          ⚠ Убедитесь что ваш IP добавлен в белый список в Settings → иначе можете заблокировать себя.
        </div>
      )}
    </>
  );
}

function SensitivityStep({ value, onChange }: { value: Sensitivity; onChange: (v: Sensitivity) => void }) {
  return (
    <>
      <h2 className={s.title}>Чувствительность детектора</h2>
      <p className={s.subtitle}>
        Насколько строго классифицировать трафик как атаку?
      </p>
      <div className={s.opts}>
        <Opt selected={value === "conservative"} onClick={() => onChange("conservative")}
          label="Консервативная"
          hint="Высокий порог (0.85) — меньше ложных тревог, возможны пропуски атак" />
        <Opt selected={value === "balanced"} onClick={() => onChange("balanced")}
          label="Сбалансированная" isDefault
          hint="Стандартный порог (0.70) — оптимальное соотношение точности и охвата" />
        <Opt selected={value === "aggressive"} onClick={() => onChange("aggressive")}
          label="Агрессивная"
          hint="Низкий порог (0.55) — максимальный охват, больше ложных тревог" />
      </div>
    </>
  );
}

function DoneStep({
  device, runMode, ifaceName, allowRemote, autoblock, sensitivity,
}: { device: DeviceType; runMode: RunMode; ifaceName: string; allowRemote: boolean; autoblock: boolean; sensitivity: Sensitivity }) {
  const rows: [string, string][] = [
    ["Устройство",    device === "pc" ? "Персональный компьютер" : "Сервер"],
    ["Система",       runMode === "windows_live" ? "Windows" : "Linux"],
    ["Интерфейс",     ifaceName || "Авто"],
    ["Защита",        autoblock ? "Автоблокировка включена" : "Только оповещения"],
    ["Чувствительность", sensitivity === "conservative" ? "Консервативная" : sensitivity === "aggressive" ? "Агрессивная" : "Сбалансированная"],
  ];
  if (device === "server") {
    rows.splice(2, 0, ["Удалённый доступ", allowRemote ? "Включён (любой IP)" : "Только localhost"]);
  }
  return (
    <>
      <img src="/logo.png" alt="AnomalyNet" className={s.logo} />
      <h2 className={s.title}>Всё готово!</h2>
      <p className={s.subtitle}>Параметры можно изменить в любое время в разделе Settings.</p>
      <div className={s.summary}>
        {rows.map(([label, val]) => (
          <div key={label} className={s.summRow}>
            <span className={s.summLabel}>{label}</span>
            <span className={s.summVal}>{val}</span>
          </div>
        ))}
      </div>
    </>
  );
}

// ─── Main wizard ─────────────────────────────────────────────
export function SetupWizard() {
  const settings         = useAppStore((st) => st.settings);
  const setSettings      = useAppStore((st) => st.setSettings);
  const setSetupComplete = useAppStore((st) => st.setSetupComplete);

  const [stepIdx,    setStepIdx]    = useState(0);
  const [device,     setDevice]     = useState<DeviceType>("pc");
  const [remote,     setRemote]     = useState(false);
  const [runMode,    setRunMode]    = useState<RunMode>(detectOS());
  const [ifaceName,  setIfaceName]  = useState("");
  const [autoblock,  setAutoblock]  = useState(false);
  const [sensitivity,setSensitivity]= useState<Sensitivity>("balanced");
  const [interfaces, setInterfaces] = useState<{ name: string }[]>([]);
  const [applying,   setApplying]   = useState(false);
  const [animKey,    setAnimKey]    = useState(0);

  const theme = (document.documentElement.dataset.theme ?? settings?.theme ?? "dark") as string;

  const steps  = device === "server" ? SERVER_STEPS : PC_STEPS;
  const stepId = steps[stepIdx];

  // Dots exclude "welcome" and "done"
  const dotSteps = steps.filter((id) => id !== "welcome" && id !== "done") as StepId[];
  const dotIdx   = dotSteps.indexOf(stepId);

  useEffect(() => {
    api.getInterfaces().then((ifaces: any) => setInterfaces(ifaces)).catch(() => {});
  }, []);

  function handleTheme() {
    document.documentElement.dataset.theme = nextTheme(theme);
  }

  function advance() {
    setAnimKey((k) => k + 1);
    setStepIdx((i) => Math.min(i + 1, steps.length - 1));
  }

  async function finish(defaults = false) {
    if (!settings) { setSetupComplete(true); return; }
    setApplying(true);
    const savedTheme = (document.documentElement.dataset.theme as AppSettings["theme"]) ?? settings.theme;
    const patch: AppSettings = {
      ...settings,
      theme:                savedTheme,
      run_mode:             defaults ? detectOS()  : runMode,
      interface_name:       defaults ? ""          : ifaceName,
      allow_remote_access:  defaults ? false       : (device === "server" ? remote : false),
      auto_block:           defaults ? false       : autoblock,
      catboost_threshold:   defaults ? 0.70        : SENSITIVITY_MAP[sensitivity],
    };
    try {
      const saved = await api.updateSettings(patch);
      setSettings(saved);
    } catch {
      setSettings(patch);
    }
    setSetupComplete(true);
  }

  const isLast = stepIdx === steps.length - 1;

  return (
    <div className={s.overlay}>
      <button type="button" className={s.themeBtn} onClick={handleTheme}
        title="Сменить тему">
        {THEME_ICONS[theme] ?? "🌙"}
      </button>

      <div className={s.card}>
        {dotIdx >= 0 && <Dots total={dotSteps.length} current={dotIdx} />}

        <div className={s.content} key={animKey}>
          {stepId === "welcome"     && <WelcomeStep />}
          {stepId === "device"      && <DeviceStep value={device} onChange={setDevice} />}
          {stepId === "remote"      && <RemoteStep value={remote} onChange={setRemote} />}
          {stepId === "os"          && <OSStep value={runMode} onChange={setRunMode} />}
          {stepId === "iface"       && <IfaceStep value={ifaceName} onChange={setIfaceName} interfaces={interfaces} />}
          {stepId === "autoblock"   && <AutoblockStep value={autoblock} onChange={setAutoblock} />}
          {stepId === "sensitivity" && <SensitivityStep value={sensitivity} onChange={setSensitivity} />}
          {stepId === "done"        && (
            <DoneStep device={device} runMode={runMode} ifaceName={ifaceName}
              allowRemote={remote} autoblock={autoblock} sensitivity={sensitivity} />
          )}
        </div>

        <div className={s.nav}>
          <button type="button" className={s.skipBtn}
            onClick={() => void finish(true)} disabled={applying}>
            Оставить по умолчанию
          </button>
          <button type="button" className={s.nextBtn}
            onClick={isLast ? () => void finish() : advance}
            disabled={applying}>
            {applying ? "Сохраняем…" : isLast ? "Начать →" : "Далее →"}
          </button>
        </div>
      </div>
    </div>
  );
}
