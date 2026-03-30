from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class CoreError(Exception):
    """Base class for reusable core errors."""


@dataclass(frozen=True)
class ErrorContext:
    reason: str
    details: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = {"reason": self.reason}
        if self.details:
            payload.update(self.details)
        return payload


class ModelNotAvailableError(CoreError):
    def __init__(self, model_name: str | None = None, *, reason: str | None = None, details: dict[str, Any] | None = None):
        resolved_reason = reason or (
            f"Requested model is not available: {model_name}" if model_name else "Requested model is not available"
        )
        super().__init__(resolved_reason)
        self.model_name = model_name
        self.context = ErrorContext(reason=resolved_reason, details=details)


class BackendError(CoreError):
    def __init__(self, reason: str, *, details: dict[str, Any] | None = None):
        super().__init__(reason)
        self.context = ErrorContext(reason=reason, details=details)


class BackendNotAvailableError(BackendError):
    pass


class BackendCapabilityError(BackendError):
    pass


class ModelLoadError(CoreError):
    def __init__(self, reason: str, *, details: dict[str, Any] | None = None):
        super().__init__(reason)
        self.context = ErrorContext(reason=reason, details=details)


class TTSGenerationError(CoreError):
    def __init__(self, reason: str, *, details: dict[str, Any] | None = None):
        super().__init__(reason)
        self.context = ErrorContext(reason=reason, details=details)


class InferenceBusyError(CoreError):
    def __init__(self, reason: str = "Inference is already in progress", *, details: dict[str, Any] | None = None):
        super().__init__(reason)
        self.context = ErrorContext(reason=reason, details=details)


class AudioConversionError(CoreError):
    def __init__(self, reason: str, *, details: dict[str, Any] | None = None):
        super().__init__(reason)
        self.context = ErrorContext(reason=reason, details=details)


class AudioArtifactNotFoundError(CoreError):
    def __init__(self, reason: str, *, details: dict[str, Any] | None = None):
        super().__init__(reason)
        self.context = ErrorContext(reason=reason, details=details)


class RequestTimeoutError(CoreError):
    def __init__(self, reason: str = "Inference request timed out", *, details: dict[str, Any] | None = None):
        super().__init__(reason)
        self.context = ErrorContext(reason=reason, details=details)


class JobQueueFullError(CoreError):
    def __init__(self, reason: str = "Local job queue is full", *, details: dict[str, Any] | None = None):
        super().__init__(reason)
        self.context = ErrorContext(reason=reason, details=details)


class JobNotFoundError(CoreError):
    def __init__(self, job_id: str, *, reason: str | None = None, details: dict[str, Any] | None = None):
        resolved_reason = reason or f"Job was not found: {job_id}"
        super().__init__(resolved_reason)
        self.job_id = job_id
        payload = {"job_id": job_id}
        if details:
            payload.update(details)
        self.context = ErrorContext(reason=resolved_reason, details=payload)


class JobNotReadyError(CoreError):
    def __init__(self, job_id: str, status: str, *, reason: str | None = None, details: dict[str, Any] | None = None):
        resolved_reason = reason or f"Job result is not ready while status is {status}"
        super().__init__(resolved_reason)
        payload = {"job_id": job_id, "status": status}
        if details:
            payload.update(details)
        self.context = ErrorContext(reason=resolved_reason, details=payload)


class JobNotSucceededError(CoreError):
    def __init__(self, job_id: str, status: str, *, reason: str | None = None, details: dict[str, Any] | None = None):
        resolved_reason = reason or f"Job did not succeed and cannot produce audio while status is {status}"
        super().__init__(resolved_reason)
        payload = {"job_id": job_id, "status": status}
        if details:
            payload.update(details)
        self.context = ErrorContext(reason=resolved_reason, details=payload)


class JobNotCancellableError(CoreError):
    def __init__(self, job_id: str, status: str, *, reason: str | None = None, details: dict[str, Any] | None = None):
        resolved_reason = reason or f"Job is not cancellable while status is {status}"
        super().__init__(resolved_reason)
        payload = {"job_id": job_id, "status": status}
        if details:
            payload.update(details)
        self.context = ErrorContext(reason=resolved_reason, details=payload)


class JobIdempotencyConflictError(CoreError):
    def __init__(
        self,
        *,
        idempotency_key: str,
        existing_job_id: str,
        reason: str | None = None,
        details: dict[str, Any] | None = None,
    ):
        resolved_reason = reason or "Idempotency key was already used with a different payload"
        super().__init__(resolved_reason)
        payload = {
            "idempotency_key": idempotency_key,
            "job_id": existing_job_id,
        }
        if details:
            payload.update(details)
        self.context = ErrorContext(reason=resolved_reason, details=payload)


class UnauthorizedError(CoreError):
    def __init__(self, reason: str = "Authentication is required", *, details: dict[str, Any] | None = None):
        super().__init__(reason)
        self.context = ErrorContext(reason=reason, details=details)


class ForbiddenError(CoreError):
    def __init__(self, reason: str = "Access to the requested resource is forbidden", *, details: dict[str, Any] | None = None):
        super().__init__(reason)
        self.context = ErrorContext(reason=reason, details=details)


class RateLimitExceededError(CoreError):
    def __init__(
        self,
        *,
        policy: str,
        limit: int,
        window_seconds: int,
        retry_after_seconds: int | None = None,
        reason: str | None = None,
        details: dict[str, Any] | None = None,
    ):
        resolved_reason = reason or "Request rate limit was exceeded"
        super().__init__(resolved_reason)
        payload = {
            "policy": policy,
            "limit": limit,
            "window_seconds": window_seconds,
        }
        if retry_after_seconds is not None:
            payload["retry_after_seconds"] = retry_after_seconds
        if details:
            payload.update(details)
        self.retry_after_seconds = retry_after_seconds
        self.context = ErrorContext(reason=resolved_reason, details=payload)


class QuotaExceededError(CoreError):
    def __init__(
        self,
        *,
        policy: str,
        limit: int,
        window_seconds: int | None = None,
        retry_after_seconds: int | None = None,
        reason: str | None = None,
        details: dict[str, Any] | None = None,
    ):
        resolved_reason = reason or "Quota policy was exceeded"
        super().__init__(resolved_reason)
        payload = {
            "policy": policy,
            "limit": limit,
        }
        if window_seconds is not None:
            payload["window_seconds"] = window_seconds
        if retry_after_seconds is not None:
            payload["retry_after_seconds"] = retry_after_seconds
        if details:
            payload.update(details)
        self.retry_after_seconds = retry_after_seconds
        self.context = ErrorContext(reason=resolved_reason, details=payload)
