"""
Telegram command parser and validation.

This module provides parsing and validation logic for Telegram bot commands,
independent of the Telegram API implementation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from core.models.catalog import SPEAKER_MAP


# Speed constraints for Telegram TTS
MIN_SPEED = 0.5
MAX_SPEED = 2.0
DEFAULT_SPEED = 1.0

# Valid speakers derived from SPEAKER_MAP
VALID_SPEAKERS: frozenset[str] = frozenset(
    speaker for speakers in SPEAKER_MAP.values() for speaker in speakers
)


class CommandType(Enum):
    """Supported Telegram bot commands."""

    START = "start"
    HELP = "help"
    TTS = "tts"
    DESIGN = "design"
    CLONE = "clone"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ParsedCommand:
    """Parsed command with extracted arguments."""

    command: CommandType
    raw_text: str
    args: str
    user_id: int
    chat_id: int
    message_id: int
    reply_to_message: dict | None = None

    @property
    def tts_text(self) -> str:
        """Extract text for TTS synthesis from command args."""
        return self.args.strip()


@dataclass(frozen=True)
class ParsedTTSArgs:
    """Parsed and validated /tts command arguments."""

    text: str
    speaker: str | None = None
    speed: float | None = None
    language: str = "auto"


@dataclass(frozen=True)
class CommandValidationResult:
    """Result of command validation."""

    is_valid: bool
    error_message: Optional[str] = None


# Pattern for /tts command with extended syntax:
# /tts [speaker=<speaker>] [speed=<speed>] -- <text>
# Examples:
#   /tts -- Hello world
#   /tts speaker=Vivian -- Hello world
#   /tts speed=1.5 -- Hello world
#   /tts speaker=Ryan speed=0.8 -- Hello world
_TTS_ARGS_PATTERN = re.compile(
    r"""
    ^
    (?:(?P<speaker>speaker=\S+))?\s*          # Optional: speaker=<value>
    (?:(?P<speed>speed=\S+))?\s*              # Optional: speed=<value>
    --\s*                                     # Required delimiter
    (?P<text>.*)                               # Text after --
    $
    """,
    re.VERBOSE | re.IGNORECASE,
)


def _normalize_language(value: str) -> str:
    normalized = value.strip().lower()
    if not normalized:
        raise ValueError("Language must not be empty")
    return normalized


def parse_command(
    text: str,
    user_id: int,
    chat_id: int,
    message_id: int,
    reply_to_message: dict | None = None,
) -> ParsedCommand | None:
    """
    Parse incoming text as a bot command.

    Args:
        text: Raw message text
        user_id: Telegram user ID
        chat_id: Telegram chat ID
        message_id: Telegram message ID
        reply_to_message: Optional replied Telegram message payload

    Returns:
        ParsedCommand if text starts with /, None otherwise
    """
    if not text or not text.startswith("/"):
        return None

    parts = text.split(maxsplit=1)
    command_part = parts[0].lstrip("/")

    # Handle /command@botname format
    if "@" in command_part:
        command_part = command_part.split("@")[0]

    command_str = command_part.lower()
    args = parts[1] if len(parts) > 1 else ""

    try:
        command_type = CommandType(command_str)
    except ValueError:
        command_type = CommandType.UNKNOWN

    return ParsedCommand(
        command=command_type,
        raw_text=text,
        args=args,
        user_id=user_id,
        chat_id=chat_id,
        message_id=message_id,
        reply_to_message=reply_to_message,
    )


def parse_tts_args(args: str) -> ParsedTTSArgs | None:
    """
    Parse /tts command arguments using the extended syntax.

    Contract:
        /tts [speaker=<speaker>] [speed=<speed>] -- <text>

    Args:
        args: Raw arguments after /tts command

    Returns:
        ParsedTTSArgs if valid syntax, None otherwise
    """
    if not args:
        return None

    normalized_args = args.strip()

    if "--" in normalized_args:
        before_separator, after_separator = normalized_args.split("--", 1)
        speaker: str | None = None
        speed: float | None = None
        language = "auto"

        for token in before_separator.strip().split():
            lowered = token.lower()
            if lowered.startswith("speaker="):
                value = token.split("=", 1)[1].strip()
                if not value or speaker is not None:
                    return None
                speaker = value
                continue
            if lowered.startswith("speed="):
                value = token.split("=", 1)[1].strip()
                if not value or speed is not None:
                    return None
                try:
                    speed = float(value)
                except ValueError:
                    return None
                continue
            if lowered.startswith("lang="):
                if language != "auto":
                    return None
                try:
                    language = _normalize_language(token.split("=", 1)[1])
                except ValueError:
                    return None
                continue
            return None

        return ParsedTTSArgs(
            text=after_separator.strip(),
            speaker=speaker,
            speed=speed,
            language=language,
        )

    # Fall back to legacy syntax: /tts <text> (no -- separator)
    # This maintains backward compatibility
    if "--" not in args:
        return ParsedTTSArgs(text=args.strip())

    return None


def validate_tts_args(parsed_args: ParsedTTSArgs) -> CommandValidationResult:
    """
    Validate parsed /tts arguments.

    Args:
        parsed_args: Parsed TTS arguments

    Returns:
        CommandValidationResult with validation status and error message
    """
    # Validate speaker if provided
    if parsed_args.speaker is not None:
        if parsed_args.speaker not in VALID_SPEAKERS:
            valid_list = ", ".join(sorted(VALID_SPEAKERS))
            return CommandValidationResult(
                is_valid=False,
                error_message=f"Unknown speaker '{parsed_args.speaker}'. "
                f"Available speakers: {valid_list}",
            )

    # Validate speed if provided
    if parsed_args.speed is not None:
        if not (MIN_SPEED <= parsed_args.speed <= MAX_SPEED):
            return CommandValidationResult(
                is_valid=False,
                error_message=f"Speed must be between {MIN_SPEED} and {MAX_SPEED}. "
                f"Got: {parsed_args.speed}",
            )

    # Validate text is not empty
    if not parsed_args.text:
        return CommandValidationResult(
            is_valid=False,
            error_message="Please provide text after /tts. "
            f"Usage: /tts [-- speaker=<speaker>] [-- speed=<speed>] -- <text>",
        )

    if not parsed_args.language:
        return CommandValidationResult(
            is_valid=False,
            error_message="Language must not be empty. Usage: /tts [speaker=<speaker>] [speed=<speed>] [lang=<language>] -- <text>",
        )

    return CommandValidationResult(is_valid=True)


def validate_tts_command(
    parsed: ParsedCommand,
    max_length: int,
) -> CommandValidationResult:
    """
    Validate TTS command arguments.

    Args:
        parsed: Parsed command
        max_length: Maximum allowed text length

    Returns:
        CommandValidationResult with validation status and error message
    """
    if parsed.command != CommandType.TTS:
        return CommandValidationResult(is_valid=True)

    if not parsed.args:
        return CommandValidationResult(
            is_valid=False,
            error_message="Please provide text after /tts. "
            f"Usage: /tts [-- speaker=<speaker>] [-- speed=<speed>] -- <text>",
        )

    # Try to parse extended syntax
    parsed_args = parse_tts_args(parsed.args)
    if parsed_args is None:
        return CommandValidationResult(
            is_valid=False,
            error_message="Invalid /tts syntax. Use: /tts [-- speaker=<speaker>] [-- speed=<speed>] -- <text>",
        )

    # Validate parsed arguments
    validation = validate_tts_args(parsed_args)
    if not validation.is_valid:
        return validation

    # Check text length
    if len(parsed_args.text) > max_length:
        return CommandValidationResult(
            is_valid=False,
            error_message=f"Text is too long. Maximum {max_length} characters allowed. "
            f"Your text: {len(parsed_args.text)} characters.",
        )

    return CommandValidationResult(is_valid=True)


def get_valid_speakers() -> list[str]:
    """Get list of valid speaker names sorted alphabetically."""
    return sorted(VALID_SPEAKERS)


def is_private_chat(chat_type: str) -> bool:
    """
    Check if chat is a private conversation.

    Args:
        chat_type: Telegram chat type ('private', 'group', 'supergroup', 'channel')

    Returns:
        True if private chat
    """
    return chat_type == "private"


# ============================================================================
# Voice Design Command Support (Stage 3)
# ============================================================================

# Voice Design constraints (aligned with core/server limits)
MIN_VOICE_DESCRIPTION_LENGTH = 3
MAX_VOICE_DESCRIPTION_LENGTH = 500
MIN_TEXT_LENGTH = 1
MAX_TEXT_LENGTH = 1000  # Same as typical Telegram text limit


@dataclass(frozen=True)
class ParsedDesignArgs:
    """Parsed and validated /design command arguments."""

    voice_description: str
    text: str
    language: str = "auto"


def _consume_leading_language(args: str) -> tuple[str, str] | None:
    stripped_args = args.strip()
    if not stripped_args.lower().startswith("lang="):
        return "auto", stripped_args

    parts = stripped_args.split(None, 1)
    language_token = parts[0]
    try:
        language = _normalize_language(language_token.split("=", 1)[1])
    except ValueError:
        return None
    remainder = parts[1] if len(parts) > 1 else ""
    return language, remainder.strip()


def parse_design_args(args: str) -> ParsedDesignArgs | None:
    """
    Parse /design command arguments.

    Contract:
        /design <voice_description> -- <text>

    Args:
        args: Raw arguments after /design command

    Returns:
        ParsedDesignArgs if valid syntax, None otherwise
    """
    if not args:
        return None

    consumed = _consume_leading_language(args)
    if consumed is None:
        return None
    language, remaining_args = consumed

    # Find the separator
    separator = " -- "
    if separator not in remaining_args:
        return None

    parts = remaining_args.split(separator, 1)
    if len(parts) != 2:
        return None

    voice_description = parts[0].strip()
    text = parts[1].strip()

    return ParsedDesignArgs(
        voice_description=voice_description,
        text=text,
        language=language,
    )


def validate_design_args(parsed_args: ParsedDesignArgs) -> CommandValidationResult:
    """
    Validate parsed /design arguments.

    Args:
        parsed_args: Parsed Design arguments

    Returns:
        CommandValidationResult with validation status and error message
    """
    # Validate voice_description is not empty after trim
    if not parsed_args.voice_description:
        return CommandValidationResult(
            is_valid=False,
            error_message="Voice description cannot be empty. "
            f"Usage: /design <voice_description> -- <text>",
        )

    # Validate voice_description length
    if len(parsed_args.voice_description) < MIN_VOICE_DESCRIPTION_LENGTH:
        return CommandValidationResult(
            is_valid=False,
            error_message=f"Voice description is too short. "
            f"Minimum {MIN_VOICE_DESCRIPTION_LENGTH} characters required. "
            f"Got: {len(parsed_args.voice_description)}",
        )

    if len(parsed_args.voice_description) > MAX_VOICE_DESCRIPTION_LENGTH:
        return CommandValidationResult(
            is_valid=False,
            error_message=f"Voice description is too long. "
            f"Maximum {MAX_VOICE_DESCRIPTION_LENGTH} characters allowed. "
            f"Got: {len(parsed_args.voice_description)}",
        )

    # Validate text is not empty after trim
    if not parsed_args.text:
        return CommandValidationResult(
            is_valid=False,
            error_message="Text cannot be empty. "
            f"Usage: /design <voice_description> -- <text>",
        )

    # Validate text length
    if len(parsed_args.text) < MIN_TEXT_LENGTH:
        return CommandValidationResult(
            is_valid=False,
            error_message=f"Text is too short. "
            f"Minimum {MIN_TEXT_LENGTH} character required. "
            f"Got: {len(parsed_args.text)}",
        )

    if len(parsed_args.text) > MAX_TEXT_LENGTH:
        return CommandValidationResult(
            is_valid=False,
            error_message=f"Text is too long. "
            f"Maximum {MAX_TEXT_LENGTH} characters allowed. "
            f"Got: {len(parsed_args.text)}",
        )

    if not parsed_args.language:
        return CommandValidationResult(
            is_valid=False,
            error_message="Language must not be empty. Usage: /design [lang=<language>] <voice_description> -- <text>",
        )

    return CommandValidationResult(is_valid=True)


def validate_design_command(
    parsed: ParsedCommand,
    max_voice_description_length: int = MAX_VOICE_DESCRIPTION_LENGTH,
    max_text_length: int = MAX_TEXT_LENGTH,
) -> CommandValidationResult:
    """
    Validate Design command arguments.

    Args:
        parsed: Parsed command
        max_voice_description_length: Maximum voice description length
        max_text_length: Maximum text length

    Returns:
        CommandValidationResult with validation status and error message
    """
    if parsed.command != CommandType.DESIGN:
        return CommandValidationResult(is_valid=True)

    if not parsed.args:
        return CommandValidationResult(
            is_valid=False,
            error_message="Please provide voice description and text. "
            f"Usage: /design <voice_description> -- <text>",
        )

    # Try to parse design syntax
    parsed_args = parse_design_args(parsed.args)
    if parsed_args is None:
        return CommandValidationResult(
            is_valid=False,
            error_message="Invalid /design syntax. Use: /design <voice_description> -- <text>",
        )

    # Validate parsed arguments
    validation = validate_design_args(parsed_args)
    if not validation.is_valid:
        return validation

    return CommandValidationResult(is_valid=True)


# ============================================================================
# Voice Clone Command Support (Stage 4)
# ============================================================================

# Voice Clone constraints (aligned with core/server limits)
MIN_REF_TEXT_LENGTH = 1
MAX_REF_TEXT_LENGTH = 500
MIN_CLONE_TEXT_LENGTH = 1
MAX_CLONE_TEXT_LENGTH = 1000


@dataclass(frozen=True)
class ParsedCloneArgs:
    """Parsed and validated /clone command arguments."""

    ref_text: str | None = None
    text: str = ""
    language: str = "auto"


# Pattern for /clone command:
# /clone [ref=<ref_text>] -- <text>
# Examples:
#   /clone -- Hello world
#   /clone ref=This is my sample -- Hello world
_CLONE_ARGS_PATTERN = re.compile(
    r"""
    ^
    (?:(?P<ref_text>ref=\S+))?\s*              # Optional: ref=<text>
    --\s*                                        # Required delimiter
    (?P<text>.*)                                  # Text after --
    $
    """,
    re.VERBOSE | re.IGNORECASE,
)


def parse_clone_args(args: str) -> ParsedCloneArgs | None:
    """
    Parse /clone command arguments.

    Contract:
        /clone [ref=<ref_text>] -- <text>

    Args:
        args: Raw arguments after /clone command

    Returns:
        ParsedCloneArgs if valid syntax, None otherwise
    """
    if not args:
        return None

    consumed = _consume_leading_language(args)
    if consumed is None:
        return None
    language, remaining_args = consumed

    # Find the separator (must have --)
    if " -- " not in remaining_args and "--" not in remaining_args:
        return None

    # Try pattern matching
    match = _CLONE_ARGS_PATTERN.match(remaining_args)
    if match:
        ref_text_value: str | None = None

        ref_text_match = match.group("ref_text")
        if ref_text_match:
            # Extract value after "ref="
            ref_text_value = ref_text_match.split("=", 1)[1].strip()

        text = match.group("text") or ""

        return ParsedCloneArgs(
            ref_text=ref_text_value if ref_text_value else None,
            text=text.strip(),
            language=language,
        )

    # Fallback: try to find -- separator manually
    # Support both " -- " and bare "--" as separator
    separator_index = remaining_args.find("--")
    if separator_index == -1:
        return None

    before_sep = remaining_args[:separator_index].strip()
    after_sep = remaining_args[separator_index + 2 :].strip()

    ref_text: str | None = None

    # Check if there's ref= before separator
    if before_sep.lower().startswith("ref="):
        ref_text = before_sep[4:].strip()
        if not ref_text:
            ref_text = None
    elif before_sep:
        # There's text before -- but no ref=, which is valid
        # (just empty before separator, text comes after)
        pass

    if not after_sep:
        return None

    return ParsedCloneArgs(
        ref_text=ref_text,
        text=after_sep.strip(),
        language=language,
    )


def validate_clone_args(parsed_args: ParsedCloneArgs) -> CommandValidationResult:
    """
    Validate parsed /clone arguments.

    Args:
        parsed_args: Parsed Clone arguments

    Returns:
        CommandValidationResult with validation status and error message
    """
    # Validate ref_text length if provided
    if parsed_args.ref_text is not None:
        if len(parsed_args.ref_text) > MAX_REF_TEXT_LENGTH:
            return CommandValidationResult(
                is_valid=False,
                error_message=f"Reference text is too long. "
                f"Maximum {MAX_REF_TEXT_LENGTH} characters allowed. "
                f"Got: {len(parsed_args.ref_text)}",
            )

    # Validate text is not empty
    if not parsed_args.text:
        return CommandValidationResult(
            is_valid=False,
            error_message="Text cannot be empty. "
            f"Usage: /clone [-- ref=<transcript>] -- <text>",
        )

    # Validate text length
    if len(parsed_args.text) < MIN_CLONE_TEXT_LENGTH:
        return CommandValidationResult(
            is_valid=False,
            error_message=f"Text is too short. "
            f"Minimum {MIN_CLONE_TEXT_LENGTH} character required. "
            f"Got: {len(parsed_args.text)}",
        )

    if len(parsed_args.text) > MAX_CLONE_TEXT_LENGTH:
        return CommandValidationResult(
            is_valid=False,
            error_message=f"Text is too long. "
            f"Maximum {MAX_CLONE_TEXT_LENGTH} characters allowed. "
            f"Got: {len(parsed_args.text)}",
        )

    if not parsed_args.language:
        return CommandValidationResult(
            is_valid=False,
            error_message="Language must not be empty. Usage: /clone [lang=<language>] [ref=<transcript>] -- <text>",
        )

    return CommandValidationResult(is_valid=True)


def validate_clone_command(
    parsed: ParsedCommand,
    max_ref_text_length: int = MAX_REF_TEXT_LENGTH,
    max_text_length: int = MAX_CLONE_TEXT_LENGTH,
) -> CommandValidationResult:
    """
    Validate Clone command arguments.

    Args:
        parsed: Parsed command
        max_ref_text_length: Maximum reference text length
        max_text_length: Maximum text length

    Returns:
        CommandValidationResult with validation status and error message
    """
    if parsed.command != CommandType.CLONE:
        return CommandValidationResult(is_valid=True)

    if not parsed.args:
        return CommandValidationResult(
            is_valid=False,
            error_message="Please provide text after /clone. "
            f"Usage: /clone [-- ref=<transcript>] -- <text>",
        )

    # Check for unsupported parameters (speaker, speed, model are not supported for clone)
    unsupported_params = ["speaker=", "speed=", "model="]
    for param in unsupported_params:
        if param in parsed.args.lower():
            param_name = param.rstrip("=")
            return CommandValidationResult(
                is_valid=False,
                error_message=f"Unsupported parameter '{param_name}' for /clone. "
                f"Only 'lang=' and 'ref=' are supported. Use: /clone [lang=<language>] [ref=<transcript>] -- <text>",
            )

    # Try to parse clone syntax
    parsed_args = parse_clone_args(parsed.args)
    if parsed_args is None:
        return CommandValidationResult(
            is_valid=False,
            error_message="Invalid /clone syntax. Use: /clone [lang=<language>] [ref=<transcript>] -- <text>",
        )

    # Validate parsed arguments
    validation = validate_clone_args(parsed_args)
    if not validation.is_valid:
        return validation

    return CommandValidationResult(is_valid=True)
