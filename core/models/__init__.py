# FILE: core/models/__init__.py
# VERSION: 1.0.0
# START_MODULE_CONTRACT
#   PURPOSE: Re-export public model metadata types and catalog helpers.
#   SCOPE: barrel re-exports for manifest and catalog symbols
#   DEPENDS: M-MODELS
#   LINKS: M-MODELS
#   ROLE: BARREL
#   MAP_MODE: SUMMARY
# END_MODULE_CONTRACT
#
# START_MODULE_MAP
#   ModelManifest - Parsed manifest root model
#   ModelManifestValidationError - Manifest validation error type
#   ModelSpec - Model specification type
#   MODEL_SPECS - Read-only model specification mapping
#   SPEAKER_MAP - Supported speakers by language
#   EMOTION_EXAMPLES - Example voice design prompts
#   get_model_manifest - Load the model manifest
#   get_model_specs - Build mutable model spec mapping
# END_MODULE_MAP
#
# START_CHANGE_SUMMARY
#   LAST_CHANGE: [v1.0.0 - GRACE integration: added MODULE_CONTRACT, MODULE_MAP, and function contracts]
# END_CHANGE_SUMMARY

from core.models.catalog import (
    EMOTION_EXAMPLES,
    MODEL_SPECS,
    SPEAKER_MAP,
    get_model_manifest,
    get_model_specs,
)
from core.models.manifest import ModelManifest, ModelManifestValidationError, ModelSpec

__all__ = [
    "EMOTION_EXAMPLES",
    "MODEL_SPECS",
    "ModelManifest",
    "ModelManifestValidationError",
    "ModelSpec",
    "SPEAKER_MAP",
    "get_model_manifest",
    "get_model_specs",
]
