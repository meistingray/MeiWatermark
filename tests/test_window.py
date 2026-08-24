import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from PySide6.QtWidgets import QApplication

from meiwatermark.model import ExportSettings, LayerKind, ResizeMode, WatermarkLayer
from meiwatermark.presets import save_preset
from meiwatermark.window import MainWindow, display_image_name


class WindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_long_image_name_is_truncated_to_twelve_characters(self) -> None:
        self.assertEqual(display_image_name(Path("very-long-photo-name.jpg")), "very-long-p…")

    def test_applying_preset_restores_all_export_controls(self) -> None:
        settings = ExportSettings(resize_mode=ResizeMode.SCALE, resize_value=63, allow_upscale=True, keep_exif=False, keep_icc=False, output_path="/Mei")
        with TemporaryDirectory() as directory, patch.dict(os.environ, {"LOCALAPPDATA": directory}):
            save_preset("full-export", [], settings)
            window = MainWindow()
            window.apply_preset("full-export")
            self.assertEqual(window.resize_value.text(), "63")
            self.assertTrue(window.allow_upscale.isChecked())
            self.assertFalse(window.keep_exif.isChecked())
            self.assertFalse(window.keep_icc.isChecked())
            self.assertEqual(window.output_path.text(), "/Mei")
            window.close()

    def test_export_uses_a_deep_copied_layer_snapshot(self) -> None:
        with patch("meiwatermark.window.ExportWorker") as worker_class:
            window = MainWindow()
            layer = WatermarkLayer(LayerKind.TEXT, "text", text="MeiStingray")
            window.layers = [layer]
            window.paths = [Path("photo.jpg")]
            window.settings = ExportSettings(output_path="/Mei")
            window.export_batch()
            snapshot = worker_class.call_args.args[2]
            self.assertIsNot(snapshot[0], layer)
            layer.opacity = 10
            self.assertEqual(snapshot[0].opacity, 80)
            window.close()


if __name__ == "__main__":
    unittest.main()
