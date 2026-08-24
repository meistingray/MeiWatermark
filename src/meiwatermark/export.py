from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Signal

from .model import ExportSettings, WatermarkLayer
from .render import load_image, render, resize_for_export, save_image


class ExportWorker(QThread):
    progressed = Signal(int, int, str)
    finished_batch = Signal(int, list[str])

    def __init__(self, paths: list[Path], destination: Path, layers: list[WatermarkLayer], settings: ExportSettings) -> None:
        super().__init__()
        self.paths, self.destination, self.layers, self.settings = paths, destination, layers, settings
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        failures: list[str] = []
        complete = 0
        extension = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}[self.settings.format]
        for index, path in enumerate(self.paths, start=1):
            if self._cancelled:
                break
            try:
                source = load_image(path)
                output = resize_for_export(render(source.image, self.layers), self.settings)
                target = self.destination / f"{path.stem}{self.settings.suffix}{extension}"
                counter = 2
                while target.exists():
                    target = self.destination / f"{path.stem}{self.settings.suffix}_{counter}{extension}"
                    counter += 1
                save_image(output, target, self.settings, source)
                complete += 1
            except Exception as exc:  # noqa: BLE001
                failures.append(f"{path.name}: {exc}")
            self.progressed.emit(index, len(self.paths), path.name)
        self.finished_batch.emit(complete, failures)
