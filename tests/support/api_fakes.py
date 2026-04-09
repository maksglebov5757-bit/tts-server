from __future__ import annotations

import io
import json
import time
import wave
from pathlib import Path
from typing import cast

import pytest

from core.backends.base import TTSBackend
from core.contracts.results import AudioResult, GenerationResult
from core.errors import (
    InferenceBusyError,
    ModelLoadError,
    ModelNotAvailableError,
    TTSGenerationError,
)
from core.services.model_registry import ModelRegistry
from server.bootstrap import ServerSettings


class DummyRegistry(ModelRegistry):
    def __init__(self, settings: ServerSettings):
        self.settings = settings

    @property
    def backend(self) -> TTSBackend:
        return cast(
            TTSBackend,
            type("BackendStub", (), {"key": "mlx", "label": "MLX Apple Silicon"})(),
        )

    def list_models(self) -> list[dict]:
        return [
            {
                "key": "1",
                "id": "Qwen3-TTS-12Hz-1.7B-CustomVoice-8bit",
                "name": "Custom Voice",
                "mode": "custom",
                "folder": "Qwen3-TTS-12Hz-1.7B-CustomVoice-8bit",
                "available": True,
                "backend": "mlx",
                "capabilities": {
                    "supports_custom": True,
                    "supports_design": True,
                    "supports_clone": True,
                },
            },
            {
                "key": "3",
                "id": "Qwen3-TTS-12Hz-1.7B-Base-8bit",
                "name": "Voice Cloning",
                "mode": "clone",
                "folder": "Qwen3-TTS-12Hz-1.7B-Base-8bit",
                "available": True,
                "backend": "mlx",
                "capabilities": {
                    "supports_custom": True,
                    "supports_design": True,
                    "supports_clone": True,
                },
            },
        ]

    def readiness_report(self) -> dict:
        return {
            "configured_models": 2,
            "available_models": 2,
            "loadable_models": 2,
            "runtime_ready_models": 2,
            "loaded_models": 1,
            "selected_backend": "mlx",
            "selected_backend_label": "MLX Apple Silicon",
            "backend_selection": {
                "requested_backend": None,
                "auto_selected": True,
                "selection_reason": "platform_and_runtime_match",
            },
            "backend_capabilities": {
                "supports_custom": True,
                "supports_design": True,
                "supports_clone": True,
                "supports_streaming": False,
                "supports_local_models": True,
                "supports_voice_prompt_cache": False,
                "supports_reference_transcription": False,
                "preferred_formats": ["wav"],
                "platforms": ["darwin"],
            },
            "backend_diagnostics": {
                "backend": "mlx",
                "label": "MLX Apple Silicon",
                "available": True,
                "ready": True,
                "reason": None,
                "details": {
                    "platform_supported": True,
                    "load_model_available": True,
                    "generate_audio_available": True,
                },
            },
            "cache_diagnostics": {
                "cached_model_count": 1,
                "cached_model_ids": ["Qwen3-TTS-12Hz-1.7B-CustomVoice-8bit"],
                "cache_policy": {
                    "cache_scope": "process_local",
                    "eviction": "not_configured",
                    "normalized_runtime_dirs": 1,
                },
                "loaded_models": [
                    {
                        "cache_key": "Qwen3-TTS-12Hz-1.7B-CustomVoice-8bit",
                        "model_id": "Qwen3-TTS-12Hz-1.7B-CustomVoice-8bit",
                        "backend": "mlx",
                        "loaded": True,
                        "resolved_path": "/tmp/custom",
                        "runtime_path": "/tmp/custom-runtime",
                        "normalized_runtime": True,
                    }
                ],
            },
            "metrics": {
                "selected_backend": {
                    "cache": {
                        "hit": {"mlx": 1},
                        "miss": {"mlx": 1},
                    },
                    "load": {
                        "failures": {},
                        "duration_ms": {
                            "mlx": {
                                "count": 1,
                                "avg_ms": 1.0,
                                "max_ms": 1.0,
                                "last_ms": 1.0,
                            }
                        },
                    },
                },
                "operational": {
                    "execution": {
                        "submitted": 1,
                        "started": 1,
                        "completed": 1,
                        "failed": 0,
                        "timeout": 0,
                        "cancelled": 0,
                        "queue_depth": {"current": 0, "peak": 1},
                    },
                    "models": {
                        "cache": {"hit": {"mlx": 1}, "miss": {"mlx": 1}},
                        "load": {
                            "failures": {},
                            "duration_ms": {
                                "mlx": {
                                    "count": 1,
                                    "avg_ms": 1.0,
                                    "max_ms": 1.0,
                                    "last_ms": 1.0,
                                }
                            },
                        },
                    },
                },
            },
            "preload": {
                "policy": "listed",
                "configured_model_ids": ["Qwen3-TTS-12Hz-1.7B-CustomVoice-8bit"],
                "requested_model_ids": ["Qwen3-TTS-12Hz-1.7B-CustomVoice-8bit"],
                "resolved_model_ids": ["Qwen3-TTS-12Hz-1.7B-CustomVoice-8bit"],
                "status": "completed",
                "policy_reason": "configured",
                "attempted": 1,
                "loaded": 1,
                "failed": 0,
                "loaded_model_ids": ["Qwen3-TTS-12Hz-1.7B-CustomVoice-8bit"],
                "failed_model_ids": [],
                "errors": [],
            },
            "available_backends": [
                {
                    "key": "mlx",
                    "label": "MLX Apple Silicon",
                    "selected": True,
                    "platform_supported": True,
                    "available": True,
                    "capabilities": {
                        "supports_custom": True,
                        "supports_design": True,
                        "supports_clone": True,
                    },
                    "diagnostics": {
                        "backend": "mlx",
                        "label": "MLX Apple Silicon",
                        "available": True,
                        "ready": True,
                        "reason": None,
                        "details": {},
                    },
                }
            ],
            "items": [
                {
                    "key": "1",
                    "id": "Qwen3-TTS-12Hz-1.7B-CustomVoice-8bit",
                    "name": "Custom Voice",
                    "mode": "custom",
                    "folder": "Qwen3-TTS-12Hz-1.7B-CustomVoice-8bit",
                    "backend": "mlx",
                    "configured": True,
                    "available": True,
                    "loadable": True,
                    "runtime_ready": True,
                    "cached": True,
                    "resolved_path": "/tmp/custom",
                    "runtime_path": "/tmp/custom-runtime",
                    "cache": {
                        "loaded": True,
                        "cache_key": "Qwen3-TTS-12Hz-1.7B-CustomVoice-8bit",
                        "backend": "mlx",
                        "normalized_runtime": True,
                        "runtime_path": "/tmp/custom-runtime",
                        "eviction_policy": "not_configured",
                    },
                    "preload": {
                        "policy": "listed",
                        "requested": True,
                        "status": "loaded",
                    },
                    "missing_artifacts": [],
                    "required_artifacts": [
                        "config.json",
                        "model.safetensors|model.safetensors.index.json",
                        "tokenizer_config.json|vocab.json",
                    ],
                    "capabilities": {
                        "supports_custom": True,
                        "supports_design": True,
                        "supports_clone": True,
                    },
                },
                {
                    "key": "3",
                    "id": "Qwen3-TTS-12Hz-1.7B-Base-8bit",
                    "name": "Voice Cloning",
                    "mode": "clone",
                    "folder": "Qwen3-TTS-12Hz-1.7B-Base-8bit",
                    "backend": "mlx",
                    "configured": True,
                    "available": True,
                    "loadable": True,
                    "runtime_ready": True,
                    "cached": False,
                    "resolved_path": "/tmp/clone",
                    "runtime_path": "/tmp/clone",
                    "cache": {
                        "loaded": False,
                        "cache_key": "Qwen3-TTS-12Hz-1.7B-Base-8bit",
                        "backend": "mlx",
                        "normalized_runtime": False,
                        "runtime_path": "/tmp/clone",
                        "eviction_policy": "not_configured",
                    },
                    "preload": {
                        "policy": "listed",
                        "requested": False,
                        "status": "not_requested",
                    },
                    "missing_artifacts": [],
                    "required_artifacts": [
                        "config.json",
                        "model.safetensors|model.safetensors.index.json",
                        "tokenizer_config.json|vocab.json",
                    ],
                    "capabilities": {
                        "supports_custom": True,
                        "supports_design": True,
                        "supports_clone": True,
                    },
                },
            ],
            "registry_ready": True,
        }

    def is_ready(self):
        report = self.readiness_report()
        return True, report


class DummyTTSService:
    def __init__(self, settings: ServerSettings):
        self.settings = settings
        self.last_clone_request = None
        self.last_custom_request = None
        self.last_design_request = None

    def synthesize_custom(self, request):
        self.last_custom_request = request
        return GenerationResult(
            audio=_audio_result(self.settings.outputs_dir / "dummy_custom.wav"),
            saved_path=(self.settings.outputs_dir / "saved_custom.wav")
            if request.save_output
            else None,
            model=request.model or "Qwen3-TTS-12Hz-1.7B-CustomVoice-8bit",
            mode="custom",
            backend="mlx",
        )

    def synthesize_design(self, request):
        self.last_design_request = request
        return GenerationResult(
            audio=_audio_result(self.settings.outputs_dir / "dummy_design.wav"),
            saved_path=(self.settings.outputs_dir / "saved_design.wav")
            if request.save_output
            else None,
            model=request.model or "Qwen3-TTS-12Hz-1.7B-VoiceDesign-8bit",
            mode="design",
            backend="mlx",
        )

    def synthesize_clone(self, request):
        self.last_clone_request = request
        return GenerationResult(
            audio=_audio_result(self.settings.outputs_dir / "dummy_clone.wav"),
            saved_path=(self.settings.outputs_dir / "saved_clone.wav")
            if request.save_output
            else None,
            model=request.model or "Qwen3-TTS-12Hz-1.7B-Base-8bit",
            mode="clone",
            backend="mlx",
        )


class FailingTTSService(DummyTTSService):
    def synthesize_custom(self, request):
        raise ModelLoadError(
            "mlx runtime failed",
            details={"model": request.model, "runtime_dependency": "mlx_audio"},
        )


class BusyTTSService(DummyTTSService):
    def synthesize_custom(self, request):
        raise InferenceBusyError(
            "Inference is already in progress", details={"queue_depth": 1}
        )


class MissingModelTTSService(DummyTTSService):
    def synthesize_custom(self, request):
        raise ModelNotAvailableError(
            model_name=request.model,
            details={"model": request.model, "backend": "mlx"},
        )


class MissingModeTTSService(DummyTTSService):
    def synthesize_design(self, request):
        raise ModelNotAvailableError(
            reason="No local model is available for mode: design",
            details={"mode": "design", "backend": "mlx"},
        )


class SlowTTSService(DummyTTSService):
    def __init__(self, settings: ServerSettings, *, sleep_seconds: float):
        super().__init__(settings)
        self.sleep_seconds = sleep_seconds

    def synthesize_custom(self, request):
        time.sleep(self.sleep_seconds)
        return super().synthesize_custom(request)


class WorkerFailingTTSService(DummyTTSService):
    def synthesize_custom(self, request):
        raise TTSGenerationError(
            "worker execution failed", details={"failure_kind": "worker_exception"}
        )


class DegradedRegistry(DummyRegistry):
    def readiness_report(self) -> dict:
        report = super().readiness_report()
        report["runtime_ready_models"] = 0
        report["registry_ready"] = False
        report["backend_diagnostics"]["ready"] = False
        report["preload"]["status"] = "failed"
        report["preload"]["failed"] = 1
        report["preload"]["failed_model_ids"] = ["Qwen3-TTS-12Hz-1.7B-CustomVoice-8bit"]
        report["preload"]["errors"] = [
            {
                "model": "Qwen3-TTS-12Hz-1.7B-CustomVoice-8bit",
                "reason": "missing_artifacts",
            }
        ]
        report["items"][0]["runtime_ready"] = False
        report["items"][0]["preload"]["status"] = "failed"
        report["items"][0]["missing_artifacts"] = ["config.json"]
        return report


def make_wav_bytes() -> bytes:
    buffer = io.BytesIO()
    silence_frame = bytes([0, 0])
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(24000)
        wav_file.writeframes(silence_frame * 240)
    return buffer.getvalue()


def _audio_result(path: Path) -> AudioResult:
    return AudioResult(path=path, bytes_data=make_wav_bytes())


def extract_json_logs(caplog: pytest.LogCaptureFixture, event_name: str) -> list[dict]:
    matched: list[dict] = []
    for record in caplog.records:
        try:
            payload = json.loads(record.getMessage())
        except json.JSONDecodeError:
            continue
        if payload.get("event") == event_name:
            matched.append(payload)
    return matched
