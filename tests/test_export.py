from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from PIL import Image

from meiwatermark.export import ExportWorker
from meiwatermark.model import ExportSettings


class ExportTests(unittest.TestCase):
    def test_relative_destination_is_resolved_from_each_original(self) -> None:
        with TemporaryDirectory() as directory:
            source = Path(directory) / "photo.png"
            Image.new("RGB", (20, 20), "white").save(source)
            ExportWorker([source], Path("output"), [], ExportSettings(format="PNG")).run()
            self.assertTrue((source.parent / "output" / "photo_watermarked.png").is_file())


if __name__ == "__main__":
    unittest.main()
