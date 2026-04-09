# FILE: core/backends/__init__.py
# VERSION: 1.0.0
# START_MODULE_CONTRACT
#   PURPOSE: Re-export public backend types.
#   SCOPE: barrel re-exports for BackendRegistry, MLXBackend, TorchBackend
#   DEPENDS: none
#   LINKS: M-BACKENDS
#   ROLE: BARREL
#   MAP_MODE: SUMMARY
# END_MODULE_CONTRACT
#
# START_MODULE_MAP
#   Backend protocols - Re-export backend interfaces, loaded model handles, and capability DTOs
#   Runtime backends - Re-export MLX and Torch backend implementations
#   Registry surface - Re-export backend registry and backend selection metadata
# END_MODULE_MAP
#
# START_CHANGE_SUMMARY
#   LAST_CHANGE: [v1.0.0 - GRACE integration: added MODULE_CONTRACT, MODULE_MAP, and function contracts]
# END_CHANGE_SUMMARY

from core.backends.base import LoadedModelHandle, TTSBackend
from core.backends.capabilities import BackendCapabilitySet, BackendDiagnostics
from core.backends.mlx_backend import MLXBackend
from core.backends.registry import BackendRegistry, BackendSelection
from core.backends.torch_backend import TorchBackend

__all__ = [
    "BackendCapabilitySet",
    "BackendDiagnostics",
    "BackendRegistry",
    "BackendSelection",
    "LoadedModelHandle",
    "MLXBackend",
    "TTSBackend",
    "TorchBackend",
]
