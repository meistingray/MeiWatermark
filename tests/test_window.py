import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from PIL import Image
from PySide6.QtCore import QEventLoop, QPoint, Qt, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QCheckBox, QDialog, QLabel, QPushButton, QRadioButton, QToolButton

from meiwatermark.model import ExportSettings, LayerKind, ResizeMode, WatermarkLayer
from meiwatermark.presets import save_preset
from meiwatermark.i18n import translate
from meiwatermark.window import LayerDelegate, LayerList, MainWindow, ThumbnailDelegate, display_image_name


class WindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_long_image_name_is_truncated_to_twelve_characters(self) -> None:
        self.assertEqual(display_image_name(Path("very-long-photo-name.jpg")), "very-long-p…")

    def test_thumbnail_selection_has_no_native_focus_outline(self) -> None:
        window = MainWindow()
        self.assertIsInstance(window.thumbnails.itemDelegate(), ThumbnailDelegate)
        self.assertIsInstance(window.layer_list.itemDelegate(), LayerDelegate)
        window.close()

    def test_layer_delete_button_removes_its_layer(self) -> None:
        window = MainWindow()
        first, second = WatermarkLayer(LayerKind.TEXT, "text", text="First"), WatermarkLayer(LayerKind.TEXT, "text", text="Second")
        window.add_layer(first)
        window.add_layer(second)
        row = window.layer_list.itemWidget(window.layer_list.item(1))
        button = row.findChild(QToolButton, "deleteLayer")
        self.assertIsNotNone(button)
        button.click()
        self.assertEqual([layer.id for layer in window.layers], [first.id])
        self.assertEqual(window.layer_list.count(), 1)
        window.close()

    def test_tiled_layer_has_an_editor_and_disables_position_controls(self) -> None:
        window = MainWindow()
        layer = WatermarkLayer(LayerKind.IMAGE, "全屏图片", image_path="logo.png", tiled=True)
        window.add_layer(layer)
        row = window.layer_list.itemWidget(window.layer_list.currentItem())
        self.assertIsNotNone(row.findChild(QToolButton, "editLayer"))
        self.assertFalse(window.horizontal_row.isEnabled())
        self.assertFalse(window.vertical_row.isEnabled())
        self.assertFalse(window.anchor_grid.isEnabled())
        self.assertTrue(window.size_value.isEnabled())
        self.assertTrue(window.opacity.isEnabled())
        self.assertTrue(window.rotation.isEnabled())
        window.close()

    def test_tiled_dialog_selection_and_columns_are_stable(self) -> None:
        window = MainWindow()
        window.edit_text_dialog = lambda layer: True
        state = {}

        def inspect() -> None:
            dialog = next(widget for widget in self.app.topLevelWidgets() if isinstance(widget, QDialog))
            image_mode = dialog.findChild(QRadioButton, "tileImageMode")
            text_mode = dialog.findChild(QRadioButton, "tileTextMode")
            text_button = dialog.findChild(QPushButton, "tileText")
            state["initial"] = (image_mode.isChecked(), text_mode.isChecked())
            text_button.click()
            state["selected"] = (image_mode.isChecked(), text_mode.isChecked())
            state["selected_is_visible"] = image_mode.grab().toImage() != text_mode.grab().toImage()
            state["buttons_enabled"] = dialog.findChild(QPushButton, "tileImage").isEnabled() and text_button.isEnabled()
            state["indicator_x"] = (image_mode.x(), dialog.findChild(QCheckBox, "tileStagger").x())
            state["label_x"] = tuple(dialog.findChild(QLabel, name).x() for name in ("tileImageLabel", "tileTextLabel", "tileGapLabel", "tileStaggerLabel"))
            dialog.reject()

        QTimer.singleShot(0, inspect)
        window.edit_tiled_dialog(WatermarkLayer(LayerKind.TEXT, "全屏文字", tiled=True), select_mode=False)
        self.assertEqual(state["initial"], (False, False))
        self.assertEqual(state["selected"], (False, True))
        self.assertTrue(state["selected_is_visible"])
        self.assertTrue(state["buttons_enabled"])
        self.assertEqual(len(set(state["indicator_x"])), 1)
        self.assertEqual(len(set(state["label_x"])), 1)
        window.close()

    def test_layer_list_uses_the_row_mouse_position_for_drag_preview(self) -> None:
        layer_list = LayerList()
        preview = QPixmap(20, 20)
        layer_list.set_drag_preview(preview, QPoint(7, 11))
        self.assertEqual(layer_list.drag_hotspot, QPoint(7, 11))
        self.assertEqual((layer_list.drag_pixmap.width(), layer_list.drag_pixmap.height()), (20, 20))
        layer_list.close()

    def test_combo_boxes_use_the_flat_arrow_style(self) -> None:
        window = MainWindow()
        self.assertIn("QComboBox::drop-down", window.styleSheet())
        self.assertIn("QComboBox:on", window.styleSheet())
        self.assertIn("QComboBox QAbstractItemView", window.styleSheet())
        self.assertIn("down-arrow.svg", window.styleSheet())
        self.assertIn("width: 18px", window.styleSheet())
        self.assertNotIn("padding-right: 26px", window.styleSheet())
        window.close()

    def test_unchanged_estimate_is_not_scheduled_again(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "photo.png"
            Image.new("RGB", (40, 30), "white").save(path)
            window = MainWindow()
            window.add_paths([path])
            window.estimate_timer.stop()
            window._estimate_cache[window._estimate_key(path)] = 1024
            window.schedule_estimate()
            self.assertFalse(window.estimate_timer.isActive())
            window.layers.append(WatermarkLayer(LayerKind.TEXT, "text"))
            window.schedule_estimate()
            self.assertTrue(window.estimate_timer.isActive())
            window.close()

    def test_automatic_estimate_only_uses_the_current_photo(self) -> None:
        with TemporaryDirectory() as directory, patch("meiwatermark.window.EstimateWorker") as worker_class:
            first, second = Path(directory) / "first.png", Path(directory) / "second.png"
            Image.new("RGB", (12, 12), "white").save(first)
            Image.new("RGB", (12, 12), "black").save(second)
            window = MainWindow()
            window.add_paths([first, second])
            window.estimate_timer.stop()
            window.update_estimate()
            self.assertEqual(len(worker_class.call_args.args[0]), 1)
            self.assertEqual(worker_class.call_args.args[0][0][1], second)
            window.close()

    def test_compact_unit_translations(self) -> None:
        self.assertEqual([translate("百分比", language) for language in ("zh", "en", "es", "ja")], ["%", "%", "%", "%"])
        self.assertEqual([translate("视觉比例", language) for language in ("zh", "en", "es", "ja")], ["比例", "Ratio", "Ratio", "比率"])
        self.assertEqual([translate("字重", language) for language in ("zh", "en", "es", "ja")], ["字重", "Weight", "Peso", "ウェイト"])
        self.assertEqual([translate("图片水印", language) for language in ("zh", "en", "es", "ja")], ["图片", "Image", "Imagen", "画像"])
        self.assertEqual([translate("删除图层", language) for language in ("zh", "en", "es", "ja")], ["删除图层", "Delete Layer", "Eliminar capa", "レイヤーを削除"])
        self.assertEqual([translate("添加全屏水印", language) for language in ("zh", "en", "es", "ja")], ["+全屏水印", "+ Tile", "+ Mosaico", "+全画面透かし"])

    def test_unit_choices_update_after_language_switch(self) -> None:
        window = MainWindow()
        for language, ratio in (("zh", "比例"), ("en", "Ratio"), ("es", "Ratio"), ("ja", "比率")):
            window.set_language(language)
            self.assertEqual((window.size_unit.itemText(0), window.size_unit.itemText(1)), ("%", "px"))
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
        self.assertEqual(window.opacity.value(), 80)
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

    def test_newly_added_photo_becomes_current(self) -> None:
        with TemporaryDirectory() as directory:
            first, latest = Path(directory) / "first.png", Path(directory) / "latest.png"
            Image.new("RGB", (12, 12), "white").save(first)
            Image.new("RGB", (12, 12), "black").save(latest)
            window = MainWindow()
            window.add_paths([first])
            window.add_paths([latest])
            self.assertEqual(window.thumbnails.currentItem().data(Qt.ItemDataRole.UserRole), latest)
            window.close()

    def test_switching_photo_changes_only_the_current_estimate(self) -> None:
        with TemporaryDirectory() as directory:
            first, second = Path(directory) / "first.png", Path(directory) / "second.png"
            Image.new("RGB", (12, 12), "white").save(first)
            Image.new("RGB", (12, 12), "black").save(second)
            window = MainWindow()
            window.add_paths([first, second])
            window._estimate_cache[window._estimate_key(first)] = 1024 * 1024
            window._estimate_cache[window._estimate_key(second)] = 2 * 1024 * 1024
            window._refresh_estimate_labels()
            batch = window.batch_estimate.text()
            self.assertIn("2.0 MB", window.current_estimate.text())
            window.thumbnails.setCurrentRow(0)
            self.assertIn("1.0 MB", window.current_estimate.text())
            self.assertEqual(window.batch_estimate.text(), batch)
            window.close()

    def test_completed_batch_estimate_stays_fixed_when_selection_changes(self) -> None:
        with TemporaryDirectory() as directory:
            first, second = Path(directory) / "first.png", Path(directory) / "second.png"
            Image.new("RGB", (400, 300), "white").save(first)
            Image.effect_noise((400, 300), 100).convert("RGB").save(second)
            window = MainWindow()
            window.add_paths([first, second])
            window.estimate_timer.stop()
            window.estimate_batch()
            loop = QEventLoop()
            window.estimate_worker.finished.connect(loop.quit)
            QTimer.singleShot(5000, loop.quit)
            loop.exec()
            batch = window.batch_estimate.text()
            current = window.current_estimate.text()
            window.thumbnails.setCurrentRow(0)
            self.assertNotEqual(window.current_estimate.text(), current)
            self.assertEqual(window.batch_estimate.text(), batch)
            window.close()


if __name__ == "__main__":
    unittest.main()
