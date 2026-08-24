from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from uuid import uuid4


class LayerKind(StrEnum):
    IMAGE = "image"
    TEXT = "text"


class Unit(StrEnum):
    PERCENT = "percent"
    PIXELS = "pixels"
    VISUAL = "visual"


class Anchor(StrEnum):
    TOP_LEFT = "top_left"
    TOP = "top"
    TOP_RIGHT = "top_right"
    LEFT = "left"
    CENTER = "center"
    RIGHT = "right"
    BOTTOM_LEFT = "bottom_left"
    BOTTOM = "bottom"
    BOTTOM_RIGHT = "bottom_right"


class ResizeMode(StrEnum):
    NONE = "none"
    LONG_EDGE = "long_edge"
    SHORT_EDGE = "short_edge"
    SCALE = "scale"


@dataclass(slots=True)
class WatermarkLayer:
    kind: LayerKind
    name: str
    id: str = field(default_factory=lambda: uuid4().hex)
    visible: bool = True
    opacity: int = 80
    size: float = 20
    size_unit: Unit = Unit.PERCENT
    horizontal_inset: float = 4
    horizontal_unit: Unit = Unit.VISUAL
    vertical_inset: float = 4
    vertical_unit: Unit = Unit.VISUAL
    anchor: Anchor = Anchor.BOTTOM_RIGHT
    rotation: float = 0
    image_path: str | None = None
    text: str = "© 2025"
    font_path: str | None = None
    color: tuple[int, int, int] = (255, 255, 255)
    stroke_color: tuple[int, int, int] = (0, 0, 0)


@dataclass(slots=True)
class ExportSettings:
    format: str = "JPEG"
    quality: int = 100
    resize_mode: ResizeMode = ResizeMode.NONE
    resize_value: float = 0
    allow_upscale: bool = False
    keep_exif: bool = True
    keep_icc: bool = True
    suffix: str = "_watermarked"
    output_path: str = ""


def default_font_path() -> str | None:
    for candidate in (
        Path("C:/Windows/Fonts/msyh.ttc"),
        Path("C:/Windows/Fonts/arial.ttf"),
    ):
        if candidate.exists():
            return str(candidate)
    return None
