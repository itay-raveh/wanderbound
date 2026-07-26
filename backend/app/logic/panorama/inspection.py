"""Inspect untouched image metadata for cylindrical panoramas."""

from __future__ import annotations

import re
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from app.models.album_media import PanoramaConfig, canonical_captured_fov

_MIN_PANORAMA_ASPECT_RATIO = 2
_DEFAULT_PERSPECTIVE_FOV = 70.0
_MAX_XMP_SCAN_BYTES = 4 * 1024 * 1024


def inspect_panorama(path: Path) -> PanoramaConfig | None:
    """Return detected panorama configuration without altering the source image."""
    try:
        xmp = _read_xmp(path)
        with Image.open(path) as raw:
            oriented = ImageOps.exif_transpose(raw) or raw
            source_width, source_height = oriented.size
    except UnidentifiedImageError, OSError, SyntaxError:
        return None

    gpano = _gpano_config(xmp, source_width, source_height)
    if gpano is not None:
        return gpano
    if source_width / source_height < _MIN_PANORAMA_ASPECT_RATIO:
        return None
    return PanoramaConfig(
        status="suggested",
        detection="dimensions",
        source_width=source_width,
        source_height=source_height,
        captured_fov=canonical_captured_fov(
            90 * source_width / source_height,
        ),
    )


def _read_xmp(path: Path) -> str:
    with path.open("rb") as source:
        raw = source.read(_MAX_XMP_SCAN_BYTES)
    start = raw.find(b"<x:xmpmeta")
    if start < 0:
        start = raw.find(b"<xmpmeta")
    if start < 0:
        return ""
    end = raw.find(b"</x:xmpmeta>", start)
    closing = b"</x:xmpmeta>"
    if end < 0:
        end = raw.find(b"</xmpmeta>", start)
        closing = b"</xmpmeta>"
    if end < 0:
        return ""
    return raw[start : end + len(closing)].decode("utf-8", errors="ignore")


def _gpano_config(
    xmp: str,
    source_width: int,
    source_height: int,
) -> PanoramaConfig | None:
    values = {key: _xmp_value(xmp, key) for key in _GPANO_FIELDS}
    if values["ProjectionType"] is None:
        return None
    if values["ProjectionType"].lower() != "cylindrical":
        return None
    try:
        cropped_width = _integer(values["CroppedAreaImageWidthPixels"])
        cropped_height = _integer(values["CroppedAreaImageHeightPixels"])
        full_width = _integer(values["FullPanoWidthPixels"])
        full_height = _optional_integer(values["FullPanoHeightPixels"])
        cropped_left = _integer(
            values["CroppedAreaLeftPixels"], default=0, allow_zero=True
        )
        cropped_top = _integer(
            values["CroppedAreaTopPixels"],
            default=0,
            allow_zero=True,
            allow_negative=True,
        )
    except ValueError:
        return None
    if (
        cropped_width > full_width
        or cropped_left + cropped_width > full_width
        or (full_height is not None and cropped_top + cropped_height > full_height)
    ):
        return None
    return PanoramaConfig(
        status="suggested",
        detection="gpano",
        source_width=source_width,
        source_height=source_height,
        cropped_area_width=cropped_width,
        cropped_area_height=cropped_height,
        cropped_area_left=cropped_left,
        cropped_area_top=cropped_top,
        full_pano_width=full_width,
        full_pano_height=full_height,
        captured_fov=canonical_captured_fov(360 * cropped_width / full_width),
        yaw=_number(values["InitialViewHeadingDegrees"], default=0),
        pitch=_number(values["InitialViewPitchDegrees"], default=0),
        perspective_fov=_number(
            values["InitialHorizontalFOVDegrees"],
            default=_DEFAULT_PERSPECTIVE_FOV,
        ),
    )


_GPANO_FIELDS = (
    "ProjectionType",
    "CroppedAreaImageWidthPixels",
    "CroppedAreaImageHeightPixels",
    "CroppedAreaLeftPixels",
    "CroppedAreaTopPixels",
    "FullPanoWidthPixels",
    "FullPanoHeightPixels",
    "InitialViewHeadingDegrees",
    "InitialViewPitchDegrees",
    "InitialHorizontalFOVDegrees",
)


def _xmp_value(xmp: str, key: str) -> str | None:
    attribute = re.search(rf'GPano:{key}\s*=\s*["\']([^"\']+)', xmp)
    if attribute:
        return attribute.group(1)
    element = re.search(rf"<GPano:{key}>([^<]+)</GPano:{key}>", xmp)
    return element.group(1) if element else None


def _integer(
    value: str | None,
    *,
    default: int | None = None,
    allow_zero: bool = False,
    allow_negative: bool = False,
) -> int:
    if value is None:
        if default is None:
            raise ValueError("Missing GPano integer")
        return default
    parsed = int(value)
    if (parsed < 0 and not allow_negative) or (parsed == 0 and not allow_zero):
        raise ValueError("GPano dimensions must be positive")
    return parsed


def _optional_integer(value: str | None) -> int | None:
    return _integer(value) if value is not None else None


def _number(value: str | None, *, default: float) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default
