# AnomalyNet — GUI Application

Real-time network traffic IDS with a local web interface.  
Powered by a CatBoost model trained on CIC IoT Dataset 2024 (see [AnomalyNet-ml](https://github.com/DimaFi/AnomalyNet-ml)).

## Features

- Live packet capture via Scapy (Linux) or mock simulation (Windows/demo)
- 71-feature CICFlowMeter-compatible flow aggregation
- CatBoost inference with configurable threshold (default 0.70)
- Toast notifications for warnings / anomalies
- IP blocking via iptables (Linux, requires root)
- Dark / light theme, bilingual (RU / EN)

## Architecture

```
AppCode/
├── backend/          FastAPI + uvicorn
│   └── app/
│       ├── api/      REST routes + WebSocket
│       ├── capture/  Packet capture adapters (scapy / mock)
│       ├── model/    CatBoost adapter + factory
│       ├── preprocess/ Feature pipeline
│       └── pipeline/ Orchestration service
├── frontend/         Vite + React + Zustand
├── config/
│   ├── settings.json         App settings
│   └── models_registry.json  Available models
└── shared/
    └── contracts/    Feature contracts (JSON)
```

## Quick start (development)

**Requirements**: Python 3.10+, Node 18+

```bash
# Backend
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Frontend (separate terminal)
cd frontend
npm install
npm run dev
```

Open http://localhost:5173

## Configuration

Edit `config/settings.json`:

| Key | Default | Description |
|-----|---------|-------------|
| `run_mode` | `"mock"` | `"mock"` / `"linux_live"` |
| `model_id` | `"mock-v1"` | Model from `models_registry.json` |
| `catboost_threshold` | `0.70` | Detection threshold |
| `catboost_model_dir` | `""` | Path to `model.cbm` directory |
| `preprocessing_artifacts_dir` | `""` | Path to artifacts folder |
| `interface_name` | `"eth0"` | Network interface (linux_live only) |
| `auto_block` | `false` | Auto-block anomaly IPs via iptables |

## Model

Download from [AnomalyNet-ml](https://github.com/DimaFi/AnomalyNet-ml) and point `catboost_model_dir` + `preprocessing_artifacts_dir` at the downloaded folders.

## License

MIT
