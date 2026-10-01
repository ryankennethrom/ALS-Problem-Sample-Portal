"""Ticket-image normalization and storage compression.

Ticket images are evidence/reference photos, not archival originals.  Normalize
uploads before they reach Django storage so a phone photo does not consume
several megabytes of the persistent Railway volume.
"""

from __future__ import annotations

from io import BytesIO
import os
import re

from PIL import Image, ImageOps


# Keep enough detail for labels/sample inspection while putting a firm practical
# ceiling on storage. Most real photos end up far below this target.
TARGET_STORED_IMAGE_BYTES = 450 * 1024
MAX_STORED_IMAGE_EDGE = 1600

# Ordered from least destructive to most aggressive. We stop as soon as the
# encoded WebP is at or under the target size.
_COMPRESSION_STEPS = (
    (1600, 78),
    (1600, 74),
    (1600, 70),
    (1440, 74),
    (1440, 70),
    (1440, 66),
    (1280, 72),
    (1280, 68),
    (1280, 64),
    (1152, 68),
    (1152, 64),
    (1152, 60),
    (1024, 64),
    (1024, 60),
    (1024, 56),
    (896, 56),
)


def _safe_webp_name(original_name: str | None) -> str:
    raw = os.path.basename(str(original_name or "ticket-image"))
    stem = os.path.splitext(raw)[0] or "ticket-image"
    # Keep filenames human-readable while avoiding path/control characters.
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", stem).strip(".-") or "ticket-image"
    return f"{stem[:180]}.webp"


def _normalized_frame(file_obj) -> Image.Image:
    try:
        file_obj.seek(0)
    except Exception:
        pass

    with Image.open(file_obj) as source:
        # Ticket uploads are treated as still evidence photos. For animated
        # formats, use the first frame rather than preserving a storage-heavy
        # animation.
        try:
            source.seek(0)
        except EOFError:
            pass
        source.load()
        image = ImageOps.exif_transpose(source).copy()

    has_alpha = image.mode in {"RGBA", "LA"} or (
        image.mode == "P" and "transparency" in image.info
    )
    return image.convert("RGBA" if has_alpha else "RGB")


def _resized_copy(image: Image.Image, max_edge: int) -> Image.Image:
    width, height = image.size
    longest = max(width, height)
    if longest <= max_edge:
        return image.copy()

    scale = max_edge / float(longest)
    size = (max(1, round(width * scale)), max(1, round(height * scale)))
    return image.resize(size, Image.Resampling.LANCZOS)


def _encode_webp(image: Image.Image, quality: int) -> bytes:
    output = BytesIO()
    image.save(
        output,
        format="WEBP",
        quality=quality,
        method=6,
        # We intentionally do not pass EXIF/ICC/XMP metadata. Ticket images do
        # not need camera metadata, and stripping it saves space/privacy.
    )
    return output.getvalue()


def compress_problem_image(file_obj, original_name: str | None = None) -> tuple[bytes, str]:
    """Return normalized WebP bytes and a storage-safe WebP filename.

    Images are auto-oriented, metadata is stripped, oversized dimensions are
    reduced, and WebP quality/resolution is stepped down only as far as needed
    to reach the practical 450 KiB storage target.
    """

    image = _normalized_frame(file_obj)
    best: bytes | None = None

    try:
        for max_edge, quality in _COMPRESSION_STEPS:
            candidate_image = _resized_copy(image, max_edge)
            try:
                candidate = _encode_webp(candidate_image, quality)
            finally:
                candidate_image.close()

            if best is None or len(candidate) < len(best):
                best = candidate
            if len(candidate) <= TARGET_STORED_IMAGE_BYTES:
                return candidate, _safe_webp_name(original_name)

        # Extremely noisy/pathological images can still miss the target after
        # the normal quality floor. Continue reducing resolution, preserving a
        # usable full-screen preview, until the target is met.
        for max_edge in (800, 720, 640):
            candidate_image = _resized_copy(image, max_edge)
            try:
                candidate = _encode_webp(candidate_image, 54)
            finally:
                candidate_image.close()
            if best is None or len(candidate) < len(best):
                best = candidate
            if len(candidate) <= TARGET_STORED_IMAGE_BYTES:
                return candidate, _safe_webp_name(original_name)
    finally:
        image.close()

    # This is only a final safety fallback for unusually incompressible images.
    return best or b"", _safe_webp_name(original_name)
