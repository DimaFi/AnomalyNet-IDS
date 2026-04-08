import { useTranslation } from "react-i18next";
import { useAppStore } from "../../app/store";
import { StatusPill } from "../../components/StatusPill";
import { formatBytes } from "../../lib/format";
import { useBlockIp } from "../../lib/useBlockIp";
import styles from "../panel.module.css";
import blockStyles from "./StreamView.module.css";

export function StreamView() {
  const { t } = useTranslation();
  const stream     = useAppStore((state) => state.stream);
  const blockedIps = useAppStore((state) => state.blockedIps);
  const blockIp    = useBlockIp();

  return (
    <section className={styles.panel}>
      <div className={styles.panelHeader}>
        <div>
          <h2>{t("stream.title")}</h2>
          <p className={styles.panelSubtitle}>
            {t("stream.subtitle", "Потоки в реальном времени — признаки, предсказания, статус")}
          </p>
        </div>
        <span className={blockStyles.counter}>
          {stream.length} {t("stream.events", "событий")}
        </span>
      </div>

      <div className={styles.tableWrap}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th>{t("stream.source")}</th>
              <th>{t("stream.route")}</th>
              <th>{t("stream.protocol")}</th>
              <th>{t("stream.volume")}</th>
              <th style={{ minWidth: 80 }}>Score</th>
              <th>{t("stream.verdict")}</th>
              <th style={{ width: 120 }}>{t("stream.actions", "Действия")}</th>
            </tr>
          </thead>
          <tbody>
            {stream.map((item) => {
              const isAttack  = item.inference.label !== "normal";
              const isBlocked = blockedIps.has(item.event.src_ip);

              return (
                <tr
                  key={item.event.event_id}
                  className={isAttack ? blockStyles.attackRow : ""}
                >
                  <td>{item.event.source}</td>
                  <td className={blockStyles.route}>
                    <span className={blockStyles.ip}>{item.event.src_ip}</span>
                    <span className={blockStyles.port}>:{item.event.src_port}</span>
                    <span className={blockStyles.arrow}>→</span>
                    <span className={blockStyles.ip}>{item.event.dst_ip}</span>
                    <span className={blockStyles.port}>:{item.event.dst_port}</span>
                  </td>
                  <td>{item.event.protocol}</td>
                  <td>
                    {item.event.packet_count} / {formatBytes(item.event.byte_count)}
                  </td>
                  <td className={blockStyles.scoreCell}>
                    <span
                      className={[
                        blockStyles.score,
                        item.inference.score >= 0.85 ? blockStyles.scoreDanger
                          : item.inference.score >= 0.7 ? blockStyles.scoreWarn
                          : blockStyles.scoreOk,
                      ].join(" ")}
                    >
                      {item.inference.score.toFixed(2)}
                    </span>
                  </td>
                  <td>
                    <StatusPill value={item.inference.label} />
                  </td>
                  <td>
                    {isAttack && (
                      isBlocked ? (
                        <span className={blockStyles.blockedBadge}>
                          Заблокирован
                        </span>
                      ) : (
                        <button
                          className={blockStyles.blockBtn}
                          onClick={() => blockIp(item.event.src_ip, item.event.event_id)}
                          title={`Заблокировать ${item.event.src_ip}`}
                        >
                          Блокировать
                        </button>
                      )
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {!stream.length && (
          <p className={styles.emptyState}>
            {t("stream.empty", "Нет событий. Ожидание трафика...")}
          </p>
        )}
      </div>
    </section>
  );
}
