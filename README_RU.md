# Traffic Analysis Console

Локальное web-приложение для будущего анализа сетевого трафика, подготовки признаков и подключения ML-модели.

Сейчас внутри уже есть:
- frontend на `React + TypeScript + Vite`
- backend на `FastAPI`
- mock pipeline `capture -> preprocess -> inference -> verdict`
- двуязычный интерфейс `RU/EN`
- тёмная и светлая темы
- локальное хранение настроек и истории в JSON/NDJSON
- каркас для будущих адаптеров `WinDivert` и `pcap`

Проект полностью расположен в `G:\Диплом\App\AppCode` и не зависит жёстко от кода в `G:\Диплом\Code`.

