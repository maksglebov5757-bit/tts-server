from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ErrorDescriptor:
    status_code: int
    code: str
    message: str
    details: dict[str, Any]
    retryable: bool = False
    headers: dict[str, str] | None = None


@dataclass(frozen=True)
class ExceptionMapping:
    error_type: type[Exception]
    builder: Any
