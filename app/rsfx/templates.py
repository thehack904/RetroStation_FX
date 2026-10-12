from __future__ import annotations

from copy import deepcopy

from .models import Appearance, Eligibility, StylePut, TriggerPolicy
from .compositions import get_composition

# Built-in templates are immutable product content. They are intentionally
# separate from the user's Style table: merely installing or browsing a
# template must never create ErsatzTV Script Graphics YAML.
BUILTIN_TEMPLATES = [
    {
        "id": "classic-cable",
        "family": "Classic cable/satellite",
        "name": "Classic Cable Lower Third",
        "description": "A restrained cable/satellite lower third with a strong channel accent and clear NOW/NEXT hierarchy.",
        "style": StylePut(
            overlay_display_seconds=7.0,
            trigger_policy=TriggerPolicy(show_on_tune=True, show_on_program_change=True),
            appearance=Appearance(theme="classic-cable", position="bottom-left", width_percent=64, opacity=0.94, font_size=28, channel_font_size=12, now_font_size=28, next_font_size=17, accent="#F5C242", entrance_animation_style="slide-left", entrance_duration_seconds=0.45, exit_animation_style="fade", exit_duration_seconds=0.3),
        ),
    },
    {
        "id": "broadcast-1980s",
        "family": "1980s broadcast",
        "name": "1980s Broadcast",
        "description": "Bold geometric bars and hard-edged presentation inspired by character-generator-era television graphics.",
        "style": StylePut(
            overlay_display_seconds=6.0,
            trigger_policy=TriggerPolicy(show_on_tune=True, show_on_program_change=False),
            appearance=Appearance(theme="broadcast-1980s", position="bottom-left", width_percent=70, opacity=1.0, font_size=30, channel_font_size=13, now_font_size=30, next_font_size=18, accent="#32D6FF", entrance_animation_style="slide-right", entrance_duration_seconds=0.32, exit_animation_style="slide-left", exit_duration_seconds=0.28),
        ),
    },
    {
        "id": "cable-1990s",
        "family": "1990s cable",
        "name": "1990s Cable",
        "description": "Layered, energetic cable-network presentation with diagonal accents and a prominent NOW title.",
        "style": StylePut(
            overlay_display_seconds=7.0,
            trigger_policy=TriggerPolicy(show_on_tune=True, show_on_program_change=True),
            appearance=Appearance(theme="cable-1990s", position="bottom-left", width_percent=72, opacity=0.96, font_size=29, channel_font_size=13, now_font_size=29, next_font_size=17, accent="#FF4FA3", entrance_animation_style="slide-left", entrance_duration_seconds=0.38, exit_animation_style="slide-right", exit_duration_seconds=0.32),
        ),
    },
    {
        "id": "digital-cable-2000s",
        "family": "Early-2000s digital cable",
        "name": "Digital Cable 2000",
        "description": "A polished translucent digital-cable treatment with softer geometry and compact information hierarchy.",
        "style": StylePut(
            overlay_display_seconds=7.0,
            trigger_policy=TriggerPolicy(show_on_tune=True, show_on_program_change=True),
            appearance=Appearance(theme="digital-cable-2000s", position="bottom-center", width_percent=68, opacity=0.88, font_size=27, channel_font_size=12, now_font_size=27, next_font_size=16, accent="#4EA1FF", entrance_animation_style="slide-up", entrance_duration_seconds=0.5, exit_animation_style="fade", exit_duration_seconds=0.35),
        ),
    },
    {
        "id": "retro-local",
        "family": "Retro local station",
        "name": "Retro Local Station",
        "description": "A practical local-station lower third with a station-ID block and straightforward program information.",
        "style": StylePut(
            overlay_display_seconds=8.0,
            trigger_policy=TriggerPolicy(show_on_tune=True, show_on_program_change=True),
            appearance=Appearance(theme="retro-local", position="bottom-left", width_percent=66, opacity=0.95, font_size=27, channel_font_size=12, now_font_size=27, next_font_size=16, accent="#F04A3A", entrance_animation_style="slide-left", entrance_duration_seconds=0.4, exit_animation_style="none", exit_duration_seconds=0.0),
        ),
    },
    {
        "id": "saturday-morning",
        "family": "Cartoon / Saturday morning",
        "name": "Saturday Morning",
        "description": "Bright, playful cartoon-block presentation with offset shapes, punchy type, and quicker motion.",
        "style": StylePut(
            overlay_display_seconds=6.0,
            trigger_policy=TriggerPolicy(show_on_tune=True, show_on_program_change=True),
            appearance=Appearance(theme="saturday-morning", position="bottom-left", width_percent=70, opacity=0.96, font_size=30, channel_font_size=13, now_font_size=30, next_font_size=18, accent="#FFD43B", entrance_animation_style="slide-down", entrance_duration_seconds=0.35, exit_animation_style="slide-right", exit_duration_seconds=0.3),
        ),
    },
    {
        "id": "movie-channel",
        "family": "Movie channel",
        "name": "Movie Channel",
        "description": "A cinematic, restrained title treatment with generous spacing and quiet motion.",
        "style": StylePut(
            overlay_display_seconds=9.0,
            trigger_policy=TriggerPolicy(show_on_tune=True, show_on_program_change=False),
            appearance=Appearance(theme="movie-channel", position="bottom-center", width_percent=76, opacity=0.84, font_size=31, channel_font_size=14, now_font_size=31, next_font_size=19, accent="#D8B46A", entrance_animation_style="fade", entrance_duration_seconds=0.75, exit_animation_style="fade", exit_duration_seconds=0.6),
        ),
    },
    {
        "id": "sports-info",
        "family": "Sports",
        "name": "Sports Info Banner",
        "description": "A dense segmented sports-broadcast banner designed for fast recognition and compact NOW/NEXT information.",
        "style": StylePut(
            overlay_display_seconds=6.0,
            trigger_policy=TriggerPolicy(
                show_on_tune=True,
                show_on_program_change=True,
                position_mode="remaining",
                position_percent=25,
            ),
            appearance=Appearance(theme="sports-info", position="bottom-center", width_percent=84, opacity=0.98, font_size=25, channel_font_size=11, now_font_size=25, next_font_size=15, accent="#3DDC84", entrance_animation_style="slide-up", entrance_duration_seconds=0.28, exit_animation_style="slide-down", exit_duration_seconds=0.25),
        ),
    },
    {
        "id": "modern-minimal",
        "family": "Modern minimal",
        "name": "Modern Minimal",
        "description": "Flat, quiet contemporary presentation with minimal ornamentation and generous negative space.",
        "style": StylePut(
            overlay_display_seconds=6.5,
            trigger_policy=TriggerPolicy(show_on_tune=True, show_on_program_change=True),
            appearance=Appearance(theme="modern-minimal", position="bottom-left", width_percent=58, opacity=0.86, font_size=27, channel_font_size=12, now_font_size=27, next_font_size=16, accent="#FFFFFF", entrance_animation_style="fade", entrance_duration_seconds=0.42, exit_animation_style="fade", exit_duration_seconds=0.32),
        ),
    },
]


def list_templates() -> list[dict]:
    result = []
    for item in BUILTIN_TEMPLATES:
        style = deepcopy(item["style"])
        result.append(
            {
                "id": item["id"],
                "family": item["family"],
                "name": item["name"],
                "description": item["description"],
                "builtin": True,
                "style": style.model_dump(),
                "generated_description": style.generated_description,
                "composition": deepcopy(get_composition(style.appearance.theme)),
            }
        )
    return result


def get_template(template_id: str) -> dict | None:
    for item in list_templates():
        if item["id"] == template_id:
            return item
    return None
