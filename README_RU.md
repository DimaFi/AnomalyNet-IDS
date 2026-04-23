# AnomalyNet — GUI

> Система обнаружения сетевых вторжений с локальным веб-интерфейсом.  
> Работает по умолчанию на моделях CatBoost, обученных на датасетах CIC IoT 2023/2024.

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=black)
![TypeScript](https://img.shields.io/badge/TypeScript-5.6-3178C6?logo=typescript&logoColor=white)
![CatBoost](https://img.shields.io/badge/CatBoost-ML-yellow)
![License](https://img.shields.io/badge/License-MIT-green)

🇬🇧 [English version](README.md)

---

## Описание

AnomalyNet захватывает живой сетевой трафик, по умолчанию извлекает 71 CICFlowMeter-совместимый признак из каждого потока и классифицирует его каскадом моделей CatBoost — от быстрого бинарного фильтра до детального классификатора из 8 классов атак. Всё работает локально: никаких облаков, никакой телеметрии.

ML-модели находятся в отдельном репозитории: [AnomalyNet-ml](https://github.com/DimaFi/AnomalyNet-ml).

---

## Возможности

| Функция | Описание |
|---|---|
| **Живой захват** | Scapy AsyncSniffer на любом Linux-интерфейсе; mock-симуляция на Windows/demo |
| **Агрегация потоков** | Отслеживание по 5-tuple, таймаут 60 с, мгновенное закрытие по FIN/RST |
| **71 CICFlowMeter-признак** | Длительность, IAT-статистика, счётчики флагов, размеры окон, активные/простойные периоды |
| **Каскадное обнаружение** | Бинарный фильтр Stage 1 → многоклассовый Stage 2/3 (маршрутизация по протоколу) |
| **Классы атак** | Benign · DoS · DDoS · Recon · BruteForce · WebAttack · Bot · Spoofing |
| **Блокировка IP** | Ручная или авто-блокировка через iptables с настраиваемым белым списком |
| **Toast-уведомления** | Предупреждения и оповещения об аномалиях с IP источника и классом атаки |
| **История** | Ежедневные NDJSON-логи с настраиваемым хранением (1–30 дней) |
| **Экспорт** | Скачать полный отчёт (сводка + список событий) в формате JSON |
| **Тема и язык** | Светлая / тёмная тема · Русский / английский интерфейс |
| **Подключение своих моделей** | Добавьте совместимый адаптер в `plugins/` — модель появится в интерфейсе без изменений в коде |
| **Удалённое управление** | Полноценный REST API — управление настройками, моделями, блокировкой IP и экспортом с любого устройства в сети |

---

## Режимы обнаружения

AnomalyNet поддерживает четыре пресета, которые выбираются из интерфейса:

| Пресет | Пайплайн | Когда использовать |
|---|---|---|
| **Binary** | Только Stage 1 | Максимальная скорость; "атака или нет", без класса |
| **Simple Cascade** | Stage 1 → Stage 2 | Стандартный режим; 8 классов, те же 71 признак |
| **Advanced Cascade** | Stage 1 → Stage 3 | Оптимизирован для IoT; 46 признаков CIC-IoT-2023, Macro F1 = 0.82 |
| **Cascade Routed** | Stage 1 → Stage 2 или Stage 3 | Наилучшее покрытие; маршрутизация по протоколу (TCP→S2, UDP/ICMP→S3) |

---

## Архитектура

```
AppCode/
├── backend/                FastAPI + Uvicorn
│   └── app/
│       ├── api/            REST-эндпоинты + SSE-поток
│       ├── capture/        Scapy-адаптер, FlowAggregator, вычисление признаков
│       ├── model/          CatBoost-адаптер, каскадные адаптеры, фабрика
│       ├── preprocess/     Пайплайн признаков, скейлер, загрузка артефактов
│       ├── pipeline/       Оркестрирующий сервис, логика авто-блокировки
│       └── storage/        JSON-хранилище (настройки, история, реестр)
├── frontend/               Vite + React 18 + Zustand + i18next
│   └── src/
│       ├── app/            Оболочка приложения, store, роутер, типы
│       ├── features/       Dashboard · Stream · Plugins · Settings · About
│       └── components/     Toast, TopBar, общие компоненты
├── config/
│   ├── settings.json       Конфигурация приложения
│   ├── models_registry.json  Метаданные доступных моделей
│   └── model_presets.json  Пресеты обнаружения в один клик
├── shared/contracts/       JSON-файлы контрактов признаков
├── plugins/                Директория плагинов
└── install.sh              Установщик одной командой (мульти-дистрибутивный Linux)
```

---

## Быстрый старт (разработка)

**Требования:** Python 3.10+, Node.js 18+

```bash
# 1. Клонировать
git clone https://github.com/DimaFi/AnomalyNet-gui
cd AnomalyNet-gui/AppCode

# 2. Бэкенд
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# 3. Фронтенд (в отдельном терминале)
cd ../frontend
npm install
npm run dev
```

Открыть **http://localhost:5173** — запускается в режиме `mock`, root-права и модели не нужны.

---

## Установка на Linux (продакшн)

Установщик одной командой с автоматическим определением дистрибутива:

```bash
curl -fsSL https://raw.githubusercontent.com/DimaFi/AnomalyNet-gui/main/install.sh | sudo bash
```

Репозитории клонируются автоматически. Для обновления существующей установки запустите ту же команду ещё раз.

**Поддерживаемые дистрибутивы:** Ubuntu/Debian · Alt Linux (Sisyphus/p10) · Fedora · RHEL/CentOS/Rocky/AlmaLinux · Arch/Manjaro · openSUSE

Установщик:
- Устанавливает системные зависимости (Python 3, libpcap, Node.js через NVM)
- Создаёт Python-окружение и устанавливает зависимости бэкенда
- Собирает продакшн-сборку фронтенда
- Настраивает и включает **systemd-сервис** (`anomalynet.service`)

После установки разместите ML-артефакты в `/opt/anomalynet-ml/` (структуру см. в [AnomalyNet-ml](https://github.com/DimaFi/AnomalyNet-ml)), затем:

```bash
sudo systemctl restart anomalynet
```

Откройте интерфейс по адресу **http://\<ip-сервера\>:8000**

> **Примечание:** Живой захват требует root или `CAP_NET_RAW`. Systemd-сервис запускается от root по умолчанию.

---

## Конфигурация

Отредактируйте `config/settings.json` (или воспользуйтесь вкладкой Настройки в интерфейсе):

| Ключ | По умолчанию | Описание |
|---|---|---|
| `run_mode` | `"mock"` | `"mock"` · `"linux_live"` |
| `active_model_id` | `"mock-default"` | ID модели из `models_registry.json` |
| `detection_mode` | `"simple"` | `"simple"` · `"advanced"` |
| `catboost_threshold` | `0.70` | Порог аномалии (0.70 = warning, 0.85 = anomaly) |
| `catboost_model_dir` | `""` | Путь к директории с `model.cbm` (Stage 1) |
| `preprocessing_artifacts_dir` | `""` | Путь к артефактам Stage 1 (скейлер, контракт) |
| `catboost_secondary_model_dir` | `""` | Путь к модели Stage 2 или Stage 3 |
| `catboost_stage3_model_dir` | `""` | Путь к модели Stage 3 (только Cascade Routed) |
| `interface_name` | `"eth0"` | Интерфейс захвата (только `linux_live`) |
| `interface_names` | `[]` | Список интерфейсов (переопределяет `interface_name`) |
| `auto_block` | `false` | Авто-блокировка IP аномалий через iptables |
| `auto_block_level` | `"anomaly"` | Порог блокировки: `"anomaly"` или `"warning"` |
| `auto_unblock` | `false` | Автоматически снимать блокировку после cooldown |
| `auto_unblock_cooldown_min` | `10` | Время до авто-разблокировки (минуты) |
| `whitelist_ips` | `[]` | IP-адреса, которые никогда не блокируются |
| `retention_days` | `7` | Хранение логов истории (дни) |

---

## REST API

| Метод | Путь | Описание |
|---|---|---|
| `GET` | `/api/health` | Состояние сервиса и активный режим |
| `GET` | `/api/stream/snapshot` | Текущий буфер обнаружения (последние N событий) |
| `GET` | `/api/history` | История событий с пагинацией |
| `GET` | `/api/export` | Скачать полный отчёт в формате JSON |
| `GET` | `/api/debug/stats` | Статистика: лейблы, протоколы, топ IP |
| `POST` | `/api/debug/infer` | Пакетный инференс на заранее вычисленных признаках |
| `GET` | `/api/settings` | Текущие настройки |
| `PUT` | `/api/settings` | Обновить настройки |
| `GET` | `/api/models` | Реестр моделей |
| `POST` | `/api/models/select` | Переключить активную модель |
| `GET` | `/api/model-presets` | Пресеты обнаружения |
| `POST` | `/api/model-presets/apply/{id}` | Применить пресет |
| `POST` | `/api/block` | Заблокировать IP через iptables |
| `GET` | `/api/interfaces` | Список доступных сетевых интерфейсов |
| `GET` | `/api/fs/ls` | Браузер директорий (для выбора пути к модели) |

---

## Структура ML-проекта

ML-модели и скрипты обучения находятся в отдельном репозитории:

**[AnomalyNet-ml](https://github.com/DimaFi/AnomalyNet-ml)**

```
AnomalyNet-ml/
├── stage1/          Бинарный детектор — CIC IoT 2024, 71 признак, F1 = 99.4%
├── stage2/          8-классовый мультиклассовый — те же 71 признак
├── stage3/          IoT-мультиклассовый — 46 признаков CIC-IoT-2023, Macro F1 = 0.82
└── stage4/          Расширенные эксперименты с каскадом
```

Ожидаемая структура на сервере:

```
/opt/anomalynet-ml/
├── model/           model.cbm для stage1
├── artifacts/       скейлер и контракт признаков stage1
├── stage2_multiclass/models/catboost/   model.cbm + class_mapping.json
└── stage3_cic2023/
    ├── models/catboost/   model.cbm для stage3
    └── artifacts/         скейлер и контракт признаков stage3
```

---

## Логика оценки

```
predict_proba(flow) → p

p ≥ 0.85  →  anomaly   (красный алерт)
p ≥ 0.70  →  warning   (оранжевый алерт)
p <  0.70  →  normal    (без алерта)
```

В каскадном режиме Stage 1 — бинарный фильтр. Потоки, классифицированные как атаки, передаются в Stage 2/3 для определения класса (DoS, DDoS, Recon, BruteForce, WebAttack, Bot, Spoofing).

---

## Подключение своих моделей

AnomalyNet поддерживает подключение сторонних моделей без изменений в коде:

1. Поместите адаптер модели в директорию `plugins/`, реализовав стандартный интерфейс
2. Перезапустите сервис — модель автоматически появится в реестре **Моделей** и в интерфейсе настроек
3. Выберите её через UI или через `POST /api/models/select`

Это позволяет подключать собственные или сторонние модели (scikit-learn, PyTorch, ONNX и др.) рядом со встроенным CatBoost-пайплайном.

---

## Удалённое управление

Бэкенд предоставляет полноценный REST API — управлять системой можно с любого устройства в той же сети, без SSH:

```bash
# Проверить статус
curl http://<ip-сервера>:8000/api/health

# Переключить пресет обнаружения
curl -X POST http://<ip-сервера>:8000/api/model-presets/apply/cascade-routed

# Заблокировать подозрительный IP
curl -X POST http://<ip-сервера>:8000/api/block \
     -H "Content-Type: application/json" \
     -d '{"ip_address": "10.0.0.5"}'

# Скачать полный отчёт
curl http://<ip-сервера>:8000/api/export -o report.json
```

Веб-интерфейс также полностью доступен удалённо — откройте `http://<ip-сервера>:8000` в любом браузере.

---

## Технологический стек

**Бэкенд**
- [FastAPI](https://fastapi.tiangolo.com/) + Uvicorn — асинхронный REST API
- [Scapy](https://scapy.net/) — захват пакетов на уровне сети
- [CatBoost](https://catboost.ai/) — инференс градиентного бустинга
- NumPy · Pandas · Joblib · psutil

**Фронтенд**
- [React 18](https://react.dev/) + [TypeScript](https://www.typescriptlang.org/)
- [Zustand](https://zustand-demo.pmnd.rs/) — управление состоянием
- [Vite](https://vitejs.dev/) — инструмент сборки
- [i18next](https://www.i18next.com/) — интернационализация (RU/EN)

---

## Лицензия

[MIT](LICENSE)
