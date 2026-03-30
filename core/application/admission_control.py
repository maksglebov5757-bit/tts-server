from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


RATE_LIMIT_POLICY_SYNC_TTS = "sync_tts"
RATE_LIMIT_POLICY_ASYNC_SUBMIT = "async_submit"
RATE_LIMIT_POLICY_JOB_READ = "job_read"
RATE_LIMIT_POLICY_JOB_CANCEL = "job_cancel"
RATE_LIMIT_POLICY_CONTROL_PLANE = "control_plane"
QUOTA_POLICY_COMPUTE = "compute_requests"
QUOTA_POLICY_ACTIVE_ASYNC_JOBS = "active_async_jobs"


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    policy: str
    limit: int
    window_seconds: int
    retry_after_seconds: int | None = None


@dataclass(frozen=True)
class QuotaDecision:
    allowed: bool
    policy: str
    limit: int
    window_seconds: int | None = None
    retry_after_seconds: int | None = None
    current_usage: int | None = None


@runtime_checkable
class RateLimiter(Protocol):
    def check_and_consume(self, *, principal_id: str, policy: str) -> RateLimitDecision:
        ...


@runtime_checkable
class QuotaGuard(Protocol):
    def check_and_consume_compute(self, *, principal_id: str) -> QuotaDecision:
        ...

    def check_active_async_jobs(self, *, principal_id: str) -> QuotaDecision:
        ...


__all__ = [
    "QUOTA_POLICY_ACTIVE_ASYNC_JOBS",
    "QUOTA_POLICY_COMPUTE",
    "RATE_LIMIT_POLICY_ASYNC_SUBMIT",
    "RATE_LIMIT_POLICY_CONTROL_PLANE",
    "RATE_LIMIT_POLICY_JOB_CANCEL",
    "RATE_LIMIT_POLICY_JOB_READ",
    "RATE_LIMIT_POLICY_SYNC_TTS",
    "QuotaDecision",
    "QuotaGuard",
    "RateLimitDecision",
    "RateLimiter",
]
