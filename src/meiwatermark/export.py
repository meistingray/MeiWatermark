from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from .model import ExportSettings, ResizeMode, WatermarkLayer
from .render import ImageSource, OutputSizeLimitError, estimate_size, export_size, load_image, load_preview, render, resize_for_export, save_image, scaled_layers


class ExportWorker(QThread):
    progressed = Signal(int, int, str)
    finished_batch = Signal(int, list)

    def __init__(self, paths: list[Path], destination: Path, layers: list[WatermarkLayer], settings: ExportSettings, size_limit_message: str = "File header or retained metadata exceeds the limit; increase the KB limit or disable EXIF/ICC retention.") -> None:
        super().__init__()
        self.paths, self.destination, self.layers, self.settings = list(paths), destination, layers, settings
        self._cancelled = False
        self.size_limit_message = size_limit_message

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
                base = resize_for_export(source.image, self.settings)
                layers = scaled_layers(self.layers, base.width / source.image.width)
                output = render(base, layers)
                destination = self.destination if self.destination.is_absolute() else path.parent / str(self.destination).lstrip("\\/")
                target = destination / f"{path.stem}{self.settings.suffix}{extension}"
                counter = 2
                while target.exists():
                    target = destination / f"{path.stem}{self.settings.suffix}_{counter}{extension}"
                    counter += 1
                save_image(output, target, self.settings, source)
                complete += 1
            except OutputSizeLimitError as exc:
                failures.append(f"{path.name}: {self.size_limit_message} ({exc})")
            except Exception as exc:  # noqa: BLE001
                failures.append(f"{path.name}: {exc}")
            self.progressed.emit(index, len(self.paths), path.name)
        self.finished_batch.emit(complete, failures)


class EstimateWorker(QThread):
    estimated = Signal(object, float)
    failed = Signal(object)
    limit_exceeded = Signal(object)

    def __init__(self, tasks: list[tuple[tuple, Path, ImageSource | None]], layers: list[WatermarkLayer], settings: ExportSettings) -> None:
        super().__init__()
        self.tasks, self.layers, self.settings = tasks, layers, settings
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        for key, path, loaded in self.tasks:
            if self._cancelled:
                return
            try:
                if self.settings.max_size_kb > 0:
                    # A downsampled estimate cannot verify a hard byte limit.
                    source = load_image(path)
                    base = resize_for_export(source.image, self.settings)
                    layers = scaled_layers(self.layers, base.width / source.image.width)
                    output = render(base, layers)
                    estimated = estimate_size(output, replace(self.settings, resize_mode=ResizeMode.NONE), source)
                    self.estimated.emit(key, estimated)
                    continue
                source = loaded or load_preview(path, (1200, 1200))
                layers = scaled_layers(self.layers, source.image.width / source.original_size[0])
                sample = render(source.image, layers)
                output_size = export_size(source.original_size, self.settings)
                estimated = estimate_size(sample, replace(self.settings, resize_mode=ResizeMode.NONE), source)
                estimated *= (output_size[0] * output_size[1]) / max(1, sample.width * sample.height)
                self.estimated.emit(key, estimated)
            except OutputSizeLimitError:
                self.limit_exceeded.emit(key)
            except Exception:  # noqa: BLE001
                self.failed.emit(key)
