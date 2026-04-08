from __future__ import annotations

from app.capture.base import CaptureAdapter
from app.contracts.schemas import NormalizedFlowEvent


class LinuxPcapStubAdapter(CaptureAdapter):
    mode = "linux_stub"
    name = "Linux PCAP Stub"

    async def next_event(self) -> NormalizedFlowEvent:
        raise RuntimeError(
            "Linux capture adapter is not implemented yet. "
            "Replace this stub with a pcap/AF_PACKET backed collector."
        )

