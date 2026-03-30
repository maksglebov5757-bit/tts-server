from __future__ import annotations

from dataclasses import dataclass

from core.application import (
    InMemoryJobExecutor,
    JobArtifactStore,
    JobExecutionBackend,
    JobExecutionGateway,
    JobMetadataStore,
    QuotaGuard,
    RateLimiter,
    TTSApplicationService,
)
from core.backends import BackendRegistry, MLXBackend, TorchBackend
from core.config import CoreSettings
from core.infrastructure import (
    InferenceGuard,
    LocalBoundedExecutionManager,
    LocalInMemoryJobStore,
    LocalJobArtifactStore,
    build_quota_guard,
    build_rate_limiter,
)
from core.metrics import OperationalMetricsRegistry
from core.services.model_registry import ModelRegistry
from core.services.tts_service import TTSService


@dataclass(frozen=True)
class CoreRuntime:
    settings: CoreSettings
    backend_registry: BackendRegistry
    registry: ModelRegistry
    tts_service: TTSService
    application: TTSApplicationService
    job_artifact_store: JobArtifactStore
    job_store: JobMetadataStore
    job_executor: InMemoryJobExecutor
    job_manager: JobExecutionBackend
    job_execution: JobExecutionGateway
    rate_limiter: RateLimiter
    quota_guard: QuotaGuard
    inference_guard: InferenceGuard
    metrics: OperationalMetricsRegistry



def build_job_artifact_store(settings: CoreSettings) -> JobArtifactStore:
    if settings.job_artifact_backend == "local":
        return LocalJobArtifactStore()
    raise ValueError(f"Unsupported job artifact backend: {settings.job_artifact_backend}")



def build_job_metadata_store(settings: CoreSettings, *, artifact_store: JobArtifactStore) -> JobMetadataStore:
    if settings.job_metadata_backend == "local":
        return LocalInMemoryJobStore(artifact_store=artifact_store)
    raise ValueError(f"Unsupported job metadata backend: {settings.job_metadata_backend}")



def build_job_execution_backend(
    settings: CoreSettings,
    *,
    store: JobMetadataStore,
    executor: InMemoryJobExecutor,
    metrics: OperationalMetricsRegistry,
) -> JobExecutionBackend:
    if settings.job_execution_backend == "local":
        return LocalBoundedExecutionManager(store=store, executor=executor, metrics=metrics)
    raise ValueError(f"Unsupported job execution backend: {settings.job_execution_backend}")



def build_runtime(settings: CoreSettings) -> CoreRuntime:
    settings.ensure_directories()
    inference_guard = InferenceGuard()
    metrics = OperationalMetricsRegistry()
    backend_registry = BackendRegistry(
        [
            MLXBackend(settings.models_dir, metrics=metrics),
            TorchBackend(settings.models_dir, metrics=metrics),
        ],
        requested_backend=settings.backend,
        autoselect=settings.backend_autoselect,
        model_manifest_path=settings.model_manifest_path,
    )
    registry = ModelRegistry(
        backend_registry=backend_registry,
        preload_policy=settings.model_preload_policy,
        preload_model_ids=settings.model_preload_ids,
        metrics=metrics,
    )
    tts_service = TTSService(registry=registry, settings=settings, inference_guard=inference_guard)
    application = TTSApplicationService(tts_service=tts_service)
    job_artifact_store = build_job_artifact_store(settings)
    job_store = build_job_metadata_store(settings, artifact_store=job_artifact_store)
    job_executor = InMemoryJobExecutor(application_service=application)
    job_manager = build_job_execution_backend(settings, store=job_store, executor=job_executor, metrics=metrics)
    job_execution = JobExecutionGateway(store=job_store, manager=job_manager)
    rate_limiter = build_rate_limiter(settings)
    quota_guard = build_quota_guard(settings, store=job_store)
    return CoreRuntime(
        settings=settings,
        backend_registry=backend_registry,
        registry=registry,
        tts_service=tts_service,
        application=application,
        job_artifact_store=job_artifact_store,
        job_store=job_store,
        job_executor=job_executor,
        job_manager=job_manager,
        job_execution=job_execution,
        rate_limiter=rate_limiter,
        quota_guard=quota_guard,
        inference_guard=inference_guard,
        metrics=metrics,
    )
