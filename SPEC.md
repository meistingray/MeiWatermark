# MeiWatermark specification

- Brand logo is application branding only, never a default photo watermark.
- Whole-window image drag and drop is supported.
- The action row is: Open Images, Add Image Watermark, Add Text Watermark.
- Each preset stores watermark layers and export settings together in one JSON file.
- Image watermark size supports percent and pixels. Insets support visual ratio, percent, and pixels.
- Preview fits the actual preview viewport and uses the same layout calculation as export.
- Export formats: JPEG, PNG, WebP. JPEG/WebP quality defaults to 100.
- Resize is optional: none, long edge, short edge, or scale percentage. Aspect ratio is always kept.
- GPL-3.0-or-later is the project license.
