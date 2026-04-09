# FILE: server/api/routes_health.py
# VERSION: 1.0.0
# START_MODULE_CONTRACT
#   PURPOSE: Define health check HTTP endpoints.
#   SCOPE: GET /health/live, GET /health/ready
#   DEPENDS: M-MODEL-REGISTRY, M-METRICS
#   LINKS: M-SERVER
#   ROLE: RUNTIME
#   MAP_MODE: EXPORTS
# END_MODULE_CONTRACT
#
# START_MODULE_MAP
#   register_health_routes - Register liveness and readiness routes on the FastAPI app
#   build_readiness_report - Build a structured readiness response payload
# END_MODULE_MAP
#
# START_CHANGE_SUMMARY
#   LAST_CHANGE: [v1.0.0 - GRACE integration: added MODULE_CONTRACT, MODULE_MAP, and function contracts]
# END_CHANGE_SUMMARY

from __future__ import annotations

from fastapi import FastAPI, Request

from core.infrastructure.audio_io import check_ffmpeg_available
from core.observability import log_event, operation_scope
from server.api.policies import enforce_control_plane_admission
from server.schemas.audio import HealthResponse


# START_CONTRACT: register_health_routes
#   PURPOSE: Register liveness and readiness HTTP endpoints on the FastAPI application.
#   INPUTS: { app: FastAPI - application to attach routes to, logger: Any - structured logger used by endpoint handlers }
#   OUTPUTS: { None - routes are attached in place }
#   SIDE_EFFECTS: Mutates FastAPI routing table by registering health endpoints
#   LINKS: M-SERVER, M-METRICS
# END_CONTRACT: register_health_routes
def register_health_routes(app: FastAPI, logger) -> None:
    @app.get("/health/live", response_model=HealthResponse, tags=["health"])
    # START_CONTRACT: health_live
    #   PURPOSE: Return a simple liveness probe indicating the server process is alive.
    #   INPUTS: { none: None - endpoint has no request parameters }
    #   OUTPUTS: { HealthResponse - liveness payload for process health }
    #   SIDE_EFFECTS: none
    #   LINKS: M-SERVER
    # END_CONTRACT: health_live
    async def health_live() -> HealthResponse:
        return HealthResponse(status="ok", checks={"process": "alive"})

    @app.get("/health/ready", response_model=HealthResponse, tags=["health"])
    # START_CONTRACT: health_ready
    #   PURPOSE: Evaluate server readiness using admission checks and runtime readiness details.
    #   INPUTS: { request: Request - incoming readiness probe request }
    #   OUTPUTS: { HealthResponse - readiness status with diagnostic checks }
    #   SIDE_EFFECTS: Consumes control-plane admission checks and emits readiness logs
    #   LINKS: M-SERVER, M-METRICS, M-MODEL-REGISTRY
    # END_CONTRACT: health_ready
    async def health_ready(request: Request) -> HealthResponse:
        with operation_scope("server.health_ready"):
            await enforce_control_plane_admission(request)
            readiness = build_readiness_report(request)
            log_event(
                logger,
                level=20,
                event="[RoutesHealth][health_ready][HEALTH_READY]",
                message="Readiness probe evaluated",
                status=readiness.status,
                available_models=readiness.checks["models"]["available_models"],
                runtime_ready_models=readiness.checks["models"]["runtime_ready_models"],
                loaded_models=readiness.checks["models"]["loaded_models"],
                preload_status=readiness.checks["models"]["preload"]["status"],
                ffmpeg_available=readiness.checks["ffmpeg"]["available"],
            )
            return readiness


# START_CONTRACT: build_readiness_report
#   PURPOSE: Build a structured readiness report from registry, ffmpeg, config, and runtime state.
#   INPUTS: { request: Request - request carrying app state dependencies }
#   OUTPUTS: { HealthResponse - readiness payload with detailed checks }
#   SIDE_EFFECTS: Reads shared app state and inspects filesystem-backed configuration paths
#   LINKS: M-SERVER, M-MODEL-REGISTRY, M-METRICS
# END_CONTRACT: build_readiness_report
def build_readiness_report(request: Request) -> HealthResponse:
    registry_report = request.app.state.registry.readiness_report()
    ffmpeg_ready = check_ffmpeg_available()
    settings = request.app.state.settings
    config = {
        "models_dir": str(settings.models_dir),
        "models_dir_exists": settings.models_dir.exists(),
        "outputs_dir": str(settings.outputs_dir),
        "outputs_dir_exists": settings.outputs_dir.exists(),
        "voices_dir": str(settings.voices_dir),
        "voices_dir_exists": settings.voices_dir.exists(),
        "sample_rate": settings.sample_rate,
        "max_upload_size_bytes": settings.max_upload_size_bytes,
        "model_preload_policy": settings.model_preload_policy,
        "model_preload_ids": list(settings.model_preload_ids),
    }
    runtime = {
        "inference_busy": request.app.state.runtime.inference_guard.is_busy(),
        "streaming_enabled": settings.enable_streaming,
        "default_save_output": settings.default_save_output,
        "request_timeout_seconds": settings.request_timeout_seconds,
        "configured_backend": settings.backend,
        "backend_autoselect": settings.backend_autoselect,
        "metrics": request.app.state.metrics.readiness_summary(),
    }
    status = (
        "ok"
        if registry_report["registry_ready"]
        and ffmpeg_ready
        and config["models_dir_exists"]
        else "degraded"
    )
    return HealthResponse(
        status=status,
        checks={
            "models": registry_report,
            "ffmpeg": {"available": ffmpeg_ready},
            "config": config,
            "runtime": runtime,
        },
    )

__all__ = [
    "register_health_routes",
    "build_readiness_report",
]
