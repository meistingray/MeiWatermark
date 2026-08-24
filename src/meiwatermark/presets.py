from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from PySide6.QtCore import QStandardPaths

from .model import Anchor, ExportSettings, LayerKind, ResizeMode, Unit, WatermarkLayer


def _directory() -> Path:
    return Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppConfigLocation))


def _read(name: str) -> dict[str, object]:
    path = _directory() / name
    try:
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _write(name: str, values: dict[str, object]) -> None:
    directory = _directory()
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_text(json.dumps(values, ensure_ascii=False, indent=2), encoding="utf-8")


def load_watermark_presets() -> dict[str, list[WatermarkLayer]]:
    loaded = _read("watermark-presets.json")
    result: dict[str, list[WatermarkLayer]] = {}
    for name, values in loaded.items():
        if not isinstance(values, list):
            continue
        try:
            result[name] = [
                WatermarkLayer(
                    **{
                        **item,
                        "kind": LayerKind(item["kind"]),
                        "size_unit": Unit(item["size_unit"]),
                        "horizontal_unit": Unit(item["horizontal_unit"]),
                        "vertical_unit": Unit(item["vertical_unit"]),
                        "anchor": Anchor(item["anchor"]),
                    }
                )
                for item in values
            ]
        except (KeyError, TypeError, ValueError):
            continue
    return result


def save_watermark_preset(name: str, layers: list[WatermarkLayer]) -> None:
    presets = _read("watermark-presets.json")
    presets[name] = [asdict(layer) for layer in layers]
    _write("watermark-presets.json", presets)


def load_export_presets() -> dict[str, ExportSettings]:
    loaded = _read("export-presets.json")
    result: dict[str, ExportSettings] = {}
    for name, values in loaded.items():
        if isinstance(values, dict):
            try:
                result[name] = ExportSettings(**{**values, "resize_mode": ResizeMode(values["resize_mode"])})
            except (KeyError, TypeError, ValueError):
                continue
    return result


def save_export_preset(name: str, settings: ExportSettings) -> None:
    presets = _read("export-presets.json")
    presets[name] = asdict(settings)
    _write("export-presets.json", presets)
