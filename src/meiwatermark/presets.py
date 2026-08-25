from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path

from PySide6.QtCore import QStandardPaths

from .model import Anchor, ExportSettings, LayerKind, ResizeMode, Unit, WatermarkLayer


def _directory() -> Path:
    base = os.environ.get("LOCALAPPDATA") or QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation)
    return Path(base) / "MeiWatermark"


def preset_directory() -> Path:
    directory = _directory()
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _read(path: Path) -> dict[str, object]:
    try:
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _path(name: str) -> Path:
    if not name or any(character in '<>:"/\\|?*' for character in name):
        raise ValueError("invalid preset name")
    return preset_directory() / f"{name}.json"


def load_presets() -> dict[str, tuple[list[WatermarkLayer], ExportSettings]]:
    result: dict[str, tuple[list[WatermarkLayer], ExportSettings]] = {}
    for path in preset_directory().glob("*.json"):
        values = _read(path)
        if not isinstance(values, dict) or not isinstance(values.get("layers"), list) or not isinstance(values.get("export"), dict):
            continue
        try:
            layers = [WatermarkLayer(**{**item, "kind": LayerKind(item["kind"]), "size_unit": Unit(item["size_unit"]), "horizontal_unit": Unit(item["horizontal_unit"]), "vertical_unit": Unit(item["vertical_unit"]), "anchor": Anchor(item["anchor"])}) for item in values["layers"]]
            settings = ExportSettings(**{**values["export"], "resize_mode": ResizeMode(values["export"]["resize_mode"])})
            if settings.format not in {"JPEG", "PNG", "WEBP"}:
                continue
            result[path.stem] = layers, settings
        except (KeyError, TypeError, ValueError):
            continue
    return result


def save_preset(name: str, layers: list[WatermarkLayer], settings: ExportSettings) -> None:
    _path(name).write_text(json.dumps({"layers": [asdict(layer) for layer in layers], "export": asdict(settings)}, ensure_ascii=False, indent=2), encoding="utf-8")


def preset_exists(name: str) -> bool:
    return _path(name).is_file()
