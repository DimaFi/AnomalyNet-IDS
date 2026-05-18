from __future__ import annotations

from app.capture.adapters.linux.adapter import LinuxPcapStubAdapter
from app.capture.adapters.mock.adapter import MockCaptureAdapter
from app.capture.adapters.windows.adapter import WindowsWinDivertStubAdapter
from app.capture.base import CaptureAdapter
from app.contracts.schemas import AppSettings, RunMode


def build_capture_adapter(mode: RunMode, settings: AppSettings | None = None) -> CaptureAdapter:
    if mode == "linux_live":
        from app.capture.adapters.linux.scapy_adapter import LinuxScapyAdapter
        if settings and settings.interface_names:
            interfaces = settings.interface_names
        elif settings:
            interfaces = [settings.interface_name]
        else:
            interfaces = ["eth0"]
        detection_mode = settings.detection_mode if settings else "simple"
        bpf_filter = settings.bpf_filter if settings else ""
        return LinuxScapyAdapter(interfaces=interfaces, detection_mode=detection_mode, bpf_filter=bpf_filter)

    if mode == "windows_live":
        from app.capture.adapters.windows.npcap_adapter import WindowsNpcapCapture
        if settings and settings.interface_names:
            interfaces = settings.interface_names
        elif settings:
            interfaces = [settings.interface_name]
        else:
            interfaces = ["Ethernet"]
        detection_mode = settings.detection_mode if settings else "simple"
        bpf_filter = settings.bpf_filter if settings else ""
        return WindowsNpcapCapture(interfaces=interfaces, detection_mode=detection_mode, bpf_filter=bpf_filter)

    adapters: dict[RunMode, CaptureAdapter] = {
        "mock": MockCaptureAdapter(),
        "windows_stub": WindowsWinDivertStubAdapter(),
        "linux_stub": LinuxPcapStubAdapter(),
    }
    return adapters[mode]
