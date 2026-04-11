#!/usr/bin/env python3
# FILE: scripts/runtime_self_check.py
# VERSION: 1.0.0
# START_MODULE_CONTRACT
#   PURPOSE: Provide an operator-facing self-check utility for validating runtime dependencies, model assets, and readiness metadata.
#   SCOPE: CLI entry point for shared runtime self-check reporting, asset validation, and support evidence snapshots
#   DEPENDS: M-BOOTSTRAP, M-CONFIG, M-MODEL-REGISTRY
#   LINKS: M-BOOTSTRAP
#   ROLE: SCRIPT
#   MAP_MODE: LOCALS
# END_MODULE_CONTRACT
#
# START_MODULE_MAP
#   parse_args - Parse CLI arguments for self-check execution
#   build_asset_report - Build filesystem and runtime validation results for declared model assets
#   build_self_check_payload - Build the full runtime self-check payload for a given environment snapshot
#   main - Execute the runtime self-check and print JSON results
# END_MODULE_MAP
#
# START_CHANGE_SUMMARY
#   LAST_CHANGE: [v1.1.0 - Added reusable self-check payload builder for validation automation and CI orchestration]
# END_CHANGE_SUMMARY

from __future__ import annotations

import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import sys
from typing import Any, Mapping


# START_BLOCK_BOOTSTRAP_IMPORT_PATH
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
# END_BLOCK_BOOTSTRAP_IMPORT_PATH

from core.bootstrap import build_runtime  # noqa: E402
from core.config import CoreSettings, parse_core_settings_from_env  # noqa: E402


@contextmanager
def _overlaid_environment(environ: Mapping[str, str] | None):
    if environ is None:
        yield
        return

    original: dict[str, str | None] = {key: os.environ.get(key) for key in environ}
    missing_keys = [key for key, value in original.items() if value is None]
    try:
        for key, value in environ.items():
            os.environ[key] = value
        yield
    finally:
        for key in missing_keys:
            os.environ.pop(key, None)
        for key, value in original.items():
            if value is not None:
                os.environ[key] = value


# START_CONTRACT: parse_args
#   PURPOSE: Parse CLI arguments controlling runtime self-check output and strictness.
#   INPUTS: { argv: list[str] | None - optional raw CLI arguments }
#   OUTPUTS: { argparse.Namespace - parsed argument payload }
#   SIDE_EFFECTS: none
#   LINKS: M-BOOTSTRAP
# END_CONTRACT: parse_args
def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate local runtime dependencies, configured models, and readiness state.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero when the shared runtime is not ready or when any configured model is missing required assets.",
    )
    parser.add_argument(
        "--indent",
        type=int,
        default=2,
        help="JSON indentation level for the output payload.",
    )
    return parser.parse_args(argv)


# START_CONTRACT: build_asset_report
#   PURPOSE: Build per-model asset validation details for operator-facing setup checks.
#   INPUTS: { readiness_report: dict[str, Any] - registry readiness payload }
#   OUTPUTS: { dict[str, Any] - summarized asset validation state for configured models }
#   SIDE_EFFECTS: none
#   LINKS: M-MODEL-REGISTRY
# END_CONTRACT: build_asset_report
def build_asset_report(readiness_report: dict[str, Any]) -> dict[str, Any]:
    items = readiness_report.get("items", [])
    configured = [
        {
            "id": item.get("id"),
            "family": item.get("family"),
            "backend_support": item.get("backend_support", []),
            "folder": item.get("folder"),
            "available": item.get("available"),
            "loadable": item.get("loadable"),
            "runtime_ready": item.get("runtime_ready"),
            "execution_backend": item.get("execution_backend") or item.get("backend"),
            "selected_backend": item.get("selected_backend"),
            "capabilities_supported": item.get("capabilities_supported", []),
            "route_candidates": item.get("route", {}).get("candidates", []),
            "missing_artifacts": item.get("missing_artifacts", []),
            "required_artifacts": item.get("required_artifacts", []),
            "route_reason": item.get("route", {}).get("route_reason"),
        }
        for item in items
    ]
    missing_assets = [
        item
        for item in configured
        if item["missing_artifacts"] or not item["available"]
    ]
    return {
        "configured_models": configured,
        "models_missing_assets": missing_assets,
    }


# START_CONTRACT: build_self_check_payload
#   PURPOSE: Build the full runtime self-check payload for the active or provided environment mapping.
#   INPUTS: { environ: Mapping[str, str] | None - optional environment override used to resolve runtime settings }
#   OUTPUTS: { dict[str, Any] - structured runtime self-check payload suitable for local operators, CI, and validation scripts }
#   SIDE_EFFECTS: Builds the shared runtime, inspects model readiness, and resolves configured filesystem paths
#   LINKS: M-BOOTSTRAP, M-MODEL-REGISTRY
# END_CONTRACT: build_self_check_payload
def build_self_check_payload(
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    env = os.environ if environ is None else environ
    with _overlaid_environment(environ):
        settings = CoreSettings(**parse_core_settings_from_env(environ))
        runtime = build_runtime(settings)
        readiness = runtime.registry.readiness_report()
    return {
        "status": "ok" if readiness["registry_ready"] else "degraded",
        "settings": {
            "models_dir": str(settings.models_dir),
            "outputs_dir": str(settings.outputs_dir),
            "voices_dir": str(settings.voices_dir),
            "upload_staging_dir": str(settings.upload_staging_dir),
            "model_manifest_path": str(settings.model_manifest_path),
            "configured_backend": settings.backend,
            "backend_autoselect": settings.backend_autoselect,
            "qwen_fast_enabled": settings.qwen_fast_enabled,
            "qwen_fast_test_mode": env.get("QWEN_TTS_QWEN_FAST_TEST_MODE") or None,
            "model_preload_policy": settings.model_preload_policy,
            "model_preload_ids": list(settings.model_preload_ids),
        },
        "readiness": readiness,
        "assets": build_asset_report(readiness),
    }


# START_CONTRACT: main
#   PURPOSE: Execute the runtime self-check and print a JSON readiness snapshot for operators and CI.
#   INPUTS: { argv: list[str] | None - optional raw CLI arguments }
#   OUTPUTS: { int - process exit code }
#   SIDE_EFFECTS: Builds the shared runtime, performs filesystem checks, and writes JSON to stdout
#   LINKS: M-BOOTSTRAP, M-MODEL-REGISTRY
# END_CONTRACT: main
def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    payload = build_self_check_payload()
    print(json.dumps(payload, indent=args.indent, sort_keys=True))

    if not args.strict:
        return 0
    if (
        payload["readiness"]["registry_ready"]
        and not payload["assets"]["models_missing_assets"]
    ):
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
