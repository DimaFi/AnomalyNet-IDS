"""
Official AnomalyNet model catalog.

Lists the officially supported model repositories that can be downloaded
and installed automatically. Each entry describes a git repo that contains
a models/ subfolder with standard ModelPackage structure.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class OfficialModel:
    id: str
    name: str
    description: str
    repo_url: str
    models_subdir: str        # subdir inside the repo that contains model packages
    size_mb: int

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "repo_url": self.repo_url,
            "models_subdir": self.models_subdir,
            "size_mb": self.size_mb,
        }


OFFICIAL_CATALOG: list[OfficialModel] = [
    OfficialModel(
        id="anomalynet-ml",
        name="AnomalyNet ML",
        description=(
            "5 моделей: IoT Binary, IoT Multiclass (8 классов), "
            "IoT Advanced (46 признаков, Macro F1=0.819), "
            "General Binary, General Multiclass (CICIDS 2017, 7 классов). "
            "Покрывает IoT-устройства и обычные ПК/домашние сети."
        ),
        repo_url="https://github.com/DimaFi/AnomalyNet-ml.git",
        models_subdir="models",
        size_mb=85,
    ),
]


def get_catalog() -> list[OfficialModel]:
    return OFFICIAL_CATALOG


def get_by_id(catalog_id: str) -> OfficialModel | None:
    return next((m for m in OFFICIAL_CATALOG if m.id == catalog_id), None)
