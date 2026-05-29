# AnomalyNet — GUI

> Система обнаружения сетевых вторжений с локальным веб-интерфейсом.  
> Работает по умолчанию на моделях CatBoost, обученных на датасетах CIC IoT 2023/2024.

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=black)
![TypeScript](https://img.shields.io/badge/TypeScript-5.6-3178C6?logo=typescript&logoColor=white)
![CatBoost](https://img.shields.io/badge/CatBoost-ML-yellow)
![Platform](https://img.shields.io/badge/Платформа-Linux%20%7C%20Windows-blue)
![License](https://img.shields.io/badge/License-MIT-green)

🇬🇧 [English version](README.md)

---

## Описание

AnomalyNet захватывает живой сетевой трафик, извлекает CICFlowMeter-совместимые признаки из каждого потока и классифицирует его каскадом моделей CatBoost — от быстрого бинарного фильтра до детального классификатора из 8 классов атак. Всё работает локально: никаких облаков, никакой телеметрии.

**v2.0.0** добавляет полную кросс-платформенную поддержку: захват трафика на Windows через Npcap, блокировка через netsh, обнаружение устройств через ARP на обеих платформах, capability-aware интерфейс.

ML-модели находятся в отдельном репозитории: [AnomalyNet-ml](https://github.com/DimaFi/AnomalyNet-ml).

---

## Поддержка платформ

| Функция | Linux | Windows |
|---|---|---|
| Захват трафика | Scapy AsyncSniffer (root) | Npcap-адаптер (Admin) |
| Блокировка IP | iptables ANOMALYNET chains | netsh advfirewall |
| Откат правил | iptables-save/restore | — |
| Активный ARP-скан | Scapy srp (root) | Scapy + Npcap (Admin) |
| Пассивное обнаружение | — | `arp -a` fallback |
| Автозапуск | systemd service | Task Scheduler |
| Demo-режим | ✓ (без root) | ✓ (без Admin) |

Интерфейс автоматически определяет возможности платформы и показывает статус в Settings. Недоступные функции отключаются с объяснением причины.

---

## Возможности

| Функция | Описание |
|---|---|
| **Живой захват** | Scapy на Linux; Npcap на Windows; mock-симуляция в demo-режиме |
| **Агрегация потоков** | Отслеживание по 5-tuple, таймаут 60 с, мгновенное закрытие по FIN/RST |
| **CICFlowMeter-признаки** | 71 признак: длительность, IAT-статистика, флаги, размеры окон, active/idle |
| **Каскадное обнаружение** | Бинарный фильтр Stage 1 → многоклассовый Stage 2/3 |
| **Классы атак** | Benign · DoS · DDoS · Recon · BruteForce · WebAttack · Bot · Spoofing |
| **Блокировка IP** | Ручная/авто-блокировка: iptables (Linux) или netsh (Windows); белый список |
| **DNS-мониторинг** | Пассивный перехват, обнаружение DGA, репутация доменов, поведенческие алерты |
| **TLS fingerprinting** | JA4-совместимые fingerprints с поведенческим профилированием и репутацией |
| **Карта сети** | ARP-обнаружение устройств, OUI-база производителей, D3 force-граф |
| **Device-aware routing** | IoT-устройства → IoT-пайплайн; ПК/телефоны → General Network |
| **Toast-уведомления** | Warning/anomaly с IP источника и классом атаки |
| **История** | Ежедневные NDJSON-логи с настраиваемым хранением (1–30 дней) |
| **Экспорт** | EVE JSON и CSV с фильтром по времени и приоритету |
| **Тема и язык** | Светлая / тёмная тема · Русский / английский интерфейс |
| **Свои модели** | Добавьте адаптер в `plugins/` — без изменений кода |
| **Удалённое управление** | Полноценный REST API |

---

## Режимы обнаружения

| Пресет | Пайплайн | Когда использовать |
|---|---|---|
| **Binary** | Только Stage 1 | Максимальная скорость; "атака или нет" без класса |
| **Simple Cascade** | Stage 1 → Stage 2 | Стандартный режим; 8 классов, 71 признак |
| **Advanced Cascade** | Stage 1 → Stage 3 | Оптимизирован для IoT; 46 признаков, Macro F1 = 0.82 |
| **Cascade Routed** | Stage 1 → S2 или S3 | Наилучшее покрытие; маршрутизация по протоколу |
| **General Network** | General S1 → S2 | Для ПК/серверов; обучен на CICIDS 2017 |
| **Auto** | Device-aware routing | Выбирает пайплайн по типу устройства-источника |

---

## Карта сети и обнаружение устройств

AnomalyNet автоматически строит карту устройств локальной сети и использует её для маршрутизации трафика к нужной модели.

```
Сеть
 ├─ 📷 Камера  192.168.1.10  (Hikvision)   → IoT pipeline    → Advanced Cascade
 ├─ 📡 Датчик  192.168.1.20  (Espressif)   → IoT pipeline    → Advanced Cascade
 ├─ 💻 ПК      192.168.1.30  (Microsoft)   → General pipeline → General Network
 ├─ 📱 Телефон 192.168.1.50  (Apple)       → General pipeline → General Network
 └─ 🌐 Роутер  192.168.1.1   (TP-Link)     → IoT pipeline    → Advanced Cascade
```

### ARP-обнаружение — кросс-платформенно

| Платформа | Условие | Метод | Тег |
|---|---|---|---|
| Linux | root | Scapy `srp()` активный скан | `scapy` |
| Windows | Admin + Npcap | Scapy `srp()` активный скан | `npcap` |
| Windows | Admin, нет Npcap | `arp -a` (fallback) | `arp_cache` |
| Windows | Нет Admin | `arp -a` | `arp_cache` |

---

## Логика оценки

```
predict_proba(поток) → p

p ≥ 0.85  →  anomaly   (красный алерт)
p ≥ 0.70  →  warning   (оранжевый алерт)
p <  0.70  →  normal    (нет алерта)
```

В каскадном режиме Stage 1 работает как бинарный фильтр. Атаки передаются на Stage 2/3 для классификации.

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

# 3. Фронтенд (отдельный терминал)
cd ../frontend
npm install
npm run dev
```

Открыть **http://localhost:5173** — запускается в режиме `mock`, root/Admin и модели не нужны.

---

## Установка

Есть два способа установки — выберите один:

| | **Быстрый (portable)** | **Полная системная установка** |
|---|---|---|
| Куда | работает из папки проекта | `/opt/anomalynet` · `C:\AnomalyNet` |
| Права | root/админ не нужны | root / Администратор |
| Автозапуск | на уровне пользователя (вход) | systemd / Task Scheduler |
| Linux | `bash install.sh` | `sudo bash installers/linux/install-linux.sh` |
| Windows | двойной клик `install.bat` | `installers\windows\install-windows.bat` (админ) |

### Linux — полная системная установка

```bash
sudo bash installers/linux/install-linux.sh
# Параметры (env): INTERFACE=eth0 PORT=8000 DETECTION_MODE=simple AUTO_BLOCK=false
```

**Поддерживаемые дистрибутивы:** Ubuntu/Debian · Alt Linux · Fedora · RHEL/CentOS/Rocky/AlmaLinux · Arch/Manjaro · openSUSE

Установщик:
- Устанавливает Python 3, libpcap, Node.js (NVM fallback для нестандартных дистрибутивов)
- Создаёт Python venv и устанавливает зависимости
- Собирает фронтенд (`npm run build`)
- Записывает `config/settings.json` с автоопределением интерфейса и путей к моделям
- Создаёт и включает **systemd-сервис** `anomalynet`

### Windows — полная системная установка (PowerShell от Администратора)

```powershell
powershell -ExecutionPolicy Bypass -File installers\windows\install-windows.ps1
# Параметры: -InstallDir C:\AnomalyNet -Port 8000 -InstallNpcap -AutoBlock
```

Установщик:
- Проверяет Python 3.10+, Git, Node.js 18+
- Клонирует оба репозитория в `C:\AnomalyNet\`
- Создаёт Python venv + устанавливает зависимости
- Собирает React-фронтенд
- Проверяет Npcap; опционально устанавливает (`-InstallNpcap`)
- Устанавливает машинную переменную `ANOMALYNET_APP_ROOT`
- Создаёт **задачу в Task Scheduler** (запуск при входе с максимальными правами)

### Удаление

Быстрый (portable) — из папки приложения:
```bash
bash uninstall.sh          # Linux
uninstall.bat              # Windows (двойной клик)
```

Полная системная установка:
```bash
# Linux — сохранить данные:
sudo bash installers/linux/uninstall-linux.sh
# Linux — полное удаление:
sudo bash installers/linux/uninstall-linux.sh --purge
```

```powershell
# Windows — сохранить данные:
powershell -File installers\windows\uninstall-windows.ps1
# Windows — полное удаление:
powershell -File installers\windows\uninstall-windows.ps1 -Purge
```

---

## Обновление

### Через интерфейс (рекомендуется)
Вкладка **«О программе»** → **Проверить обновления** → **Применить**.

Бэкенд автоматически:
1. `git pull` обоих репозиториев
2. `pip install` (если изменились зависимости)
3. `npm run build` (если изменился фронтенд)
4. Перезапускает сервис при изменении бэкенда

### Повторный запуск установщика
```bash
sudo bash installers/linux/install-linux.sh   # идемпотентный — безопасно запускать повторно
```

---

## Архитектура

```
AppCode/
├── backend/                FastAPI + Uvicorn
│   └── app/
│       ├── api/            REST-эндпоинты, SSE стрим, update/reinstall/uninstall
│       ├── capture/        Scapy-адаптер (Linux), Npcap-адаптер (Windows), FlowAggregator
│       ├── discovery/      ARP-сканер, OUI-база, классификатор устройств, DeviceTracker
│       │   └── backends/   ArpBackend ABC, LinuxArpBackend, WindowsArpBackend (dual-mode)
│       ├── dns/            DNS-монитор, DGA-детектор, репутация доменов
│       ├── tls/            JA4-fingerprinting, поведенческий монитор, репутация
│       ├── model/          CatBoost-адаптер, каскадные адаптеры, фабрика
│       ├── platform/       Уровень платформенной абстракции
│       │   ├── base/       PlatformCapabilities, AbstractServiceManager, BaseFirewall
│       │   ├── linux/      SystemdManager, LinuxFirewall, linux_capabilities()
│       │   └── windows/    WindowsTaskSchedulerManager, WindowsNetshFirewall, windows_capabilities()
│       ├── security/       Блокировщик IP (iptables / netsh), GeoIP, репутация JA4
│       └── pipeline/       Оркестрация, авто-блокировка, авто-разблокировка
├── frontend/               Vite + React 18 + Zustand + i18next
│   └── src/
│       ├── app/            App-оболочка, store (capabilities), роутер, типы
│       ├── features/       Dashboard · Stream · Карта сети · Плагины · Settings · О программе
│       └── components/     Toast, TopBar, ModelPresetPicker
├── config/
│   ├── settings.json       Конфигурация
│   ├── models_registry.json  Доступные модели
│   └── model_presets.json  Пресеты обнаружения
├── installers/             Все установщики и вспомогательные скрипты
│   ├── linux/              install-linux.sh · uninstall-linux.sh (полная установка)
│   ├── windows/            install-windows.ps1/.bat · uninstall-windows.ps1 · build_installer.ps1
│   ├── shared/             download_oui.py (помощник для базы OUI)
│   ├── legacy/             setup.sh (старый curl-установщик) · run_*.ps1 (dev-помощники)
│   └── README.md           Документация по установке
├── install.sh · install.bat        Быстрая portable-установка (из этой папки)
├── uninstall.sh · uninstall.bat    Быстрое portable-удаление
└── launch.sh · launch.bat · launch.vbs   Лаунчеры (для ярлыков и автозапуска)
```

---

## Конфигурация

Редактировать `config/settings.json` или через вкладку **Настройки** в интерфейсе:

| Ключ | По умолчанию | Описание |
|---|---|---|
| `run_mode` | `"mock"` | `"mock"` · `"linux_live"` · `"windows_live"` |
| `active_model_id` | `"mock-default"` | ID модели из `models_registry.json` |
| `detection_mode` | `"simple"` | `"simple"` · `"advanced"` |
| `catboost_threshold` | `0.70` | Порог аномалии |
| `catboost_model_dir` | `""` | Путь к Stage 1 `model.cbm` |
| `preprocessing_artifacts_dir` | `""` | Путь к артефактам Stage 1 |
| `catboost_secondary_model_dir` | `""` | Путь к Stage 2 или Stage 3 модели |
| `interface_name` | `""` | Интерфейс для захвата |
| `auto_block` | `false` | Авто-блокировка аномальных IP |
| `whitelist_ips` | `[]` | IP которые никогда не блокируются |
| `retention_days` | `7` | Хранение истории (дни) |

---

## REST API (основные эндпоинты)

| Метод | Путь | Описание |
|---|---|---|
| `GET` | `/api/health` | Статус сервиса |
| `GET` | `/api/capabilities` | Возможности платформы (admin, npcap, firewall...) |
| `GET` | `/api/stream/snapshot` | Текущий буфер обнаружения |
| `GET` | `/api/history` | История событий с пагинацией |
| `GET` | `/api/export` | Скачать отчёт (EVE JSON или CSV) |
| `PUT` | `/api/settings` | Обновить настройки |
| `POST` | `/api/model-presets/apply/{id}` | Применить пресет |
| `POST` | `/api/block` | Заблокировать IP |
| `GET` | `/api/devices` | Карта устройств |
| `POST` | `/api/devices/scan` | Запустить ARP-сканирование |
| `GET` | `/api/update/check` | Проверить обновления (git) |
| `POST` | `/api/update/apply` | Применить обновления |
| `POST` | `/api/update/restart` | Перезапустить сервис |
| `POST` | `/api/update/reinstall` | Переустановить (pull + pip + npm) |
| `POST` | `/api/update/uninstall` | Удалить приложение |

---

## ML-модели

Модели и скрипты обучения: **[AnomalyNet-ml](https://github.com/DimaFi/AnomalyNet-ml)**

```
AnomalyNet-ml/
├── model/                   Stage 1 binary — CIC IoT 2024, 71 признак, F1 = 99.4%
├── artifacts/               Stage 1 scaler + feature contract
├── stage2_multiclass/       8-классовый — 71 признак, обучен с CICIDS 2017/2018
├── stage3_cic2023/          IoT multiclass — 46 признаков, Macro F1 = 0.82
└── general_network/         General Network — CICIDS 2017 (ПК/серверный трафик)
```

---

## Лицензия

MIT — см. файл `LICENSE`.
