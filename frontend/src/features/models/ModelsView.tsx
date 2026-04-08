import { useTranslation } from "react-i18next";
import { useAppStore } from "../../app/store";
import { api } from "../../lib/api";
import styles from "../panel.module.css";

export function ModelsView() {
  const { t } = useTranslation();
  const models = useAppStore((state) => state.models);
  const settings = useAppStore((state) => state.settings);
  const setModels = useAppStore((state) => state.setModels);
  const setSettings = useAppStore((state) => state.setSettings);

  async function activate(modelId: string) {
    try {
      const registry = await api.selectModel(modelId);
      setModels(registry);
      if (settings) {
        setSettings({ ...settings, active_model_id: modelId });
      }
    } catch {
      if (models) {
        setModels({
          ...models,
          active_model_id: modelId,
          items: models.items.map((item) => ({
            ...item,
            status: item.model_id === modelId ? "active" : "idle"
          }))
        });
      }
      if (settings) {
        setSettings({ ...settings, active_model_id: modelId });
      }
    }
  }

  return (
    <section className={styles.panel}>
      <div className={styles.panelHeader}>
        <div>
          <h2>{t("models.title")}</h2>
          <p>Registry-first model onboarding with contract-aware descriptors.</p>
        </div>
      </div>
      <div className={styles.cardList}>
        {models?.items.map((item) => {
          const isActive = models.active_model_id === item.model_id;
          return (
            <article key={item.model_id} className={styles.modelCard}>
              <div className={styles.modelHeader}>
                <div>
                  <h3>{item.display_name}</h3>
                  <p>{item.description}</p>
                </div>
                <span className={styles.versionTag}>{item.version}</span>
              </div>
              <div className={styles.modelMeta}>
                <span>{t("models.provider")}: {item.provider}</span>
                <span>{t("models.profile")}: {item.profile_name}</span>
                <span>Contract: {item.contract_version}</span>
              </div>
              <button className={styles.primaryButton} disabled={isActive} onClick={() => void activate(item.model_id)}>
                {isActive ? t("models.active") : t("models.activate")}
              </button>
            </article>
          );
        })}
      </div>
    </section>
  );
}
