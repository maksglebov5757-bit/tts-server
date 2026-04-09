# FILE: core/services/model_registry.py
# VERSION: 1.0.0
# START_MODULE_CONTRACT
#   PURPOSE: Discover, validate, preload, and serve model handles through the selected backend.
#   SCOPE: ModelRegistry class with get_model, list_models, readiness_report, preload management
#   DEPENDS: M-BACKENDS, M-CONFIG, M-ERRORS, M-OBSERVABILITY, M-METRICS
#   LINKS: M-MODEL-REGISTRY
#   ROLE: RUNTIME
#   MAP_MODE: EXPORTS
# END_MODULE_CONTRACT
#
# START_MODULE_MAP
#   LOGGER - Module logger for model registry events
#   SUPPORTED_PRELOAD_POLICIES - Allowed model preload policy values
#   ModelRegistry - High-level model discovery and loading facade
# END_MODULE_MAP
#
# START_CHANGE_SUMMARY
#   LAST_CHANGE: [v1.0.0 - GRACE integration: added MODULE_CONTRACT, MODULE_MAP, function contracts, semantic blocks, and migrated log events to block-reference format]
# END_CHANGE_SUMMARY

from __future__ import annotations

from typing import Any, Optional

from core.backends import BackendRegistry
from core.backends.base import LoadedModelHandle
from core.errors import ModelLoadError, ModelNotAvailableError
from core.metrics import OperationalMetricsRegistry
from core.models.catalog import ModelSpec
from core.observability import get_logger, log_event, operation_scope


LOGGER = get_logger(__name__)
SUPPORTED_PRELOAD_POLICIES = {"none", "all", "listed"}


# START_CONTRACT: ModelRegistry
#   PURPOSE: Provide high-level model discovery, readiness reporting, and backend-backed model loading.
#   INPUTS: { backend_registry: BackendRegistry - Backend registry that selects the active backend and model manifest, preload_policy: str - Startup model preload strategy, preload_model_ids: tuple[str, ...] - Explicit model identifiers for listed preload policy, metrics: OperationalMetricsRegistry | None - Optional metrics facade for readiness summaries }
#   OUTPUTS: { instance - Model registry coordinating backend-backed model access }
#   SIDE_EFFECTS: May preload model runtimes during initialization
#   LINKS: M-MODEL-REGISTRY
# END_CONTRACT: ModelRegistry
class ModelRegistry:
    def __init__(
        self,
        backend_registry: BackendRegistry,
        *,
        preload_policy: str = "none",
        preload_model_ids: tuple[str, ...] = (),
        metrics: OperationalMetricsRegistry | None = None,
    ):
        self.backend_registry = backend_registry
        self._metrics = metrics or OperationalMetricsRegistry()
        normalized_policy = (preload_policy or "none").strip().lower()
        self._preload_policy = (
            normalized_policy
            if normalized_policy in SUPPORTED_PRELOAD_POLICIES
            else "none"
        )
        self._preload_model_ids = tuple(preload_model_ids)
        self._preload_report = self._build_preload_report(status="not_started")
        self._apply_preload_policy()

    @property
    def backend(self):
        return self.backend_registry.selected_backend

    @property
    def model_specs(self) -> tuple[ModelSpec, ...]:
        return self.backend_registry.model_specs

    # START_CONTRACT: list_models
    #   PURPOSE: List configured models together with backend capability and availability status.
    #   INPUTS: {}
    #   OUTPUTS: { list[dict[str, Any]] - Per-model availability and capability records }
    #   SIDE_EFFECTS: none
    #   LINKS: M-MODEL-REGISTRY
    # END_CONTRACT: list_models
    def list_models(self) -> list[dict[str, Any]]:
        models = []
        backend = self.backend
        capabilities = backend.capabilities().to_dict()
        for spec in self.model_specs:
            status = self.inspect_model(spec)
            models.append(
                {
                    "key": spec.key,
                    "id": spec.api_name,
                    "name": spec.public_name,
                    "mode": spec.mode,
                    "folder": spec.folder,
                    "available": status["available"],
                    "backend": backend.key,
                    "capabilities": capabilities,
                }
            )
        return models

    # START_CONTRACT: get_model_spec
    #   PURPOSE: Resolve a model specification by model identifier or synthesis mode.
    #   INPUTS: { model_name: Optional[str] - Requested model identifier, mode: Optional[str] - Requested synthesis mode fallback }
    #   OUTPUTS: { ModelSpec - Matching enabled model specification }
    #   SIDE_EFFECTS: none
    #   LINKS: M-MODEL-REGISTRY
    # END_CONTRACT: get_model_spec
    def get_model_spec(
        self, model_name: Optional[str] = None, mode: Optional[str] = None
    ) -> ModelSpec:
        return self.backend_registry.get_model_spec(model_name=model_name, mode=mode)

    # START_CONTRACT: get_model
    #   PURPOSE: Resolve and load a model handle for the active backend.
    #   INPUTS: { model_name: Optional[str] - Requested model identifier, mode: Optional[str] - Requested synthesis mode fallback }
    #   OUTPUTS: { tuple[ModelSpec, LoadedModelHandle] - Resolved model spec and loaded backend handle }
    #   SIDE_EFFECTS: Loads model runtimes through the selected backend and emits structured logs
    #   LINKS: M-MODEL-REGISTRY
    # END_CONTRACT: get_model
    def get_model(
        self, model_name: Optional[str] = None, mode: Optional[str] = None
    ) -> tuple[ModelSpec, LoadedModelHandle]:
        with operation_scope("core.model_registry.get_model"):
            spec = self.get_model_spec(model_name=model_name, mode=mode)
            log_event(
                LOGGER,
                level=20,
                event="[ModelRegistry][get_model][GET_MODEL]",
                message="Loading model handle through backend registry",
                model=spec.api_name,
                mode=spec.mode,
                backend=self.backend.key,
            )
            handle = self.backend.load_model(spec)
            log_event(
                LOGGER,
                level=20,
                event="[ModelRegistry][get_model][GET_MODEL]",
                message="Model handle loaded through backend registry",
                model=spec.api_name,
                mode=spec.mode,
                backend=self.backend.key,
                model_path=str(handle.resolved_path) if handle.resolved_path else None,
            )
            return spec, handle

    def resolve_model_path(self, folder_name: str):
        return self.backend.resolve_model_path(folder_name)

    def inspect_model(self, spec: ModelSpec) -> dict[str, Any]:
        item = self.backend.inspect_model(spec)
        preload_state = self._preload_state_for_model(spec)
        item["preload"] = preload_state
        return item

    # START_CONTRACT: readiness_report
    #   PURPOSE: Build a full readiness report for configured models, backend selection, cache state, and preload status.
    #   INPUTS: {}
    #   OUTPUTS: { dict[str, Any] - Registry readiness report for operational consumers }
    #   SIDE_EFFECTS: none
    #   LINKS: M-MODEL-REGISTRY
    # END_CONTRACT: readiness_report
    def readiness_report(self) -> dict[str, Any]:
        # START_BLOCK_COLLECT_MODEL_STATUS
        items = [self.inspect_model(spec) for spec in self.model_specs]
        available_count = sum(1 for item in items if item["available"])
        loadable_count = sum(1 for item in items if item["loadable"])
        runtime_ready_count = sum(1 for item in items if item["runtime_ready"])
        loaded_count = sum(1 for item in items if item.get("cached"))
        backend_diagnostics = self.backend.readiness_diagnostics().to_dict()
        cache_diagnostics = self.backend.cache_diagnostics()
        # END_BLOCK_COLLECT_MODEL_STATUS
        # START_BLOCK_BUILD_READINESS_REPORT
        report = {
            "configured_models": len(items),
            "available_models": available_count,
            "loadable_models": loadable_count,
            "runtime_ready_models": runtime_ready_count,
            "loaded_models": loaded_count,
            "selected_backend": self.backend.key,
            "selected_backend_label": self.backend.label,
            "backend_selection": {
                "requested_backend": self.backend_registry.selection.requested_backend,
                "auto_selected": self.backend_registry.selection.auto_selected,
                "selection_reason": self.backend_registry.selection.selection_reason,
            },
            "backend_capabilities": self.backend.capabilities().to_dict(),
            "backend_diagnostics": backend_diagnostics,
            "cache_diagnostics": cache_diagnostics,
            "metrics": self._build_metrics_summary(),
            "preload": self._build_preload_report(
                status=self._preload_report["status"],
                requested_model_ids=self._preload_report["requested_model_ids"],
                resolved_model_ids=self._preload_report["resolved_model_ids"],
                loaded_model_ids=self._preload_report["loaded_model_ids"],
                failed_model_ids=self._preload_report["failed_model_ids"],
                errors=self._preload_report["errors"],
                policy_reason=self._preload_report["policy_reason"],
            ),
            "available_backends": self.backend_registry.list_backends(),
            "items": items,
            "manifest": {
                "version": self.backend_registry._model_manifest.version,
                "metadata": dict(self.backend_registry._model_manifest.metadata),
            },
        }
        report["registry_ready"] = (
            runtime_ready_count > 0 and backend_diagnostics["ready"]
        )
        return report
        # END_BLOCK_BUILD_READINESS_REPORT

    # START_CONTRACT: is_ready
    #   PURPOSE: Evaluate whether the registry has at least one runtime-ready model and return the supporting report.
    #   INPUTS: {}
    #   OUTPUTS: { tuple[bool, dict[str, Any]] - Readiness boolean and full readiness report }
    #   SIDE_EFFECTS: none
    #   LINKS: M-MODEL-REGISTRY
    # END_CONTRACT: is_ready
    def is_ready(self) -> tuple[bool, dict[str, Any]]:
        report = self.readiness_report()
        return report["registry_ready"], report

    def _apply_preload_policy(self) -> None:
        # START_BLOCK_RESOLVE_PRELOAD_SPECS
        specs = self._resolve_preload_specs()
        requested_ids = self._requested_preload_model_ids()
        if not specs:
            policy_reason = (
                "disabled" if self._preload_policy == "none" else "no_matching_models"
            )
            self._preload_report = self._build_preload_report(
                status="skipped",
                requested_model_ids=requested_ids,
                resolved_model_ids=[],
                policy_reason=policy_reason,
            )
            return
        # END_BLOCK_RESOLVE_PRELOAD_SPECS

        # START_BLOCK_EXECUTE_PRELOAD
        preload_result = self.backend.preload_models(tuple(specs))
        status = "completed"
        if preload_result["failed"] and preload_result["loaded"]:
            status = "completed_with_errors"
        elif preload_result["failed"] and not preload_result["loaded"]:
            status = "failed"
        self._preload_report = self._build_preload_report(
            status=status,
            requested_model_ids=requested_ids,
            resolved_model_ids=[spec.api_name for spec in specs],
            loaded_model_ids=preload_result["loaded_model_ids"],
            failed_model_ids=preload_result["failed_model_ids"],
            errors=preload_result["errors"],
            policy_reason="configured",
        )
        # END_BLOCK_EXECUTE_PRELOAD

    def _resolve_preload_specs(self) -> list[ModelSpec]:
        if self._preload_policy == "none":
            return []
        if self._preload_policy == "all":
            return [spec for spec in self.model_specs if self._is_preloadable(spec)]
        if self._preload_policy == "listed":
            specs: list[ModelSpec] = []
            for model_id in self._preload_model_ids:
                try:
                    spec = self.get_model_spec(model_name=model_id)
                except (ModelNotAvailableError, ModelLoadError):
                    continue
                if self._is_preloadable(spec) and spec not in specs:
                    specs.append(spec)
            return specs
        return []

    def _requested_preload_model_ids(self) -> list[str]:
        if self._preload_policy == "all":
            return [spec.api_name for spec in self.model_specs]
        return list(self._preload_model_ids)

    def _is_preloadable(self, spec: ModelSpec) -> bool:
        status = self.backend.inspect_model(spec)
        return bool(status["runtime_ready"])

    def _preload_state_for_model(self, spec: ModelSpec) -> dict[str, Any]:
        requested = (
            self._preload_policy == "all"
            or spec.api_name in self._preload_model_ids
            or spec.folder in self._preload_model_ids
            or spec.key in self._preload_model_ids
        )
        if self._preload_policy == "none":
            status = "disabled"
        elif spec.api_name in self._preload_report["loaded_model_ids"]:
            status = "loaded"
        elif spec.api_name in self._preload_report["failed_model_ids"]:
            status = "failed"
        elif requested:
            status = "requested"
        else:
            status = "not_requested"
        return {
            "policy": self._preload_policy,
            "requested": requested,
            "status": status,
        }

    def _build_metrics_summary(self) -> dict[str, Any]:
        return {
            "selected_backend": self.backend.metrics_summary(),
            "operational": self._metrics.readiness_summary(),
        }

    def _build_preload_report(
        self,
        *,
        status: str,
        requested_model_ids: list[str] | None = None,
        resolved_model_ids: list[str] | None = None,
        loaded_model_ids: list[str] | None = None,
        failed_model_ids: list[str] | None = None,
        errors: list[dict[str, Any]] | None = None,
        policy_reason: str | None = None,
    ) -> dict[str, Any]:
        requested_model_ids = requested_model_ids or []
        resolved_model_ids = resolved_model_ids or []
        loaded_model_ids = loaded_model_ids or []
        failed_model_ids = failed_model_ids or []
        errors = errors or []
        return {
            "policy": self._preload_policy,
            "configured_model_ids": list(self._preload_model_ids),
            "requested_model_ids": requested_model_ids,
            "resolved_model_ids": resolved_model_ids,
            "status": status,
            "policy_reason": policy_reason,
            "attempted": len(resolved_model_ids),
            "loaded": len(loaded_model_ids),
            "failed": len(failed_model_ids),
            "loaded_model_ids": loaded_model_ids,
            "failed_model_ids": failed_model_ids,
            "errors": errors,
        }

__all__ = [
    "LOGGER",
    "SUPPORTED_PRELOAD_POLICIES",
    "ModelRegistry",
]
