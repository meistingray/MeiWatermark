from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from PIL import Image

from meiwatermark.export import EstimateWorker, ExportWorker
from meiwatermark.model import ExportSettings
from meiwatermark.render import load_image


class ExportTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
