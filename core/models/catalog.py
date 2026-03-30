from __future__ import annotations

from types import MappingProxyType

from core.models.manifest import DEFAULT_MODEL_MANIFEST_PATH, ModelManifest, ModelSpec, load_model_manifest


SPEAKER_MAP = {
    "English": ["Ryan", "Aiden", "Ethan", "Chelsie", "Serena", "Vivian"],
    "Chinese": ["Vivian", "Serena", "Uncle_Fu", "Dylan", "Eric"],
    "Japanese": ["Ono_Anna"],
    "Korean": ["Sohee"],
}

EMOTION_EXAMPLES = [
    "Sad and crying, speaking slowly",
    "Excited and happy, speaking very fast",
    "Angry and shouting",
    "Whispering quietly",
]


def get_model_manifest(path=DEFAULT_MODEL_MANIFEST_PATH) -> ModelManifest:
    return load_model_manifest(path)


def get_model_specs() -> dict[str, ModelSpec]:
    return dict(get_model_manifest().models)


MODEL_SPECS = MappingProxyType(get_model_specs())


__all__ = [
    "DEFAULT_MODEL_MANIFEST_PATH",
    "EMOTION_EXAMPLES",
    "MODEL_SPECS",
    "ModelManifest",
    "ModelSpec",
    "SPEAKER_MAP",
    "get_model_manifest",
    "get_model_specs",
]
