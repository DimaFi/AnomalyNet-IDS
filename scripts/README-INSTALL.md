# AnomalyNet IDS — Руководство по установке

## Быстрый старт

### Linux
```bash
sudo bash install.sh
# или напрямую:
sudo bash scripts/install-linux.sh
```

### Windows (PowerShell от Администратора)
```powershell
powershell -ExecutionPolicy Bypass -File scripts\install-windows.ps1
```

---

## Linux

### Требования
- Один из дистрибутивов: Ubuntu 22.04/24.04, Debian 12, Alt Linux p10, CentOS/RHEL 8+, Rocky Linux, Arch Linux
- Python 3.10+ (устанавливается автоматически)
- Node.js 18+ (устанавливается автоматически)
- Git, curl
- RAM ≥ 2 ГБ (на VPS с 2 ГБ скрипт автоматически создаёт swap)
- Права root

### Параметры (env vars)
| Переменная | По умолчанию | Описание |
|-----------|-------------|---------|
| `INSTALL_DIR` | `/opt/anomalynet` | Каталог установки |
| `INTERFACE` | auto | Сетевой интерфейс для захвата |
| `PORT` | `8000` | Порт веб-интерфейса |
| `DETECTION_MODE` | `simple` | `simple` или `advanced` |
| `AUTO_BLOCK` | `false` | Автоблокировка атак |

Пример с параметрами:
```bash
sudo INTERFACE=enp3s0 PORT=9000 DETECTION_MODE=advanced bash scripts/install-linux.sh
```

### Что делает установщик
1. Определяет дистрибутив и устанавливает системные пакеты
2. Создаёт swap при нехватке RAM (VPS)
3. Открывает порт в UFW
4. Клонирует или обновляет AnomalyNet-gui и AnomalyNet-ml
5. Создаёт структуру моделей в `/opt/anomalynet/models/`
6. Создаёт Python venv + устанавливает зависимости
7. Собирает React-фронтенд (npm run build)
8. Записывает `config/settings.json` и `config/model_presets.json`
9. Создаёт и запускает systemd-сервис `anomalynet`

### Управление сервисом
```bash
systemctl status anomalynet
systemctl start anomalynet
systemctl stop anomalynet
systemctl restart anomalynet
journalctl -u anomalynet -f      # логи в реальном времени
```

### Обновление
Через веб-интерфейс (вкладка «О программе»): кнопка «Проверить обновления» → «Применить».

Или вручную:
```bash
sudo bash scripts/install-linux.sh   # идемпотентный — безопасно запускать повторно
```

### Удаление
```bash
# Удалить сервис, сохранить данные:
sudo bash scripts/uninstall-linux.sh

# Полное удаление включая /opt/anomalynet:
sudo bash scripts/uninstall-linux.sh --purge
```

---

## Windows

### Требования
- Windows 10/11 (x64)
- Python 3.10+ — добавлен в PATH ([скачать](https://www.python.org/downloads/))
- Git — добавлен в PATH ([скачать](https://git-scm.com/))
- Node.js 18+ с npm ([скачать](https://nodejs.org/))
- Права Администратора
- RAM ≥ 4 ГБ

### Параметры
| Параметр | По умолчанию | Описание |
|---------|-------------|---------|
| `-InstallDir` | `C:\AnomalyNet` | Каталог установки |
| `-Port` | `8000` | Порт веб-интерфейса |
| `-InstallNpcap` | — | Скачать и установить Npcap |
| `-AutoBlock` | — | Включить автоблокировку |

```powershell
# Пример с параметрами:
powershell -ExecutionPolicy Bypass -File scripts\install-windows.ps1 `
    -InstallDir "D:\AnomalyNet" -Port 9000 -InstallNpcap
```

### Что делает установщик
1. Проверяет наличие Python, Git, Node.js
2. Клонирует или обновляет репозитории в `C:\AnomalyNet\`
3. Копирует модели в `C:\AnomalyNet\models\`
4. Создаёт Python venv и устанавливает зависимости
5. Собирает React-фронтенд
6. Проверяет Npcap (опционально устанавливает)
7. Записывает `config/settings.json`
8. Устанавливает системные переменные `ANOMALYNET_APP_ROOT`, `ANOMALYNET_MODELS_ROOT`
9. Создаёт задачу в Task Scheduler (автозапуск при входе)
10. Запускает сервис

### Npcap и возможности
| Условие | ARP-сканирование | Блокировка IP |
|---------|-----------------|---------------|
| Admin + Npcap | Активное (Scapy srp) | netsh ✓ |
| Admin, нет Npcap | Пассивное (arp -a) | netsh ✓ |
| Без Admin | Пассивное (arp -a) | ✗ |

Npcap нужен только для активного ARP-сканирования. Блокировка работает без него.

### Управление
```powershell
# Запустить вручную (если не запустился автоматически):
schtasks /run /tn AnomalyNet

# Остановить:
Stop-Process -Name python -ErrorAction SilentlyContinue  # ОСТОРОЖНО — останавливает все python

# Просмотр статуса задачи:
schtasks /query /tn AnomalyNet /fo LIST
```

### Удаление
```powershell
# Удалить задачу и правила, сохранить данные:
powershell -ExecutionPolicy Bypass -File scripts\uninstall-windows.ps1

# Полное удаление включая C:\AnomalyNet:
powershell -ExecutionPolicy Bypass -File scripts\uninstall-windows.ps1 -Purge
```

---

## Веб-интерфейс — кнопки управления

После установки перейдите на вкладку **«О программе»**:

| Кнопка | Действие |
|--------|---------|
| **Проверить обновления** | GET /api/update/check — сравнивает HEAD с origin/main для GUI и ML |
| **Применить обновления** | POST /api/update/apply — git pull + npm build + restart если бэкенд изменился |
| **Перезапустить** | POST /api/update/restart — systemctl restart (Linux) / re-exec (Windows) |
| **Переустановить** | POST /api/update/reinstall — git pull + pip install + npm build + restart |
| **Удалить** | POST /api/update/uninstall — останавливает сервис и удаляет файлы |

### Совместимость со старыми установками
- Linux-установки через старый `install.sh` полностью совместимы: `install.sh` теперь вызывает `scripts/install-linux.sh`
- Кнопки в UI используют `ANOMALYNET_APP_ROOT` для определения пути — переменная задаётся автоматически в systemd.service (Linux) или как Machine-level env var (Windows)
- Если `ANOMALYNET_APP_ROOT` не задан: Linux fallback → `/opt/anomalynet/AnomalyNet-gui`, Windows fallback → `C:\AnomalyNet\AnomalyNet-gui`

---

## Структура каталогов

### Linux
```
/opt/anomalynet/
├── AnomalyNet-gui/          ← GUI-репозиторий
│   ├── backend/             ← Python FastAPI
│   │   └── .venv/           ← Python virtualenv
│   ├── frontend/dist/       ← собранный React
│   └── config/
│       ├── settings.json
│       └── model_presets.json
├── AnomalyNet-ml/           ← ML-репозиторий
└── models/                  ← Модели CatBoost
    ├── stage1/catboost/     ← model.cbm (binary gate)
    ├── stage1/artifacts/    ← scaler.joblib, preprocessing_params.json
    ├── stage2/catboost/     ← model_mc.cbm (Simple multiclass)
    └── stage3/catboost/     ← model.cbm (Advanced IoT2023)
```

### Windows
```
C:\AnomalyNet\               ← аналогичная структура
├── AnomalyNet-gui\
│   ├── backend\.venv\Scripts\python.exe
│   └── config\settings.json
├── AnomalyNet-ml\
└── models\
```

---

## Решение проблем

### Linux: сервис не запускается
```bash
journalctl -u anomalynet -n 50 --no-pager
# Проверить права на libpcap:
ls -la /usr/lib/x86_64-linux-gnu/libpcap*
```

### Linux: npm build не хватает памяти
```bash
# Увеличить swap вручную:
fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
```

### Windows: ошибка ExecutionPolicy
```powershell
Set-ExecutionPolicy -ExecutionPolicy Bypass -Scope Process
```

### Windows: порт занят
```powershell
netstat -ano | findstr :8000
# Изменить порт через -Port параметр установщика
```

### Обновление не работает в UI (кнопки)
1. Проверить `ANOMALYNET_APP_ROOT`: `echo $ANOMALYNET_APP_ROOT` (Linux) или `[System.Environment]::GetEnvironmentVariable("ANOMALYNET_APP_ROOT","Machine")` (Windows)
2. Если пустой — переустановить через скрипт, или задать вручную
3. Проверить наличие git в PATH процесса сервера
