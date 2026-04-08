import { useTranslation } from "react-i18next";
import type { StatusLevel, VerdictLabel } from "../app/types";
import { statusTone } from "../lib/format";
import styles from "./StatusPill.module.css";

export function StatusPill({ value }: { value: StatusLevel | VerdictLabel }) {
  const { t } = useTranslation();
  const tone = statusTone(value);
  return <span className={`${styles.pill} ${styles[tone]}`}>{t(`common.${value}`, value)}</span>;
}

