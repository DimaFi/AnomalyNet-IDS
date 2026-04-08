from __future__ import annotations

from app.capture.base import CaptureAdapter
from app.contracts.schemas import NormalizedFlowEvent


class WindowsWinDivertStubAdapter(CaptureAdapter):
    mode = "windows_stub"
    name = "Windows WinDivert Stub"

    async def next_event(self) -> NormalizedFlowEvent:
        raise RuntimeError(
            "Windows capture adapter is not implemented yet. "
            "Replace this stub with a WinDivert-backed collector."
        )

