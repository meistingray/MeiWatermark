from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image

from meiwatermark.model import Anchor, ExportSettings, LayerKind, ResizeMode, Unit, WatermarkLayer
from meiwatermark.render import _image_stamp, _resized_watermark, _size_pixels, _text_stamp, _watermark_image, estimate_size, export_size, load_image, load_preview, load_thumbnail, render, resize_for_export, save_image, system_fonts


class RenderTests(unittest.TestCase):
    def test_visual_inset_uses_short_edge(self) -> None:
        base = Image.new("RGBA", (1000, 500), "black")
        layer = WatermarkLayer(LayerKind.TEXT, "text", text="X", size=10, horizontal_inset=10, horizontal_unit=Unit.VISUAL, vertical_inset=10, vertical_unit=Unit.VISUAL, anchor=Anchor.BOTTOM_RIGHT)
        result = render(base, [layer])
        self.assertEqual(result.size, base.size)

    def test_size_percent_uses_the_short_image_edge(self) -> None:
        width, height = 1000, 500
        self.assertEqual(_size_pixels(WatermarkLayer(LayerKind.TEXT, "text", size=10, size_unit=Unit.PERCENT), width, height), 50)

    def test_tiled_watermark_repeats_across_the_canvas(self) -> None:
        base = Image.new("RGBA", (40, 40), "black")
        with TemporaryDirectory() as directory:
            path = Path(directory) / "red.png"
            Image.new("RGBA", (8, 8), "red").save(path)
            layer = WatermarkLayer(LayerKind.IMAGE, "tile", image_path=str(path), size=8, size_unit=Unit.PIXELS, opacity=100, tiled=True, tile_gap=0, tile_stagger=False)
            result = render(base, [layer])
        self.assertGreater(result.getpixel((0, 0))[0], 0)
        self.assertGreater(result.getpixel((24, 24))[0], 0)

    def test_image_stamp_reuses_the_resized_watermark(self) -> None:
        _watermark_image.cache_clear()
        _resized_watermark.cache_clear()
        with TemporaryDirectory() as directory:
            path = Path(directory) / "mark.png"
            Image.new("RGBA", (800, 800), "red").save(path)
            layer = WatermarkLayer(LayerKind.IMAGE, "mark", image_path=str(path))
            first = _image_stamp(layer, 96)
            second = _image_stamp(layer, 96)
        self.assertIs(first, second)
        self.assertEqual(_resized_watermark.cache_info().hits, 1)

    def test_resize_long_edge_keeps_ratio(self) -> None:
        image = Image.new("RGBA", (4000, 2000))
        settings = ExportSettings(resize_mode=ResizeMode.LONG_EDGE, resize_value=1000)
        self.assertEqual(resize_for_export(image, settings).size, (1000, 500))

    def test_resize_does_not_upscale_by_default(self) -> None:
        image = Image.new("RGBA", (100, 50))
        settings = ExportSettings(resize_mode=ResizeMode.LONG_EDGE, resize_value=1000)
        self.assertEqual(resize_for_export(image, settings).size, image.size)

    def test_export_size_for_short_edge(self) -> None:
        settings = ExportSettings(resize_mode=ResizeMode.SHORT_EDGE, resize_value=1000)
        self.assertEqual(export_size((6000, 4000), settings), (1500, 1000))

    def test_topmost_layer_is_the_first_one_in_the_list(self) -> None:
        base = Image.new("RGBA", (200, 100), "black")
        with TemporaryDirectory() as directory:
            red_path = Path(directory) / "red.png"
            green_path = Path(directory) / "green.png"
            Image.new("RGBA", (20, 20), "red").save(red_path)
            Image.new("RGBA", (20, 20), "green").save(green_path)
            bottom = WatermarkLayer(LayerKind.IMAGE, "bottom", image_path=str(green_path), size=50, anchor=Anchor.TOP_LEFT, horizontal_inset=0, vertical_inset=0)
            top = WatermarkLayer(LayerKind.IMAGE, "top", image_path=str(red_path), size=50, anchor=Anchor.TOP_LEFT, horizontal_inset=0, vertical_inset=0)
            result = render(base, [top, bottom])
        self.assertGreater(result.getpixel((10, 10))[0], result.getpixel((10, 10))[1])

    def test_zero_inset_places_visible_watermark_content_at_edge(self) -> None:
        base = Image.new("RGBA", (100, 100), "black")
        with TemporaryDirectory() as directory:
            path = Path(directory) / "padded.png"
            stamp = Image.new("RGBA", (20, 20))
            stamp.alpha_composite(Image.new("RGBA", (10, 10), "red"), (5, 5))
            stamp.save(path)
            layer = WatermarkLayer(LayerKind.IMAGE, "edge", image_path=str(path), size=10, anchor=Anchor.TOP_LEFT, horizontal_inset=0, vertical_inset=0)
            result = render(base, [layer])
        self.assertGreater(result.getpixel((0, 0))[0], 0)

    def test_text_stamp_keeps_its_descenders_inside_the_canvas(self) -> None:
        stamp = _text_stamp(WatermarkLayer(LayerKind.TEXT, "text", text="© 2025"), 80)
        bounds = stamp.getchannel("A").getbbox()
        self.assertIsNotNone(bounds)
        self.assertLess(bounds[3], stamp.height)

    def test_text_size_sets_the_visible_stamp_long_edge(self) -> None:
        stamp = _text_stamp(WatermarkLayer(LayerKind.TEXT, "text", text="MeiStingray but longer"), 100)
        bounds = stamp.getchannel("A").getbbox()
        self.assertIsNotNone(bounds)
        self.assertLessEqual(abs(max(bounds[2] - bounds[0], bounds[3] - bounds[1]) - 100), 1)

    def test_text_stamp_supports_text_or_outline_only(self) -> None:
        outline_only = _text_stamp(WatermarkLayer(LayerKind.TEXT, "text", text="A", color=None, stroke_color=(255, 0, 0), stroke_width=3), 80)
        invisible = _text_stamp(WatermarkLayer(LayerKind.TEXT, "text", text="A", color=None, stroke_color=None), 80)
        self.assertIsNotNone(outline_only.getchannel("A").getbbox())
        self.assertIsNone(invisible.getchannel("A").getbbox())

    def test_negative_inset_moves_watermark_outside_the_canvas(self) -> None:
        base = Image.new("RGBA", (20, 20), "black")
        with TemporaryDirectory() as directory:
            path = Path(directory) / "red.png"
            Image.new("RGBA", (10, 10), "red").save(path)
            layer = WatermarkLayer(LayerKind.IMAGE, "red", image_path=str(path), size=50, anchor=Anchor.TOP_LEFT, horizontal_inset=-5, horizontal_unit=Unit.PIXELS, vertical_inset=0)
            result = render(base, [layer])
        self.assertGreater(result.getpixel((0, 2))[0], 0)
        self.assertEqual(result.getpixel((6, 2))[0], 0)

    def test_system_font_names_do_not_contain_null_characters(self) -> None:
        fonts = system_fonts("zh")
        self.assertTrue(all("\x00" not in choice.family and "\ufffd" not in choice.family for choice in fonts))
        self.assertTrue(all(Path(choice.path).is_file() for choice in fonts))

    def test_variable_font_instances_are_enumerated(self) -> None:
        fonts = system_fonts("zh")
        noto = [choice for choice in fonts if Path(choice.path).name == "NotoSansSC-VF.ttf"]
        if noto:
            self.assertGreaterEqual(len(noto), 7)
            self.assertIn((900.0,), {choice.variation for choice in noto})

    def test_preview_and_thumbnail_are_bounded_before_display(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "portrait.jpg"
            exif = Image.Exif()
            exif[274] = 6
            Image.new("RGB", (300, 600), "white").save(path, exif=exif)
            preview = load_preview(path, (100, 80))
            thumbnail = load_thumbnail(path, (60, 40))
        self.assertEqual(preview.original_size, (600, 300))
        self.assertLessEqual(preview.image.width, 100)
        self.assertLessEqual(preview.image.height, 80)
        self.assertLessEqual(thumbnail.width, 60)
        self.assertLessEqual(thumbnail.height, 40)

    def test_jpeg_estimate_uses_export_encoding_options(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "source.jpg"
            target = Path(directory) / "target.jpg"
            Image.new("RGB", (80, 60), "white").save(path)
            source = load_image(path)
            settings = ExportSettings(format="JPEG", quality=90)
            estimated = estimate_size(source.image, settings, source)
            save_image(source.image, target, settings, source)
            self.assertEqual(estimated, target.stat().st_size)


if __name__ == "__main__":
    unittest.main()
