# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for AnomalyNet.exe

Build:
    cd AppCode/backend
    pyinstaller anomalynet.spec

Output: AppCode/backend/dist/AnomalyNet.exe  (single file)
"""
import sys
from pathlib import Path

ROOT = Path(SPECPATH).parent  # AppCode/

block_cipher = None

a = Analysis(
    ["launcher.py"],
    pathex=[str(Path(SPECPATH))],
    binaries=[],
    datas=[
        # Config files
        (str(ROOT / "config"),          "config"),
        # Shared feature contracts
        (str(ROOT / "shared"),          "shared"),
        # Built frontend (must exist — run `npm run build` first)
        (str(ROOT / "frontend" / "dist"), "frontend/dist"),
    ],
    hiddenimports=[
        # FastAPI / uvicorn internals
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.loops.asyncio",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
        # CatBoost
        "catboost",
        # Pydantic
        "pydantic",
        "pydantic.v1",
        # Multipart (fastapi form)
        "multipart",
        "multipart.multipart",
        # psutil
        "psutil",
        # joblib
        "joblib",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["scapy"],       # scapy needs Npcap — exclude from bundle
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="AnomalyNet",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,        # no console window — set True while debugging
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon="assets/icon.ico",   # uncomment if you have an icon
)
