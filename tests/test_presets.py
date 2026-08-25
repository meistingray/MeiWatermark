from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from meiwatermark.model import ExportSettings, LayerKind, ResizeMode, WatermarkLayer
from meiwatermark.presets import load_presets, preset_directory, preset_exists, save_preset


class PresetTests(unittest.TestCase):
    def test_combined_preset_stores_layers_and_export_settings(self) -> None:
        with TemporaryDirectory() as directory, patch.dict(os.environ, {"LOCALAPPDATA": directory}):
            export = ExportSettings(format="PNG", quality=92, resize_mode=ResizeMode.SCALE, resize_value=63, allow_upscale=True, keep_exif=False, keep_icc=False, output_path="/Mei")
            save_preset("test", [WatermarkLayer(LayerKind.TEXT, "全屏文字", text="MeiStingray", font_path="C:/Fonts/font.ttc", font_index=3, font_variation=[700], tiled=True, tile_gap=8, tile_stagger=False)], export)
            layers, settings = load_presets()["test"]
            self.assertEqual(layers[0].text, "MeiStingray")
            self.assertEqual((layers[0].font_path, layers[0].font_index, layers[0].font_variation), ("C:/Fonts/font.ttc", 3, [700]))
            self.assertEqual((layers[0].tiled, layers[0].tile_gap, layers[0].tile_stagger), (True, 8, False))
            self.assertEqual((settings.format, settings.quality), ("PNG", 92))
            self.assertEqual((settings.resize_mode, settings.resize_value), (ResizeMode.SCALE, 63))
            self.assertEqual((settings.allow_upscale, settings.keep_exif, settings.keep_icc, settings.output_path), (True, False, False, "/Mei"))
            self.assertTrue((Path(directory) / "MeiWatermark" / "test.json").is_file())

    def test_same_name_overwrites_one_preset_file(self) -> None:
        with TemporaryDirectory() as directory, patch.dict(os.environ, {"LOCALAPPDATA": directory}):
            save_preset("test", [], ExportSettings(quality=80))
            save_preset("test", [], ExportSettings(quality=95))
            self.assertTrue(preset_exists("test"))
            self.assertEqual(load_presets()["test"][1].quality, 95)

    def test_preset_directory_is_a_single_app_data_folder(self) -> None:
        with TemporaryDirectory() as directory, patch.dict(os.environ, {"LOCALAPPDATA": directory}):
            self.assertEqual(preset_directory(), Path(directory) / "MeiWatermark")


if __name__ == "__main__":
    unittest.main()
