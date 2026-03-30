from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable

from core.contracts.jobs import (
    JobCreateResolution,
    JobFailureSnapshot,
    JobOperation,
    JobResultResolution,
    JobSnapshot,
    JobStatus,
    JobSubmission,
    JobSuccessSnapshot,
    StoredJob,
)
from core.contracts.results import GenerationResult
from core.errors import JobNotCancellableError, JobQueueFullError


@runtime_checkable
class JobArtifactStore(Protocol):
    def cleanup_submission_artifacts(self, submission: JobSubmission) -> None:
        ...

    def cleanup_paths(self, paths: tuple[object, ...]) -> None:
        ...


@runtime_checkable
class JobMetadataStore(Protocol):
    artifact_store: JobArtifactStore

    def create(self, submission: JobSubmission) -> JobSnapshot:
        ...

    def create_or_get(self, submission: JobSubmission) -> JobCreateResolution:
        ...

    def get(self, job_id: str) -> StoredJob | None:
        ...

    def get_snapshot(self, job_id: str) -> JobSnapshot | None:
        ...

    def count_active_jobs_for_principal(self, principal_id: str) -> int:
        ...

    def get_by_idempotency_key(self, idempotency_key: str, *, scope: str | None = None) -> StoredJob | None:
        ...

    def mark_running(self, job_id: str, *, started_at: datetime | None = None) -> JobSnapshot:
        ...

    def mark_succeeded(
        self,
        job_id: str,
        *,
        success: JobSuccessSnapshot,
        completed_at: datetime | None = None,
    ) -> JobSnapshot:
        ...

    def mark_failed(
        self,
        job_id: str,
        *,
        status: JobStatus,
        failure: JobFailureSnapshot,
        completed_at: datetime | None = None,
    ) -> JobSnapshot:
        ...

    def cancel(self, job_id: str, *, completed_at: datetime | None = None) -> JobSnapshot:
        ...

    def get_result(self, job_id: str) -> JobResultResolution | None:
        ...


class JobExecutor(Protocol):
    def execute(self, submission: JobSubmission) -> GenerationResult:
        ...


@runtime_checkable
class JobExecutionBackend(Protocol):
    def start(self) -> None:
        ...

    def stop(self, *, drain: bool = False) -> None:
        ...

    def submit(self, submission: JobSubmission) -> JobSnapshot:
        ...

    def submit_idempotent(self, submission: JobSubmission) -> JobCreateResolution:
        ...

    def cancel(self, job_id: str) -> JobSnapshot | None:
        ...


JobStore = JobMetadataStore
JobManager = JobExecutionBackend


@dataclass(frozen=True)
class InMemoryJobExecutor:
    application_service: object

    def execute(self, submission: JobSubmission) -> GenerationResult:
        if submission.operation is JobOperation.SYNTHESIZE_CUSTOM:
            return self.application_service.synthesize_custom(submission.command)
        if submission.operation is JobOperation.SYNTHESIZE_DESIGN:
            return self.application_service.synthesize_design(submission.command)
        if submission.operation is JobOperation.SYNTHESIZE_CLONE:
            return self.application_service.synthesize_clone(submission.command)
        raise ValueError(f"Unsupported job operation: {submission.operation.value}")


@dataclass
class JobExecutionGateway:
    store: JobStore
    manager: JobManager | None = None

    def submit(self, submission: JobSubmission) -> JobSnapshot:
        if self.manager is not None:
            return self.manager.submit(submission)
        return self.store.create(submission)

    def submit_idempotent(self, submission: JobSubmission) -> JobCreateResolution:
        if self.manager is not None:
            return self.manager.submit_idempotent(submission)
        return self.store.create_or_get(submission)

    def get_job(self, job_id: str) -> JobSnapshot | None:
        return self.store.get_snapshot(job_id)

    def get_result(self, job_id: str) -> JobResultResolution | None:
        return self.store.get_result(job_id)

    def cancel(self, job_id: str) -> JobSnapshot | None:
        if self.manager is not None:
            return self.manager.cancel(job_id)
        return self.store.cancel(job_id)


__all__ = [
    "InMemoryJobExecutor",
    "JobExecutionGateway",
    "JobExecutor",
    "JobManager",
    "JobNotCancellableError",
    "JobQueueFullError",
    "JobStore",
]
