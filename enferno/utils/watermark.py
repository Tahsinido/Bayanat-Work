"""Stamp the organisation name into a file as it is handed over.

The stamp goes on at download time rather than at rest: the stored file stays
byte-identical to what was collected, which is what the hash on the media row
attests to, and only the copy leaving the system carries the mark. Watermarking
the original would break that attestation.

Only images and PDFs are stamped, because those are the formats that can be
marked without rewriting the document. Word files, video and audio pass through
untouched -- stamping them would mean re-encoding, and a silently re-encoded
exhibit is worse than an unstamped one.

Failure here is never fatal: if the stamp cannot be applied the original bytes
are returned, since refusing an approved download because a cosmetic overlay
failed would be the wrong trade.
"""

from __future__ import annotations

import io
import math
import os
from typing import Optional

from enferno.utils.logging_utils import get_logger

logger = get_logger()

IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "bmp", "tiff", "gif"}
PDF_EXTENSIONS = {"pdf"}

# Four marks to a page, laid out 2 x 2. Dense tiling buried the content; four
# larger marks still make the origin unmistakable on any crop big enough to be
# worth passing on, while leaving the exhibit readable.
_GRID_COLS = 2
_GRID_ROWS = 2
_OPACITY = 0.22
_ANGLE_DEG = 30


def _extension(filename: str) -> str:
    return os.path.splitext(filename or "")[1].lstrip(".").lower()


def can_stamp(filename: str) -> bool:
    """Whether this file is a format the stamp can be applied to."""
    ext = _extension(filename)
    return ext in IMAGE_EXTENSIONS or ext in PDF_EXTENSIONS


def _stamp_image(data: bytes, text: str) -> bytes:
    from PIL import Image, ImageDraw, ImageFont

    with Image.open(io.BytesIO(data)) as source:
        fmt = source.format or "PNG"
        # Animated or paletted sources are flattened to a single RGBA frame;
        # keeping the animation would mean stamping every frame for no benefit.
        base = source.convert("RGBA")

    width, height = base.size
    if width < 32 or height < 32:
        return data

    # Sized so one mark spans roughly two thirds of its cell, which keeps four
    # of them legible without them running into each other.
    cell_w = width / _GRID_COLS
    font_size = max(14, int(cell_w * 0.66 / max(len(text), 4) * 1.7))
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", font_size)
    except OSError:
        # The container may carry no TrueType fonts; the bitmap default still
        # marks the image, just without scaling.
        font = ImageFont.load_default()

    # Draw the text once, then place that one tile at each cell centre.
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    box = probe.textbbox((0, 0), text, font=font)
    text_w, text_h = box[2] - box[0], box[3] - box[1]

    tile = Image.new("RGBA", (text_w + 40, text_h + 40), (0, 0, 0, 0))
    ImageDraw.Draw(tile).text(
        (20, 20), text, font=font, fill=(255, 255, 255, int(255 * _OPACITY))
    )
    tile = tile.rotate(_ANGLE_DEG, expand=True, resample=Image.BICUBIC)

    # A dark halo under the light glyphs keeps the mark legible on pale images.
    shadow = Image.new("RGBA", (text_w + 40, text_h + 40), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).text(
        (21, 21), text, font=font, fill=(0, 0, 0, int(255 * _OPACITY * 0.7))
    )
    shadow = shadow.rotate(_ANGLE_DEG, expand=True, resample=Image.BICUBIC)

    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    for row in range(_GRID_ROWS):
        for col in range(_GRID_COLS):
            cx = (col + 0.5) * width / _GRID_COLS
            cy = (row + 0.5) * height / _GRID_ROWS
            x = int(cx - tile.width / 2)
            y = int(cy - tile.height / 2)
            overlay.alpha_composite(shadow, (x + 1, y + 1))
            overlay.alpha_composite(tile, (x, y))

    stamped = Image.alpha_composite(base, overlay)

    out = io.BytesIO()
    if fmt.upper() in ("JPEG", "JPG"):
        stamped.convert("RGB").save(out, format="JPEG", quality=92)
    else:
        stamped.save(out, format="PNG")
    return out.getvalue()


def _stamp_pdf(data: bytes, text: str) -> bytes:
    import fitz  # PyMuPDF

    doc = fitz.open(stream=data, filetype="pdf")
    try:
        rotation = fitz.Matrix(
            math.cos(math.radians(-_ANGLE_DEG)),
            math.sin(math.radians(-_ANGLE_DEG)),
            -math.sin(math.radians(-_ANGLE_DEG)),
            math.cos(math.radians(-_ANGLE_DEG)),
            0,
            0,
        )
        for page in doc:
            rect = page.rect
            cell_w = rect.width / _GRID_COLS
            font_size = max(12, int(cell_w * 0.66 / max(len(text), 4) * 1.7))
            # Width of the drawn string, so each mark can be centred in its cell
            # rather than starting at the cell's left edge.
            text_w = fitz.get_text_length(text, fontname="helv", fontsize=font_size)

            for row in range(_GRID_ROWS):
                for col in range(_GRID_COLS):
                    cx = rect.x0 + (col + 0.5) * rect.width / _GRID_COLS
                    cy = rect.y0 + (row + 0.5) * rect.height / _GRID_ROWS
                    origin = fitz.Point(cx - text_w / 2, cy)
                    page.insert_text(
                        origin,
                        text,
                        fontsize=font_size,
                        fontname="helv",
                        color=(0.45, 0.45, 0.45),
                        fill_opacity=_OPACITY,
                        # Rotate about the mark's own centre so it stays inside
                        # its cell instead of swinging off the page.
                        morph=(fitz.Point(cx, cy), rotation),
                    )
        return doc.tobytes()
    finally:
        doc.close()


def stamp_copy(path: str, filename: Optional[str] = None, text: Optional[str] = None) -> bool:
    """Stamp a file in place, for files that are already a copy.

    Only ever call this on a copy that is on its way out -- an export staging
    file, a temporary download. It rewrites whatever path it is given, so
    pointing it at the stored original would destroy the very thing the stamp
    exists to protect.

    `filename` decides the format when the copy has been given a working name;
    it defaults to the path itself.

    Returns True when the file was rewritten. Like stamp(), it never raises: a
    file that cannot be marked is left as it is rather than failing the export
    that contains it.
    """
    if text is None:
        from flask import current_app

        text = current_app.config.get("MEDIA_WATERMARK_TEXT")
    if not text or not str(text).strip():
        return False

    name = filename or os.path.basename(path)
    if not can_stamp(name):
        return False

    try:
        with open(path, "rb") as f:
            original = f.read()
        stamped = stamp(original, name, text)
        if stamped is original or stamped == original:
            return False
        with open(path, "wb") as f:
            f.write(stamped)
        return True
    except Exception as e:
        logger.error(f"Could not watermark the copy at {path}: {e}", exc_info=True)
        return False


def stamp(data: bytes, filename: str, text: Optional[str]) -> bytes:
    """Return the file with the stamp applied, or unchanged if it cannot be.

    Never raises: a download that has already been approved and paid for with a
    verification code must not fail because the overlay did not render.
    """
    if not text or not str(text).strip():
        return data
    text = str(text).strip()

    ext = _extension(filename)
    try:
        if ext in IMAGE_EXTENSIONS:
            return _stamp_image(data, text)
        if ext in PDF_EXTENSIONS:
            return _stamp_pdf(data, text)
    except Exception as e:
        logger.error(f"Could not watermark {filename}: {e}", exc_info=True)
        return data
    return data
