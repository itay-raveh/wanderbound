"""Tests for panorama metadata inspection."""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image

from app.logic.panorama.inspection import inspect_panorama


def _jpeg_with_xmp(
    path: Path,
    width: int,
    height: int,
    xmp: str,
    *,
    exif_orientation: int | None = None,
) -> Path:
    image = Image.new("RGB", (width, height), color="red")
    exif = image.getexif()
    if exif_orientation is not None:
        exif[0x0112] = exif_orientation
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", exif=exif.tobytes())
    xmp_bytes = b"http://ns.adobe.com/xap/1.0/\x00" + xmp.encode()
    app1 = b"\xff\xe1" + (len(xmp_bytes) + 2).to_bytes(2, "big") + xmp_bytes
    jpeg = buffer.getvalue()
    path.write_bytes(jpeg[:2] + app1 + jpeg[2:])
    return path


def _gpano(**attributes: object) -> str:
    defaults = {
        "ProjectionType": "cylindrical",
        "CroppedAreaImageWidthPixels": 300,
        "CroppedAreaImageHeightPixels": 100,
        "CroppedAreaLeftPixels": 0,
        "CroppedAreaTopPixels": 0,
        "FullPanoWidthPixels": 400,
        "FullPanoHeightPixels": 100,
        "InitialViewHeadingDegrees": 12,
        "InitialViewPitchDegrees": -3,
    }
    values = {**defaults, **attributes}
    tags = " ".join(f'GPano:{key}="{value}"' for key, value in values.items())
    return (
        '<x:xmpmeta xmlns:x="adobe:ns:meta/">'
        '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
        '<rdf:Description xmlns:GPano="http://ns.google.com/photos/1.0/panorama/" '
        f"{tags} />"
        "</rdf:RDF></x:xmpmeta>"
    )


def test_cylindrical_gpano_activates_with_captured_horizontal_fov(
    tmp_path: Path,
) -> None:
    source = _jpeg_with_xmp(tmp_path / "cylindrical.jpg", 300, 100, _gpano())

    panorama = inspect_panorama(source)

    assert panorama is not None
    assert panorama.status == "active"
    assert panorama.detection == "gpano"
    assert panorama.source_width == 300
    assert panorama.source_height == 100
    assert panorama.cropped_area_width == 300
    assert panorama.full_pano_width == 400
    assert panorama.captured_fov == 270
    assert panorama.yaw == 12
    assert panorama.pitch == -3
    assert panorama.revision > 0


def test_oriented_two_to_one_image_is_suggested(tmp_path: Path) -> None:
    source = _jpeg_with_xmp(
        tmp_path / "oriented.jpg",
        100,
        200,
        "<x:xmpmeta />",
        exif_orientation=6,
    )

    panorama = inspect_panorama(source)

    assert panorama is not None
    assert panorama.status == "suggested"
    assert panorama.detection == "dimensions"
    assert (panorama.source_width, panorama.source_height) == (200, 100)
    assert panorama.captured_fov == 180


def test_narrow_image_is_not_a_panorama(tmp_path: Path) -> None:
    source = _jpeg_with_xmp(tmp_path / "narrow.jpg", 199, 100, "<x:xmpmeta />")

    assert inspect_panorama(source) is None


def test_malformed_gpano_falls_back_to_dimension_suggestion(tmp_path: Path) -> None:
    source = _jpeg_with_xmp(
        tmp_path / "malformed.jpg",
        200,
        100,
        _gpano(CroppedAreaImageWidthPixels="not-a-number"),
    )

    panorama = inspect_panorama(source)

    assert panorama is not None
    assert panorama.status == "suggested"
    assert panorama.detection == "dimensions"


def test_gpano_coverage_is_clamped_to_a_partial_cylinder(tmp_path: Path) -> None:
    source = _jpeg_with_xmp(
        tmp_path / "narrow-capture.jpg",
        1,
        1,
        _gpano(
            CroppedAreaImageWidthPixels=1,
            CroppedAreaImageHeightPixels=1,
            FullPanoWidthPixels=400,
            FullPanoHeightPixels=1,
        ),
    )

    panorama = inspect_panorama(source)

    assert panorama is not None
    assert panorama.captured_fov == 1
