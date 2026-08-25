import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from meiwatermark.model import ExportSettings, LayerKind, ResizeMode, WatermarkLayer
from meiwatermark.presets import save_preset
from meiwatermark.i18n import translate
from meiwatermark.window import MainWindow, ThumbnailDelegate, display_image_name


class WindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_long_image_name_is_truncated_to_twelve_characters(self) -> None:
        self.assertEqual(display_image_name(Path("very-long-photo-name.jpg")), "very-long-p…")

    def test_thumbnail_selection_has_no_native_focus_outline(self) -> None:
        window = MainWindow()
        self.assertIsInstance(window.thumbnails.itemDelegate(), ThumbnailDelegate)
        window.close()

    def test_combo_boxes_use_the_flat_arrow_style(self) -> None:
        window = MainWindow()
        self.assertIn("QComboBox::drop-down", window.styleSheet())
        self.assertIn("down-arrow.svg", window.styleSheet())
        window.close()

    def test_compact_unit_translations(self) -> None:
        self.assertEqual([translate("百分比", language) for language in ("zh", "en", "es", "ja")], ["%", "%", "%", "%"])
        self.assertEqual([translate("视觉比例", language) for language in ("zh", "en", "es", "ja")], ["比例", "Ratio", "Ratio", "比率"])

    def test_unit_choices_update_after_language_switch(self) -> None:
        window = MainWindow()
        for language, ratio in (("zh", "比例"), ("en", "Ratio"), ("es", "Ratio"), ("ja", "比率")):
            window.set_language(language)
            self.assertEqual(window.size_unit.itemText(0), "%")
            self.assertEqual(window.horizontal_unit.itemText(0), ratio)
        window.close()

    def test_slider_fields_accept_direct_values_and_double_click_resets(self) -> None:
        window = MainWindow()
        self.assertEqual([field.width() for field in (window.opacity_number, window.rotation_number, window.quality_number)], [42, 42, 42])
        for field, slider, value in ((window.opacity_number, window.opacity, "35"), (window.rotation_number, window.rotation, "-45"), (window.quality_number, window.quality, "72")):
            field.setText(value)
            field.editingFinished.emit()
            self.assertEqual(slider.value(), int(value))
        window.show()
        QTest.mouseDClick(window.opacity, Qt.MouseButton.LeftButton)
        QTest.mouseDClick(window.rotation, Qt.MouseButton.LeftButton)
        QTest.mouseDClick(window.quality, Qt.MouseButton.LeftButton)
        self.assertEqual(window.opacity.value(), 0)
        self.assertEqual(window.rotation.value(), 0)
        self.assertEqual(window.quality.value(), 100)
        window.close()

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

    def test_delete_key_removes_the_selected_photo_and_clear_empties_list(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "photo.png"
            Image.new("RGB", (12, 12), "white").save(path)
            window = MainWindow()
            window.add_paths([path])
            window.show()
            window.thumbnails.setFocus()
            QTest.keyClick(window.thumbnails, Qt.Key.Key_Delete)
            self.app.processEvents()
            self.assertFalse(window.paths)
            self.assertEqual(window.thumbnails.count(), 0)
            window.add_paths([path])
            window.clear_photo_list()
            self.assertFalse(window.paths)
            self.assertEqual(window.thumbnails.count(), 0)
            window.close()


if __name__ == "__main__":
    unittest.main()
