# FILE: core/backends/registry.py
# VERSION: 1.0.0
# START_MODULE_CONTRACT
#   PURPOSE: Select and manage TTS inference backends based on configuration and availability.
#   SCOPE: BackendRegistry class with backend selection, model spec resolution
#   DEPENDS: M-CONFIG, M-ERRORS, M-OBSERVABILITY
#   LINKS: M-BACKENDS
#   ROLE: RUNTIME
#   MAP_MODE: EXPORTS
# END_MODULE_CONTRACT
#
# START_MODULE_MAP
#   BackendSelection - Selected backend with request and fallback metadata
#   BackendRegistry - Backend selection and model spec resolution
# END_MODULE_MAP
#
# START_CHANGE_SUMMARY
#   LAST_CHANGE: [v1.0.0 - GRACE integration: added MODULE_CONTRACT, MODULE_MAP, and function contracts]
# END_CHANGE_SUMMARY

from __future__ import annotations

import platform
from dataclasses import dataclass
from typing import Iterable, Sequence

from core.backends.base import TTSBackend
from core.errors import (
    BackendCapabilityError,
    BackendNotAvailableError,
    ModelNotAvailableError,
)
from core.models.catalog import ModelSpec, get_model_manifest


@dataclass(frozen=True)
class BackendSelection:
    backend: TTSBackend
    requested_backend: str | None
    auto_selected: bool
    selection_reason: str


# START_CONTRACT: BackendRegistry
#   PURPOSE: Select the active inference backend and resolve supported model specifications against it.
#   INPUTS: { backends: Sequence[TTSBackend] - Registered backend implementations, requested_backend: str | None - Optional explicit backend override, autoselect: bool - Whether backend selection may fall back automatically, model_manifest_path: object - Optional manifest path override }
#   OUTPUTS: { instance - Backend registry with a resolved backend selection }
#   SIDE_EFFECTS: Loads the model manifest and selects an active backend during initialization
#   LINKS: M-BACKENDS
# END_CONTRACT: BackendRegistry
class BackendRegistry:
    def __init__(
        self,
        backends: Sequence[TTSBackend],
        *,
        requested_backend: str | None = None,
        autoselect: bool = True,
        model_manifest_path=None,
    ):
        if not backends:
            raise ValueError("At least one backend must be registered")
        self._backends = {backend.key: backend for backend in backends}
        self._requested_backend = requested_backend
        self._autoselect = autoselect
        self._model_manifest = (
            get_model_manifest(model_manifest_path)
            if model_manifest_path is not None
            else get_model_manifest()
        )
        self._selection = self._select_backend()

    @property
    def selected_backend(self) -> TTSBackend:
        return self._selection.backend

    @property
    def selection(self) -> BackendSelection:
        return self._selection

    @property
    def model_specs(self) -> tuple[ModelSpec, ...]:
        return tuple(self._model_manifest.enabled_models())

    # START_CONTRACT: list_backends
    #   PURPOSE: List registered backends together with selection state, capabilities, and readiness diagnostics.
    #   INPUTS: {}
    #   OUTPUTS: { list[dict[str, object]] - Structured backend descriptors }
    #   SIDE_EFFECTS: none
    #   LINKS: M-BACKENDS
    # END_CONTRACT: list_backends
    def list_backends(self) -> list[dict[str, object]]:
        selected_key = self.selected_backend.key
        return [
            {
                "key": backend.key,
                "label": backend.label,
                "selected": backend.key == selected_key,
                "platform_supported": backend.supports_platform(),
                "available": backend.is_available(),
                "capabilities": backend.capabilities().to_dict(),
                "diagnostics": backend.readiness_diagnostics().to_dict(),
            }
            for backend in self._backends.values()
        ]

    # START_CONTRACT: get_model_spec
    #   PURPOSE: Resolve a manifest model specification that is compatible with the selected backend.
    #   INPUTS: { model_name: str | None - Requested model identifier, mode: str | None - Requested synthesis mode fallback }
    #   OUTPUTS: { ModelSpec - Selected compatible model specification }
    #   SIDE_EFFECTS: none
    #   LINKS: M-BACKENDS
    # END_CONTRACT: get_model_spec
    def get_model_spec(
        self, model_name: str | None = None, mode: str | None = None
    ) -> ModelSpec:
        # START_BLOCK_RESOLVE_MODEL_BY_NAME
        if model_name:
            for spec in self.model_specs:
                if model_name in {spec.api_name, spec.folder, spec.key}:
                    self.ensure_model_supported(spec)
                    return spec
            raise ModelNotAvailableError(
                model_name=model_name,
                details={"model": model_name, "backend": self.selected_backend.key},
            )
        # END_BLOCK_RESOLVE_MODEL_BY_NAME

        # START_BLOCK_RESOLVE_MODEL_BY_MODE
        if mode:
            self.ensure_mode_supported(mode)
            matching_specs = [
                spec for spec in self.model_specs if spec.mode == mode and spec.enabled
            ]
            matching_specs.sort(
                key=lambda spec: spec.rollout.default_preference, reverse=True
            )
            for spec in matching_specs:
                if self.selected_backend.resolve_model_path(spec.folder):
                    self.ensure_model_supported(spec)
                    return spec
            if matching_specs:
                raise ModelNotAvailableError(
                    reason=f"No local model is available for mode: {mode}",
                    details={"mode": mode, "backend": self.selected_backend.key},
                )
            raise ModelNotAvailableError(
                reason=f"Requested mode is not available: {mode}",
                details={"mode": mode, "backend": self.selected_backend.key},
            )
        # END_BLOCK_RESOLVE_MODEL_BY_MODE

        # START_BLOCK_REJECT_EMPTY_MODEL_REQUEST
        raise ModelNotAvailableError(
            reason="No model or mode was specified",
            details={"backend": self.selected_backend.key},
        )
        # END_BLOCK_REJECT_EMPTY_MODEL_REQUEST

    # START_CONTRACT: ensure_model_supported
    #   PURPOSE: Validate that the selected backend supports the provided model specification.
    #   INPUTS: { spec: ModelSpec - Model specification to validate }
    #   OUTPUTS: { None - Completes when the model is supported }
    #   SIDE_EFFECTS: none
    #   LINKS: M-BACKENDS
    # END_CONTRACT: ensure_model_supported
    def ensure_model_supported(self, spec: ModelSpec) -> None:
        self.ensure_mode_supported(spec.mode)
        if spec.supports_backend(self.selected_backend.key):
            return
        raise BackendCapabilityError(
            f"Backend '{self.selected_backend.key}' is not enabled for model '{spec.api_name}'",
            details={
                "backend": self.selected_backend.key,
                "model": spec.api_name,
                "mode": spec.mode,
            },
        )

    # START_CONTRACT: ensure_mode_supported
    #   PURPOSE: Validate that the selected backend supports the requested synthesis mode.
    #   INPUTS: { mode: str - Requested synthesis mode }
    #   OUTPUTS: { None - Completes when the mode is supported }
    #   SIDE_EFFECTS: none
    #   LINKS: M-BACKENDS
    # END_CONTRACT: ensure_mode_supported
    def ensure_mode_supported(self, mode: str) -> None:
        if self.selected_backend.capabilities().supports_mode(mode):
            return
        raise BackendCapabilityError(
            f"Backend '{self.selected_backend.key}' does not support mode '{mode}'",
            details={"backend": self.selected_backend.key, "mode": mode},
        )

    def _select_backend(self) -> BackendSelection:
        # START_BLOCK_HANDLE_EXPLICIT_BACKEND_SELECTION
        if self._requested_backend:
            backend = self._backends.get(self._requested_backend)
            if backend is None:
                raise BackendNotAvailableError(
                    f"Configured backend is unknown: {self._requested_backend}",
                    details={
                        "backend": self._requested_backend,
                        "known_backends": sorted(self._backends),
                    },
                )
            return BackendSelection(
                backend=backend,
                requested_backend=self._requested_backend,
                auto_selected=False,
                selection_reason="explicit_config",
            )
        # END_BLOCK_HANDLE_EXPLICIT_BACKEND_SELECTION

        # START_BLOCK_HANDLE_FIXED_BACKEND_ORDER
        if not self._autoselect:
            first = next(iter(self._backends.values()))
            return BackendSelection(
                backend=first,
                requested_backend=None,
                auto_selected=False,
                selection_reason="first_registered",
            )
        # END_BLOCK_HANDLE_FIXED_BACKEND_ORDER

        # START_BLOCK_AUTOSELECT_READY_BACKEND
        ordered = list(self._prefer_platform_backend(self._backends.values()))
        for backend in ordered:
            if backend.supports_platform() and backend.is_available():
                return BackendSelection(
                    backend=backend,
                    requested_backend=None,
                    auto_selected=True,
                    selection_reason="platform_and_runtime_match",
                )
        # END_BLOCK_AUTOSELECT_READY_BACKEND
        # START_BLOCK_AUTOSELECT_PLATFORM_BACKEND
        for backend in ordered:
            if backend.supports_platform():
                return BackendSelection(
                    backend=backend,
                    requested_backend=None,
                    auto_selected=True,
                    selection_reason="platform_match_runtime_missing",
                )
        # END_BLOCK_AUTOSELECT_PLATFORM_BACKEND
        # START_BLOCK_FALLBACK_BACKEND_SELECTION
        first = ordered[0]
        return BackendSelection(
            backend=first,
            requested_backend=None,
            auto_selected=True,
            selection_reason="fallback_first_backend",
        )
        # END_BLOCK_FALLBACK_BACKEND_SELECTION

    @staticmethod
    def _prefer_platform_backend(
        backends: Iterable[TTSBackend],
    ) -> Iterable[TTSBackend]:
        current = platform.system().lower()
        if current == "darwin":
            preferred = ["mlx", "torch"]
        else:
            preferred = ["torch", "mlx"]
        ranked = sorted(
            backends,
            key=lambda backend: preferred.index(backend.key)
            if backend.key in preferred
            else len(preferred),
        )
        return ranked

__all__ = [
    "BackendSelection",
    "BackendRegistry",
]
