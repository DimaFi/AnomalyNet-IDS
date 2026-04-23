# AnomalyNet — GUI

> Real-time network intrusion detection system with a local web interface.  
> Powered by CatBoost models trained on CIC IoT Dataset 2023/2024.

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=black)
![TypeScript](https://img.shields.io/badge/TypeScript-5.6-3178C6?logo=typescript&logoColor=white)
![CatBoost](https://img.shields.io/badge/CatBoost-ML-yellow)
![License](https://img.shields.io/badge/License-MIT-green)

---

## Overview

AnomalyNet captures live network traffic, extracts 71 CICFlowMeter-compatible features per flow, and classifies each flow with a CatBoost cascade — from a fast binary gate to a detailed 8-class attack classifier. Everything runs locally; no cloud, no telemetry.

The ML models live in a separate repository: [AnomalyNet-ml](https://github.com/DimaFi/AnomalyNet-ml).

---

## Features

| Feature | Details |
|---|---|
| **Live capture** | Scapy AsyncSniffer on any Linux interface; mock simulation on Windows/demo |
| **Flow aggregation** | 5-tuple tracking, 60 s idle timeout, FIN/RST instant close |
| **71 CICFlowMeter features** | Duration, IAT stats, flag counts, window sizes, active/idle periods |
| **Cascade detection** | Stage 1 binary gate → Stage 2/3 multiclass (protocol-routed) |
| **Attack classes** | Benign · DoS · DDoS · Recon · BruteForce · WebAttack · Bot · Spoofing |
| **IP blocking** | One-click or auto-block via iptables; configurable whitelist |
| **Toast alerts** | Warning / anomaly notifications with source IP and attack class |
| **History** | Per-day NDJSON log with configurable retention (1–30 days) |
| **Export** | Download full report (summary + event list) as JSON |
| **Theme & i18n** | Dark / light theme · Russian / English UI |

---

## Detection Modes

AnomalyNet supports four presets selectable from the UI:

| Preset | Pipeline | Use case |
|---|---|---|
| **Binary** | Stage 1 only | Fastest; "attack or not", no class label |
| **Simple Cascade** | Stage 1 → Stage 2 | Standard; 8-class labelling, same 71 features |
| **Advanced Cascade** | Stage 1 → Stage 3 | IoT-optimised; 46 CIC-IoT-2023 features, Macro F1 = 0.82 |
| **Cascade Routed** | Stage 1 → Stage 2 or Stage 3 | Best coverage; routes by protocol (TCP→S2, UDP/ICMP→S3) |

---

## Architecture

```
AppCode/
├── backend/                FastAPI + Uvicorn
│   └── app/
│       ├── api/            REST endpoints + SSE stream
│       ├── capture/        Scapy adapter, FlowAggregator, feature computers
│       ├── model/          CatBoost adapter, cascade adapters, factory
│       ├── preprocess/     Feature pipeline, scaler, artifact loader
│       ├── pipeline/       Orchestration service, auto-block logic
│       └── storage/        JSON file store (settings, history, registry)
├── frontend/               Vite + React 18 + Zustand + i18next
│   └── src/
│       ├── app/            App shell, store, router, types
│       ├── features/       Dashboard · Stream · Plugins · Settings · About
│       └── components/     Toast, TopBar, shared UI
├── config/
│   ├── settings.json       Runtime configuration
│   ├── models_registry.json  Available models metadata
│   └── model_presets.json  One-click detection presets
├── shared/contracts/       Feature contract JSON files
├── plugins/                Drop-in plugin directory
└── install.sh              One-command installer (multi-distro Linux)
```

---

## Quick Start (Development)

**Requirements:** Python 3.10+, Node.js 18+

```bash
# 1. Clone
git clone https://github.com/DimaFi/AnomalyNet-gui
cd AnomalyNet-gui/AppCode

# 2. Backend
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# 3. Frontend (separate terminal)
cd ../frontend
npm install
npm run dev
```

Open **http://localhost:5173** — starts in `mock` mode, no root or models required.

---

## Installation on Linux (Production)

One-command installer with automatic distro detection:

```bash
git clone https://github.com/DimaFi/AnomalyNet-gui /opt/anomalynet/AnomalyNet-gui
sudo bash /opt/anomalynet/AnomalyNet-gui/AppCode/install.sh
```

**Supported distributions:** Ubuntu/Debian · Alt Linux (Sisyphus/p10) · Fedora · RHEL/CentOS/Rocky/AlmaLinux · Arch/Manjaro · openSUSE

The installer:
- Installs system dependencies (Python 3, libpcap, Node.js via NVM fallback)
- Creates a Python venv and installs backend requirements
- Builds the frontend production bundle
- Configures and enables a **systemd service** (`anomalynet.service`)

After install, place ML model artifacts in `/opt/anomalynet-ml/` (see [AnomalyNet-ml](https://github.com/DimaFi/AnomalyNet-ml) for structure), then:

```bash
sudo systemctl restart anomalynet
```

Access the UI at **http://\<server-ip\>:8000**

> **Note:** Live capture requires root or `CAP_NET_RAW`. The systemd service runs as root by default.

---

## Configuration

Edit `config/settings.json` (or use the Settings view in the UI):

| Key | Default | Description |
|---|---|---|
| `run_mode` | `"mock"` | `"mock"` · `"linux_live"` |
| `active_model_id` | `"mock-default"` | Model ID from `models_registry.json` |
| `detection_mode` | `"simple"` | `"simple"` · `"advanced"` |
| `catboost_threshold` | `0.70` | Anomaly score threshold (0.70 = warning, 0.85 = anomaly) |
| `catboost_model_dir` | `""` | Path to Stage 1 `model.cbm` directory |
| `preprocessing_artifacts_dir` | `""` | Path to Stage 1 artifacts (scaler, contract) |
| `catboost_secondary_model_dir` | `""` | Path to Stage 2 or Stage 3 model directory |
| `catboost_stage3_model_dir` | `""` | Path to Stage 3 model (Cascade Routed only) |
| `interface_name` | `"eth0"` | Capture interface (`linux_live` only) |
| `interface_names` | `[]` | Multi-interface list (overrides `interface_name`) |
| `auto_block` | `false` | Auto-block anomaly IPs via iptables |
| `auto_block_level` | `"anomaly"` | Block threshold: `"anomaly"` or `"warning"` |
| `auto_unblock` | `false` | Auto-unblock after cooldown |
| `auto_unblock_cooldown_min` | `10` | Cooldown before auto-unblock (minutes) |
| `whitelist_ips` | `[]` | IPs that are never auto-blocked |
| `retention_days` | `7` | History log retention (days) |

---

## REST API

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/health` | Service health and active mode |
| `GET` | `/api/stream/snapshot` | Current detection buffer (last N events) |
| `GET` | `/api/history` | Paginated event history |
| `GET` | `/api/export` | Download full report as JSON |
| `GET` | `/api/debug/stats` | Uptime stats, label/protocol breakdown, top IPs |
| `POST` | `/api/debug/infer` | Batch offline inference on pre-computed features |
| `GET` | `/api/settings` | Current settings |
| `PUT` | `/api/settings` | Update settings |
| `GET` | `/api/models` | Models registry |
| `POST` | `/api/models/select` | Switch active model |
| `GET` | `/api/model-presets` | Detection presets |
| `POST` | `/api/model-presets/apply/{id}` | Apply a preset |
| `POST` | `/api/block` | Block an IP via iptables |
| `GET` | `/api/interfaces` | List available network interfaces |
| `GET` | `/api/fs/ls` | Directory browser (for model path selection) |

---

## Project Structure (ML)

ML models and training scripts are maintained separately:

**[AnomalyNet-ml](https://github.com/DimaFi/AnomalyNet-ml)**

```
AnomalyNet-ml/
├── stage1/          Binary detector — CIC IoT 2024, 71 features, F1 = 99.4%
├── stage2/          8-class multiclass — same 71 features
├── stage3/          IoT multiclass — 46 CIC-IoT-2023 features, Macro F1 = 0.82
└── stage4/          Extended cascade experiments
```

Expected layout on the production server:

```
/opt/anomalynet-ml/
├── model/           stage1 model.cbm
├── artifacts/       stage1 scaler + feature contract
├── stage2_multiclass/models/catboost/   stage2 model.cbm + class_mapping.json
└── stage3_cic2023/
    ├── models/catboost/   stage3 model.cbm
    └── artifacts/         stage3 scaler + feature contract
```

---

## Scoring Logic

```
predict_proba(flow) → p

p ≥ 0.85  →  anomaly   (red alert)
p ≥ 0.70  →  warning   (orange alert)
p <  0.70  →  normal    (no alert)
```

In cascade mode, Stage 1 acts as a binary gate. Flows classified as attacks are forwarded to Stage 2/3 for attack class labelling (DoS, DDoS, Recon, BruteForce, WebAttack, Bot, Spoofing).

---

## Tech Stack

**Backend**
- [FastAPI](https://fastapi.tiangolo.com/) + Uvicorn — async REST API
- [Scapy](https://scapy.net/) — raw packet capture
- [CatBoost](https://catboost.ai/) — gradient boosting inference
- NumPy · Pandas · Joblib · psutil

**Frontend**
- [React 18](https://react.dev/) + [TypeScript](https://www.typescriptlang.org/)
- [Zustand](https://zustand-demo.pmnd.rs/) — state management
- [Vite](https://vitejs.dev/) — build tool
- [i18next](https://www.i18next.com/) — i18n (RU/EN)

---

## License

[MIT](LICENSE)
