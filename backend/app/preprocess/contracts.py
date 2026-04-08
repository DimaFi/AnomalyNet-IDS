from __future__ import annotations

from app.core import APP_ROOT


FEATURE_CONTRACT_PATH = APP_ROOT / "shared" / "contracts" / "feature_contract.v1.json"
DEFAULT_CONTRACT_VERSION = "feature-contract.v1"
DEFAULT_PROFILE_NAME = "production_safe_features_with_ports"

CATBOOST_CONTRACT_VERSION = "feature-contract.v1"
CATBOOST_PROFILE_NAME     = "catboost_iot_71"

# CIC IoT 2023 (stage3, 46 features)
CATBOOST_CIC2023_PROFILE      = "catboost_iot_46_cic2023"

# Cascade profile names
CATBOOST_CASCADE_SIMPLE_PROFILE = "catboost_cascade_simple"
CATBOOST_CASCADE_ADV_PROFILE    = "catboost_cascade_advanced"
