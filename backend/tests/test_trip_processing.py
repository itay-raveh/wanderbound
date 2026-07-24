"""Tests for app.logic.trip_processing."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pytest

from app.logic.layout import Layout
from app.logic.layout.media import Media
from app.logic.trip_processing import (
    _media_pipeline,
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


def test_build_album_media_rows_includes_precomputed_hashes(tmp_path: Path) -> None:
    name = "photo.jpg"
    (tmp_path / name).write_bytes(b"photo")

    rows = build_album_media_rows(
        1,
        "album",
        tmp_path,
        [Media(name=name, width=800, height=600)],
        perceptual_hashes_by_name={name: ["0123456789abcdef"]},
    )

    assert rows[0].perceptual_hashes == ["0123456789abcdef"]


async def test_media_pipeline_precomputes_hashes_after_flattening(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    photo = Media(
        name="photo.jpg",
        width=800,
        height=600,
        perceptual_hashes=["0123456789abcdef"],
    )
    video = Media(name="video.mp4", width=800, height=600)
    layout = Layout("photo.jpg", [["video.mp4"]], [photo, video])

    async def fake_fetch(*_args: object) -> AsyncIterator[tuple[int, Layout]]:
        yield 0, layout

    async def fake_prepare(_trip_dir: Path, cover_name: str) -> tuple[str, str]:
        return cover_name, "l"

    monkeypatch.setattr("app.logic.trip_processing.fetch_layouts", fake_fetch)
    monkeypatch.setattr("app.logic.trip_processing.prepare_media", fake_prepare)
    hashed_paths: list[Path] = []

    def fake_hashes(paths: list[Path]) -> dict[str, list[str]]:
        hashed_paths.extend(paths)
        return {path.name: ["fedcba9876543210"] for path in paths}

    monkeypatch.setattr(
        "app.logic.trip_processing.compute_serialized_media_hashes", fake_hashes
    )

    _, _, hashes = await _media_pipeline(
        make_user(1),
        SimpleNamespace(all_steps=[make_ps_step()]),
        tmp_path,
        "photo.jpg",
        asyncio.Queue(),
    )

    assert hashed_paths == [tmp_path / "video.mp4"]
    assert hashes == {
        "photo.jpg": ["0123456789abcdef"],
        "video.mp4": ["fedcba9876543210"],
    }


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
