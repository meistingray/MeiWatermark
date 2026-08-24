from pathlib import Path
import unittest

from meiwatermark.window import display_image_name


class WindowTests(unittest.TestCase):
    def test_long_image_name_is_truncated_to_twelve_characters(self) -> None:
        self.assertEqual(display_image_name(Path("very-long-photo-name.jpg")), "very-long-p…")


if __name__ == "__main__":
    unittest.main()
