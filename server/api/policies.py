from __future__ import annotations

from fastapi import Request

from core.application.admission_control import (
    QUOTA_POLICY_ACTIVE_ASYNC_JOBS,
    QUOTA_POLICY_COMPUTE,
    RATE_LIMIT_POLICY_ASYNC_SUBMIT,
    RATE_LIMIT_POLICY_CONTROL_PLANE,
    RATE_LIMIT_POLICY_JOB_CANCEL,
    RATE_LIMIT_POLICY_JOB_READ,
    RATE_LIMIT_POLICY_SYNC_TTS,
)
from core.errors import QuotaExceededError, RateLimitExceededError


async def enforce_sync_tts_admission(request: Request) -> None:
    principal_id = request.state.principal.principal_id
    _enforce_rate_limit(request, principal_id=principal_id, policy=RATE_LIMIT_POLICY_SYNC_TTS)
    _enforce_compute_quota(request, principal_id=principal_id)


async def enforce_async_submit_admission(request: Request) -> None:
    principal_id = request.state.principal.principal_id
    _enforce_rate_limit(request, principal_id=principal_id, policy=RATE_LIMIT_POLICY_ASYNC_SUBMIT)
    _enforce_compute_quota(request, principal_id=principal_id)
    _enforce_active_async_jobs_quota(request, principal_id=principal_id)


async def enforce_job_read_admission(request: Request) -> None:
    principal_id = request.state.principal.principal_id
    _enforce_rate_limit(request, principal_id=principal_id, policy=RATE_LIMIT_POLICY_JOB_READ)


async def enforce_job_cancel_admission(request: Request) -> None:
    principal_id = request.state.principal.principal_id
    _enforce_rate_limit(request, principal_id=principal_id, policy=RATE_LIMIT_POLICY_JOB_CANCEL)


async def enforce_control_plane_admission(request: Request) -> None:
    principal_id = request.state.principal.principal_id
    _enforce_rate_limit(request, principal_id=principal_id, policy=RATE_LIMIT_POLICY_CONTROL_PLANE)


def _enforce_rate_limit(request: Request, *, principal_id: str, policy: str) -> None:
    decision = request.app.state.rate_limiter.check_and_consume(principal_id=principal_id, policy=policy)
    if decision.allowed:
        return
    raise RateLimitExceededError(
        policy=decision.policy,
        limit=decision.limit,
        window_seconds=decision.window_seconds,
        retry_after_seconds=decision.retry_after_seconds,
    )



def _enforce_compute_quota(request: Request, *, principal_id: str) -> None:
    decision = request.app.state.quota_guard.check_and_consume_compute(principal_id=principal_id)
    if decision.allowed:
        return
    raise QuotaExceededError(
        policy=decision.policy,
        limit=decision.limit,
        window_seconds=decision.window_seconds,
        retry_after_seconds=decision.retry_after_seconds,
        details={"current_usage": decision.current_usage},
    )



def _enforce_active_async_jobs_quota(request: Request, *, principal_id: str) -> None:
    decision = request.app.state.quota_guard.check_active_async_jobs(principal_id=principal_id)
    if decision.allowed:
        return
    raise QuotaExceededError(
        policy=QUOTA_POLICY_ACTIVE_ASYNC_JOBS,
        limit=decision.limit,
        window_seconds=decision.window_seconds,
        retry_after_seconds=decision.retry_after_seconds,
        details={"current_usage": decision.current_usage},
    )
