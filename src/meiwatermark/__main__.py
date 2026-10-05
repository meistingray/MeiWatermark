from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from meiwatermark.window import MainWindow


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("MeiWatermark")
    app.setOrganizationName("MeiWatermark")
    window = MainWindow()
    if len(sys.argv) == 3 and sys.argv[1] == "--smoke-test":
        # Exercise the frozen app, including Qt and all export codecs, without
        # opening an interactive window or relying on the development environment.
        import json
        from pathlib import Path
        import random

        from PIL import Image

        from meiwatermark.model import ExportSettings
        from meiwatermark.render import save_image

        directory = Path(sys.argv[2])
        directory.mkdir(parents=True, exist_ok=True)
        window.max_size_kb.setText("1")
        window.ensurePolished()
        app.processEvents()
        assert window.settings.max_size_kb == 1
        assert window.grab().save(str(directory / "window.png"))
        image = Image.frombytes("RGB", (512, 384), random.Random(42).randbytes(512 * 384 * 3))
        results = {}
        for fmt in ("JPEG", "WEBP", "PNG"):
            target = directory / f"output.{fmt.lower()}"
            save_image(image, target, ExportSettings(format=fmt, max_size_kb=1))
            with Image.open(target) as exported:
                exported.load()
                assert target.stat().st_size <= 1024
                results[fmt] = {"bytes": target.stat().st_size, "dimensions": exported.size}
        window.close()
        (directory / "result.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
        return
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
