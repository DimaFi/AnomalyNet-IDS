from __future__ import annotations

from abc import ABC, abstractmethod

from app.contracts.schemas import NormalizedFlowEvent, RunMode


class CaptureAdapter(ABC):
    mode: RunMode
    name: str

    @abstractmethod
    async def next_event(self) -> NormalizedFlowEvent:
        raise NotImplementedError

