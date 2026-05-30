import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
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

const THEME_CYCLE = ["dark", "light", "gray", "glass"] as const;
const THEME_ICONS: Record<string, string> = { dark: "🌙", light: "☀️", gray: "◑", glass: "🫧" };

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
  return THEME_CYCLE[(i + 1) % THEME_CYCLE.length];
}

// ─── Shared sub-components ────────────────────────────────────
function Opt({
  selected, onClick, label, hint, isDefault,
}: { selected: boolean; onClick: () => void; label: string; hint?: string; isDefault?: boolean }) {
  const { t } = useTranslation();
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
          {isDefault && <span className={s.defaultBadge}>{t("setup.defaultBadge")}</span>}
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
  const { t } = useTranslation();
  return (
    <>
      <img src="/logo.png" alt="AnomalyNet" className={s.logo} />
      <h2 className={s.title}>{t("setup.welcomeTitle")}</h2>
      <p className={s.subtitle}>{t("setup.welcomeDesc")}</p>
    </>
  );
}

function DeviceStep({ value, onChange }: { value: DeviceType; onChange: (v: DeviceType) => void }) {
  const { t } = useTranslation();
  return (
    <>
      <h2 className={s.title}>{t("setup.deviceTitle")}</h2>
      <p className={s.subtitle}>{t("setup.deviceDesc")}</p>
      <div className={s.opts}>
        <Opt selected={value === "pc"} onClick={() => onChange("pc")}
          label={t("setup.devicePc")} isDefault
          hint={t("setup.devicePcHint")} />
        <Opt selected={value === "server"} onClick={() => onChange("server")}
          label={t("setup.deviceServer")}
          hint={t("setup.deviceSrvHint")} />
      </div>
    </>
  );
}

function RemoteStep({ value, onChange }: { value: boolean; onChange: (v: boolean) => void }) {
  const { t } = useTranslation();
  return (
    <>
      <h2 className={s.title}>{t("setup.remoteTitle")}</h2>
      <p className={s.subtitle}>{t("setup.remoteDesc")}</p>
      <div className={s.opts}>
        <Opt selected={!value} onClick={() => onChange(false)}
          label={t("setup.remoteLocal")} isDefault
          hint={t("setup.remoteLocalHint")} />
        <Opt selected={value} onClick={() => onChange(true)}
          label={t("setup.remoteAny")}
          hint={t("setup.remoteAnyHint")} />
      </div>
    </>
  );
}

function OSStep({ value, onChange }: { value: RunMode; onChange: (v: RunMode) => void }) {
  const { t } = useTranslation();
  return (
    <>
      <h2 className={s.title}>{t("setup.osTitle")}</h2>
      <p className={s.subtitle}>{t("setup.osDesc")}</p>
      <div className={s.opts}>
        <Opt selected={value === "windows_live"} onClick={() => onChange("windows_live")}
          label={t("setup.osWin")}
          hint={t("setup.osWinHint")} />
        <Opt selected={value === "linux_live"} onClick={() => onChange("linux_live")}
          label={t("setup.osLinux")}
          hint={t("setup.osLinuxHint")} />
      </div>
    </>
  );
}

function IfaceStep({
  value, onChange, interfaces,
}: { value: string; onChange: (v: string) => void; interfaces: { name: string }[] }) {
  const { t } = useTranslation();
  return (
    <>
      <h2 className={s.title}>{t("setup.ifaceTitle")}</h2>
      <p className={s.subtitle}>{t("setup.ifaceDesc")}</p>
      <select className={s.select} value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">{t("setup.ifaceAuto")}</option>
        {interfaces.map((iface) => (
          <option key={iface.name} value={iface.name}>{iface.name}</option>
        ))}
      </select>
      <p className={s.selectHint}>{t("setup.ifaceHint")}</p>
    </>
  );
}

function AutoblockStep({
  value, onChange, myIp, onMyIpChange,
}: { value: boolean; onChange: (v: boolean) => void; myIp: string; onMyIpChange: (v: string) => void }) {
  const { t } = useTranslation();
  return (
    <>
      <h2 className={s.title}>{t("setup.autoblockTitle")}</h2>
      <p className={s.subtitle}>{t("setup.autoblockDesc")}</p>
      <div className={s.opts}>
        <Opt selected={!value} onClick={() => onChange(false)}
          label={t("setup.autoblockOff")} isDefault
          hint={t("setup.autoblockOffHint")} />
        <Opt selected={value} onClick={() => onChange(true)}
          label={t("setup.autoblockOn")}
          hint={t("setup.autoblockOnHint")} />
      </div>
      {value && (
        <div className={s.ipBlock}>
          <label className={s.ipLabel}>{t("setup.ipLabel")}</label>
          <input
            type="text"
            className={s.ipInput}
            value={myIp}
            placeholder="192.168.1.10"
            onChange={(e) => onMyIpChange(e.target.value)}
          />
          <p className={s.remoteHint}>{t("setup.ipHint")}</p>
        </div>
      )}
    </>
  );
}

function SensitivityStep({ value, onChange }: { value: Sensitivity; onChange: (v: Sensitivity) => void }) {
  const { t } = useTranslation();
  return (
    <>
      <h2 className={s.title}>{t("setup.sensitivityTitle")}</h2>
      <p className={s.subtitle}>{t("setup.sensitivityDesc")}</p>
      <div className={s.opts}>
        <Opt selected={value === "conservative"} onClick={() => onChange("conservative")}
          label={t("setup.conservative")}
          hint={t("setup.conservativeHint")} />
        <Opt selected={value === "balanced"} onClick={() => onChange("balanced")}
          label={t("setup.balanced")} isDefault
          hint={t("setup.balancedHint")} />
        <Opt selected={value === "aggressive"} onClick={() => onChange("aggressive")}
          label={t("setup.aggressive")}
          hint={t("setup.aggressiveHint")} />
      </div>
    </>
  );
}

function DoneStep({
  device, runMode, ifaceName, allowRemote, autoblock, sensitivity,
}: { device: DeviceType; runMode: RunMode; ifaceName: string; allowRemote: boolean; autoblock: boolean; sensitivity: Sensitivity }) {
  const { t } = useTranslation();
  const rows: [string, string][] = [
    [t("setup.device"),      device === "pc" ? t("setup.pc") : t("setup.server")],
    [t("setup.system"),      runMode === "windows_live" ? "Windows" : "Linux"],
    [t("setup.interface"),   ifaceName || t("setup.auto")],
    [t("setup.protection"),  autoblock ? t("setup.protectionOn") : t("setup.protectionOff")],
    [t("setup.sensitivity"), sensitivity === "conservative" ? t("setup.conservative") : sensitivity === "aggressive" ? t("setup.aggressive") : t("setup.balanced")],
  ];
  if (device === "server") {
    rows.splice(2, 0, [t("setup.remoteAccess"), allowRemote ? t("setup.remoteOn") : t("setup.remoteOff")]);
  }
  return (
    <>
      <img src="/logo.png" alt="AnomalyNet" className={s.logo} />
      <h2 className={s.title}>{t("setup.doneTitle")}</h2>
      <p className={s.subtitle}>{t("setup.doneDesc")}</p>
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
  const { t, i18n } = useTranslation();
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
  const [myIp,       setMyIp]       = useState("");
  const [applying,   setApplying]   = useState(false);
  const [animKey,    setAnimKey]    = useState(0);
  const [localTheme, setLocalTheme] = useState<string>(
    () => document.documentElement.dataset.theme ?? settings?.theme ?? "dark"
  );

  // Language state (local, synced to i18n)
  const currentLang = i18n.language.startsWith("ru") ? "ru" : "en";

  const steps  = device === "server" ? SERVER_STEPS : PC_STEPS;
  const stepId = steps[stepIdx];

  const dotSteps = steps.filter((id) => id !== "welcome" && id !== "done") as StepId[];
  const dotIdx   = dotSteps.indexOf(stepId);

  useEffect(() => {
    api.getInterfaces().then((ifaces: any) => {
      setInterfaces(ifaces);
      const ip: string = (ifaces as { addresses?: string[] }[])
        .flatMap((i) => i.addresses ?? [])
        .find((a: string) => !a.startsWith("127.") && !a.startsWith("::") && !a.startsWith("169.254.") && a.includes(".")) ?? "";
      if (ip) setMyIp(ip);
    }).catch(() => {});
  }, []);

  function handleTheme() {
    const next = nextTheme(localTheme);
    document.documentElement.dataset.theme = next;
    setLocalTheme(next);
  }

  async function handleLang() {
    const next = currentLang === "en" ? "ru" : "en";
    await i18n.changeLanguage(next);
  }

  function advance() {
    setAnimKey((k) => k + 1);
    setStepIdx((i) => Math.min(i + 1, steps.length - 1));
  }

  async function finish(defaults = false) {
    if (!settings) { setSetupComplete(true); return; }
    setApplying(true);
    const savedTheme = (document.documentElement.dataset.theme as AppSettings["theme"]) ?? settings.theme;
    const enableAutoblock = !defaults && autoblock;
    const existingWhitelist = settings.whitelist_ips ?? [];
    const newWhitelist = enableAutoblock && myIp && !existingWhitelist.includes(myIp.trim())
      ? [...existingWhitelist, myIp.trim()]
      : existingWhitelist;
    const patch: AppSettings = {
      ...settings,
      theme:                savedTheme,
      language:             currentLang as "ru" | "en",
      run_mode:             defaults ? detectOS()  : runMode,
      interface_name:       defaults ? ""          : ifaceName,
      allow_remote_access:  defaults ? false       : (device === "server" ? remote : false),
      auto_block:           defaults ? false       : autoblock,
      catboost_threshold:   defaults ? 0.70        : SENSITIVITY_MAP[sensitivity],
      whitelist_ips:        newWhitelist,
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
      {/* Theme + Language toggles — fixed top-right, laid out in a flex row */}
      <div className={s.topControls}>
        <button
          type="button"
          className={s.themeBtn}
          onClick={handleTheme}
          title={t("theme.label")}
        >
          {THEME_ICONS[localTheme] ?? "🌙"}
        </button>
        <button
          type="button"
          className={`${s.themeBtn} ${s.langBtn}`}
          onClick={() => void handleLang()}
          title="Switch language / Сменить язык"
        >
          {currentLang.toUpperCase()}
        </button>
      </div>

      <div className={s.card}>
        {dotIdx >= 0 && <Dots total={dotSteps.length} current={dotIdx} />}

        <div className={s.content} key={animKey}>
          {stepId === "welcome"     && <WelcomeStep />}
          {stepId === "device"      && <DeviceStep value={device} onChange={setDevice} />}
          {stepId === "remote"      && <RemoteStep value={remote} onChange={setRemote} />}
          {stepId === "os"          && <OSStep value={runMode} onChange={setRunMode} />}
          {stepId === "iface"       && <IfaceStep value={ifaceName} onChange={setIfaceName} interfaces={interfaces} />}
          {stepId === "autoblock"   && <AutoblockStep value={autoblock} onChange={setAutoblock} myIp={myIp} onMyIpChange={setMyIp} />}
          {stepId === "sensitivity" && <SensitivityStep value={sensitivity} onChange={setSensitivity} />}
          {stepId === "done"        && (
            <DoneStep device={device} runMode={runMode} ifaceName={ifaceName}
              allowRemote={remote} autoblock={autoblock} sensitivity={sensitivity} />
          )}
        </div>

        <div className={s.nav}>
          <button type="button" className={s.skipBtn}
            onClick={() => void finish(true)} disabled={applying}>
            {t("setup.skipDefault")}
          </button>
          <button type="button" className={s.nextBtn}
            onClick={isLast ? () => void finish() : advance}
            disabled={applying}>
            {applying ? t("setup.saving") : isLast ? t("setup.start") : t("setup.next")}
          </button>
        </div>
      </div>
    </div>
  );
}
