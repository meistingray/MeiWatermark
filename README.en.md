# MeiWatermark

<p align="center">
  <img src="docs/assets/MeiWatermarkLogo.png" alt="MeiWatermark" width="280">
</p>

<p align="center">
  <a href="README.md">简体中文</a> · <strong>English</strong> · <a href="README.es.md">Español</a> · <a href="README.ja.md">日本語</a>
</p>

MeiWatermark is an open-source desktop batch watermarking tool that supports multi-layer watermarks with consistent visual scale and positioning across images of different sizes.

Layer and arrange image and text watermarks with nine-grid positioning, inset margins, opacity, rotation, text outlines, and reusable presets.

Batch export to JPEG, PNG, and WebP with quality control, resize constraints, file-size estimates, and relative output paths.

## Features

- **Multi-layer watermarks**: combine multiple image and text watermark layers; toggle, reorder, and drag layers as needed.
- **Consistent visual results**: set watermark size in percent or pixels, and inset margins in visual ratio, percent, or pixels for landscape, portrait, and different resolutions.
- **Precise placement**: control nine-grid anchors, horizontal and vertical insets, opacity, and rotation independently. Insets can be negative.
- **Text watermarks**: use the system font list; set text and outline colors independently, including no color, and choose an outline width.
- **Live preview**: review the result as you work; import images by dragging them anywhere onto the window and manage them from the thumbnail list.
- **Batch export**: JPEG, PNG, and WebP support; quality defaults to 100, with long-edge, short-edge, and scale-based resize limits.
- **Output control**: estimates individual and batch file sizes before export; can retain EXIF and ICC profiles; supports paths relative to each original image.
- **Preset management**: each preset stores both watermark layers and export settings in a separate JSON file for easy backup, sharing, or cleanup.
- **Local processing**: image loading, previewing, and export are performed locally without a cloud service.
- **Multilingual interface**: Simplified Chinese, English, Spanish, and Japanese are included.

## Quick Start

1. Select **Open Images**, or drag one or more images onto the window.
2. Add an image watermark or a text watermark, then arrange and enable layers in the layer list.
3. Select a layer and set its size, inset, opacity, rotation, and nine-grid anchor.
4. Choose output format, quality, resize limit, and destination.
5. Select **Export** to process the batch.

> In the thumbnail list, use the `Delete` key or the context menu to remove an image from the current list. This never deletes the original file from disk.

## Scale and Positioning

**Visual Ratio** bases the inset on the image's short edge, so landscape and portrait images keep similar perceived margins in full-screen viewing. **Percent** uses the relevant image width or height; **px** is intended for fixed-pixel requirements.

For most photographic work, use **Percent** for watermark size and **Visual Ratio** for insets. Choose the anchor with the nine-grid, then fine-tune the two inset values for consistent placement across the batch.

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
