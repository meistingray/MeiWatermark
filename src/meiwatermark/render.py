from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from struct import unpack

from PIL import Image, ImageDraw, ImageFont, ImageOps

from .model import Anchor, ExportSettings, LayerKind, ResizeMode, Unit, WatermarkLayer, default_font_path


@dataclass(slots=True)
class ImageSource:
    image: Image.Image
    exif: bytes | None
    icc_profile: bytes | None
    original_size: tuple[int, int]


def load_image(path: str | Path) -> ImageSource:
    with Image.open(path) as opened:
        normalized = ImageOps.exif_transpose(opened)
        exif = normalized.getexif().tobytes() or None
        image = normalized.convert("RGBA")
        return ImageSource(image, exif, opened.info.get("icc_profile"), image.size)


def load_preview(path: str | Path, max_size: tuple[int, int]) -> ImageSource:
    with Image.open(path) as opened:
        orientation = opened.getexif().get(274)
        original_size = (opened.height, opened.width) if orientation in (5, 6, 7, 8) else opened.size
        opened.draft("RGB", max_size)
        opened.thumbnail(max_size, Image.Resampling.LANCZOS)
        normalized = ImageOps.exif_transpose(opened)
        exif = normalized.getexif().tobytes() or None
        return ImageSource(normalized.convert("RGBA"), exif, opened.info.get("icc_profile"), original_size)


def load_thumbnail(path: str | Path, max_size: tuple[int, int]) -> Image.Image:
    return load_preview(path, max_size).image


def _unit_pixels(value: float, unit: Unit, width: int, height: int, axis: str) -> int:
    if unit is Unit.PIXELS:
        return round(value)
    if unit is Unit.VISUAL:
        return round(min(width, height) * value / 100)
    return round((width if axis == "x" else height) * value / 100)


def _size_pixels(layer: WatermarkLayer, width: int, height: int) -> int:
    if layer.size_unit is Unit.PIXELS:
        return max(1, round(layer.size))
    return max(1, round(min(width, height) * layer.size / 100))


def _font(layer: WatermarkLayer, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in (layer.font_path, default_font_path()):
        if path:
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                pass
    return ImageFont.load_default()


@lru_cache(maxsize=1)
def system_fonts() -> dict[str, str]:
    fonts: dict[str, str] = {}
    directory = Path("C:/Windows/Fonts")
    for path in [*directory.glob("*.ttf"), *directory.glob("*.otf"), *directory.glob("*.ttc")]:
        try:
            name = _font_name(path)
            fonts.setdefault(name, str(path))
        except OSError:
            continue
    return dict(sorted(fonts.items()))


def _font_name(path: Path) -> str:
    fallback = ImageFont.truetype(path, 12).getname()[0]
    try:
        with path.open("rb") as file:
            if file.read(4) == b"ttcf":
                file.read(4)
                offset = unpack(">I", file.read(4))[0]
                start = unpack(">I", file.read(4))[0] if offset else 0
            else:
                start = 0
            file.seek(start + 4)
            table_count = unpack(">H", file.read(2))[0]
            file.seek(6, 1)
            name_offset = name_length = 0
            for _ in range(table_count):
                tag, _, offset, length = unpack(">4sIII", file.read(16))
                if tag == b"name":
                    name_offset, name_length = offset, length
            if not name_offset:
                return fallback
            file.seek(name_offset + 2)
            count, strings_offset = unpack(">HH", file.read(4))
            records = [unpack(">HHHHHH", file.read(12)) for _ in range(count)]
            names: list[str] = []
            for platform, encoding, _, name_id, length, offset in records:
                if name_id != 1 or platform != 3 or encoding not in (1, 10):
                    continue
                file.seek(name_offset + strings_offset + offset)
                raw = file.read(length)
                names.append(raw.decode("utf-16-be", errors="ignore"))
            return next((name for name in names if any(ord(char) > 127 for char in name)), names[0] if names else fallback)
    except (OSError, UnicodeError, ValueError):
        return fallback


def _text_stamp(layer: WatermarkLayer, target_size: int) -> Image.Image:
    font = _font(layer, target_size)
    probe = Image.new("RGBA", (1, 1))
    stroke_width = layer.stroke_width if layer.stroke_color else 0
    box = ImageDraw.Draw(probe).textbbox((0, 0), layer.text, font=font, stroke_width=stroke_width)
    width, height = max(1, box[2] - box[0]), max(1, box[3] - box[1])
    padding = stroke_width + 2
    stamp = Image.new("RGBA", (width + padding * 2, height + padding * 2))
    draw = ImageDraw.Draw(stamp)
    if layer.color or layer.stroke_color:
        draw.text((padding - box[0], padding - box[1]), layer.text, font=font, fill=(*layer.color, 255) if layer.color else None, stroke_width=stroke_width, stroke_fill=(*layer.stroke_color, 255) if layer.stroke_color else None)
    return stamp


@lru_cache(maxsize=16)
def _watermark_image(path: str) -> Image.Image:
    with Image.open(path) as opened:
        return ImageOps.exif_transpose(opened).convert("RGBA")


def _image_stamp(layer: WatermarkLayer, target_size: int) -> Image.Image | None:
    if not layer.image_path or not Path(layer.image_path).is_file():
        return None
    stamp = _watermark_image(layer.image_path)
    scale = target_size / max(stamp.width, stamp.height)
    return stamp.resize((max(1, round(stamp.width * scale)), max(1, round(stamp.height * scale))), Image.Resampling.LANCZOS)


def _apply_opacity(stamp: Image.Image, opacity: int) -> Image.Image:
    if opacity >= 100:
        return stamp
    stamp = stamp.copy()
    alpha = stamp.getchannel("A").point(lambda value: value * max(0, opacity) // 100)
    stamp.putalpha(alpha)
    return stamp


def _trim_transparent(stamp: Image.Image) -> Image.Image:
    bounds = stamp.getchannel("A").point(lambda alpha: 255 if alpha > 4 else 0).getbbox()
    return stamp.crop(bounds) if bounds else stamp


def _position(layer: WatermarkLayer, base_size: tuple[int, int], stamp_size: tuple[int, int]) -> tuple[int, int]:
    width, height = base_size
    stamp_w, stamp_h = stamp_size
    inset_x = _unit_pixels(layer.horizontal_inset, layer.horizontal_unit, width, height, "x")
    inset_y = _unit_pixels(layer.vertical_inset, layer.vertical_unit, width, height, "y")
    horizontal = {Anchor.TOP_LEFT, Anchor.LEFT, Anchor.BOTTOM_LEFT}
    right = {Anchor.TOP_RIGHT, Anchor.RIGHT, Anchor.BOTTOM_RIGHT}
    top = {Anchor.TOP_LEFT, Anchor.TOP, Anchor.TOP_RIGHT}
    bottom = {Anchor.BOTTOM_LEFT, Anchor.BOTTOM, Anchor.BOTTOM_RIGHT}
    x = inset_x if layer.anchor in horizontal else width - stamp_w - inset_x if layer.anchor in right else (width - stamp_w) // 2
    y = inset_y if layer.anchor in top else height - stamp_h - inset_y if layer.anchor in bottom else (height - stamp_h) // 2
    return x, y


def render(base: Image.Image, layers: list[WatermarkLayer]) -> Image.Image:
    result = base.convert("RGBA").copy()
    # The first layer in the UI is visually the topmost layer.
    for layer in reversed(layers):
        if not layer.visible:
            continue
        size = _size_pixels(layer, *result.size)
        stamp = _image_stamp(layer, size) if layer.kind is LayerKind.IMAGE else _text_stamp(layer, size)
        if stamp is None:
            continue
        stamp = _trim_transparent(_apply_opacity(stamp, layer.opacity))
        if layer.rotation:
            stamp = _trim_transparent(stamp.rotate(-layer.rotation, expand=True, resample=Image.Resampling.BICUBIC))
        position = _position(layer, result.size, stamp.size)
        if 0 <= position[0] <= result.width - stamp.width and 0 <= position[1] <= result.height - stamp.height:
            result.alpha_composite(stamp, position)
        else:
            result.paste(stamp, position, stamp)
    return result


def export_size(size: tuple[int, int], settings: ExportSettings) -> tuple[int, int]:
    if settings.resize_mode is ResizeMode.NONE or settings.resize_value <= 0:
        return size
    width, height = size
    reference = max(width, height) if settings.resize_mode is ResizeMode.LONG_EDGE else min(width, height)
    scale = settings.resize_value / 100 if settings.resize_mode is ResizeMode.SCALE else settings.resize_value / reference
    if not settings.allow_upscale:
        scale = min(scale, 1)
    return max(1, round(width * scale)), max(1, round(height * scale))


def resize_for_export(image: Image.Image, settings: ExportSettings) -> Image.Image:
    target_size = export_size(image.size, settings)
    if target_size == image.size:
        return image
    return image.resize(target_size, Image.Resampling.LANCZOS)


def save_image(image: Image.Image, destination: str | Path, settings: ExportSettings, source: ImageSource | None = None) -> None:
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fmt = settings.format.upper()
    options: dict[str, object] = {}
    if source and settings.keep_exif and source.exif:
        options["exif"] = source.exif
    if source and settings.keep_icc and source.icc_profile:
        options["icc_profile"] = source.icc_profile
    if fmt == "JPEG":
        options.update(quality=settings.quality, optimize=True, progressive=True, subsampling="4:2:0")
        image.convert("RGB").save(destination, fmt, **options)
    elif fmt == "WEBP":
        options.update(quality=settings.quality, method=4)
        image.save(destination, fmt, **options)
    else:
        options["compress_level"] = round((100 - settings.quality) * 9 / 100)
        image.save(destination, "PNG", **options)


def estimate_size(image: Image.Image, settings: ExportSettings, source: ImageSource | None = None) -> int:
    buffer = BytesIO()
    preview = resize_for_export(image, settings)
    fmt = settings.format.upper()
    options: dict[str, object] = {}
    if source and settings.keep_exif and source.exif:
        options["exif"] = source.exif
    if source and settings.keep_icc and source.icc_profile:
        options["icc_profile"] = source.icc_profile
    if fmt == "JPEG":
        options.update(quality=settings.quality, optimize=True, progressive=True, subsampling="4:2:0")
        preview.convert("RGB").save(buffer, fmt, **options)
    elif fmt == "WEBP":
        options.update(quality=settings.quality, method=4)
        preview.save(buffer, fmt, **options)
    else:
        options["compress_level"] = round((100 - settings.quality) * 9 / 100)
        preview.save(buffer, "PNG", **options)
    return buffer.tell()
