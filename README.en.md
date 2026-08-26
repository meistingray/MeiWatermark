# MeiWatermark

<p align="center">
  <img src="docs/assets/MeiWatermarkLogo.png" alt="MeiWatermark" width="280">
</p>

<p align="center">
  <a href="README.md">简体中文</a> · <strong>English</strong> · <a href="README.es.md">Español</a> · <a href="README.ja.md">日本語</a>
</p>

MeiWatermark is a portable, local Windows batch image watermarking tool that supports image, text, and tiled watermarks, multiple layers, and batch export.

Layer and arrange image and text watermarks with nine-grid positioning, inset margins, opacity, rotation, text outlines, and reusable presets.

Batch export to JPEG, PNG, and WebP with quality control, resize constraints, file-size estimates, and relative output paths.

## Features

- **Multi-layer watermarks**: combine multiple image and text watermark layers; enable, reorder, and drag layers as needed.
- **Consistent visual results**: set watermark size by the image’s short-edge percent or pixels; text watermark size means the rendered text’s longest edge, so image and text layers share the same size semantics.
- **Precise placement**: control nine-grid anchors, horizontal and vertical insets, opacity, and rotation independently. Insets can be negative.
- **Text watermarks**: use the system font list with localized font names; set text and outline colors independently, including no color, and choose an outline width.
- **Tiled watermarks**: create repeated full-image text or image watermarks, with short-edge percentage gaps and optional staggering.
- **Live preview**: drag images anywhere into the window; the current preview remains visible while the next photo loads, and the newest imported image is selected and brought into view automatically.
- **Render safeguards**: pixel watermark sizes above 4096 px are adjusted to 4096; percentage watermarks whose rendered size or tile count exceeds the safe range are reported and skipped for that image.
- **Photo list management**: use the Delete key, the context menu, or Clear List to remove photos from the current list. Original files are never deleted.
- **Batch export**: JPEG, PNG, and WebP support; quality defaults to 100, with optional long-edge, short-edge, or scale-based resize limits.
- **Output control**: estimate the current image file size before export; retain EXIF and ICC profiles when needed; support paths relative to each original image.
- **Preset management**: each preset stores both watermark layers and export settings in a separate JSON file for easy backup, sharing, or cleanup.
- **Local processing**: image loading, previewing, and export are performed locally without a cloud service.
- **Multilingual interface**: Simplified Chinese, English, Spanish, and Japanese are included.

## Quick Start

1. Select **Open Images**, or drag one or more images anywhere into the window.
2. Add an image, text, or tiled watermark, then arrange and enable layers in the layer list.
3. Select a layer and set its size, inset, opacity, rotation, and nine-grid anchor.
4. Choose output format, quality, optional resize limit, and destination.
5. Select **Export** to process the batch.

## Scale and Positioning

**Visual Ratio** bases the inset on the image’s short edge, so landscape and portrait images keep similar perceived margins in full-screen viewing. Inset **Percent** uses the relevant image width or height; **px** is intended for fixed-pixel requirements.

For watermark size, **%** uses the image’s short edge. For text watermarks, the selected ratio controls the longest edge of the rendered text as a whole, not the font size, so longer text remains within the intended visual proportion.

For most photographic work, use **%** for watermark size and **Visual Ratio** for insets.

Tiled watermarks use the same size, opacity, and rotation controls, but repeat across the full image. Their gap uses the image’s short-edge percentage; tiled layers do not use insets or nine-grid positioning.

## Presets and Output Paths

Presets store both layers and export settings. Their default directory is:

```text
%LOCALAPPDATA%\MeiWatermark\
```

Each preset is a separate `.json` file. The **Manage** button opens this folder; saving an existing name prompts before overwrite.

Leave the output path empty to choose a destination before exporting. A relative path such as `/Mei` creates the destination beside each original image.

## Requirements

- Windows 10 or later
- Python 3.12 (only required when running from source)

The release build is a standalone Windows executable and does not require a separate Python installation.

## Run from Source

```powershell
conda create -n meiwatermark python=3.12 -y
conda activate meiwatermark
python -m pip install -e .
python -m meiwatermark
```

## Development and Packaging

```powershell
# Run tests
python -m unittest discover -s tests -v

# Build the Windows executable
python -m PyInstaller --noconfirm MeiWatermark.spec
```

The UI wording reference is maintained in [docs/language-reference.md](docs/language-reference.md). Update it and every bundled language whenever UI text changes.

## License

Licensed under the [GNU General Public License v3.0 or later](LICENSE) (GPL-3.0-or-later).

Copyright © 2026 MeiStingray, Kicity Studio
<https://www.kicity.com>
