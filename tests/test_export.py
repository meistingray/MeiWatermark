from __future__ import annotations

from pathlib import Path
from dataclasses import replace
from io import BytesIO
import random
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from PIL import Image

from meiwatermark.export import EstimateWorker, ExportWorker
from meiwatermark.model import ExportSettings, ResizeMode
from meiwatermark.render import ImageSource, OutputSizeLimitError, encode_image, estimate_size, load_image, save_image


class ExportTests(unittest.TestCase):
    def test_lossy_outputs_fit_limit_without_changing_dimensions(self) -> None:
        image = Image.frombytes("RGB", (160, 120), random.Random(42).randbytes(160 * 120 * 3))
        for fmt in ("JPEG", "WEBP"):
            with self.subTest(format=fmt):
                settings = ExportSettings(format=fmt, quality=90, max_size_kb=8)
                data = encode_image(image, settings)
                self.assertLessEqual(len(data), 8 * 1024)
                self.assertGreater(len(encode_image(image, replace(settings, max_size_kb=0))), 8 * 1024)
                self.assertEqual(Image.open(BytesIO(data)).size, image.size)
                self.assertEqual(estimate_size(image, settings), len(data))

    def test_limit_does_not_raise_the_quality_ceiling(self) -> None:
        image = Image.new("RGB", (40, 30), "white")
        for fmt in ("JPEG", "WEBP"):
            settings = ExportSettings(format=fmt, quality=35, max_size_kb=100)
            self.assertEqual(encode_image(image, settings), encode_image(image, replace(settings, max_size_kb=0)))

    def test_png_size_limit_preserves_pixels_and_transparency(self) -> None:
        image = Image.new("RGBA", (80, 60), (10, 20, 30, 40))
        data = encode_image(image, ExportSettings(format="PNG", max_size_kb=1))
        self.assertLessEqual(len(data), 1024)
        self.assertEqual(Image.open(BytesIO(data)).tobytes(), image.tobytes())

    def test_impossible_limits_leave_no_output_file(self) -> None:
        image = Image.frombytes("RGB", (512, 384), random.Random(42).randbytes(512 * 384 * 3))
        # Metadata can exceed the limit even when the image shrinks to one pixel.
        exif = Image.Exif()
        exif[270] = "description" * 500
        source = ImageSource(image, exif.tobytes(), None, image.size)
        with TemporaryDirectory() as directory:
            for fmt in ("JPEG", "WEBP", "PNG"):
                target = Path(directory) / f"output.{fmt.lower()}"
                with self.subTest(format=fmt), self.assertRaises(OutputSizeLimitError):
                    save_image(image, target, ExportSettings(format=fmt, max_size_kb=1), source)
                self.assertFalse(target.exists())

    def test_retained_metadata_counts_toward_limit(self) -> None:
        image = Image.new("RGB", (40, 30), "white")
        source = ImageSource(image, None, b"profile" * 1000, image.size)
        settings = ExportSettings(max_size_kb=1)
        with self.assertRaises(OutputSizeLimitError):
            encode_image(image, settings, source)
        self.assertLessEqual(len(encode_image(image, replace(settings, keep_icc=False), source)), 1024)

    def test_limited_estimate_matches_resized_batch_export(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "photo.png"
            Image.frombytes("RGB", (240, 180), random.Random(42).randbytes(240 * 180 * 3)).save(path)
            settings = ExportSettings(max_size_kb=8, resize_mode=ResizeMode.LONG_EDGE, resize_value=160)
            values = []
            worker = EstimateWorker([(("photo",), path, None)], [], settings)
            worker.estimated.connect(lambda key, value: values.append(value))
            worker.run()
            ExportWorker([path], Path(directory) / "output", [], settings).run()
            target = Path(directory) / "output" / "photo_watermarked.jpg"
            self.assertEqual(values, [target.stat().st_size])
            self.assertLessEqual(target.stat().st_size, 8 * 1024)
            with Image.open(target) as result:
                self.assertEqual(result.size, (160, 120))

    def test_impossible_estimate_emits_limit_exceeded(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "photo.png"
            exif = Image.Exif()
            exif[270] = "description" * 500
            Image.new("RGB", (40, 30), "white").save(path, exif=exif)
            keys = []
            worker = EstimateWorker([(("photo",), path, None)], [], ExportSettings(max_size_kb=1))
            worker.limit_exceeded.connect(keys.append)
            worker.run()
            self.assertEqual(keys, [("photo",)])

    def test_batch_continues_after_an_impossible_size_limit(self) -> None:
        with TemporaryDirectory() as directory:
            first, second = Path(directory) / "noise.png", Path(directory) / "white.png"
            exif = Image.Exif()
            exif[270] = "description" * 500
            Image.new("RGB", (40, 30), "white").save(first, exif=exif)
            Image.new("RGB", (40, 30), "white").save(second)
            results = []
            worker = ExportWorker([first, second], Path(directory) / "output", [], ExportSettings(max_size_kb=1))
            worker.finished_batch.connect(lambda count, failures: results.append((count, failures)))
            worker.run()
            self.assertEqual(results[0][0], 1)
            self.assertEqual(len(results[0][1]), 1)
            self.assertIn(first.name, results[0][1][0])
            self.assertFalse((Path(directory) / "output" / "noise_watermarked.jpg").exists())
            self.assertLessEqual((Path(directory) / "output" / "white_watermarked.jpg").stat().st_size, 1024)

    def test_size_limit_shrinks_dimensions_when_compression_is_not_enough(self) -> None:
        image = Image.frombytes("RGBA", (512, 384), random.Random(42).randbytes(512 * 384 * 4))
        for fmt in ("JPEG", "WEBP", "PNG"):
            with self.subTest(format=fmt):
                settings = ExportSettings(format=fmt, max_size_kb=1)
                data = encode_image(image, settings)
                self.assertLessEqual(len(data), 1024)
                with Image.open(BytesIO(data)) as result:
                    result.load()
                    self.assertLess(result.width, image.width)
                    self.assertLess(result.height, image.height)
                    self.assertAlmostEqual(result.width / result.height, image.width / image.height, delta=0.1)
                    if fmt != "JPEG":
                        self.assertIn("A", result.getbands())

    def test_automatic_shrinking_estimate_matches_export(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "photo.png"
            Image.frombytes("RGB", (512, 384), random.Random(42).randbytes(512 * 384 * 3)).save(path)
            settings = ExportSettings(max_size_kb=1, resize_mode=ResizeMode.LONG_EDGE, resize_value=400)
            values = []
            worker = EstimateWorker([(("photo",), path, None)], [], settings)
            worker.estimated.connect(lambda key, value: values.append(value))
            worker.run()
            ExportWorker([path], Path(directory) / "output", [], settings).run()
            target = Path(directory) / "output" / "photo_watermarked.jpg"
            self.assertEqual(values, [target.stat().st_size])
            self.assertLessEqual(target.stat().st_size, 1024)
            with Image.open(target) as result:
                self.assertLess(result.width, 400)

    def test_relative_destination_is_resolved_from_each_original(self) -> None:
        with TemporaryDirectory() as directory:
            source = Path(directory) / "photo.png"
            Image.new("RGB", (20, 20), "white").save(source)
            ExportWorker([source], Path("/output"), [], ExportSettings(format="PNG")).run()
            self.assertTrue((source.parent / "output" / "photo_watermarked.png").is_file())

    def test_estimate_worker_reports_a_value(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "photo.png"
            Image.new("RGB", (40, 30), "white").save(path)
            values = []
            key = ("photo",)
            worker = EstimateWorker([(key, path, load_image(path))], [], ExportSettings(format="PNG"))
            worker.estimated.connect(lambda result_key, value: values.append((result_key, value)))
            worker.run()
        self.assertEqual(len(values), 1)
        self.assertEqual(values[0][0], key)
        self.assertGreater(values[0][1], 0)

    def test_export_resizes_before_rendering(self) -> None:
        with TemporaryDirectory() as directory:
            source = Path(directory) / "photo.png"
            Image.new("RGB", (400, 200), "white").save(source)
            worker = ExportWorker([source], Path("/output"), [], ExportSettings(format="PNG", resize_mode=ResizeMode.LONG_EDGE, resize_value=100))
            with patch("meiwatermark.export.render", side_effect=lambda image, _: image) as render_image:
                worker.run()
        self.assertEqual(render_image.call_args.args[0].size, (100, 50))

    def test_export_worker_keeps_a_path_snapshot(self) -> None:
        paths = [Path("first.png")]
        worker = ExportWorker(paths, Path("output"), [], ExportSettings(format="PNG"))
        paths.clear()
        self.assertEqual(worker.paths, [Path("first.png")])


if __name__ == "__main__":
    unittest.main()
