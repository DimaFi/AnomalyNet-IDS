# Архитектура

Основной поток данных:

`capture adapter -> normalized flow/session -> preprocessing -> model adapter -> verdict -> UI/history`

Слои:
- `frontend/` показывает состояние системы, поток событий, модели и настройки
- `backend/app/capture/` содержит абстракцию захвата и платформенные адаптеры
- `backend/app/preprocess/` отвечает за преобразование flow/session в признаки
- `backend/app/model/` содержит адаптеры inference
- `backend/app/pipeline/` собирает полный runtime pipeline
- `shared/contracts/` хранит сериализуемый контракт признаков
- `config/` хранит настройки приложения и реестр моделей
- `data/history/` хранит локальную историю анализа по дням в `ndjson`

Что уже рабочее:
- mock-источник flow/session
- mock preprocessing
- mock model adapter
- WebSocket поток для UI
- экран дашборда, поток, модели, настройки

Что пока заглушка:
- `windows_stub` для будущего WinDivert
- `linux_stub` для будущего pcap/AF_PACKET
- загрузка реальных preprocessing/model artifacts

