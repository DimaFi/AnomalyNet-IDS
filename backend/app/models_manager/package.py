"""
Model Package scanner.

A model package is a self-contained directory with the following layout:

    {model_id}/
    ├── metadata.json                    (required)
    ├── model.cbm   OR  model_mc.cbm     (required)
    └── artifacts/
        ├── feature_contract.json        (required)
        ├── preprocessing_params.json    (required)
        ├── class_mapping.json           (for multiclass models)
        └── scaler.joblib                (optional)

metadata.json fields:
    id            str   unique identifier
    name          str   display name
    version       str   e.g. "1.0"
    description   str
    preprocessor  str   "cicflowmeter_71" | "ciciot_2023_46"
    model_type    str   "binary" | "multiclass"
    threshold     float decision threshold
    is_gate       bool  if true, use cascade_next after positive
    cascade_next  str | null  id of the next model in cascade
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

ModelType = Literal["binary", "multiclass"]
PreprocessorType = Literal["cicflowmeter_71", "ciciot_2023_46"]


@dataclass
class ModelPackage:
    id: str
    name: str
    version: str
    description: str
    preprocessor: PreprocessorType
    model_type: ModelType
    threshold: float
    is_gate: bool
    cascade_next: str | None
    folder_path: Path
    model_file: Path          # model.cbm or model_mc.cbm
    artifacts_dir: Path
    is_valid: bool
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "preprocessor": self.preprocessor,
            "model_type": self.model_type,
            "threshold": self.threshold,
            "is_gate": self.is_gate,
            "cascade_next": self.cascade_next,
            "folder_path": str(self.folder_path),
            "model_file": str(self.model_file),
            "artifacts_dir": str(self.artifacts_dir),
            "is_valid": self.is_valid,
            "errors": self.errors,
        }


def _load_package(folder: Path) -> ModelPackage | None:
    meta_path = folder / "metadata.json"
    if not meta_path.exists():
        return None

    errors: list[str] = []

    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Cannot parse metadata.json in %s: %s", folder, exc)
        return None

    pkg_id = meta.get("id") or folder.name
    name = meta.get("name", pkg_id)
    version = str(meta.get("version", "1.0"))
    description = meta.get("description", "")
    preprocessor = meta.get("preprocessor", "cicflowmeter_71")
    model_type: ModelType = meta.get("model_type", "binary")
    threshold = float(meta.get("threshold", 0.70))
    is_gate = bool(meta.get("is_gate", False))
    cascade_next = meta.get("cascade_next") or None

    # Locate model file
    cbm = folder / "model.cbm"
    cbm_mc = folder / "model_mc.cbm"
    if cbm.exists():
        model_file = cbm
    elif cbm_mc.exists():
        model_file = cbm_mc
    else:
        errors.append("Missing model file (model.cbm or model_mc.cbm)")
        model_file = cbm  # placeholder

    # Validate artifacts
    artifacts_dir = folder / "artifacts"
    if not artifacts_dir.exists():
        errors.append("Missing artifacts/ directory")
    else:
        for required in ("feature_contract.json", "preprocessing_params.json"):
            if not (artifacts_dir / required).exists():
                errors.append(f"Missing artifacts/{required}")

    is_valid = len(errors) == 0

    if errors:
        logger.warning("Model package %r in %s has errors: %s", pkg_id, folder, errors)

    return ModelPackage(
        id=pkg_id,
        name=name,
        version=version,
        description=description,
        preprocessor=preprocessor,
        model_type=model_type,
        threshold=threshold,
        is_gate=is_gate,
        cascade_next=cascade_next,
        folder_path=folder,
        model_file=model_file,
        artifacts_dir=artifacts_dir,
        is_valid=is_valid,
        errors=errors,
    )


def scan_models_dir(models_dir: str | Path) -> list[ModelPackage]:
    """
    Scan a directory for model packages. Returns valid packages only.
    Invalid packages are logged as warnings and skipped.
    """
    path = Path(models_dir)
    if not path.exists() or not path.is_dir():
        logger.debug("models_dir does not exist or is not a directory: %s", path)
        return []

    packages: list[ModelPackage] = []
    for sub in sorted(path.iterdir()):
        if not sub.is_dir():
            continue
        pkg = _load_package(sub)
        if pkg is None:
            continue
        if pkg.is_valid:
            packages.append(pkg)
        else:
            logger.warning("Skipping invalid model package %r: %s", pkg.id, pkg.errors)

    logger.info("scan_models_dir(%s): found %d valid packages", path, len(packages))
    return packages
