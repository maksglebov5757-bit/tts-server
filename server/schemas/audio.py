from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


def normalize_text_value(value: str, *, empty_message: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError(empty_message)
    return value


def normalize_language_value(value: str) -> str:
    value = value.strip().lower()
    if not value:
        raise ValueError("Language must not be empty")
    return value


def validate_text_length(value: str, *, field_name: str, max_chars: int) -> str:
    if len(value) > max_chars:
        raise ValueError(f"{field_name} must be at most {max_chars} characters")
    return value


class OpenAISpeechRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str = Field(..., description="Model identifier")
    input: str = Field(..., min_length=1, description="Input text")
    voice: str = Field(default="Vivian", description="Speaker/voice name")
    language: str = Field(default="auto", description="Language code or auto")
    response_format: Literal["wav", "pcm"] = Field(default="wav")
    speed: float = Field(default=1.0, ge=0.25, le=4.0)

    @field_validator("input")
    @classmethod
    def validate_input(cls, value: str) -> str:
        return normalize_text_value(value, empty_message="Input text must not be empty")

    @field_validator("language")
    @classmethod
    def validate_language(cls, value: str) -> str:
        return normalize_language_value(value)


class CustomTTSRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: Optional[str] = Field(
        default=None, description="Optional custom voice model override"
    )
    text: str = Field(..., min_length=1)
    speaker: str = Field(default="Vivian")
    emotion: Optional[str] = Field(default=None)
    instruct: Optional[str] = Field(default=None)
    language: str = Field(default="auto")
    speed: float = Field(default=1.0, ge=0.25, le=4.0)
    save_output: Optional[bool] = Field(default=None)

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        return normalize_text_value(value, empty_message="Text must not be empty")

    @field_validator("language")
    @classmethod
    def validate_language(cls, value: str) -> str:
        return normalize_language_value(value)


class DesignTTSRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: Optional[str] = Field(
        default=None, description="Optional voice design model override"
    )
    text: str = Field(..., min_length=1)
    voice_description: str = Field(..., min_length=1)
    language: str = Field(default="auto")
    save_output: Optional[bool] = Field(default=None)

    @field_validator("text", "voice_description")
    @classmethod
    def validate_non_empty(cls, value: str) -> str:
        return normalize_text_value(value, empty_message="Value must not be empty")

    @field_validator("language")
    @classmethod
    def validate_language(cls, value: str) -> str:
        return normalize_language_value(value)


class JobFailurePayload(BaseModel):
    code: str
    message: str
    details: Optional[dict[str, object]] = None


class JobSnapshotPayload(BaseModel):
    request_id: str
    job_id: str
    submit_request_id: str
    status: str
    operation: str
    mode: str
    model: Optional[str] = None
    backend: Optional[str] = None
    response_format: Optional[str] = None
    save_output: bool
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    saved_path: Optional[str] = None
    terminal_error: Optional[JobFailurePayload] = None
    status_url: str
    result_url: str
    cancel_url: str
    idempotency_key: Optional[str] = None


class TTSSuccessMetadata(BaseModel):
    request_id: str
    model: str
    mode: str
    backend: str
    saved_path: Optional[str] = None


class ModelInfo(BaseModel):
    key: str
    id: str
    name: str
    mode: str
    folder: str
    available: bool
    backend: str
    capabilities: dict[str, object]


class ModelsResponse(BaseModel):
    data: list[ModelInfo]


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    checks: dict[str, object]
