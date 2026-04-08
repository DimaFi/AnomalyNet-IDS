import i18n from "i18next";
import { initReactI18next } from "react-i18next";

const resources = {
  ru: {
    translation: {
      appTitle: "Traffic Analysis Console",
      appSubtitle: "Локальный центр анализа сетевого трафика и ML-пайплайна",
      nav: {
        dashboard: "Дашборд",
        stream: "Поток",
        models: "Модели",
        settings: "Настройки"
      },
      common: {
        active: "Активно",
        idle: "Ожидание",
        warning: "Предупреждение",
        error: "Ошибка",
        normal: "Норма",
        anomaly: "Аномалия"
      },
      dashboard: {
        title: "Обзор системы",
        status: "Статус сервиса",
        mode: "Режим",
        activeModel: "Активная модель",
        retention: "Хранение истории",
        latestVerdicts: "Последние вердикты",
        contract: "Версия контракта"
      },
      stream: {
        title: "Live поток flow/session",
        source: "Источник",
        route: "Маршрут",
        protocol: "Протокол",
        volume: "Объём",
        verdict: "Вердикт",
        score: "Оценка",
        blockIp: "Заблокировать IP",
        blocked: "Заблокирован"
      },
      models: {
        title: "Реестр моделей",
        profile: "Профиль признаков",
        provider: "Провайдер",
        activate: "Активировать",
        active: "Активна"
      },
      settings: {
        title: "Настройки приложения",
        subtitle: "Локальные предпочтения, политика хранения и режим захвата",
        groupGeneral: "Общие",
        groupCapture: "Захват трафика",
        groupCatboost: "Модель CatBoost",
        language: "Язык",
        theme: "Тема",
        runMode: "Режим запуска",
        retention: "Хранение истории, дней",
        capture: "Захват включён",
        autostart: "Автостарт потока",
        interfaceName: "Сетевой интерфейс",
        catboostThreshold: "Порог обнаружения",
        catboostModelDir: "Путь к модели (model.cbm)",
        preprocessingDir: "Путь к артефактам предобработки",
        autoBlock: "Автоматически блокировать атаки"
      }
    }
  },
  en: {
    translation: {
      appTitle: "Traffic Analysis Console",
      appSubtitle: "Local network traffic and ML pipeline analysis center",
      nav: {
        dashboard: "Dashboard",
        stream: "Stream",
        models: "Models",
        settings: "Settings"
      },
      common: {
        active: "Active",
        idle: "Idle",
        warning: "Warning",
        error: "Error",
        normal: "Normal",
        anomaly: "Anomaly"
      },
      dashboard: {
        title: "System overview",
        status: "Service status",
        mode: "Mode",
        activeModel: "Active model",
        retention: "History retention",
        latestVerdicts: "Latest verdicts",
        contract: "Contract version"
      },
      stream: {
        title: "Live flow/session stream",
        source: "Source",
        route: "Route",
        protocol: "Protocol",
        volume: "Volume",
        verdict: "Verdict",
        score: "Score",
        blockIp: "Block IP",
        blocked: "Blocked"
      },
      models: {
        title: "Model registry",
        profile: "Feature profile",
        provider: "Provider",
        activate: "Activate",
        active: "Active"
      },
      settings: {
        title: "Application settings",
        subtitle: "Local preferences, retention policy and capture mode",
        groupGeneral: "General",
        groupCapture: "Traffic capture",
        groupCatboost: "CatBoost model",
        language: "Language",
        theme: "Theme",
        runMode: "Run mode",
        retention: "History retention, days",
        capture: "Capture enabled",
        autostart: "Stream autostart",
        interfaceName: "Network interface",
        catboostThreshold: "Detection threshold",
        catboostModelDir: "Model path (model.cbm)",
        preprocessingDir: "Preprocessing artifacts path",
        autoBlock: "Auto-block detected attacks"
      }
    }
  }
} as const;

i18n.use(initReactI18next).init({
  resources,
  lng: "ru",
  fallbackLng: "en",
  interpolation: { escapeValue: false }
});

export default i18n;
