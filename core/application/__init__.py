# FILE: core/application/__init__.py
# VERSION: 1.0.0
# START_MODULE_CONTRACT
#   PURPOSE: Re-export public application service types.
#   SCOPE: barrel re-exports
#   DEPENDS: none
#   LINKS: M-APPLICATION
#   ROLE: BARREL
#   MAP_MODE: SUMMARY
# END_MODULE_CONTRACT
#
# START_MODULE_MAP
#   Admission control ports - Re-export quota and rate-limit decision/contracts for request gating
#   Job execution ports - Re-export async job execution gateway, stores, managers, and related errors
#   Application facade - Re-export the high-level TTS application service consumed by adapters
# END_MODULE_MAP
#
# START_CHANGE_SUMMARY
#   LAST_CHANGE: [v1.0.0 - GRACE integration: added MODULE_CONTRACT, MODULE_MAP, and function contracts]
# END_CHANGE_SUMMARY

from core.application.admission_control import (
    QuotaDecision,
    QuotaGuard,
    RateLimitDecision,
    RateLimiter,
)
from core.application.job_execution import (
    InMemoryJobExecutor,
    JobArtifactStore,
    JobExecutionBackend,
    JobExecutionGateway,
    JobExecutor,
    JobManager,
    JobMetadataStore,
    JobNotCancellableError,
    JobQueueFullError,
    JobStore,
)
from core.application.tts_app_service import TTSApplicationService

__all__ = [
    "InMemoryJobExecutor",
    "JobArtifactStore",
    "JobExecutionBackend",
    "JobExecutionGateway",
    "JobExecutor",
    "JobManager",
    "JobMetadataStore",
    "JobNotCancellableError",
    "JobQueueFullError",
    "JobStore",
    "QuotaDecision",
    "QuotaGuard",
    "RateLimitDecision",
    "RateLimiter",
    "TTSApplicationService",
]
