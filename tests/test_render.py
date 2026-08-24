from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image

from meiwatermark.model import Anchor, ExportSettings, LayerKind, ResizeMode, Unit, WatermarkLayer
from meiwatermark.render import _text_stamp, export_size, render, resize_for_export, system_fonts


class RenderTests(unittest.TestCase):
    def test_visual_inset_uses_short_edge(self) -> None:
        base = Image.new("RGBA", (1000, 500), "black")
        layer = WatermarkLayer(LayerKind.TEXT, "text", text="X", size=10, horizontal_inset=10, horizontal_unit=Unit.VISUAL, vertical_inset=10, vertical_unit=Unit.VISUAL, anchor=Anchor.BOTTOM_RIGHT)
        result = render(base, [layer])
        self.assertEqual(result.size, base.size)

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
        self.assertTrue(all("\x00" not in name for name in system_fonts()))


if __name__ == "__main__":
    unittest.main()
