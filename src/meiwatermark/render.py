from __future__ import annotations

from dataclasses import dataclass, replace
from functools import lru_cache
from io import BytesIO
import json
import os
from pathlib import Path

from fontTools.ttLib import TTCollection, TTFont, TTLibError
from fontTools.ttLib.tables import _f_v_a_r, _n_a_m_e
from PIL import Image, ImageDraw, ImageFont, ImageOps

from .model import Anchor, ExportSettings, LayerKind, ResizeMode, Unit, WatermarkLayer, default_font_path

MAX_STAMP_SIZE = 4096
MAX_TILE_COUNT = 4096


class RenderLimitError(ValueError):
    pass


@dataclass(slots=True)
class ImageSource:
    image: Image.Image
    exif: bytes | None
    icc_profile: bytes | None
    original_size: tuple[int, int]


@dataclass(frozen=True, slots=True)
class FontChoice:
    family: str
    style: str
    path: str
    index: int = 0
    variation: tuple[float, ...] = ()


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
        normalized = ImageOps.exif_transpose(opened)
        normalized.thumbnail(max_size, Image.Resampling.LANCZOS)
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


def scaled_layers(layers: list[WatermarkLayer], scale: float) -> list[WatermarkLayer]:
    return [
        replace(
            layer,
            size=layer.size * scale if layer.size_unit is Unit.PIXELS else layer.size,
            horizontal_inset=layer.horizontal_inset * scale if layer.horizontal_unit is Unit.PIXELS else layer.horizontal_inset,
            vertical_inset=layer.vertical_inset * scale if layer.vertical_unit is Unit.PIXELS else layer.vertical_inset,
        )
        for layer in layers
    ]


def _font(layer: WatermarkLayer, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in (layer.font_path, default_font_path()):
        if path:
            try:
                font = ImageFont.truetype(path, size, index=layer.font_index if path == layer.font_path else 0)
                if path == layer.font_path and layer.font_variation:
                    font.set_variation_by_axes(layer.font_variation)
                return font
            except (OSError, ValueError):
                pass
    return ImageFont.load_default()


_FONT_EXTENSIONS = {".ttf", ".otf", ".ttc", ".otc"}
_FONT_LANGUAGES = {
    "zh": (0x804, 0x411, 0x412, 0x409),
    "ja": (0x411, 0x804, 0x412, 0x409),
    "en": (0x804, 0x411, 0x412, 0x409),
    "es": (0x804, 0x411, 0x412, 0x40A, 0x409),
}


def _font_sources() -> list[Path]:
    system_directory = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    user_directory = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft/Windows/Fonts"
    paths = {
        path.resolve()
        for directory in (system_directory, user_directory)
        if directory.is_dir()
        for path in directory.iterdir()
        if path.suffix.lower() in _FONT_EXTENSIONS
    }
    try:
        import winreg

        for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            try:
                with winreg.OpenKey(root, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts") as key:
                    index = 0
                    while True:
                        try:
                            _, filename, _ = winreg.EnumValue(key, index)
                        except OSError:
                            break
                        index += 1
                        path = Path(str(filename))
                        candidates = (path,) if path.is_absolute() else (system_directory / path, user_directory / path)
                        paths.update(candidate.resolve() for candidate in candidates if candidate.is_file() and candidate.suffix.lower() in _FONT_EXTENSIONS)
            except OSError:
                continue
    except (ImportError, OSError):
        pass
    return sorted(paths, key=lambda path: path.name.casefold())


def _font_cache_path() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", ".")) / "MeiWatermark" / "cache" / "fonts.json"


def _font_name(table, name_ids: tuple[int, ...], language: str) -> str:  # type: ignore[no-untyped-def]
    for name_id in name_ids:
        for locale in _FONT_LANGUAGES[language]:
            record = table.getName(name_id, 3, 1, locale)
            if record:
                return record.toUnicode()
        for record in table.names:
            if record.nameID == name_id:
                try:
                    return record.toUnicode()
                except UnicodeError:
                    continue
    return ""


def _names(table, style_id: int | None = None) -> tuple[dict[str, str], dict[str, str]]:  # type: ignore[no-untyped-def]
    families: dict[str, str] = {}
    styles: dict[str, str] = {}
    for language in _FONT_LANGUAGES:
        families[language] = _font_name(table, (16, 1), language) or "Unknown font"
        styles[language] = _font_name(table, (style_id,) if style_id else (17, 2), language) or "Regular"
    return families, styles


def _font_entries(path: Path) -> list[dict[str, object]]:
    collection = None
    fonts = []
    try:
        with path.open("rb") as file:
            if file.read(4) not in {b"\x00\x01\x00\x00", b"OTTO", b"true", b"ttcf"}:
                return []
        collection = TTCollection(path, lazy=True) if path.suffix.lower() in {".ttc", ".otc"} else None
        fonts = collection.fonts if collection else [TTFont(path, lazy=True)]
        entries: list[dict[str, object]] = []
        for index, font in enumerate(fonts):
            table = font["name"]
            if "fvar" not in font or not font["fvar"].instances:
                families, styles = _names(table)
                entries.append({"path": str(path), "index": index, "variation": [], "families": families, "styles": styles})
            else:
                axes = font["fvar"].axes
                for instance in font["fvar"].instances:
                    families, styles = _names(table, instance.subfamilyNameID)
                    entries.append({"path": str(path), "index": index, "variation": [float(instance.coordinates.get(axis.axisTag, axis.defaultValue)) for axis in axes], "families": families, "styles": styles})
        return entries
    except (OSError, KeyError, TTLibError, ValueError):
        return []
    finally:
        if collection:
            collection.close()
        else:
            for font in fonts:
                font.close()


@lru_cache(maxsize=4)
def system_fonts(language: str) -> list[FontChoice]:
    sources = _font_sources()
    fingerprint = [[str(path), path.stat().st_mtime_ns, path.stat().st_size] for path in sources]
    cache_path = _font_cache_path()
    try:
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        cached = {}
    entries = cached.get("fonts") if cached.get("version") == 2 and cached.get("sources") == fingerprint else None
    if not isinstance(entries, list):
        entries = [entry for path in sources for entry in _font_entries(path)]
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps({"version": 2, "sources": fingerprint, "fonts": entries}, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass
    choices = [FontChoice(str(entry["families"].get(language, entry["families"].get("zh", "Unknown font"))), str(entry["styles"].get(language, entry["styles"].get("zh", "Regular"))), str(entry["path"]), int(entry.get("index", 0)), tuple(float(value) for value in entry.get("variation", []))) for entry in entries if isinstance(entry, dict) and isinstance(entry.get("families"), dict) and isinstance(entry.get("styles"), dict) and entry.get("path")]
    return sorted(choices, key=lambda choice: (not any(ord(character) > 127 for character in choice.family), choice.family.casefold(), choice.style.casefold()))


def _text_stamp(layer: WatermarkLayer, target_size: int) -> Image.Image:
    stroke_width = layer.stroke_width if layer.stroke_color else 0

    def stamp_at(font_size: int) -> Image.Image:
        font = _font(layer, font_size)
        probe = Image.new("RGBA", (1, 1))
        box = ImageDraw.Draw(probe).textbbox((0, 0), layer.text, font=font, stroke_width=stroke_width)
        width, height = max(1, box[2] - box[0]), max(1, box[3] - box[1])
        padding = stroke_width + 2
        stamp = Image.new("RGBA", (width + padding * 2, height + padding * 2))
        if layer.color or layer.stroke_color:
            ImageDraw.Draw(stamp).text((padding - box[0], padding - box[1]), layer.text, font=font, fill=(*layer.color, 255) if layer.color else None, stroke_width=stroke_width, stroke_fill=(*layer.stroke_color, 255) if layer.stroke_color else None)
        return stamp

    sample_size = 100
    sample = stamp_at(sample_size)
    bounds = sample.getchannel("A").getbbox()
    if not bounds:
        return sample
    font_size = max(1, round(sample_size * target_size / max(bounds[2] - bounds[0], bounds[3] - bounds[1])))
    stamp = stamp_at(font_size)
    bounds = stamp.getchannel("A").getbbox()
    if bounds:
        stamp = stamp.crop(bounds)
        actual_size = max(stamp.size)
        if actual_size != target_size:
            scale = target_size / actual_size
            stamp = stamp.resize((max(1, round(stamp.width * scale)), max(1, round(stamp.height * scale))), Image.Resampling.LANCZOS)
        padded = Image.new("RGBA", (stamp.width + 4, stamp.height + 4))
        padded.alpha_composite(stamp, (2, 2))
        return padded
    return stamp


@lru_cache(maxsize=8)
def _resized_watermark(path: str, modified: int, file_size: int, target_size: int) -> Image.Image:
    with Image.open(path) as opened:
        stamp = ImageOps.exif_transpose(opened).convert("RGBA")
    scale = target_size / max(stamp.width, stamp.height)
    return stamp.resize((max(1, round(stamp.width * scale)), max(1, round(stamp.height * scale))), Image.Resampling.LANCZOS)


def _image_stamp(layer: WatermarkLayer, target_size: int) -> Image.Image | None:
    path = Path(layer.image_path or "")
    if not layer.image_path or not path.is_file():
        return None
    path = path.resolve()
    stat = path.stat()
    return _resized_watermark(str(path), stat.st_mtime_ns, stat.st_size, target_size)


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


def _tile_count(result: Image.Image, stamp: Image.Image, layer: WatermarkLayer) -> int:
    gap = max(0, round(min(result.size) * layer.tile_gap / 100))
    step_x, step_y = max(1, stamp.width + gap), max(1, stamp.height + gap)
    rows = len(range(-step_y, result.height + step_y, step_y))
    even_columns = len(range(-step_x, result.width + step_x, step_x))
    odd_columns = len(range(-step_x + step_x // 2, result.width + step_x, step_x)) if layer.tile_stagger else even_columns
    return (rows + 1) // 2 * even_columns + rows // 2 * odd_columns


def _tile(result: Image.Image, stamp: Image.Image, layer: WatermarkLayer) -> None:
    if _tile_count(result, stamp, layer) > MAX_TILE_COUNT:
        raise RenderLimitError(f"tiled watermark exceeds {MAX_TILE_COUNT} stamps")
    gap = max(0, round(min(result.size) * layer.tile_gap / 100))
    step_x, step_y = max(1, stamp.width + gap), max(1, stamp.height + gap)
    for row, y in enumerate(range(-step_y, result.height + step_y, step_y)):
        offset = step_x // 2 if layer.tile_stagger and row % 2 else 0
        for x in range(-step_x + offset, result.width + step_x, step_x):
            result.alpha_composite(stamp, (x, y))


def render(base: Image.Image, layers: list[WatermarkLayer]) -> Image.Image:
    result = base.copy() if base.mode == "RGBA" else base.convert("RGBA")
    # The first layer in the UI is visually the topmost layer.
    for layer in reversed(layers):
        if not layer.visible:
            continue
        size = _size_pixels(layer, *result.size)
        if size > MAX_STAMP_SIZE:
            if layer.size_unit is Unit.PIXELS:
                size = MAX_STAMP_SIZE
            else:
                raise RenderLimitError(f"watermark size exceeds {MAX_STAMP_SIZE} px")
        stamp = _image_stamp(layer, size) if layer.kind is LayerKind.IMAGE else _text_stamp(layer, size)
        if stamp is None:
            continue
        stamp = _trim_transparent(_apply_opacity(stamp, layer.opacity))
        if layer.rotation:
            stamp = _trim_transparent(stamp.rotate(-layer.rotation, expand=True, resample=Image.Resampling.BICUBIC))
        if layer.tiled:
            _tile(result, stamp, layer)
            continue
        position = _position(layer, result.size, stamp.size)
        result.alpha_composite(stamp, position)
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


def _flatten_rgba(image: Image.Image) -> Image.Image:
    if "A" not in image.getbands():
        return image.convert("RGB")
    background = Image.new("RGB", image.size, (255, 255, 255))
    background.paste(image, mask=image.getchannel("A"))
    return background


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
        _flatten_rgba(image).save(destination, fmt, **options)
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
        _flatten_rgba(preview).save(buffer, fmt, **options)
    elif fmt == "WEBP":
        options.update(quality=settings.quality, method=4)
        preview.save(buffer, fmt, **options)
    else:
        options["compress_level"] = round((100 - settings.quality) * 9 / 100)
        preview.save(buffer, "PNG", **options)
    return buffer.tell()
