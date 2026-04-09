from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class GenerationCommand:
    text: str
    model: Optional[str] = None
    save_output: bool = False
    language: str = "auto"
    language: str = "auto"

    def __post_init__(self) -> None:
        normalized_language = self.language.strip().lower()
        if not normalized_language:
            raise ValueError("Language must not be empty")
        object.__setattr__(self, "language", normalized_language)


@dataclass(frozen=True)
class CustomVoiceCommand(GenerationCommand):
    speaker: str = "Vivian"
    instruct: str = "Normal tone"
    speed: float = 1.0


@dataclass(frozen=True)
class VoiceDesignCommand(GenerationCommand):
    voice_description: str = ""


@dataclass(frozen=True)
class VoiceCloneCommand(GenerationCommand):
    ref_audio_path: Optional[Path] = None
    ref_text: Optional[str] = None
