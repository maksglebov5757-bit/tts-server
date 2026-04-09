# FILE: tests/unit/core/test_backend_registry.py
# VERSION: 1.0.0
# START_MODULE_CONTRACT
#   PURPOSE: Unit tests for backend registry selection and model resolution.
#   SCOPE: Backend discovery, capability checks, model metadata inspection
#   DEPENDS: M-CORE
#   LINKS: V-M-CORE
#   ROLE: TEST
#   MAP_MODE: LOCALS
# END_MODULE_CONTRACT
#
# START_MODULE_MAP
#   StubBackend - Minimal backend stub used for registry selection and capability tests
#   NoAffinityBackend - Backend stub with no manifest affinity match for rejection tests
#   test_backend_registry_prefers_explicit_backend - Verifies explicit backend selection wins over autoselection
#   test_backend_registry_raises_for_unknown_backend - Verifies unknown backend ids are rejected
#   test_backend_registry_rejects_unsupported_mode - Verifies unsupported synthesis modes raise capability errors
#   test_backend_registry_lists_selected_backend_metadata - Verifies list_backends reports selection state
#   test_backend_registry_resolves_model_spec_for_mode - Verifies mode-based model resolution
#   test_backend_registry_prefers_highest_rollout_preference_for_mode - Verifies rollout preference ordering for model selection
#   test_backend_registry_raises_model_not_available_for_unknown_model_identifier - Verifies unknown model ids surface not-available errors
#   test_backend_registry_raises_model_not_available_when_mode_has_no_local_artifacts - Verifies missing local artifacts surface not-available errors
#   test_backend_registry_rejects_model_when_backend_is_not_in_affinity - Verifies backend affinity is enforced
#   test_model_registry_applies_listed_preload_policy - Verifies listed preload policy preloads requested models
# END_MODULE_MAP
#
# START_CHANGE_SUMMARY
#   LAST_CHANGE: [v1.0.0 - GRACE integration: added MODULE_CONTRACT and MODULE_MAP]
# END_CHANGE_SUMMARY

from __future__ import annotations

from pathlib import Path

import pytest

from core.backends.base import LoadedModelHandle, TTSBackend
from core.backends.capabilities import BackendCapabilitySet, BackendDiagnostics
from core.backends.registry import BackendRegistry
from core.errors import (
    BackendCapabilityError,
    BackendNotAvailableError,
    ModelNotAvailableError,
)
from core.models.catalog import MODEL_SPECS
from core.services.model_registry import ModelRegistry


pytestmark = pytest.mark.unit


class StubBackend(TTSBackend):
    def __init__(
        self,
        *,
        key: str,
        available: bool,
        platform_supported: bool,
        missing_folders: set[str] | None = None,
    ):
        self.key = key
        self.label = key.upper()
        self._available = available
        self._platform_supported = platform_supported
        self._missing_folders = missing_folders or set()
        self.preloaded_specs: list[str] = []

    def capabilities(self) -> BackendCapabilitySet:
        return BackendCapabilitySet(
            supports_custom=True,
            supports_design=self.key != "clone-only",
            supports_clone=True,
            platforms=("darwin", "linux", "windows"),
        )

    def is_available(self) -> bool:
        return self._available

    def supports_platform(self) -> bool:
        return self._platform_supported

    def resolve_model_path(self, folder_name: str) -> Path | None:
        if folder_name in self._missing_folders:
            return None
        return Path(".models") / folder_name

    def load_model(self, spec):
        return LoadedModelHandle(
            spec=spec,
            runtime_model=object(),
            resolved_path=Path(".models") / spec.folder,
            backend_key=self.key,
        )

    def inspect_model(self, spec):
        cached = spec.api_name in self.preloaded_specs
        return {
            "key": spec.key,
            "id": spec.api_name,
            "name": spec.public_name,
            "mode": spec.mode,
            "folder": spec.folder,
            "backend": self.key,
            "configured": True,
            "available": True,
            "loadable": True,
            "runtime_ready": self._available,
            "cached": cached,
            "resolved_path": str(Path(".models") / spec.folder),
            "runtime_path": str(Path(".models") / spec.folder),
            "cache": {
                "loaded": cached,
                "cache_key": spec.folder,
                "backend": self.key,
                "normalized_runtime": False,
                "runtime_path": str(Path(".models") / spec.folder),
                "eviction_policy": "not_configured",
            },
            "missing_artifacts": [],
            "required_artifacts": ["config.json"],
            "capabilities": self.capabilities().to_dict(),
        }

    def readiness_diagnostics(self) -> BackendDiagnostics:
        return BackendDiagnostics(
            backend_key=self.key,
            backend_label=self.label,
            available=self._available,
            ready=self._available and self._platform_supported,
            reason=None,
            details={},
        )

    def cache_diagnostics(self) -> dict[str, object]:
        return {
            "cached_model_count": len(self.preloaded_specs),
            "cached_model_ids": list(self.preloaded_specs),
            "cache_policy": {
                "cache_scope": "process_local",
                "eviction": "not_configured",
            },
            "loaded_models": [
                {
                    "cache_key": model_id,
                    "model_id": model_id,
                    "backend": self.key,
                    "loaded": True,
                    "resolved_path": str(Path(".models") / model_id),
                    "runtime_path": str(Path(".models") / model_id),
                    "normalized_runtime": False,
                }
                for model_id in self.preloaded_specs
            ],
        }

    def preload_models(self, specs) -> dict[str, object]:
        loaded_model_ids = [spec.api_name for spec in specs]
        self.preloaded_specs = loaded_model_ids
        return {
            "requested": len(specs),
            "attempted": len(specs),
            "loaded": len(specs),
            "failed": 0,
            "loaded_model_ids": loaded_model_ids,
            "failed_model_ids": [],
            "errors": [],
        }

    def synthesize_custom(
        self,
        handle,
        *,
        text: str,
        output_dir: Path,
        language: str,
        speaker: str,
        instruct: str,
        speed: float,
    ) -> None:
        return None

    def synthesize_design(
        self,
        handle,
        *,
        text: str,
        output_dir: Path,
        language: str,
        voice_description: str,
    ) -> None:
        return None

    def synthesize_clone(
        self,
        handle,
        *,
        text: str,
        output_dir: Path,
        language: str,
        ref_audio_path: Path,
        ref_text: str | None,
    ) -> None:
        return None


class NoAffinityBackend(StubBackend):
    def __init__(self):
        super().__init__(key="custom-backend", available=True, platform_supported=True)


def test_backend_registry_prefers_explicit_backend():
    registry = BackendRegistry(
        [
            StubBackend(key="mlx", available=True, platform_supported=True),
            StubBackend(key="torch", available=True, platform_supported=True),
        ],
        requested_backend="torch",
        autoselect=True,
    )

    assert registry.selected_backend.key == "torch"
    assert registry.selection.selection_reason == "explicit_config"


def test_backend_registry_raises_for_unknown_backend():
    with pytest.raises(BackendNotAvailableError):
        BackendRegistry(
            [StubBackend(key="mlx", available=True, platform_supported=True)],
            requested_backend="unknown",
            autoselect=True,
        )


def test_backend_registry_rejects_unsupported_mode():
    registry = BackendRegistry(
        [StubBackend(key="clone-only", available=True, platform_supported=True)],
        autoselect=True,
    )

    with pytest.raises(BackendCapabilityError):
        registry.ensure_mode_supported("design")


def test_backend_registry_lists_selected_backend_metadata():
    registry = BackendRegistry(
        [
            StubBackend(key="mlx", available=False, platform_supported=True),
            StubBackend(key="torch", available=True, platform_supported=True),
        ],
        requested_backend="torch",
        autoselect=True,
    )

    payload = registry.list_backends()

    assert any(item["key"] == "torch" and item["selected"] is True for item in payload)
    assert any(item["key"] == "mlx" and item["selected"] is False for item in payload)


def test_backend_registry_resolves_model_spec_for_mode():
    registry = BackendRegistry(
        [StubBackend(key="torch", available=True, platform_supported=True)],
        requested_backend="torch",
        autoselect=True,
    )

    spec = registry.get_model_spec(mode="custom")

    assert spec == MODEL_SPECS["1"]


def test_backend_registry_prefers_highest_rollout_preference_for_mode():
    registry = BackendRegistry(
        [StubBackend(key="torch", available=True, platform_supported=True)],
        requested_backend="torch",
        autoselect=True,
    )

    spec = registry.get_model_spec(mode="clone")

    assert spec == MODEL_SPECS["3"]


def test_backend_registry_raises_model_not_available_for_unknown_model_identifier():
    registry = BackendRegistry(
        [StubBackend(key="torch", available=True, platform_supported=True)],
        requested_backend="torch",
        autoselect=True,
    )

    with pytest.raises(ModelNotAvailableError) as exc_info:
        registry.get_model_spec(model_name="unknown-model")

    assert exc_info.value.model_name == "unknown-model"
    assert exc_info.value.context.to_dict() == {
        "reason": "Requested model is not available: unknown-model",
        "model": "unknown-model",
        "backend": "torch",
    }


def test_backend_registry_raises_model_not_available_when_mode_has_no_local_artifacts():
    registry = BackendRegistry(
        [
            StubBackend(
                key="torch",
                available=True,
                platform_supported=True,
                missing_folders={
                    spec.folder
                    for spec in MODEL_SPECS.values()
                    if spec.mode == "custom"
                },
            )
        ],
        requested_backend="torch",
        autoselect=True,
    )

    with pytest.raises(ModelNotAvailableError) as exc_info:
        registry.get_model_spec(mode="custom")

    assert exc_info.value.model_name is None
    assert exc_info.value.context.to_dict() == {
        "reason": "No local model is available for mode: custom",
        "mode": "custom",
        "backend": "torch",
    }


def test_backend_registry_rejects_model_when_backend_is_not_in_affinity():
    registry = BackendRegistry(
        [NoAffinityBackend()], requested_backend="custom-backend", autoselect=True
    )

    with pytest.raises(BackendCapabilityError) as exc_info:
        registry.get_model_spec(model_name=MODEL_SPECS["1"].api_name)

    assert exc_info.value.context.to_dict() == {
        "reason": "Backend 'custom-backend' is not enabled for model 'Qwen3-TTS-12Hz-1.7B-CustomVoice-8bit'",
        "backend": "custom-backend",
        "model": "Qwen3-TTS-12Hz-1.7B-CustomVoice-8bit",
        "mode": "custom",
    }


def test_model_registry_applies_listed_preload_policy():
    backend = StubBackend(key="torch", available=True, platform_supported=True)
    backend_registry = BackendRegistry(
        [backend], requested_backend="torch", autoselect=True
    )

    registry = ModelRegistry(
        backend_registry=backend_registry,
        preload_policy="listed",
        preload_model_ids=(MODEL_SPECS["1"].api_name,),
    )

    report = registry.readiness_report()

    assert backend.preloaded_specs == [MODEL_SPECS["1"].api_name]
    assert report["loaded_models"] == 1
    assert report["preload"]["policy"] == "listed"
    assert report["preload"]["loaded_model_ids"] == [MODEL_SPECS["1"].api_name]
    assert report["cache_diagnostics"]["cached_model_count"] == 1
    assert report["items"][0]["preload"]["status"] == "loaded"
