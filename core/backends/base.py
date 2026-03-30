from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.backends.capabilities import BackendCapabilitySet, BackendDiagnostics
from core.models.catalog import ModelSpec


@dataclass(frozen=True)
class LoadedModelHandle:
    spec: ModelSpec
    runtime_model: Any
    resolved_path: Path | None
    backend_key: str


class TTSBackend(ABC):
    key: str
    label: str

    @abstractmethod
    def capabilities(self) -> BackendCapabilitySet:
        raise NotImplementedError

    @abstractmethod
    def is_available(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def supports_platform(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def resolve_model_path(self, folder_name: str) -> Path | None:
        raise NotImplementedError

    @abstractmethod
    def load_model(self, spec: ModelSpec) -> LoadedModelHandle:
        raise NotImplementedError

    @abstractmethod
    def inspect_model(self, spec: ModelSpec) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def readiness_diagnostics(self) -> BackendDiagnostics:
        raise NotImplementedError

    def cache_diagnostics(self) -> dict[str, Any]:
        return {
            "cached_model_count": 0,
            "cached_model_ids": [],
            "cache_policy": {
                "eviction": "not_configured",
            },
            "loaded_models": [],
        }

    def metrics_summary(self) -> dict[str, Any]:
        return {
            "cache": {
                "hit": {},
                "miss": {},
            },
            "load": {
                "failures": {},
                "duration_ms": {},
            },
        }

    def preload_models(self, specs: tuple[ModelSpec, ...]) -> dict[str, Any]:
        return {
            "requested": 0,
            "attempted": 0,
            "loaded": 0,
            "failed": 0,
            "loaded_model_ids": [],
            "failed_model_ids": [],
            "errors": [],
        }

    @abstractmethod
    def synthesize_custom(
        self,
        handle: LoadedModelHandle,
        *,
        text: str,
        output_dir: Path,
        speaker: str,
        instruct: str,
        speed: float,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    def synthesize_design(
        self,
        handle: LoadedModelHandle,
        *,
        text: str,
        output_dir: Path,
        voice_description: str,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    def synthesize_clone(
        self,
        handle: LoadedModelHandle,
        *,
        text: str,
        output_dir: Path,
        ref_audio_path: Path,
        ref_text: str | None,
    ) -> None:
        raise NotImplementedError
