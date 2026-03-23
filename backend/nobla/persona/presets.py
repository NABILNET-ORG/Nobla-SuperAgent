"""Bundled persona presets — always available, even without DB."""
from __future__ import annotations

from dataclasses import dataclass, field


# Stable UUIDs for builtins (deterministic, never change).
PROFESSIONAL_ID = "00000000-0000-4000-a000-000000000001"
FRIENDLY_ID = "00000000-0000-4000-a000-000000000002"
MILITARY_ID = "00000000-0000-4000-a000-000000000003"

BUILTIN_NAMES = frozenset({"professional", "friendly", "military"})


@dataclass(frozen=True)
class PresetPersona:
    """Immutable in-memory persona preset."""

    id: str
    name: str
    personality: str
    language_style: str
    background: str
    rules: list[str] = field(default_factory=list)
    voice_config: dict | None = None
    temperature_bias: float | None = None
    max_response_length: int | None = None
    is_builtin: bool = True


_PROFESSIONAL = PresetPersona(
    id=PROFESSIONAL_ID,
    name="Professional",
    personality="Expert assistant focused on clarity and efficiency",
    language_style="formal, concise, structured",
    background="Productivity-oriented AI assistant",
    rules=[
        "Use bullet points for lists",
        "Cite sources when available",
        "Avoid colloquialisms",
    ],
    temperature_bias=0.0,
)

_FRIENDLY = PresetPersona(
    id=FRIENDLY_ID,
    name="Friendly",
    personality="Warm conversational companion, encouraging and approachable",
    language_style="casual, warm, uses analogies",
    background="Approachable AI companion for everyday conversations",
    rules=[
        "Match the user's energy level",
        "Use simple language",
        "Encourage questions",
    ],
    temperature_bias=0.2,
)

_MILITARY = PresetPersona(
    id=MILITARY_ID,
    name="Military",
    personality="Direct, mission-focused tactical advisor",
    language_style="terse, action-oriented, uses military terminology",
    background="Tactical advisor with military communication style",
    rules=[
        "Lead with the bottom line",
        "Use short sentences",
        "No hedging or filler",
    ],
    temperature_bias=-0.3,
)

PRESETS: dict[str, PresetPersona] = {
    "professional": _PROFESSIONAL,
    "friendly": _FRIENDLY,
    "military": _MILITARY,
}

_PRESETS_BY_ID: dict[str, PresetPersona] = {
    p.id: p for p in PRESETS.values()
}


def get_preset(name: str) -> PresetPersona | None:
    """Get a preset by lowercase name."""
    return PRESETS.get(name.lower())


def get_preset_by_id(preset_id: str) -> PresetPersona | None:
    """Get a preset by its stable UUID."""
    return _PRESETS_BY_ID.get(preset_id)
