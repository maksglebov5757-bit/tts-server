from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Mapping


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MODELS_DIR = PROJECT_ROOT / ".models"
DEFAULT_OUTPUTS_DIR = PROJECT_ROOT / ".outputs"
DEFAULT_VOICES_DIR = PROJECT_ROOT / ".voices"
DEFAULT_UPLOAD_STAGING_DIR = PROJECT_ROOT / ".uploads"


LOCAL_JOB_EXECUTION_BACKEND = "local"
LOCAL_JOB_METADATA_BACKEND = "local"
LOCAL_JOB_ARTIFACT_BACKEND = "local"
LOCAL_RATE_LIMIT_BACKEND = "local"
LOCAL_QUOTA_BACKEND = "local"


AuthMode = Literal["off", "static_bearer"]


@dataclass(frozen=True)
class CoreSettings:
    models_dir: Path
    outputs_dir: Path
    voices_dir: Path
    upload_staging_dir: Path = field(default_factory=lambda: DEFAULT_UPLOAD_STAGING_DIR)
    model_manifest_path: Path = field(default_factory=lambda: (PROJECT_ROOT / "core" / "models" / "manifest.v1.json"))
    backend: str | None = None
    backend_autoselect: bool = True
    model_preload_policy: str = "none"
    model_preload_ids: tuple[str, ...] = ()
    job_execution_backend: str = LOCAL_JOB_EXECUTION_BACKEND
    job_metadata_backend: str = LOCAL_JOB_METADATA_BACKEND
    job_artifact_backend: str = LOCAL_JOB_ARTIFACT_BACKEND
    auth_mode: AuthMode = "off"
    auth_static_bearer_token: str | None = None
    auth_static_bearer_principal_id: str | None = None
    auth_static_bearer_credential_id: str | None = None
    rate_limit_enabled: bool = False
    rate_limit_backend: str = LOCAL_RATE_LIMIT_BACKEND
    rate_limit_sync_tts_per_minute: int = 0
    rate_limit_async_submit_per_minute: int = 0
    rate_limit_job_read_per_minute: int = 0
    rate_limit_job_cancel_per_minute: int = 0
    rate_limit_control_plane_per_minute: int = 0
    quota_enabled: bool = False
    quota_backend: str = LOCAL_QUOTA_BACKEND
    quota_compute_requests_per_window: int = 0
    quota_compute_window_seconds: int = 60
    quota_max_active_jobs_per_principal: int = 0
    sample_rate: int = 24000
    filename_max_len: int = 20
    default_save_output: bool = False
    enable_streaming: bool = True
    max_upload_size_bytes: int = 25 * 1024 * 1024
    max_input_text_chars: int = 5_000
    request_timeout_seconds: int = 300
    inference_busy_status_code: int = 503
    auto_play_cli: bool = True

    def ensure_directories(self) -> None:
        self.outputs_dir.mkdir(parents=True, exist_ok=True)
        self.voices_dir.mkdir(parents=True, exist_ok=True)
        self.upload_staging_dir.mkdir(parents=True, exist_ok=True)


def env_text(name: str, default: str, environ: Mapping[str, str] | None = None) -> str:
    env = os.environ if environ is None else environ
    return env.get(name, default)



def env_int(name: str, default: int, environ: Mapping[str, str] | None = None) -> int:
    return int(env_text(name, str(default), environ))



def env_bool(name: str, default: bool, environ: Mapping[str, str] | None = None) -> bool:
    env = os.environ if environ is None else environ
    value = env.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}



def env_path(name: str, default: Path, environ: Mapping[str, str] | None = None) -> Path:
    env = os.environ if environ is None else environ
    return Path(env.get(name, str(default))).resolve()



def _parse_csv_env(name: str, environ: Mapping[str, str] | None = None) -> tuple[str, ...]:
    raw = env_text(name, "", environ)
    values: list[str] = []
    for part in raw.split(","):
        value = part.strip()
        if value and value not in values:
            values.append(value)
    return tuple(values)



def parse_core_settings_from_env(environ: Mapping[str, str] | None = None) -> dict[str, object]:
    backend = env_text("QWEN_TTS_BACKEND", "", environ).strip() or None
    auth_mode = env_text("QWEN_TTS_AUTH_MODE", "off", environ).strip().lower() or "off"
    if auth_mode not in {"off", "static_bearer"}:
        raise ValueError(f"Unsupported auth mode: {auth_mode}")
    auth_static_bearer_token = env_text("QWEN_TTS_AUTH_STATIC_BEARER_TOKEN", "", environ).strip() or None
    auth_static_bearer_principal_id = env_text("QWEN_TTS_AUTH_STATIC_BEARER_PRINCIPAL_ID", "", environ).strip() or None
    auth_static_bearer_credential_id = env_text("QWEN_TTS_AUTH_STATIC_BEARER_CREDENTIAL_ID", "", environ).strip() or None
    return {
        "models_dir": env_path("QWEN_TTS_MODELS_DIR", DEFAULT_MODELS_DIR, environ),
        "outputs_dir": env_path("QWEN_TTS_OUTPUTS_DIR", DEFAULT_OUTPUTS_DIR, environ),
        "voices_dir": env_path("QWEN_TTS_VOICES_DIR", DEFAULT_VOICES_DIR, environ),
        "upload_staging_dir": env_path("QWEN_TTS_UPLOAD_STAGING_DIR", DEFAULT_UPLOAD_STAGING_DIR, environ),
        "model_manifest_path": env_path(
            "QWEN_TTS_MODEL_MANIFEST_PATH",
            PROJECT_ROOT / "core" / "models" / "manifest.v1.json",
            environ,
        ),
        "backend": backend,
        "backend_autoselect": env_bool("QWEN_TTS_BACKEND_AUTOSELECT", True, environ),
        "model_preload_policy": env_text("QWEN_TTS_MODEL_PRELOAD_POLICY", "none", environ).strip().lower() or "none",
        "model_preload_ids": _parse_csv_env("QWEN_TTS_MODEL_PRELOAD_IDS", environ),
        "job_execution_backend": env_text(
            "QWEN_TTS_JOB_EXECUTION_BACKEND",
            LOCAL_JOB_EXECUTION_BACKEND,
            environ,
        ).strip()
        or LOCAL_JOB_EXECUTION_BACKEND,
        "job_metadata_backend": env_text(
            "QWEN_TTS_JOB_METADATA_BACKEND",
            LOCAL_JOB_METADATA_BACKEND,
            environ,
        ).strip()
        or LOCAL_JOB_METADATA_BACKEND,
        "job_artifact_backend": env_text(
            "QWEN_TTS_JOB_ARTIFACT_BACKEND",
            LOCAL_JOB_ARTIFACT_BACKEND,
            environ,
        ).strip()
        or LOCAL_JOB_ARTIFACT_BACKEND,
        "auth_mode": auth_mode,
        "auth_static_bearer_token": auth_static_bearer_token,
        "auth_static_bearer_principal_id": auth_static_bearer_principal_id,
        "auth_static_bearer_credential_id": auth_static_bearer_credential_id,
        "rate_limit_enabled": env_bool("QWEN_TTS_RATE_LIMIT_ENABLED", False, environ),
        "rate_limit_backend": env_text("QWEN_TTS_RATE_LIMIT_BACKEND", LOCAL_RATE_LIMIT_BACKEND, environ).strip()
        or LOCAL_RATE_LIMIT_BACKEND,
        "rate_limit_sync_tts_per_minute": env_int("QWEN_TTS_RATE_LIMIT_SYNC_TTS_PER_MINUTE", 0, environ),
        "rate_limit_async_submit_per_minute": env_int("QWEN_TTS_RATE_LIMIT_ASYNC_SUBMIT_PER_MINUTE", 0, environ),
        "rate_limit_job_read_per_minute": env_int("QWEN_TTS_RATE_LIMIT_JOB_READ_PER_MINUTE", 0, environ),
        "rate_limit_job_cancel_per_minute": env_int("QWEN_TTS_RATE_LIMIT_JOB_CANCEL_PER_MINUTE", 0, environ),
        "rate_limit_control_plane_per_minute": env_int("QWEN_TTS_RATE_LIMIT_CONTROL_PLANE_PER_MINUTE", 0, environ),
        "quota_enabled": env_bool("QWEN_TTS_QUOTA_ENABLED", False, environ),
        "quota_backend": env_text("QWEN_TTS_QUOTA_BACKEND", LOCAL_QUOTA_BACKEND, environ).strip() or LOCAL_QUOTA_BACKEND,
        "quota_compute_requests_per_window": env_int("QWEN_TTS_QUOTA_COMPUTE_REQUESTS_PER_WINDOW", 0, environ),
        "quota_compute_window_seconds": env_int("QWEN_TTS_QUOTA_COMPUTE_WINDOW_SECONDS", 60, environ),
        "quota_max_active_jobs_per_principal": env_int("QWEN_TTS_QUOTA_MAX_ACTIVE_JOBS_PER_PRINCIPAL", 0, environ),
        "default_save_output": env_bool("QWEN_TTS_DEFAULT_SAVE_OUTPUT", False, environ),
        "enable_streaming": env_bool("QWEN_TTS_ENABLE_STREAMING", True, environ),
        "max_upload_size_bytes": env_int("QWEN_TTS_MAX_UPLOAD_SIZE_BYTES", 25 * 1024 * 1024, environ),
        "max_input_text_chars": env_int("QWEN_TTS_MAX_INPUT_TEXT_CHARS", 5_000, environ),
        "request_timeout_seconds": env_int("QWEN_TTS_REQUEST_TIMEOUT_SECONDS", 300, environ),
        "inference_busy_status_code": env_int("QWEN_TTS_INFERENCE_BUSY_STATUS_CODE", 503, environ),
        "sample_rate": env_int("QWEN_TTS_SAMPLE_RATE", 24000, environ),
        "filename_max_len": env_int("QWEN_TTS_FILENAME_MAX_LEN", 20, environ),
        "auto_play_cli": env_bool("QWEN_TTS_AUTO_PLAY_CLI", True, environ),
    }
