# FILE: core/services/tts_service.py
# VERSION: 1.0.0
# START_MODULE_CONTRACT
#   PURPOSE: Coordinate inference for custom, design, and clone synthesis modes.
#   SCOPE: TTSService class with synthesize_custom/design/clone, generate_audio dispatcher
#   DEPENDS: M-MODEL-REGISTRY, M-CONFIG, M-ERRORS, M-OBSERVABILITY, M-INFRASTRUCTURE
#   LINKS: M-TTS-SERVICE
#   ROLE: RUNTIME
#   MAP_MODE: EXPORTS
# END_MODULE_CONTRACT
#
# START_MODULE_MAP
#   LOGGER - Module logger for synthesis service events
#   TTSService - Core synthesis coordinator with inference guard
#   generate_audio - Dispatch synthesis call to the appropriate backend method
# END_MODULE_MAP
#
# START_CHANGE_SUMMARY
#   LAST_CHANGE: [v1.0.0 - GRACE integration: added MODULE_CONTRACT, MODULE_MAP, function contracts, semantic blocks, and migrated log events to block-reference format]
# END_CHANGE_SUMMARY

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.config import CoreSettings
from core.contracts.commands import (
    CustomVoiceCommand,
    VoiceCloneCommand,
    VoiceDesignCommand,
)
from core.contracts.results import GenerationResult
from core.errors import AudioArtifactNotFoundError, TTSGenerationError
from core.infrastructure.audio_io import (
    convert_audio_to_wav_if_needed,
    persist_output,
    read_generated_wav,
    temporary_output_dir,
)
from core.infrastructure.concurrency import InferenceGuard
from core.models.catalog import ModelSpec
from core.observability import Timer, get_logger, log_event, operation_scope
from core.services.model_registry import ModelRegistry


LOGGER = get_logger(__name__)


# START_CONTRACT: generate_audio
#   PURPOSE: Dispatch a generation request to the backend method that matches the requested synthesis mode.
#   INPUTS: { args: tuple[object, ...] - Positional passthrough arguments, kwargs: dict[str, Any] - Backend, handle, mode, text, output_path, and mode-specific generation fields }
#   OUTPUTS: { None - Invokes the backend synthesis method and writes output artifacts }
#   SIDE_EFFECTS: Triggers backend inference and writes generated audio files into the provided output directory
#   LINKS: M-TTS-SERVICE
# END_CONTRACT: generate_audio
def generate_audio(*args, **kwargs):
    backend = kwargs.pop("backend")
    mode = kwargs.pop("mode")
    handle = kwargs.pop("handle")
    output_path = Path(kwargs.pop("output_path"))
    text = kwargs.pop("text")
    language = kwargs.pop("language")

    if mode == "custom":
        backend.synthesize_custom(
            handle,
            text=text,
            output_dir=output_path,
            language=language,
            speaker=kwargs.pop("voice"),
            instruct=kwargs.pop("instruct"),
            speed=kwargs.pop("speed"),
        )
        return

    if mode == "design":
        backend.synthesize_design(
            handle,
            text=text,
            output_dir=output_path,
            language=language,
            voice_description=kwargs.pop("instruct"),
        )
        return

    if mode == "clone":
        backend.synthesize_clone(
            handle,
            text=text,
            output_dir=output_path,
            language=language,
            ref_audio_path=Path(kwargs.pop("ref_audio")),
            ref_text=kwargs.pop("ref_text", None),
        )
        return

    raise TTSGenerationError(
        f"Unsupported generation mode: {mode}",
        details={"mode": mode, "backend": handle.backend_key},
    )


# START_CONTRACT: TTSService
#   PURPOSE: Coordinate model resolution, guarded inference execution, and output persistence for TTS requests.
#   INPUTS: { registry: ModelRegistry - Model registry used to resolve and load models, settings: CoreSettings - Shared runtime settings controlling audio handling and persistence, inference_guard: InferenceGuard | None - Optional shared inference concurrency guard }
#   OUTPUTS: { instance - TTS synthesis service for custom, design, and clone modes }
#   SIDE_EFFECTS: none
#   LINKS: M-TTS-SERVICE
# END_CONTRACT: TTSService
class TTSService:
    def __init__(
        self,
        registry: ModelRegistry,
        settings: CoreSettings,
        inference_guard: InferenceGuard | None = None,
    ):
        self.registry = registry
        self.settings = settings
        self.inference_guard = inference_guard or InferenceGuard()

    def _backend_key(self, fallback: str | None = None) -> str | None:
        backend = getattr(self.registry, "backend", None)
        if backend is not None:
            return getattr(backend, "key", fallback)
        return fallback

    @staticmethod
    def _handle_backend_key(handle, fallback: str | None = None) -> str | None:
        return getattr(handle, "backend_key", fallback)

    # START_CONTRACT: synthesize_custom
    #   PURPOSE: Run a guarded custom-voice synthesis workflow from a validated command.
    #   INPUTS: { command: CustomVoiceCommand - Custom voice synthesis request }
    #   OUTPUTS: { GenerationResult - Generated audio result and persistence metadata }
    #   SIDE_EFFECTS: Loads model state, emits structured logs, performs inference, and may persist generated audio
    #   LINKS: M-TTS-SERVICE
    # END_CONTRACT: synthesize_custom
    def synthesize_custom(self, command: CustomVoiceCommand) -> GenerationResult:
        with operation_scope("core.tts_service.synthesize_custom"):
            log_event(
                LOGGER,
                level=20,
                event="[TTSService][synthesize_custom][SYNTHESIZE_CUSTOM]",
                message="Starting custom voice synthesis",
                model=command.model,
                mode="custom",
                save_output=command.save_output,
                text_length=len(command.text),
                language=command.language,
                backend=self._backend_key(),
            )
            spec, handle = self.registry.get_model(
                model_name=command.model, mode="custom"
            )
            result = self._run_generation(
                spec=spec,
                handle=handle,
                text=command.text,
                save_output=command.save_output,
                generation_kwargs={
                    "language": command.language,
                    "voice": command.speaker,
                    "instruct": command.instruct,
                    "speed": command.speed,
                },
            )
            log_event(
                LOGGER,
                level=20,
                event="[TTSService][synthesize_custom][SYNTHESIZE_CUSTOM]",
                message="Custom voice synthesis finished",
                model=result.model,
                mode=result.mode,
                saved_path=str(result.saved_path) if result.saved_path else None,
                backend=result.backend,
            )
            return result

    # START_CONTRACT: synthesize_design
    #   PURPOSE: Run a guarded voice-design synthesis workflow from a validated command.
    #   INPUTS: { command: VoiceDesignCommand - Voice design synthesis request }
    #   OUTPUTS: { GenerationResult - Generated audio result and persistence metadata }
    #   SIDE_EFFECTS: Loads model state, emits structured logs, performs inference, and may persist generated audio
    #   LINKS: M-TTS-SERVICE
    # END_CONTRACT: synthesize_design
    def synthesize_design(self, command: VoiceDesignCommand) -> GenerationResult:
        with operation_scope("core.tts_service.synthesize_design"):
            log_event(
                LOGGER,
                level=20,
                event="[TTSService][synthesize_design][SYNTHESIZE_DESIGN]",
                message="Starting voice design synthesis",
                model=command.model,
                mode="design",
                save_output=command.save_output,
                text_length=len(command.text),
                language=command.language,
                backend=self._backend_key(),
            )
            spec, handle = self.registry.get_model(
                model_name=command.model, mode="design"
            )
            result = self._run_generation(
                spec=spec,
                handle=handle,
                text=command.text,
                save_output=command.save_output,
                generation_kwargs={
                    "language": command.language,
                    "instruct": command.voice_description,
                },
            )
            log_event(
                LOGGER,
                level=20,
                event="[TTSService][synthesize_design][SYNTHESIZE_DESIGN]",
                message="Voice design synthesis finished",
                model=result.model,
                mode=result.mode,
                saved_path=str(result.saved_path) if result.saved_path else None,
                backend=result.backend,
            )
            return result

    # START_CONTRACT: synthesize_clone
    #   PURPOSE: Run a guarded voice-clone synthesis workflow including reference audio preparation.
    #   INPUTS: { command: VoiceCloneCommand - Voice clone synthesis request with reference audio metadata }
    #   OUTPUTS: { GenerationResult - Generated audio result and persistence metadata }
    #   SIDE_EFFECTS: Copies and may convert reference audio, loads model state, emits structured logs, performs inference, and may persist generated audio
    #   LINKS: M-TTS-SERVICE
    # END_CONTRACT: synthesize_clone
    def synthesize_clone(self, command: VoiceCloneCommand) -> GenerationResult:
        with operation_scope("core.tts_service.synthesize_clone"):
            # START_BLOCK_VALIDATE_CLONE_INPUT
            if command.ref_audio_path is None:
                raise TTSGenerationError(
                    "Reference audio is required for clone synthesis",
                    details={
                        "mode": "clone",
                        "reference_audio": None,
                        "backend": self._backend_key(),
                    },
                )
            # END_BLOCK_VALIDATE_CLONE_INPUT

            log_event(
                LOGGER,
                level=20,
                event="[TTSService][synthesize_clone][SYNTHESIZE_CLONE]",
                message="Starting clone synthesis",
                model=command.model,
                mode="clone",
                save_output=command.save_output,
                text_length=len(command.text),
                language=command.language,
                ref_text_provided=bool(command.ref_text),
                ref_audio_path=str(command.ref_audio_path),
                backend=self._backend_key(),
            )
            spec, handle = self.registry.get_model(
                model_name=command.model, mode="clone"
            )

            with temporary_output_dir(prefix="qwen3_tts_clone_input_") as temp_dir:
                # START_BLOCK_PREPARE_REFERENCE_AUDIO
                source_audio = temp_dir / command.ref_audio_path.name
                source_audio.write_bytes(command.ref_audio_path.read_bytes())
                wav_audio, converted = convert_audio_to_wav_if_needed(
                    source_audio, self.settings
                )
                log_event(
                    LOGGER,
                    level=20,
                    event="[TTSService][synthesize_clone][BLOCK_PREPARE_REFERENCE_AUDIO]",
                    message="Reference audio prepared for clone synthesis",
                    model=spec.api_name,
                    mode=spec.mode,
                    source_audio=str(source_audio),
                    prepared_audio=str(wav_audio),
                    converted=converted,
                    backend=self._handle_backend_key(handle, self._backend_key()),
                )
                # END_BLOCK_PREPARE_REFERENCE_AUDIO
                try:
                    # START_BLOCK_EXECUTE_CLONE
                    result = self._run_generation(
                        spec=spec,
                        handle=handle,
                        text=command.text,
                        save_output=command.save_output,
                        generation_kwargs={
                            "language": command.language,
                            "ref_audio": str(wav_audio),
                            "ref_text": command.ref_text or ".",
                        },
                    )
                    log_event(
                        LOGGER,
                        level=20,
                        event="[TTSService][synthesize_clone][BLOCK_EXECUTE_CLONE]",
                        message="Clone synthesis finished",
                        model=result.model,
                        mode=result.mode,
                        saved_path=str(result.saved_path)
                        if result.saved_path
                        else None,
                        backend=result.backend,
                    )
                    return result
                    # END_BLOCK_EXECUTE_CLONE
                finally:
                    # START_BLOCK_CLEANUP_TEMP_FILES
                    if converted and wav_audio.exists():
                        wav_audio.unlink(missing_ok=True)
                    # END_BLOCK_CLEANUP_TEMP_FILES

    # START_CONTRACT: _run_generation
    #   PURPOSE: Execute the shared guarded generation pipeline for a resolved model handle.
    #   INPUTS: { spec: ModelSpec - Resolved model specification, handle: object - Loaded backend model handle, text: str - Input text to synthesize, save_output: bool - Whether the generated audio should be persisted, generation_kwargs: dict[str, Any] - Mode-specific backend generation arguments }
    #   OUTPUTS: { GenerationResult - Generated audio result and persistence metadata }
    #   SIDE_EFFECTS: Acquires and releases the inference guard, writes temporary output files, emits structured logs, and may persist generated audio
    #   LINKS: M-TTS-SERVICE
    # END_CONTRACT: _run_generation
    def _run_generation(
        self,
        *,
        spec: ModelSpec,
        handle,
        text: str,
        save_output: bool,
        generation_kwargs: dict[str, Any],
    ) -> GenerationResult:
        timer = Timer()
        generation_kwargs = dict(generation_kwargs)
        language = generation_kwargs.pop("language", "auto")
        # START_BLOCK_ACQUIRE_INFERENCE
        self.inference_guard.acquire()
        log_event(
            LOGGER,
            level=20,
            event="[TTSService][_run_generation][BLOCK_ACQUIRE_INFERENCE]",
            message="Inference slot acquired",
            model=spec.api_name,
            mode=spec.mode,
            save_output=save_output,
            text_length=len(text),
            language=language,
            backend=self._handle_backend_key(handle, self._backend_key()),
        )
        # END_BLOCK_ACQUIRE_INFERENCE
        try:
            with temporary_output_dir(prefix="qwen3_tts_output_") as output_dir:
                try:
                    # START_BLOCK_RUN_BACKEND_SYNTHESIS
                    generate_audio(
                        backend=getattr(self.registry, "backend", None),
                        handle=handle,
                        mode=spec.mode,
                        text=text,
                        language=language,
                        output_path=str(output_dir),
                        **generation_kwargs,
                    )
                    audio = read_generated_wav(output_dir)
                    # END_BLOCK_RUN_BACKEND_SYNTHESIS
                except AudioArtifactNotFoundError as exc:
                    # START_BLOCK_HANDLE_GENERATION_ERRORS
                    log_event(
                        LOGGER,
                        level=40,
                        event="[TTSService][_run_generation][BLOCK_HANDLE_GENERATION_ERRORS]",
                        message="Generation finished without output artifact",
                        model=spec.api_name,
                        mode=spec.mode,
                        duration_ms=timer.elapsed_ms,
                        language=language,
                        error=str(exc),
                        backend=self._handle_backend_key(handle, self._backend_key()),
                    )
                    raise TTSGenerationError(
                        str(exc),
                        details={
                            "model": spec.api_name,
                            "mode": spec.mode,
                            "failure_kind": "missing_artifact",
                            "backend": self._handle_backend_key(
                                handle, self._backend_key()
                            ),
                        },
                    ) from exc
                except TTSGenerationError as exc:
                    log_event(
                        LOGGER,
                        level=40,
                        event="[TTSService][_run_generation][BLOCK_HANDLE_GENERATION_ERRORS]",
                        message="Generation failed with controlled error",
                        model=spec.api_name,
                        mode=spec.mode,
                        language=language,
                        duration_ms=timer.elapsed_ms,
                        error=str(exc),
                        backend=self._handle_backend_key(handle, self._backend_key()),
                    )
                    raise
                except Exception as exc:  # pragma: no cover
                    log_event(
                        LOGGER,
                        level=40,
                        event="[TTSService][_run_generation][BLOCK_HANDLE_GENERATION_ERRORS]",
                        message="Generation failed with unexpected error",
                        model=spec.api_name,
                        mode=spec.mode,
                        language=language,
                        duration_ms=timer.elapsed_ms,
                        error=str(exc),
                        backend=self._handle_backend_key(handle, self._backend_key()),
                    )
                    raise TTSGenerationError(
                        str(exc),
                        details={
                            "model": spec.api_name,
                            "mode": spec.mode,
                            "backend": self._handle_backend_key(
                                handle, self._backend_key()
                            ),
                        },
                    ) from exc
                    # END_BLOCK_HANDLE_GENERATION_ERRORS

                # START_BLOCK_PERSIST_OUTPUT
                saved_path = None
                if save_output:
                    saved_path = persist_output(
                        audio, spec.output_subfolder, text, self.settings
                    )

                result = GenerationResult(
                    audio=audio,
                    saved_path=saved_path,
                    model=spec.api_name,
                    mode=spec.mode,
                    backend=self._handle_backend_key(handle, self._backend_key())
                    or "unknown",
                )
                log_event(
                    LOGGER,
                    level=20,
                    event="[TTSService][_run_generation][BLOCK_PERSIST_OUTPUT]",
                    message="Generation completed successfully",
                    model=result.model,
                    mode=result.mode,
                    duration_ms=timer.elapsed_ms,
                    language=language,
                    saved_path=str(result.saved_path) if result.saved_path else None,
                    audio_path=str(result.audio.path),
                    backend=result.backend,
                )
                return result
                # END_BLOCK_PERSIST_OUTPUT
        finally:
            # START_BLOCK_RELEASE_INFERENCE
            self.inference_guard.release()
            log_event(
                LOGGER,
                level=20,
                event="[TTSService][_run_generation][BLOCK_RELEASE_INFERENCE]",
                message="Inference slot released",
                model=spec.api_name,
                mode=spec.mode,
                duration_ms=timer.elapsed_ms,
                language=language,
                backend=self._handle_backend_key(handle, self._backend_key()),
            )
            # END_BLOCK_RELEASE_INFERENCE

__all__ = [
    "LOGGER",
    "generate_audio",
    "TTSService",
]
