from __future__ import annotations

import re
from typing import Literal, Optional

from pydantic import BaseModel, Field, computed_field, field_validator, model_validator

Position = Literal["top-left", "top-center", "top-right", "bottom-left", "bottom-center", "bottom-right"]
AnimationStyle = Literal["slide-left", "slide-right", "slide-up", "slide-down", "fade", "none"]
TriggerPositionMode = Literal["off", "elapsed", "remaining"]
Theme = Literal["classic-cable", "broadcast-1980s", "cable-1990s", "digital-cable-2000s", "retro-local", "saturday-morning", "movie-channel", "sports-info", "modern-minimal"]


class Appearance(BaseModel):
    theme: Theme = "classic-cable"
    position: Position = "bottom-left"
    width_percent: float = Field(62.0, ge=20.0, le=95.0)
    opacity: float = Field(0.92, ge=0.0, le=1.0)
    # Legacy shared text size retained for v0.1.0 compatibility.
    # New Styles persist explicit per-element values below.
    font_size: int = Field(28, ge=8, le=96)
    channel_font_size: int = Field(12, ge=8, le=96)
    now_font_size: int = Field(28, ge=8, le=96)
    next_font_size: int = Field(17, ge=8, le=96)
    accent: str = "#F5C242"
    animation_style: Optional[AnimationStyle] = None
    entrance_animation_style: AnimationStyle = "slide-left"
    entrance_duration_seconds: float = Field(0.45, ge=0.0, le=10.0)
    exit_animation_style: AnimationStyle = "none"
    exit_duration_seconds: float = Field(0.35, ge=0.0, le=10.0)
    show_now: bool = True
    show_next: bool = True
    show_channel_label: bool = True
    channel_label_text: Optional[str] = Field(
        default=None,
        max_length=160,
    )

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_appearance(cls, value):
        if isinstance(value, dict):
            value = dict(value)

            if (
                "entrance_animation_style" not in value
                and value.get("animation_style")
            ):
                value["entrance_animation_style"] = value[
                    "animation_style"
                ]

            # Styles saved before per-element typography used one
            # preferred NOW size. Channel and NEXT sizes were derived
            # by the renderer. Materialize those historical effective
            # values when the new fields are absent.
            legacy = int(value.get("font_size", 28))

            value.setdefault(
                "channel_font_size",
                max(11, int(legacy * 0.46)),
            )

            value.setdefault(
                "now_font_size",
                legacy,
            )

            value.setdefault(
                "next_font_size",
                max(12, int(legacy * 0.62)),
            )

        return value

    @field_validator("channel_label_text")
    @classmethod
    def normalize_channel_label_text(
        cls,
        value: Optional[str],
    ) -> Optional[str]:
        if value is None:
            return None

        value = value.strip()
        return value or None

    @field_validator("accent")
    @classmethod
    def validate_accent(cls, value: str) -> str:
        value = value.strip().upper()
        if len(value) != 7 or not value.startswith("#"):
            raise ValueError("accent must be #RRGGBB")
        int(value[1:], 16)
        return value


class Eligibility(BaseModel):
    start_seconds: float = Field(0.0, ge=0.0, le=86400.0)
    duration_seconds: float = Field(21600.0, gt=0.0, le=604800.0)


class TriggerPolicy(BaseModel):
    show_on_tune: bool = True
    tune_delay_seconds: float = Field(2.0, ge=0.0, le=30.0)
    show_on_program_change: bool = False
    position_mode: TriggerPositionMode = "off"
    position_percent: float = Field(50.0, ge=1.0, le=99.0)


def _animation_label(value: AnimationStyle) -> str:
    return {"slide-left": "Slide Left", "slide-right": "Slide Right", "slide-up": "Slide Up", "slide-down": "Slide Down", "fade": "Fade", "none": "Static"}[value]


def _number_label(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else f"{value:g}"


def style_description(appearance: Appearance, trigger: TriggerPolicy) -> str:
    actions: list[str] = []
    if trigger.show_on_tune:
        actions.append("Tune")
    if trigger.show_on_program_change:
        actions.append("Change")
    if trigger.position_mode != "off":
        mode = "Position" if trigger.position_mode == "elapsed" else "Remaining"
        actions.append(f"{mode} {_number_label(trigger.position_percent)}%")
    if not actions:
        actions.append("No Trigger")
    return f"{_animation_label(appearance.entrance_animation_style)} · {' + '.join(actions)}"


def style_slug(value: str) -> str:
    value = value.strip().lower().replace("·", " ")
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return value or "style"


class StylePut(BaseModel):
    name: Optional[str] = Field(default=None, max_length=160)
    overlay_display_seconds: float = Field(7.0, gt=0.0, le=120.0)
    eligibility: Eligibility = Field(default_factory=Eligibility)
    trigger_policy: TriggerPolicy = Field(default_factory=TriggerPolicy)
    appearance: Appearance = Field(default_factory=Appearance)
    z_index: int = Field(20, ge=-10000, le=10000)
    manage_ersatztv_yaml: bool = True

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @computed_field
    @property
    def generated_description(self) -> str:
        return style_description(self.appearance, self.trigger_policy)

    @computed_field
    @property
    def display_name(self) -> str:
        return self.name or self.generated_description

    @property
    def generated_slug(self) -> str:
        return style_slug(self.name or self.generated_description)


class Style(StylePut):
    id: int
    slug: str
    yaml_path: Optional[str] = None
    created_at: str
    updated_at: str


class UserTemplatePut(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: Optional[str] = Field(
        default=None,
        max_length=1000,
    )
    source_kind: Optional[Literal["builtin", "user"]] = None
    source_template_id: Optional[str] = Field(
        default=None,
        max_length=160,
    )
    source_template_name: Optional[str] = Field(
        default=None,
        max_length=160,
    )
    style: StylePut

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("name must not be blank")
        return value

    @field_validator(
        "description",
        "source_template_id",
        "source_template_name",
    )
    @classmethod
    def normalize_user_template_text(
        cls,
        value,
    ):
        if value is None:
            return None

        value = value.strip()

        if not value:
            return None

        return value


class UserTemplate(UserTemplatePut):
    id: int
    slug: str
    builtin: bool = False
    created_at: str
    updated_at: str


class ChannelPut(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    enabled: bool = True


class Channel(ChannelPut):
    id: str
    style_ids: list[int] = Field(default_factory=list)
    created_at: str
    updated_at: str


class StyleAssignment(BaseModel):
    style_id: int
    channel_id: str
    created_at: str


class RenderRequest(BaseModel):
    style_id: int
    channel_id: str = ""
    channel_name: Optional[str] = None
    context: dict


class NormalizedContext(BaseModel):
    channel_id: str
    channel_name: str
    current_show: str = ""
    current_subtitle: str = ""
    current_title: str = ""
    next_show: str = ""
    next_subtitle: str = ""
    next_title: str = ""
    session_key: str = ""
    program_key: str = ""
    media_path: str = ""
    elapsed_seconds: Optional[float] = None
    duration_seconds: Optional[float] = None
    elapsed_percent: Optional[float] = None
    remaining_percent: Optional[float] = None
    width: int
    height: int
    fps: float
