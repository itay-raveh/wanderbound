"""Tests for app.logic.trip_processing."""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image

from app.logic.layout.media import Media
from app.logic.trip_processing import (
    build_album_media_rows,
    default_media_resolution_warning_preset,
    resolve_international_waters,
    segment_timezone,
)
from app.models.album import (
    DEFAULT_MEDIA_RESOLUTION_WARNING_PRESET,
    DEMO_MEDIA_RESOLUTION_WARNING_PRESET,
)
from app.models.polarsteps import Location, PSStep
from tests.factories import make_ps_step, make_user


def _write_gpano_jpeg(path: Path) -> None:
    image = Image.new("RGB", (300, 100), color="red")
    buffer = io.BytesIO()
    image.save(buffer, "JPEG")
    xmp = (
        b'<x:xmpmeta xmlns:x="adobe:ns:meta/">'
        b'<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
        b'<rdf:Description xmlns:GPano="http://ns.google.com/photos/1.0/panorama/" '
        b'GPano:ProjectionType="cylindrical" '
        b'GPano:CroppedAreaImageWidthPixels="300" '
        b'GPano:CroppedAreaImageHeightPixels="100" '
        b'GPano:FullPanoWidthPixels="400" '
        b'GPano:FullPanoHeightPixels="100" />'
        b"</rdf:RDF></x:xmpmeta>"
    )
    payload = b"http://ns.adobe.com/xap/1.0/\x00" + xmp
    app1 = b"\xff\xe1" + (len(payload) + 2).to_bytes(2, "big") + payload
    jpeg = buffer.getvalue()
    path.write_bytes(jpeg[:2] + app1 + jpeg[2:])


class TestDefaultMediaResolutionWarningPreset:
    def test_uses_standard_preset_for_normal_users(self) -> None:
        user = make_user(1, google_sub="test-sub")

        assert (
            default_media_resolution_warning_preset(user)
            == DEFAULT_MEDIA_RESOLUTION_WARNING_PRESET
        )

    def test_uses_demo_preset_for_demo_users(self) -> None:
        user = make_user(1, first_name="Demo", is_demo=True)

        assert (
            default_media_resolution_warning_preset(user)
            == DEMO_MEDIA_RESOLUTION_WARNING_PRESET
        )


def test_zip_panorama_uses_existing_media_as_authoritative_original(
    tmp_path: Path,
) -> None:
    media_name = "panorama.jpg"
    _write_gpano_jpeg(tmp_path / media_name)

    rows = build_album_media_rows(
        1,
        "trip-1",
        tmp_path,
        [Media(name=media_name, width=300, height=100)],
    )

    assert rows[0].panorama is not None
    assert rows[0].panorama.original_path == media_name
    assert not (tmp_path / ".panoramas").exists()


def _step(name: str, country_code: str, timestamp: float = 0) -> PSStep:
    return make_ps_step(
        int(timestamp),
        name=name,
        description="",
        timestamp=timestamp,
        location=Location(
            name=name, detail="", country_code=country_code, lat=0, lon=0
        ),
    )


class TestResolveInternationalWaters:
    def test_replaces_with_previous_code(self) -> None:
        steps = [
            _step("Tortuga Bay", "EC", 1),
            _step("Gordon Rocks", "00", 2),
            _step("Camino de Tortugas", "EC", 3),
        ]
        resolve_international_waters(steps)
        assert steps[1].location.country_code == "ec"

    def test_multiple_consecutive_zeros(self) -> None:
        steps = [
            _step("Naples", "IT", 1),
            _step("At Sea 1", "00", 2),
            _step("At Sea 2", "00", 3),
            _step("Sorrento", "IT", 4),
        ]
        resolve_international_waters(steps)
        assert steps[1].location.country_code == "it"
        assert steps[2].location.country_code == "it"

    def test_attribution_when_next_country_differs(self) -> None:
        steps = [
            _step("Piraeus", "GR", 1),
            _step("At Sea", "00", 2),
            _step("Kusadasi", "TR", 3),
        ]
        resolve_international_waters(steps)

        assert steps[1].location.country_code == "gr"

    def test_leading_zeros_unchanged(self) -> None:
        steps = [
            _step("At Sea", "00", 1),
            _step("Naples", "IT", 2),
        ]
        resolve_international_waters(steps)
        assert steps[0].location.country_code == "00"

    def test_trailing_zeros(self) -> None:
        steps = [
            _step("Naples", "IT", 1),
            _step("At Sea", "00", 2),
        ]
        resolve_international_waters(steps)
        assert steps[1].location.country_code == "it"


class TestSegmentTimezone:
    def test_picks_step_before_segment_start(self) -> None:
        steps = [
            _step("A", "CL", 100),
            _step("B", "CL", 200),
            _step("C", "CL", 400),
        ]
        steps[0].timezone_id = "America/Santiago"
        steps[1].timezone_id = "America/Santiago"
        steps[2].timezone_id = "America/Buenos_Aires"
        assert segment_timezone(250, steps) == "America/Santiago"

    def test_falls_back_to_first_step(self) -> None:
        steps = [_step("A", "CL", 500)]
        steps[0].timezone_id = "America/Santiago"
        assert segment_timezone(100, steps) == "America/Santiago"
