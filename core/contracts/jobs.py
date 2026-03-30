from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional
from uuid import uuid4

from core.contracts.commands import CustomVoiceCommand, GenerationCommand, VoiceCloneCommand, VoiceDesignCommand
from core.contracts.results import GenerationResult


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"

    @property
    def is_terminal(self) -> bool:
        return self in {self.SUCCEEDED, self.FAILED, self.TIMEOUT, self.CANCELLED}


class JobOperation(str, Enum):
    SYNTHESIZE_CUSTOM = "synthesize_custom"
    SYNTHESIZE_DESIGN = "synthesize_design"
    SYNTHESIZE_CLONE = "synthesize_clone"

    @property
    def mode(self) -> str:
        return {
            JobOperation.SYNTHESIZE_CUSTOM: "custom",
            JobOperation.SYNTHESIZE_DESIGN: "design",
            JobOperation.SYNTHESIZE_CLONE: "clone",
        }[self]


TERMINAL_JOB_STATUSES = {
    JobStatus.SUCCEEDED,
    JobStatus.FAILED,
    JobStatus.TIMEOUT,
    JobStatus.CANCELLED,
}

_ALLOWED_TRANSITIONS: dict[JobStatus, set[JobStatus]] = {
    JobStatus.QUEUED: {JobStatus.RUNNING, JobStatus.CANCELLED},
    JobStatus.RUNNING: {JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.TIMEOUT, JobStatus.CANCELLED},
    JobStatus.SUCCEEDED: set(),
    JobStatus.FAILED: set(),
    JobStatus.TIMEOUT: set(),
    JobStatus.CANCELLED: set(),
}


@dataclass(frozen=True)
class JobFailureSnapshot:
    code: str
    message: str
    details: dict[str, object] | None = None


@dataclass(frozen=True)
class JobSuccessSnapshot:
    generation: GenerationResult


@dataclass(frozen=True)
class JobSubmission:
    operation: JobOperation
    command: GenerationCommand
    submit_request_id: str
    owner_principal_id: str
    response_format: Optional[str]
    save_output: bool
    execution_timeout_seconds: float
    staged_input_paths: tuple[Path, ...] = ()
    idempotency_key: Optional[str] = None
    idempotency_scope: Optional[str] = None
    idempotency_fingerprint: Optional[str] = None

    @property
    def requested_model(self) -> Optional[str]:
        return self.command.model

    @property
    def mode(self) -> str:
        return self.operation.mode


@dataclass(frozen=True)
class JobSnapshot:
    job_id: str
    submit_request_id: str
    owner_principal_id: str
    status: JobStatus
    operation: JobOperation
    mode: str
    requested_model: Optional[str]
    response_format: Optional[str]
    save_output: bool
    execution_timeout_seconds: float
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    backend: Optional[str] = None
    saved_path: Optional[Path] = None
    terminal_error: Optional[JobFailureSnapshot] = None
    retention_expires_at: Optional[datetime] = None
    idempotency_key: Optional[str] = None

    @property
    def is_terminal(self) -> bool:
        return self.status.is_terminal


@dataclass(frozen=True)
class JobTerminalState:
    status: JobStatus
    completed_at: datetime
    retention_expires_at: Optional[datetime] = None
    backend: Optional[str] = None
    saved_path: Optional[Path] = None
    success: Optional[JobSuccessSnapshot] = None
    failure: Optional[JobFailureSnapshot] = None


@dataclass(frozen=True)
class StoredJob:
    snapshot: JobSnapshot
    submission: JobSubmission
    success: Optional[JobSuccessSnapshot] = None
    terminal_state: Optional[JobTerminalState] = None


@dataclass(frozen=True)
class JobCreateResolution:
    snapshot: JobSnapshot
    created: bool


@dataclass(frozen=True)
class JobStatusTransition:
    from_status: JobStatus
    to_status: JobStatus
    changed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def validate(self) -> None:
        allowed = _ALLOWED_TRANSITIONS[self.from_status]
        if self.to_status not in allowed:
            raise ValueError(f"Illegal job status transition: {self.from_status.value} -> {self.to_status.value}")


@dataclass(frozen=True)
class JobResultResolution:
    snapshot: JobSnapshot
    success: Optional[JobSuccessSnapshot]
    terminal_state: Optional[JobTerminalState] = None


def create_job_submission(*,
    operation: JobOperation,
    command: GenerationCommand,
    submit_request_id: str,
    owner_principal_id: str,
    response_format: Optional[str],
    save_output: bool,
    execution_timeout_seconds: float,
    staged_input_paths: tuple[Path, ...] = (),
    idempotency_key: Optional[str] = None,
    idempotency_scope: Optional[str] = None,
    idempotency_fingerprint: Optional[str] = None,
) -> JobSubmission:
    if operation is JobOperation.SYNTHESIZE_CUSTOM and not isinstance(command, CustomVoiceCommand):
        raise TypeError("synthesize_custom requires CustomVoiceCommand")
    if operation is JobOperation.SYNTHESIZE_DESIGN and not isinstance(command, VoiceDesignCommand):
        raise TypeError("synthesize_design requires VoiceDesignCommand")
    if operation is JobOperation.SYNTHESIZE_CLONE and not isinstance(command, VoiceCloneCommand):
        raise TypeError("synthesize_clone requires VoiceCloneCommand")
    return JobSubmission(
        operation=operation,
        command=command,
        submit_request_id=submit_request_id,
        owner_principal_id=owner_principal_id,
        response_format=response_format,
        save_output=save_output,
        execution_timeout_seconds=execution_timeout_seconds,
        staged_input_paths=staged_input_paths,
        idempotency_key=idempotency_key,
        idempotency_scope=idempotency_scope,
        idempotency_fingerprint=idempotency_fingerprint,
    )


def create_queued_job(*, submission: JobSubmission, job_id: Optional[str] = None, created_at: Optional[datetime] = None) -> StoredJob:
    timestamp = created_at or datetime.now(timezone.utc)
    snapshot = JobSnapshot(
        job_id=job_id or str(uuid4()),
        submit_request_id=submission.submit_request_id,
        owner_principal_id=submission.owner_principal_id,
        status=JobStatus.QUEUED,
        operation=submission.operation,
        mode=submission.mode,
        requested_model=submission.requested_model,
        response_format=submission.response_format,
        save_output=submission.save_output,
        execution_timeout_seconds=submission.execution_timeout_seconds,
        created_at=timestamp,
        idempotency_key=submission.idempotency_key,
    )
    return StoredJob(snapshot=snapshot, submission=submission)


def apply_job_transition(*,
    job: StoredJob,
    transition: JobStatusTransition,
    backend: Optional[str] = None,
    saved_path: Optional[Path] = None,
    failure: Optional[JobFailureSnapshot] = None,
    success: Optional[JobSuccessSnapshot] = None,
    retention_expires_at: Optional[datetime] = None,
) -> StoredJob:
    transition.validate()
    if job.snapshot.status != transition.from_status:
        raise ValueError(
            f"Job state mismatch for transition: expected {transition.from_status.value}, got {job.snapshot.status.value}"
        )

    started_at = job.snapshot.started_at
    completed_at = job.snapshot.completed_at
    if transition.to_status is JobStatus.RUNNING:
        started_at = transition.changed_at
    if transition.to_status in TERMINAL_JOB_STATUSES:
        completed_at = transition.changed_at

    resolved_backend = backend if backend is not None else job.snapshot.backend
    resolved_saved_path = saved_path if saved_path is not None else job.snapshot.saved_path
    updated_snapshot = replace(
        job.snapshot,
        status=transition.to_status,
        started_at=started_at,
        completed_at=completed_at,
        backend=resolved_backend,
        saved_path=resolved_saved_path,
        terminal_error=failure,
        retention_expires_at=retention_expires_at,
    )
    terminal_state = job.terminal_state
    if transition.to_status in TERMINAL_JOB_STATUSES and completed_at is not None:
        terminal_state = JobTerminalState(
            status=transition.to_status,
            completed_at=completed_at,
            retention_expires_at=retention_expires_at,
            backend=resolved_backend,
            saved_path=resolved_saved_path,
            success=success,
            failure=failure,
        )
    return StoredJob(snapshot=updated_snapshot, submission=job.submission, success=success, terminal_state=terminal_state)
