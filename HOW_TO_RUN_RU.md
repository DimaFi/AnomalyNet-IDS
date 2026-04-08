# Как запускать

## Требования
- `Node.js 22+`
- `Python 3.10+`

## Backend
1. Перейти в `AppCode\\backend`
2. Создать локальную `venv`:
   `python -m venv .venv`
3. Установить зависимости именно в неё:
   `.venv\\Scripts\\python.exe -m pip install -r requirements.txt`
4. Запустить backend из этой `venv`:
   `.venv\\Scripts\\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000`

## Frontend
1. Перейти в `AppCode\\frontend`
2. Установить зависимости:
   `npm install`
3. Запустить:
   `npm run dev`

## Готовые PowerShell-скрипты
- `scripts\\run_backend.ps1`
- `scripts\\run_frontend.ps1`
- `scripts\\run_tests.ps1`

## Что должно открыться
- frontend: `http://127.0.0.1:5173`
- backend swagger: `http://127.0.0.1:8000/docs`
