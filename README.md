# AnomalyNet — GUI

> Real-time network intrusion detection system with a local web interface.  
> Powered by CatBoost models trained on CIC IoT Dataset 2023/2024.

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=black)
![TypeScript](https://img.shields.io/badge/TypeScript-5.6-3178C6?logo=typescript&logoColor=white)
![CatBoost](https://img.shields.io/badge/CatBoost-ML-yellow)
![Platform](https://img.shields.io/badge/Platform-Linux%20%7C%20Windows-blue)
![License](https://img.shields.io/badge/License-MIT-green)

🇷🇺 [Русская версия](README_RU.md)

---

## Overview

AnomalyNet captures live network traffic, extracts CICFlowMeter-compatible features per flow, and classifies each flow with a CatBoost cascade — from a fast binary gate to a detailed 8-class attack classifier. Everything runs locally; no cloud, no telemetry.

**v2.0.0** adds full cross-platform support: Windows live capture via Npcap, Windows firewall integration (netsh), cross-platform ARP device discovery, and capability-aware UI.

The ML models live in a separate repository: [AnomalyNet-ml](https://github.com/DimaFi/AnomalyNet-ml).

---

## Platform Support

| Feature | Linux | Windows |
|---|---|---|
| Live packet capture | Scapy AsyncSniffer (root) | Npcap adapter (Admin) |
| IP blocking | iptables ANOMALYNET chains | netsh advfirewall |
| Firewall rollback | iptables-save/restore | — |
| Active ARP scan | Scapy srp (root) | Scapy + Npcap (Admin) |
| Passive ARP discovery | — | `arp -a` cache fallback |
| Autostart | systemd service | Task Scheduler |
| Demo mode | ✓ (no root) | ✓ (no Admin) |

The UI automatically detects and displays platform capabilities. Features that are unavailable on the current platform are greyed out with an explanation.

---

## Features

| Feature | Details |
|---|---|
| **Live capture** | Scapy on Linux; Npcap adapter on Windows; mock simulation in demo mode |
| **Flow aggregation** | 5-tuple tracking, 60 s idle timeout, FIN/RST instant close |
| **CICFlowMeter features** | 71 features: duration, IAT stats, flag counts, window sizes, active/idle periods |
| **Cascade detection** | Stage 1 binary gate → Stage 2/3 multiclass (protocol-routed) |
| **Attack classes** | Benign · DoS · DDoS · Recon · BruteForce · WebAttack · Bot · Spoofing |
| **IP blocking** | One-click or auto-block; iptables (Linux) or netsh (Windows); configurable whitelist |
| **DNS monitoring** | Passive sniffer with DGA detection, domain reputation, behavioral alerts |
| **TLS fingerprinting** | JA4-compatible fingerprints with behavioral profiling and reputation scoring |
| **Network Map** | ARP device discovery, OUI vendor lookup, device type classification, D3 force graph |
| **Device-aware routing** | IoT devices → IoT pipeline; PCs/phones → General Network pipeline |
| **Toast alerts** | Warning / anomaly notifications with source IP and attack class |
| **History** | Per-day NDJSON log with configurable retention (1–30 days) |
| **Export** | EVE JSON and CSV export with time range and priority filters |
| **Theme & i18n** | Dark / light theme · Russian / English UI |
| **Custom model plugins** | Drop any compatible adapter into `plugins/` — no code changes needed |
| **Remote management** | Full REST API for settings, models, blocking, and reports |

---

## Detection Modes

| Preset | Pipeline | Use case |
|---|---|---|
| **Binary** | Stage 1 only | Fastest; attack/normal, no class label |
| **Simple Cascade** | Stage 1 → Stage 2 | Standard; 8-class labelling, 71 features |
| **Advanced Cascade** | Stage 1 → Stage 3 | IoT-optimised; 46 CIC-IoT-2023 features, Macro F1 = 0.82 |
| **Cascade Routed** | Stage 1 → Stage 2 or Stage 3 | Best coverage; routes by protocol (TCP→S2, UDP/ICMP→S3) |
| **General Network** | General Stage 1 → Stage 2 | PC/server traffic; trained on CICIDS 2017 |
| **Auto** | Device-aware routing | Selects pipeline based on source device type |

---

## Network Map & Device Discovery

AnomalyNet builds a live map of all devices on the local network and uses it to route traffic to the appropriate detection model.

```
Network
 ├─ 📷 Camera  192.168.1.10  (Hikvision)   → IoT pipeline    → Advanced Cascade
 ├─ 📡 Sensor  192.168.1.20  (Espressif)   → IoT pipeline    → Advanced Cascade
 ├─ 💻 PC      192.168.1.30  (Microsoft)   → General pipeline → General Network
 ├─ 📱 Phone   192.168.1.50  (Apple)       → General pipeline → General Network
 └─ 🌐 Router  192.168.1.1   (TP-Link)     → IoT pipeline    → Advanced Cascade
```

### ARP discovery — cross-platform

| Platform | Condition | Method | Tag |
|---|---|---|---|
| Linux | root | Scapy `srp()` active scan | `scapy` |
| Windows | Admin + Npcap | Scapy `srp()` active scan | `npcap` |
| Windows | Admin, no Npcap | `arp -a` cache (fallback) | `arp_cache` |
| Windows | No Admin | `arp -a` cache | `arp_cache` |

---

## Scoring Logic

```
predict_proba(flow) → p

p ≥ 0.85  →  anomaly   (red alert)
p ≥ 0.70  →  warning   (orange alert)
p <  0.70  →  normal    (no alert)
```

In cascade mode, Stage 1 acts as a binary gate. Flows classified as attacks are forwarded to Stage 2/3 for attack class labelling.

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

Open **http://localhost:5173** — starts in `mock` mode, no root/Admin or models required.

---

## Installation

There are two ways to install. Pick one:

| | **Quick (portable)** | **Full system install** |
|---|---|---|
| Where | runs from the cloned folder | `/opt/anomalynet` · `C:\AnomalyNet` |
| Rights | no root/admin needed | root / Administrator |
| Autostart | user-level (login) | systemd / Task Scheduler |
| Linux | `bash install.sh` | `sudo bash installers/linux/install-linux.sh` |
| Windows | double-click `install.bat` | `installers\windows\install-windows.bat` (admin) |

### Linux — full system install

```bash
sudo bash installers/linux/install-linux.sh
# Options: INTERFACE=eth0 PORT=8000 DETECTION_MODE=simple AUTO_BLOCK=false
```

**Supported distributions:** Ubuntu/Debian · Alt Linux · Fedora · RHEL/CentOS/Rocky/AlmaLinux · Arch/Manjaro · openSUSE

The installer:
- Installs Python 3, libpcap, Node.js (NVM fallback for unsupported distros)
- Creates a Python venv and installs backend requirements
- Builds the frontend production bundle
- Writes `config/settings.json` with detected interface and model paths
- Configures and enables a **systemd service** (`anomalynet.service`)

### Windows — full system install (PowerShell, as Administrator)

```powershell
powershell -ExecutionPolicy Bypass -File installers\windows\install-windows.ps1
# Options: -InstallDir C:\AnomalyNet -Port 8000 -InstallNpcap -AutoBlock
```

The installer:
- Verifies Python 3.10+, Git, Node.js 18+
- Clones both repos into `C:\AnomalyNet\`
- Creates Python venv + installs dependencies
- Builds the React frontend
- Checks for Npcap; optionally installs it (`-InstallNpcap`)
- Sets machine-level `ANOMALYNET_APP_ROOT` environment variable
- Creates a **Task Scheduler** task (runs at logon with highest privileges)

### Uninstall

Quick (portable) install — run from the app folder:
```bash
bash uninstall.sh          # Linux
uninstall.bat              # Windows (double-click)
```

Full system install:
```bash
# Linux — keep data:
sudo bash installers/linux/uninstall-linux.sh
# Linux — full wipe:
sudo bash installers/linux/uninstall-linux.sh --purge
```

```powershell
# Windows — keep data:
powershell -File installers\windows\uninstall-windows.ps1
# Windows — full wipe:
powershell -File installers\windows\uninstall-windows.ps1 -Purge
```

---

## Updating

### Via UI (recommended)
Go to the **About** tab → click **Check for updates** → **Apply updates**.

The backend will:
1. `git pull` both repos
2. `pip install -r requirements.txt` (if dependencies changed)
3. `npm run build` (if frontend sources changed)
4. Restart the service automatically if the backend changed

### Via re-install script
```bash
sudo bash installers/linux/install-linux.sh   # idempotent — safe to run again
```

---

## Architecture

```
AppCode/
├── backend/                FastAPI + Uvicorn
│   └── app/
│       ├── api/            REST endpoints + SSE stream + update/reinstall/uninstall
│       ├── capture/        Scapy adapter (Linux), Npcap adapter (Windows), FlowAggregator
│       ├── discovery/      ARP scanner, OUI lookup, device classifier, DeviceTracker
│       │   └── backends/   ArpBackend ABC, LinuxArpBackend, WindowsArpBackend
│       ├── dns/            DNS monitor, DGA detection, domain reputation
│       ├── tls/            JA4 fingerprinting, TLS behavioral monitor, reputation
│       ├── model/          CatBoost adapter, cascade adapters, factory
│       ├── platform/       Platform abstraction layer
│       │   ├── base/       PlatformCapabilities, AbstractServiceManager, BaseFirewall
│       │   ├── linux/      SystemdManager, LinuxFirewall, linux_capabilities()
│       │   └── windows/    WindowsTaskSchedulerManager, WindowsNetshFirewall, windows_capabilities()
│       ├── security/       IP blocker (iptables / netsh), GeoIP, JA4 reputation
│       └── pipeline/       Orchestration service, auto-block, auto-unblock
├── frontend/               Vite + React 18 + Zustand + i18next
│   └── src/
│       ├── app/            App shell, store (capabilities), router, types
│       ├── features/       Dashboard · Stream · Network Map · Plugins · Settings · About
│       └── components/     Toast, TopBar, ModelPresetPicker
├── config/
│   ├── settings.json       Runtime configuration
│   ├── models_registry.json  Available models
│   └── model_presets.json  Detection presets
├── installers/             All installers and helper scripts
│   ├── linux/              install-linux.sh · uninstall-linux.sh (full system install)
│   ├── windows/            install-windows.ps1/.bat · uninstall-windows.ps1 · build_installer.ps1
│   ├── shared/             download_oui.py (OUI vendor DB helper)
│   ├── legacy/             setup.sh (old curl installer) · run_*.ps1 (dev helpers)
│   └── README.md           Installation documentation
├── install.sh · install.bat        Quick portable install (run from this folder)
├── uninstall.sh · uninstall.bat    Quick portable uninstall
└── launch.sh · launch.bat · launch.vbs   Launchers (used by shortcuts & autostart)
```

---

## Configuration

Edit `config/settings.json` or use the **Settings** tab in the UI:

| Key | Default | Description |
|---|---|---|
| `run_mode` | `"mock"` | `"mock"` · `"linux_live"` · `"windows_live"` |
| `active_model_id` | `"mock-default"` | Model ID from `models_registry.json` |
| `detection_mode` | `"simple"` | `"simple"` · `"advanced"` |
| `catboost_threshold` | `0.70` | Anomaly score threshold |
| `catboost_model_dir` | `""` | Path to Stage 1 `model.cbm` |
| `preprocessing_artifacts_dir` | `""` | Path to Stage 1 artifacts |
| `catboost_secondary_model_dir` | `""` | Path to Stage 2 or Stage 3 model |
| `catboost_stage3_model_dir` | `""` | Path to Stage 3 model (Cascade Routed) |
| `interface_name` | `""` | Capture interface |
| `auto_block` | `false` | Auto-block anomaly IPs |
| `auto_block_level` | `"anomaly"` | Block threshold: `"anomaly"` or `"warning"` |
| `whitelist_ips` | `[]` | IPs never auto-blocked |
| `retention_days` | `7` | History log retention (days) |

---

## REST API (key endpoints)

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/health` | Service health and active mode |
| `GET` | `/api/capabilities` | Platform capabilities (admin, npcap, firewall, etc.) |
| `GET` | `/api/stream/snapshot` | Current detection buffer |
| `GET` | `/api/history` | Paginated event history |
| `GET` | `/api/export` | Download report as EVE JSON or CSV |
| `GET` | `/api/settings` | Current settings |
| `PUT` | `/api/settings` | Update settings |
| `GET` | `/api/model-presets` | Detection presets |
| `POST` | `/api/model-presets/apply/{id}` | Apply a preset |
| `POST` | `/api/block` | Block an IP |
| `GET` | `/api/devices` | Device map (all discovered devices) |
| `POST` | `/api/devices/scan` | Trigger ARP scan |
| `GET` | `/api/dns/alerts` | DNS anomaly alerts |
| `GET` | `/api/tls/alerts` | TLS fingerprint alerts |
| `GET` | `/api/update/check` | Check for updates (git) |
| `POST` | `/api/update/apply` | Apply updates (git pull + rebuild) |
| `POST` | `/api/update/restart` | Restart the service |
| `POST` | `/api/update/reinstall` | Full reinstall (pull + pip + npm) |
| `POST` | `/api/update/uninstall` | Remove the application |

---

## Project Structure (ML)

ML models and training scripts: **[AnomalyNet-ml](https://github.com/DimaFi/AnomalyNet-ml)**

```
AnomalyNet-ml/
├── model/                   Stage 1 binary detector — CIC IoT 2024, 71 features, F1 = 99.4%
├── artifacts/               Stage 1 scaler + feature contract
├── stage2_multiclass/       8-class classifier — same 71 features, augmented with CICIDS 2017/2018
├── stage3_cic2023/          IoT multiclass — 46 CIC-IoT-2023 features, Macro F1 = 0.82
└── general_network/         General Network — trained on CICIDS 2017 (PC/server traffic)
```

---

## Custom Model Plugins

1. Place your adapter in `plugins/` following the standard interface
2. Restart — the model appears in the **Models** registry and Settings UI
3. Select it from the UI or via `POST /api/models/select`

Supported formats: CatBoost `.cbm`, scikit-learn `.pkl`/`.joblib`, PyTorch `.pt`, ONNX `.onnx`, Keras `.h5`.

---

## License

MIT — see `LICENSE` file.
