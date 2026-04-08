# Smoke tests

- backend отвечает на `/api/health`
- backend отвечает на `/api/settings`
- backend отвечает на `/api/models`
- frontend рендерит главный экран
- WebSocket даёт snapshot и новые mock-события
- настройки языка и темы сохраняются
- история записывается в `data/history/*.ndjson`
