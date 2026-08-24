from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from meiwatermark.model import ExportSettings, LayerKind, WatermarkLayer
from meiwatermark.presets import load_presets, preset_directory, save_preset


class PresetTests(unittest.TestCase):
    def test_combined_preset_stores_layers_and_export_settings(self) -> None:
        with TemporaryDirectory() as directory, patch.dict(os.environ, {"LOCALAPPDATA": directory}):
            save_preset("test", [WatermarkLayer(LayerKind.TEXT, "text", text="MeiStingray")], ExportSettings(format="PNG", quality=92))
            layers, settings = load_presets()["test"]
            self.assertEqual(layers[0].text, "MeiStingray")
            self.assertEqual((settings.format, settings.quality), ("PNG", 92))
            self.assertTrue((Path(directory) / "MeiWatermark" / "presets.json").is_file())

    def test_preset_directory_is_a_single_app_data_folder(self) -> None:
        with TemporaryDirectory() as directory, patch.dict(os.environ, {"LOCALAPPDATA": directory}):
            self.assertEqual(preset_directory(), Path(directory) / "MeiWatermark")


if __name__ == "__main__":
    unittest.main()
