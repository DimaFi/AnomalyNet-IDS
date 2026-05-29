import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useAppStore } from "../app/store";
import type { ToastItem } from "../app/types";
import { useBlockIp } from "../lib/useBlockIp";
import styles from "./Toast.module.css";

interface ToastProps {
  toast: ToastItem;
}

const AUTOHIDE_MS: Record<string, number> = {
  anomaly: 10_000,
  warning: 6_000,
  normal: 4_000,
};

export function Toast({ toast }: ToastProps) {
  const dismissToast = useAppStore((state) => state.dismissToast);
  const blockedIps = useAppStore((state) => state.blockedIps);
  const blockIp = useBlockIp();
  const [leaving, setLeaving] = useState(false);

  const isBlocked = blockedIps.has(toast.src_ip);
  const delay = AUTOHIDE_MS[toast.level] ?? 6_000;

  // Auto-dismiss
  useEffect(() => {
    const timer = setTimeout(() => {
      setLeaving(true);
      setTimeout(() => dismissToast(toast.id), 200);
    }, delay);
    return () => clearTimeout(timer);
  }, [toast.id, delay, dismissToast]);

  const handleDismiss = () => {
    setLeaving(true);
    setTimeout(() => dismissToast(toast.id), 180);
  };

  const handleBlock = async () => {
    await blockIp(toast.src_ip, toast.event_id);
  };

  const { t } = useTranslation();
  const levelLabel = toast.level === "anomaly" ? t("toast.attack") : t("toast.suspicion");
  const badgeText  = toast.attack_class
    ? `${levelLabel} · ${toast.attack_class}`
    : levelLabel;

  return (
    <div
      className={[
        styles.toast,
        styles[toast.level],
        leaving ? styles.toastLeaving : "",
      ].join(" ")}
    >
      <div className={styles.header}>
        <span className={styles.badge}>{badgeText}</span>
        <button className={styles.closeBtn} onClick={handleDismiss} title={t("toast.close")}>
          ×
        </button>
      </div>

      <p className={styles.title}>{toast.title}</p>
      <p className={styles.details}>{toast.details}</p>

      <div className={styles.footer}>
        <span className={styles.ip}>{toast.src_ip}</span>
        {isBlocked ? (
          <span className={styles.blockedLabel}>{t("toast.blocked")}</span>
        ) : (
          <button className={styles.blockBtn} onClick={handleBlock}>
            {t("toast.blockBtn")}
          </button>
        )}
      </div>
    </div>
  );
}
