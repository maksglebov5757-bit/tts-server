from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import uuid
from pathlib import Path
from typing import Callable, Optional, TypeVar

from starlette.datastructures import UploadFile as StarletteUploadFile

from fastapi import FastAPI, File, Form, Header, Request, Response, UploadFile
from fastapi.responses import JSONResponse

from core.contracts.commands import (
    CustomVoiceCommand,
    VoiceCloneCommand,
    VoiceDesignCommand,
)
from core.contracts.jobs import (
    JobOperation,
    JobSnapshot,
    JobStatus,
    create_job_submission,
)
from core.errors import (
    JobNotCancellableError,
    JobNotFoundError,
    JobNotReadyError,
    JobNotSucceededError,
    RequestTimeoutError,
)
from core.observability import Timer, log_event, operation_scope
from server.api.auth import ensure_job_owner_access
from server.api.contracts import ErrorDescriptor
from server.api.policies import (
    enforce_async_submit_admission,
    enforce_job_cancel_admission,
    enforce_job_read_admission,
    enforce_sync_tts_admission,
)
from server.api.responses import (
    build_audio_response,
    build_error_response,
    public_artifact_name,
    resolve_save_output,
)
from server.schemas.audio import (
    CustomTTSRequest,
    DesignTTSRequest,
    JobFailurePayload,
    JobSnapshotPayload,
    OpenAISpeechRequest,
    normalize_language_value,
    validate_text_length,
)
from server.schemas.errors import ErrorResponse


T = TypeVar("T")


_ALLOWED_CLONE_UPLOAD_CONTENT_TYPES = frozenset(
    {
        "audio/wav",
        "audio/x-wav",
        "audio/wave",
        "audio/vnd.wave",
        "audio/mpeg",
        "audio/mp3",
        "audio/flac",
        "audio/x-flac",
        "audio/ogg",
        "audio/webm",
        "audio/mp4",
        "audio/x-m4a",
        "video/webm",
        "application/octet-stream",
    }
)
_ALLOWED_CLONE_UPLOAD_SUFFIXES = frozenset(
    {".wav", ".mp3", ".flac", ".ogg", ".webm", ".m4a", ".mp4"}
)


def build_text_length_error(
    *, request: Request, field_name: str, message: str
) -> JSONResponse:
    return build_error_response(
        request=request,
        descriptor=ErrorDescriptor(
            status_code=422,
            code="validation_error",
            message="Request validation failed",
            details={
                "errors": [
                    {"loc": ["body", field_name], "msg": message, "type": "value_error"}
                ]
            },
        ),
    )


def build_upload_validation_error(
    *, request: Request, code: str, message: str, details: dict[str, object]
) -> JSONResponse:
    return build_error_response(
        request=request,
        descriptor=ErrorDescriptor(
            status_code=400,
            code=code,
            message=message,
            details=details,
        ),
    )


def enforce_text_length(*, value: str, field_name: str, max_chars: int) -> str:
    return validate_text_length(value, field_name=field_name, max_chars=max_chars)


def current_principal_id(request: Request) -> str:
    return request.state.principal.principal_id


def resolve_idempotency_scope(request: Request) -> str:
    return current_principal_id(request)


def build_job_urls(request: Request, job_id: str) -> tuple[str, str, str]:
    return (
        str(request.url_for("tts_job_status", job_id=job_id)),
        str(request.url_for("tts_job_result", job_id=job_id)),
        str(request.url_for("tts_job_cancel", job_id=job_id)),
    )


def build_job_snapshot_payload(
    request: Request, snapshot: JobSnapshot
) -> JobSnapshotPayload:
    status_url, result_url, cancel_url = build_job_urls(request, snapshot.job_id)
    terminal_error = snapshot.terminal_error
    return JobSnapshotPayload(
        request_id=getattr(request.state, "request_id", "unknown"),
        job_id=snapshot.job_id,
        submit_request_id=snapshot.submit_request_id,
        status=snapshot.status.value,
        operation=snapshot.operation.value,
        mode=snapshot.mode,
        model=snapshot.requested_model,
        backend=snapshot.backend,
        response_format=snapshot.response_format,
        save_output=snapshot.save_output,
        created_at=snapshot.created_at,
        started_at=snapshot.started_at,
        completed_at=snapshot.completed_at,
        saved_path=public_artifact_name(snapshot.saved_path)
        if snapshot.saved_path is not None
        else None,
        terminal_error=(
            JobFailurePayload(
                code=terminal_error.code,
                message=terminal_error.message,
                details=terminal_error.details,
            )
            if terminal_error is not None
            else None
        ),
        status_url=status_url,
        result_url=result_url,
        cancel_url=cancel_url,
        idempotency_key=snapshot.idempotency_key,
    )


def get_job_snapshot_or_raise(request: Request, job_id: str) -> JobSnapshot:
    snapshot = request.app.state.job_execution.get_job(job_id)
    if snapshot is None:
        raise JobNotFoundError(job_id)
    ensure_job_owner_access(request, owner_principal_id=snapshot.owner_principal_id)
    return snapshot


def build_idempotency_fingerprint(
    *, operation: JobOperation, payload: dict[str, object]
) -> str:
    normalized_payload = json.dumps(
        {
            "operation": operation.value,
            "payload": payload,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(normalized_payload.encode("utf-8")).hexdigest()


def create_custom_job_submission_from_openai(
    request: Request,
    payload: OpenAISpeechRequest,
    *,
    idempotency_key: Optional[str] = None,
):
    input_text = enforce_text_length(
        value=payload.input,
        field_name="input",
        max_chars=request.app.state.settings.max_input_text_chars,
    )
    save_output = request.app.state.settings.default_save_output
    return create_job_submission(
        operation=JobOperation.SYNTHESIZE_CUSTOM,
        command=CustomVoiceCommand(
            text=input_text,
            model=payload.model,
            save_output=save_output,
            language=payload.language,
            speaker=payload.voice,
            instruct="Normal tone",
            speed=payload.speed,
        ),
        submit_request_id=request.state.request_id,
        owner_principal_id=current_principal_id(request),
        response_format=payload.response_format,
        save_output=save_output,
        execution_timeout_seconds=request.app.state.settings.request_timeout_seconds,
        idempotency_key=idempotency_key,
        idempotency_scope=resolve_idempotency_scope(request)
        if idempotency_key is not None
        else None,
        idempotency_fingerprint=(
            build_idempotency_fingerprint(
                operation=JobOperation.SYNTHESIZE_CUSTOM,
                payload={
                    "model": payload.model,
                    "input": input_text,
                    "voice": payload.voice,
                    "language": payload.language,
                    "response_format": payload.response_format,
                    "speed": payload.speed,
                    "save_output": save_output,
                },
            )
            if idempotency_key is not None
            else None
        ),
    )


def create_custom_job_submission_from_custom(
    request: Request,
    payload: CustomTTSRequest,
    *,
    idempotency_key: Optional[str] = None,
):
    text = enforce_text_length(
        value=payload.text,
        field_name="text",
        max_chars=request.app.state.settings.max_input_text_chars,
    )
    save_output = resolve_save_output(
        payload.save_output, request.app.state.settings.default_save_output
    )
    instruct = payload.instruct or payload.emotion or "Normal tone"
    return create_job_submission(
        operation=JobOperation.SYNTHESIZE_CUSTOM,
        command=CustomVoiceCommand(
            text=text,
            model=payload.model,
            save_output=save_output,
            language=payload.language,
            speaker=payload.speaker,
            instruct=instruct,
            speed=payload.speed,
        ),
        submit_request_id=request.state.request_id,
        owner_principal_id=current_principal_id(request),
        response_format="wav",
        save_output=save_output,
        execution_timeout_seconds=request.app.state.settings.request_timeout_seconds,
        idempotency_key=idempotency_key,
        idempotency_scope=resolve_idempotency_scope(request)
        if idempotency_key is not None
        else None,
        idempotency_fingerprint=(
            build_idempotency_fingerprint(
                operation=JobOperation.SYNTHESIZE_CUSTOM,
                payload={
                    "model": payload.model,
                    "text": text,
                    "speaker": payload.speaker,
                    "emotion": payload.emotion,
                    "instruct": instruct,
                    "language": payload.language,
                    "speed": payload.speed,
                    "save_output": save_output,
                    "response_format": "wav",
                },
            )
            if idempotency_key is not None
            else None
        ),
    )


def create_design_job_submission(
    request: Request,
    payload: DesignTTSRequest,
    *,
    idempotency_key: Optional[str] = None,
):
    text = enforce_text_length(
        value=payload.text,
        field_name="text",
        max_chars=request.app.state.settings.max_input_text_chars,
    )
    save_output = resolve_save_output(
        payload.save_output, request.app.state.settings.default_save_output
    )
    voice_description = payload.voice_description
    return create_job_submission(
        operation=JobOperation.SYNTHESIZE_DESIGN,
        command=VoiceDesignCommand(
            text=text,
            model=payload.model,
            save_output=save_output,
            language=payload.language,
            voice_description=voice_description,
        ),
        submit_request_id=request.state.request_id,
        owner_principal_id=current_principal_id(request),
        response_format="wav",
        save_output=save_output,
        execution_timeout_seconds=request.app.state.settings.request_timeout_seconds,
        idempotency_key=idempotency_key,
        idempotency_scope=resolve_idempotency_scope(request)
        if idempotency_key is not None
        else None,
        idempotency_fingerprint=(
            build_idempotency_fingerprint(
                operation=JobOperation.SYNTHESIZE_DESIGN,
                payload={
                    "model": payload.model,
                    "text": text,
                    "voice_description": voice_description,
                    "language": payload.language,
                    "save_output": save_output,
                    "response_format": "wav",
                },
            )
            if idempotency_key is not None
            else None
        ),
    )


def validate_clone_upload(
    request: Request, ref_audio: UploadFile, upload_bytes: bytes
) -> JSONResponse | None:
    if not upload_bytes:
        return build_upload_validation_error(
            request=request,
            code="invalid_upload_audio",
            message="Uploaded reference audio is empty",
            details={"field": "ref_audio"},
        )

    if len(upload_bytes) > request.app.state.settings.max_upload_size_bytes:
        return build_upload_validation_error(
            request=request,
            code="upload_too_large",
            message="Uploaded file exceeds configured size limit",
            details={
                "max_upload_size_bytes": request.app.state.settings.max_upload_size_bytes
            },
        )

    filename = ref_audio.filename or "reference.wav"
    suffix = Path(filename).suffix.lower()
    content_type = (ref_audio.content_type or "application/octet-stream").lower()

    if suffix not in _ALLOWED_CLONE_UPLOAD_SUFFIXES:
        return build_upload_validation_error(
            request=request,
            code="unsupported_upload_media_type",
            message="Unsupported reference audio file type",
            details={
                "field": "ref_audio",
                "content_type": content_type,
                "allowed_extensions": sorted(_ALLOWED_CLONE_UPLOAD_SUFFIXES),
            },
        )

    if content_type not in _ALLOWED_CLONE_UPLOAD_CONTENT_TYPES:
        return build_upload_validation_error(
            request=request,
            code="unsupported_upload_media_type",
            message="Unsupported reference audio media type",
            details={
                "field": "ref_audio",
                "content_type": content_type,
                "allowed_content_types": sorted(_ALLOWED_CLONE_UPLOAD_CONTENT_TYPES),
            },
        )

    return None


def build_clone_staged_path(
    request: Request, ref_audio: StarletteUploadFile, *, prefix: str
) -> Path:
    suffix = Path(ref_audio.filename or "reference.wav").suffix.lower() or ".wav"
    return (
        request.app.state.settings.upload_staging_dir
        / f"{prefix}_{uuid.uuid4().hex}{suffix}"
    )


async def stage_clone_job_submission(
    request: Request,
    *,
    text: str,
    ref_audio: UploadFile,
    ref_text: Optional[str],
    language: str,
    model: Optional[str],
    save_output: Optional[bool],
    idempotency_key: Optional[str] = None,
):
    stripped_text = text.strip()
    if not stripped_text:
        return None, build_text_length_error(
            request=request, field_name="text", message="Text must not be empty"
        )
    try:
        stripped_text = enforce_text_length(
            value=stripped_text,
            field_name="text",
            max_chars=request.app.state.settings.max_input_text_chars,
        )
    except ValueError as exc:
        return None, build_text_length_error(
            request=request, field_name="text", message=str(exc)
        )

    upload_bytes = await ref_audio.read()
    upload_error = validate_clone_upload(request, ref_audio, upload_bytes)
    if upload_error is not None:
        return None, upload_error

    resolved_save_output = resolve_save_output(
        save_output, request.app.state.settings.default_save_output
    )
    normalized_language = normalize_language_value(language)
    staged_path = build_clone_staged_path(request, ref_audio, prefix="job_upload")
    staged_path.write_bytes(upload_bytes)
    submission = create_job_submission(
        operation=JobOperation.SYNTHESIZE_CLONE,
        command=VoiceCloneCommand(
            text=stripped_text,
            model=model,
            save_output=resolved_save_output,
            language=normalized_language,
            ref_audio_path=staged_path,
            ref_text=ref_text,
        ),
        submit_request_id=request.state.request_id,
        owner_principal_id=current_principal_id(request),
        response_format="wav",
        save_output=resolved_save_output,
        execution_timeout_seconds=request.app.state.settings.request_timeout_seconds,
        staged_input_paths=(staged_path,),
        idempotency_key=idempotency_key,
        idempotency_scope=resolve_idempotency_scope(request)
        if idempotency_key is not None
        else None,
        idempotency_fingerprint=(
            build_idempotency_fingerprint(
                operation=JobOperation.SYNTHESIZE_CLONE,
                payload={
                    "model": model,
                    "text": stripped_text,
                    "ref_text": ref_text,
                    "language": normalized_language,
                    "save_output": resolved_save_output,
                    "response_format": "wav",
                    "ref_audio_filename": ref_audio.filename,
                    "ref_audio_size": len(upload_bytes),
                    "ref_audio_sha256": hashlib.sha256(upload_bytes).hexdigest(),
                },
            )
            if idempotency_key is not None
            else None
        ),
    )
    return submission, None


async def run_inference_with_timeout(
    *, request: Request, operation_name: str, call: Callable[[], T]
) -> T:
    timeout_seconds = request.app.state.settings.request_timeout_seconds
    logger = request.app.state.logger

    with operation_scope(f"tts.{operation_name}.execution"):
        wrapper_timer = Timer()
        log_event(
            logger,
            level=logging.INFO,
            event="tts.inference.execution.started",
            message="Inference execution wrapper started",
            inference_operation=operation_name,
            execution_mode="thread_offload",
            offloaded_from_event_loop=True,
            timeout_seconds=timeout_seconds,
        )

        def worker_call() -> T:
            log_event(
                logger,
                level=logging.INFO,
                event="tts.inference.worker.started",
                message="Adapter-level inference execution started",
                inference_operation=operation_name,
                execution_mode="thread_offload",
                offloaded_from_event_loop=True,
                timeout_seconds=timeout_seconds,
            )
            return call()

        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(worker_call), timeout=timeout_seconds
            )
        except asyncio.TimeoutError as exc:
            log_event(
                logger,
                level=logging.WARNING,
                event="tts.inference.execution.timeout",
                message="Inference execution timed out",
                inference_operation=operation_name,
                execution_mode="thread_offload",
                offloaded_from_event_loop=True,
                timeout_seconds=timeout_seconds,
                duration_ms=wrapper_timer.elapsed_ms,
            )
            raise RequestTimeoutError(
                details={
                    "operation": operation_name,
                    "timeout_seconds": timeout_seconds,
                }
            ) from exc
        except Exception as exc:
            log_event(
                logger,
                level=logging.ERROR,
                event="tts.inference.execution.failed",
                message="Inference execution failed",
                inference_operation=operation_name,
                execution_mode="thread_offload",
                offloaded_from_event_loop=True,
                timeout_seconds=timeout_seconds,
                duration_ms=wrapper_timer.elapsed_ms,
                error_type=type(exc).__name__,
                error=str(exc),
            )
            raise
        log_event(
            logger,
            level=logging.INFO,
            event="tts.inference.execution.completed",
            message="Inference execution wrapper completed",
            inference_operation=operation_name,
            execution_mode="thread_offload",
            offloaded_from_event_loop=True,
            timeout_seconds=timeout_seconds,
            duration_ms=wrapper_timer.elapsed_ms,
        )
        return result


def register_tts_routes(app: FastAPI, logger) -> None:
    @app.post(
        "/v1/audio/speech",
        tags=["tts"],
        responses={
            401: {"model": ErrorResponse},
            404: {"model": ErrorResponse},
            422: {"model": ErrorResponse},
            500: {"model": ErrorResponse},
        },
    )
    async def openai_speech(request: Request, payload: OpenAISpeechRequest) -> Response:
        with operation_scope("server.openai_speech"):
            log_event(
                logger,
                level=logging.INFO,
                event="tts.endpoint.started",
                message="OpenAI-compatible speech request received",
                endpoint="/v1/audio/speech",
                model=payload.model,
                mode="custom",
                language=payload.language,
                response_format=payload.response_format,
            )
            await enforce_sync_tts_admission(request)
            try:
                input_text = enforce_text_length(
                    value=payload.input,
                    field_name="input",
                    max_chars=request.app.state.settings.max_input_text_chars,
                )
            except ValueError as exc:
                return build_text_length_error(
                    request=request, field_name="input", message=str(exc)
                )
            result = await run_inference_with_timeout(
                request=request,
                operation_name="synthesize_custom",
                call=lambda: request.app.state.application.synthesize_custom(
                    CustomVoiceCommand(
                        text=input_text,
                        model=payload.model,
                        save_output=request.app.state.settings.default_save_output,
                        language=payload.language,
                        speaker=payload.voice,
                        instruct="Normal tone",
                        speed=payload.speed,
                    )
                ),
            )
            return build_audio_response(
                request, result, payload.response_format, logger
            )

    @app.post(
        "/api/v1/tts/custom",
        tags=["tts"],
        responses={
            401: {"model": ErrorResponse},
            404: {"model": ErrorResponse},
            422: {"model": ErrorResponse},
            500: {"model": ErrorResponse},
        },
    )
    async def tts_custom(request: Request, payload: CustomTTSRequest) -> Response:
        with operation_scope("server.tts_custom"):
            instruct = payload.instruct or payload.emotion or "Normal tone"
            resolved_save_output = resolve_save_output(
                payload.save_output, request.app.state.settings.default_save_output
            )
            log_event(
                logger,
                level=logging.INFO,
                event="tts.endpoint.started",
                message="Custom TTS request received",
                endpoint="/api/v1/tts/custom",
                model=payload.model,
                mode="custom",
                language=payload.language,
                save_output=resolved_save_output,
            )
            await enforce_sync_tts_admission(request)
            try:
                text = enforce_text_length(
                    value=payload.text,
                    field_name="text",
                    max_chars=request.app.state.settings.max_input_text_chars,
                )
            except ValueError as exc:
                return build_text_length_error(
                    request=request, field_name="text", message=str(exc)
                )
            result = await run_inference_with_timeout(
                request=request,
                operation_name="synthesize_custom",
                call=lambda: request.app.state.application.synthesize_custom(
                    CustomVoiceCommand(
                        text=text,
                        model=payload.model,
                        save_output=resolved_save_output,
                        language=payload.language,
                        speaker=payload.speaker,
                        instruct=instruct,
                        speed=payload.speed,
                    )
                ),
            )
            return build_audio_response(request, result, "wav", logger)

    @app.post(
        "/api/v1/tts/design",
        tags=["tts"],
        responses={
            401: {"model": ErrorResponse},
            404: {"model": ErrorResponse},
            422: {"model": ErrorResponse},
            500: {"model": ErrorResponse},
        },
    )
    async def tts_design(request: Request, payload: DesignTTSRequest) -> Response:
        with operation_scope("server.tts_design"):
            await enforce_sync_tts_admission(request)
            resolved_save_output = resolve_save_output(
                payload.save_output, request.app.state.settings.default_save_output
            )
            log_event(
                logger,
                level=logging.INFO,
                event="tts.endpoint.started",
                message="Voice design request received",
                endpoint="/api/v1/tts/design",
                model=payload.model,
                mode="design",
                language=payload.language,
                save_output=resolved_save_output,
            )
            try:
                text = enforce_text_length(
                    value=payload.text,
                    field_name="text",
                    max_chars=request.app.state.settings.max_input_text_chars,
                )
            except ValueError as exc:
                return build_text_length_error(
                    request=request, field_name="text", message=str(exc)
                )
            result = await run_inference_with_timeout(
                request=request,
                operation_name="synthesize_design",
                call=lambda: request.app.state.application.synthesize_design(
                    VoiceDesignCommand(
                        text=text,
                        model=payload.model,
                        save_output=resolved_save_output,
                        language=payload.language,
                        voice_description=payload.voice_description,
                    )
                ),
            )
            return build_audio_response(request, result, "wav", logger)

    @app.post(
        "/api/v1/tts/clone",
        tags=["tts"],
        responses={
            400: {"model": ErrorResponse},
            401: {"model": ErrorResponse},
            404: {"model": ErrorResponse},
            422: {"model": ErrorResponse},
            500: {"model": ErrorResponse},
        },
    )
    async def tts_clone(
        request: Request,
        text: str = Form(...),
        ref_audio: UploadFile = File(...),
        ref_text: Optional[str] = Form(default=None),
        language: Optional[str] = Form(default="auto"),
        model: Optional[str] = Form(default=None),
        save_output: Optional[bool] = Form(default=None),
    ) -> Response:
        with operation_scope("server.tts_clone"):
            await enforce_sync_tts_admission(request)
            text = text.strip()
            normalized_language = normalize_language_value(language or "auto")
            resolved_save_output = resolve_save_output(
                save_output, request.app.state.settings.default_save_output
            )
            if not text:
                return build_text_length_error(
                    request=request, field_name="text", message="Text must not be empty"
                )
            try:
                text = enforce_text_length(
                    value=text,
                    field_name="text",
                    max_chars=request.app.state.settings.max_input_text_chars,
                )
            except ValueError as exc:
                return build_text_length_error(
                    request=request, field_name="text", message=str(exc)
                )
            log_event(
                logger,
                level=logging.INFO,
                event="tts.endpoint.started",
                message="Voice clone request received",
                endpoint="/api/v1/tts/clone",
                model=model,
                mode="clone",
                language=normalized_language,
                save_output=resolved_save_output,
                ref_audio_filename=ref_audio.filename,
                ref_text_provided=bool(ref_text),
            )
            upload_bytes = await ref_audio.read()
            upload_error = validate_clone_upload(request, ref_audio, upload_bytes)
            if upload_error is not None:
                return upload_error

            temp_path = build_clone_staged_path(request, ref_audio, prefix="upload")
            temp_path.write_bytes(upload_bytes)
            try:
                result = await run_inference_with_timeout(
                    request=request,
                    operation_name="synthesize_clone",
                    call=lambda: request.app.state.application.synthesize_clone(
                        VoiceCloneCommand(
                            text=text,
                            model=model,
                            save_output=resolved_save_output,
                            language=normalized_language,
                            ref_audio_path=temp_path,
                            ref_text=ref_text,
                        )
                    ),
                )
            finally:
                temp_path.unlink(missing_ok=True)
            return build_audio_response(request, result, "wav", logger)

    @app.post(
        "/v1/audio/speech/jobs",
        tags=["tts"],
        response_model=JobSnapshotPayload,
        status_code=202,
        responses={
            401: {"model": ErrorResponse},
            404: {"model": ErrorResponse},
            409: {"model": ErrorResponse},
            422: {"model": ErrorResponse},
            500: {"model": ErrorResponse},
        },
    )
    async def openai_speech_job_submit(
        request: Request,
        payload: OpenAISpeechRequest,
        idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    ) -> JobSnapshotPayload:
        await enforce_async_submit_admission(request)
        resolution = request.app.state.job_execution.submit_idempotent(
            create_custom_job_submission_from_openai(
                request, payload, idempotency_key=idempotency_key
            )
        )
        return build_job_snapshot_payload(request, resolution.snapshot)

    @app.post(
        "/api/v1/tts/custom/jobs",
        tags=["tts"],
        response_model=JobSnapshotPayload,
        status_code=202,
        responses={
            401: {"model": ErrorResponse},
            404: {"model": ErrorResponse},
            409: {"model": ErrorResponse},
            422: {"model": ErrorResponse},
            500: {"model": ErrorResponse},
        },
    )
    async def tts_custom_job_submit(
        request: Request,
        payload: CustomTTSRequest,
        idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    ) -> JobSnapshotPayload:
        await enforce_async_submit_admission(request)
        resolution = request.app.state.job_execution.submit_idempotent(
            create_custom_job_submission_from_custom(
                request, payload, idempotency_key=idempotency_key
            )
        )
        return build_job_snapshot_payload(request, resolution.snapshot)

    @app.post(
        "/api/v1/tts/design/jobs",
        tags=["tts"],
        response_model=JobSnapshotPayload,
        status_code=202,
        responses={
            401: {"model": ErrorResponse},
            404: {"model": ErrorResponse},
            409: {"model": ErrorResponse},
            422: {"model": ErrorResponse},
            500: {"model": ErrorResponse},
        },
    )
    async def tts_design_job_submit(
        request: Request,
        payload: DesignTTSRequest,
        idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    ) -> JobSnapshotPayload:
        await enforce_async_submit_admission(request)
        resolution = request.app.state.job_execution.submit_idempotent(
            create_design_job_submission(
                request, payload, idempotency_key=idempotency_key
            )
        )
        return build_job_snapshot_payload(request, resolution.snapshot)

    @app.post(
        "/api/v1/tts/clone/jobs",
        tags=["tts"],
        response_model=JobSnapshotPayload,
        status_code=202,
        responses={
            400: {"model": ErrorResponse},
            401: {"model": ErrorResponse},
            404: {"model": ErrorResponse},
            409: {"model": ErrorResponse},
            422: {"model": ErrorResponse},
            500: {"model": ErrorResponse},
        },
    )
    async def tts_clone_job_submit(
        request: Request,
        text: str = Form(...),
        ref_audio: UploadFile = File(...),
        ref_text: Optional[str] = Form(default=None),
        language: Optional[str] = Form(default="auto"),
        model: Optional[str] = Form(default=None),
        save_output: Optional[bool] = Form(default=None),
        idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    ) -> Response:
        await enforce_async_submit_admission(request)
        submission, error_response = await stage_clone_job_submission(
            request,
            text=text,
            ref_audio=ref_audio,
            ref_text=ref_text,
            language=language or "auto",
            model=model,
            save_output=save_output,
            idempotency_key=idempotency_key,
        )
        if error_response is not None:
            return error_response
        assert submission is not None
        staged_paths = submission.staged_input_paths
        try:
            resolution = request.app.state.job_execution.submit_idempotent(submission)
        except Exception:
            for staged_path in staged_paths:
                staged_path.unlink(missing_ok=True)
            raise
        if not resolution.created:
            for staged_path in staged_paths:
                staged_path.unlink(missing_ok=True)
        return JSONResponse(
            status_code=202,
            content=build_job_snapshot_payload(request, resolution.snapshot).model_dump(
                mode="json"
            ),
        )

    @app.get(
        "/api/v1/tts/jobs/{job_id}",
        name="tts_job_status",
        tags=["tts"],
        response_model=JobSnapshotPayload,
        responses={
            401: {"model": ErrorResponse},
            403: {"model": ErrorResponse},
            404: {"model": ErrorResponse},
        },
    )
    async def tts_job_status(request: Request, job_id: str) -> JobSnapshotPayload:
        await enforce_job_read_admission(request)
        return build_job_snapshot_payload(
            request, get_job_snapshot_or_raise(request, job_id)
        )

    @app.get(
        "/api/v1/tts/jobs/{job_id}/result",
        name="tts_job_result",
        tags=["tts"],
        responses={
            401: {"model": ErrorResponse},
            403: {"model": ErrorResponse},
            404: {"model": ErrorResponse},
            409: {"model": ErrorResponse},
        },
    )
    async def tts_job_result(request: Request, job_id: str) -> Response:
        await enforce_job_read_admission(request)
        resolution = request.app.state.job_execution.get_result(job_id)
        if resolution is None:
            raise JobNotFoundError(job_id)

        snapshot = resolution.snapshot
        ensure_job_owner_access(request, owner_principal_id=snapshot.owner_principal_id)
        if snapshot.status in {JobStatus.QUEUED, JobStatus.RUNNING}:
            raise JobNotReadyError(job_id, snapshot.status.value)
        if snapshot.status is not JobStatus.SUCCEEDED or resolution.success is None:
            raise JobNotSucceededError(
                job_id,
                snapshot.status.value,
                details={
                    "terminal_error": (
                        {
                            "code": snapshot.terminal_error.code,
                            "message": snapshot.terminal_error.message,
                            "details": snapshot.terminal_error.details,
                        }
                        if snapshot.terminal_error is not None
                        else None
                    )
                },
            )

        response = build_audio_response(
            request,
            resolution.success.generation,
            snapshot.response_format or "wav",
            logger,
        )
        response.headers["x-job-id"] = snapshot.job_id
        return response

    @app.post(
        "/api/v1/tts/jobs/{job_id}/cancel",
        name="tts_job_cancel",
        tags=["tts"],
        response_model=JobSnapshotPayload,
        responses={
            401: {"model": ErrorResponse},
            403: {"model": ErrorResponse},
            404: {"model": ErrorResponse},
            409: {"model": ErrorResponse},
        },
    )
    async def tts_job_cancel(request: Request, job_id: str) -> Response:
        await enforce_job_cancel_admission(request)
        snapshot = get_job_snapshot_or_raise(request, job_id)
        if snapshot.status not in {JobStatus.QUEUED, JobStatus.CANCELLED}:
            raise JobNotCancellableError(job_id, snapshot.status.value)

        cancelled = request.app.state.job_execution.cancel(job_id)
        if cancelled is None:
            raise JobNotFoundError(job_id)

        status_code = 200 if snapshot.status is JobStatus.CANCELLED else 202
        return JSONResponse(
            status_code=status_code,
            content=build_job_snapshot_payload(request, cancelled).model_dump(
                mode="json"
            ),
        )
