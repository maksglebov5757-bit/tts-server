from __future__ import annotations

import logging
import re
from pathlib import PurePath
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from core.errors import (
    AudioConversionError,
    BackendCapabilityError,
    BackendNotAvailableError,
    ForbiddenError,
    InferenceBusyError,
    JobIdempotencyConflictError,
    JobNotCancellableError,
    JobNotFoundError,
    JobNotReadyError,
    JobNotSucceededError,
    JobQueueFullError,
    ModelLoadError,
    ModelNotAvailableError,
    QuotaExceededError,
    RateLimitExceededError,
    RequestTimeoutError,
    TTSGenerationError,
    UnauthorizedError,
)
from core.observability import log_event
from server.api.contracts import ErrorDescriptor, ExceptionMapping
from server.api.responses import build_error_response
from server.bootstrap import ServerSettings


_PATH_KEY_RE = re.compile(r"(^|_)(path|paths|dir|dirs|directory|directories|file|filename|filenames)$", re.IGNORECASE)
_PATH_VALUE_RE = re.compile(r"([A-Za-z]:[\\/]|/Users/|/tmp/|/var/|/private/|\.uploads/|\.outputs/|\.models/|\.voices/)")



def register_exception_handlers(app: FastAPI, logger) -> None:
    mappings = app.state.exception_mappings

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        descriptor = ErrorDescriptor(
            status_code=422,
            code="validation_error",
            message="Request validation failed",
            details={"errors": sanitize_validation_errors(exc.errors())},
        )
        return build_error_response(request=request, descriptor=descriptor)

    for exception_type in mappings:

        @app.exception_handler(exception_type)
        async def handle_mapped_error(request: Request, exc: Exception, _exception_type=exception_type) -> JSONResponse:
            descriptor = map_exception_to_descriptor(request, exc, mappings[_exception_type], logger)
            return build_error_response(request=request, descriptor=descriptor)

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        descriptor = ErrorDescriptor(
            status_code=500,
            code="internal_error",
            message="Unexpected internal server error",
            details={"reason": "Unexpected internal server error"},
        )
        return build_error_response(request=request, descriptor=descriptor)



def build_exception_mappings(settings: ServerSettings) -> dict[type[Exception], ExceptionMapping]:
    return {
        ModelNotAvailableError: ExceptionMapping(
            error_type=ModelNotAvailableError,
            builder=lambda exc: ErrorDescriptor(
                status_code=404,
                code="model_not_available",
                message="Requested model is not available",
                details=build_model_not_available_details(exc),
            ),
        ),
        BackendNotAvailableError: ExceptionMapping(
            error_type=BackendNotAvailableError,
            builder=lambda exc: ErrorDescriptor(
                status_code=503,
                code="backend_not_available",
                message="Configured backend is not available",
                details=build_error_details(exc, default_reason=str(exc)),
                retryable=True,
            ),
        ),
        BackendCapabilityError: ExceptionMapping(
            error_type=BackendCapabilityError,
            builder=lambda exc: ErrorDescriptor(
                status_code=422,
                code="backend_capability_missing",
                message="Selected backend does not support the requested operation",
                details=build_error_details(exc, default_reason=str(exc)),
            ),
        ),
        ModelLoadError: ExceptionMapping(
            error_type=ModelLoadError,
            builder=lambda exc: ErrorDescriptor(
                status_code=500,
                code="model_load_failed",
                message="Failed to load model",
                details=build_error_details(exc, default_reason=str(exc)),
            ),
        ),
        AudioConversionError: ExceptionMapping(
            error_type=AudioConversionError,
            builder=lambda exc: ErrorDescriptor(
                status_code=400,
                code="audio_conversion_failed",
                message="Could not process reference audio",
                details=build_error_details(exc, default_reason=str(exc)),
            ),
        ),
        InferenceBusyError: ExceptionMapping(
            error_type=InferenceBusyError,
            builder=lambda exc: ErrorDescriptor(
                status_code=settings.inference_busy_status_code,
                code="inference_busy",
                message="Server is busy processing another inference request",
                details=build_error_details(exc, default_reason=str(exc)),
                retryable=True,
            ),
        ),
        TTSGenerationError: ExceptionMapping(
            error_type=TTSGenerationError,
            builder=lambda exc: build_generation_error_descriptor(exc),
        ),
        RequestTimeoutError: ExceptionMapping(
            error_type=RequestTimeoutError,
            builder=lambda exc: ErrorDescriptor(
                status_code=504,
                code="request_timeout",
                message="Inference request timed out",
                details=build_error_details(exc, default_reason=str(exc)),
                retryable=True,
            ),
        ),
        JobQueueFullError: ExceptionMapping(
            error_type=JobQueueFullError,
            builder=lambda exc: ErrorDescriptor(
                status_code=settings.inference_busy_status_code,
                code="job_queue_full",
                message="Job queue is full",
                details=build_error_details(exc, default_reason=str(exc)),
                retryable=True,
            ),
        ),
        JobNotFoundError: ExceptionMapping(
            error_type=JobNotFoundError,
            builder=lambda exc: ErrorDescriptor(
                status_code=404,
                code="job_not_found",
                message="Job was not found",
                details=build_error_details(exc, default_reason=str(exc)),
            ),
        ),
        JobNotReadyError: ExceptionMapping(
            error_type=JobNotReadyError,
            builder=lambda exc: ErrorDescriptor(
                status_code=409,
                code="job_not_ready",
                message="Job result is not ready",
                details=build_error_details(exc, default_reason=str(exc)),
            ),
        ),
        JobNotSucceededError: ExceptionMapping(
            error_type=JobNotSucceededError,
            builder=lambda exc: ErrorDescriptor(
                status_code=409,
                code="job_not_succeeded",
                message="Job did not finish successfully",
                details=build_error_details(exc, default_reason=str(exc)),
            ),
        ),
        JobNotCancellableError: ExceptionMapping(
            error_type=JobNotCancellableError,
            builder=lambda exc: ErrorDescriptor(
                status_code=409,
                code="job_not_cancellable",
                message="Job cannot be cancelled in its current state",
                details=build_error_details(exc, default_reason=str(exc)),
            ),
        ),
        JobIdempotencyConflictError: ExceptionMapping(
            error_type=JobIdempotencyConflictError,
            builder=lambda exc: ErrorDescriptor(
                status_code=409,
                code="job_idempotency_conflict",
                message="Idempotency key conflicts with an existing job payload",
                details=build_error_details(exc, default_reason=str(exc)),
            ),
        ),
        UnauthorizedError: ExceptionMapping(
            error_type=UnauthorizedError,
            builder=lambda exc: ErrorDescriptor(
                status_code=401,
                code="unauthorized",
                message="Authentication is required or invalid",
                details=build_error_details(exc, default_reason=str(exc)),
            ),
        ),
        ForbiddenError: ExceptionMapping(
            error_type=ForbiddenError,
            builder=lambda exc: ErrorDescriptor(
                status_code=403,
                code="forbidden",
                message="Access to the requested resource is forbidden",
                details=build_error_details(exc, default_reason=str(exc)),
            ),
        ),
        RateLimitExceededError: ExceptionMapping(
            error_type=RateLimitExceededError,
            builder=lambda exc: ErrorDescriptor(
                status_code=429,
                code="rate_limit_exceeded",
                message="Request rate limit exceeded",
                details=build_error_details(exc, default_reason=str(exc)),
                retryable=True,
                headers=build_retry_after_headers(exc.retry_after_seconds),
            ),
        ),
        QuotaExceededError: ExceptionMapping(
            error_type=QuotaExceededError,
            builder=lambda exc: ErrorDescriptor(
                status_code=429,
                code="quota_exceeded",
                message="Quota exceeded for requested operation",
                details=build_error_details(exc, default_reason=str(exc)),
                retryable=True,
                headers=build_retry_after_headers(exc.retry_after_seconds),
            ),
        ),
    }



def map_exception_to_descriptor(request: Request, exc: Exception, mapping: ExceptionMapping, logger) -> ErrorDescriptor:
    descriptor = mapping.builder(exc)
    log_event(
        logger,
        level=logging.ERROR,
        event="http.error.mapped",
        message="Mapped exception to API error response",
        path=request.url.path,
        error_type=type(exc).__name__,
        code=descriptor.code,
        status_code=descriptor.status_code,
        retryable=descriptor.retryable,
        details=descriptor.details,
    )
    return descriptor



def build_generation_error_descriptor(exc: TTSGenerationError) -> ErrorDescriptor:
    details = build_error_details(exc, default_reason=str(exc))
    return ErrorDescriptor(
        status_code=500,
        code="generation_failed",
        message="Audio generation failed",
        details=details,
    )



def build_error_details(exc: Exception, *, default_reason: str) -> dict[str, object]:
    context = getattr(exc, "context", None)
    if context is not None and hasattr(context, "to_dict"):
        return sanitize_public_error_details(context.to_dict())
    return sanitize_public_error_details({"reason": default_reason})



def build_retry_after_headers(retry_after_seconds: int | None) -> dict[str, str] | None:
    if retry_after_seconds is None:
        return None
    return {"Retry-After": str(retry_after_seconds)}



def build_model_not_available_details(exc: ModelNotAvailableError) -> dict[str, object]:
    details = build_error_details(exc, default_reason=str(exc))
    if exc.model_name is not None and "model" not in details:
        details["model"] = exc.model_name
    return details



def sanitize_validation_errors(errors: list[dict]) -> list[dict]:
    sanitized: list[dict] = []
    for item in errors:
        normalized = dict(item)
        if "ctx" in normalized and isinstance(normalized["ctx"], dict):
            normalized["ctx"] = {key: str(value) for key, value in normalized["ctx"].items()}
        sanitized.append(normalized)
    return sanitized



def sanitize_public_error_details(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            if _is_path_key(key):
                if isinstance(item, (list, tuple)):
                    sanitized[key] = [_sanitize_path_value(part) for part in item]
                else:
                    sanitized[key] = _sanitize_path_value(item)
                continue
            sanitized[key] = sanitize_public_error_details(item)
        return sanitized
    if isinstance(value, list):
        return [sanitize_public_error_details(item) for item in value]
    if isinstance(value, tuple):
        return [sanitize_public_error_details(item) for item in value]
    if isinstance(value, str) and _looks_like_local_path(value):
        return _sanitize_path_string(value)
    return value



def _is_path_key(key: str) -> bool:
    return bool(_PATH_KEY_RE.search(key))



def _looks_like_local_path(value: str) -> bool:
    if _PATH_VALUE_RE.search(value):
        return True
    try:
        path = PurePath(value)
    except Exception:
        return False
    return path.is_absolute() and len(path.parts) > 1



def _sanitize_path_value(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    return PurePath(value).name or value



def _sanitize_path_string(value: str) -> str:
    sanitized = value
    for token in value.split():
        normalized = token.strip("\"'(),[]{}")
        if not _looks_like_local_path(normalized):
            continue
        sanitized = sanitized.replace(normalized, _sanitize_path_value(normalized))
    return sanitized
