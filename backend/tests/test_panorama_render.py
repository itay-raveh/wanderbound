from pathlib import Path

import pytest
from PIL import Image

from app.logic.panorama import (
    PanoramaValidationError,
    _filter_graph,
    _output_size,
    _validate_frame,
    create_panorama_source,
    panorama_render_path,
    panorama_source_path,
    render_panorama,
    resolve_panorama_source,
)
from app.models.album_media import PanoramaConfig, panorama_captured_fov


def _config(**updates: float) -> PanoramaConfig:
    return PanoramaConfig.model_validate(
        {
            "yaw": 0,
            "pitch": 0,
            "perspective_fov": 60,
            "zoom": 1,
            "aspect_ratio": 2,
        }
        | updates
    )


def _source(path: Path) -> None:
    Image.new("RGB", (400, 200), "steelblue").save(path)


def test_captured_fov_is_derived_from_aspect_ratio() -> None:
    assert panorama_captured_fov(400, 200) == 180
    assert panorama_captured_fov(1200, 200) == 359


@pytest.mark.parametrize(
    "config",
    [
        _config(yaw=61),
        _config(pitch=30),
    ],
)
def test_frame_rejects_views_outside_source(config: PanoramaConfig) -> None:
    with pytest.raises(PanoramaValidationError):
        _validate_frame(config, 400, 200)


def test_filter_keeps_perspective_and_zoom_independent() -> None:
    config = _config(perspective_fov=55, zoom=1.8)

    graph = _filter_graph(config, 400, 200, _output_size(400, config.aspect_ratio))

    assert "h_fov=55" in graph
    assert "crop=iw/1.8:ih/1.8" in graph


async def test_source_and_poster_render_with_ffmpeg(tmp_path: Path) -> None:
    source = tmp_path / "source.jpg"
    preview = tmp_path / "preview.jpg"
    output = tmp_path / "frame.jpg"
    _source(source)

    await create_panorama_source(source, preview, 400, 200)
    await render_panorama(source, _config(), output, (400, 200))

    with Image.open(preview) as image:
        assert image.size == (800, 400)
    with Image.open(output) as image:
        assert image.size == (400, 200)


async def test_poster_yaw_matches_the_interactive_viewer(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    output = tmp_path / "frame.jpg"
    image = Image.new("RGB", (400, 200), "red")
    image.paste("blue", (200, 0, 400, 200))
    image.save(source)

    await render_panorama(
        source,
        _config(yaw=30, perspective_fov=20),
        output,
        (400, 200),
    )

    with Image.open(output) as poster:
        center = poster.convert("RGB").crop((200, 100, 201, 101)).tobytes()
    assert center[0] > center[2]


def test_cached_files_track_source_and_frame(tmp_path: Path) -> None:
    source = tmp_path / "source.jpg"
    _source(source)
    initial_source = panorama_source_path(tmp_path, "source.jpg", source)
    initial_poster = panorama_render_path(tmp_path, "source.jpg", source, _config())

    source.write_bytes(source.read_bytes() + b"x")

    assert panorama_source_path(tmp_path, "source.jpg", source) != initial_source
    assert (
        panorama_render_path(tmp_path, "source.jpg", source, _config())
        != initial_poster
    )
    assert (
        panorama_render_path(
            tmp_path,
            "source.jpg",
            source,
            _config(aspect_ratio=1.5),
        )
        != initial_poster
    )


def test_source_must_stay_inside_album(tmp_path: Path) -> None:
    album = tmp_path / "album"
    album.mkdir()
    outside = tmp_path / "outside.jpg"
    _source(outside)

    with pytest.raises(FileNotFoundError):
        resolve_panorama_source(album, "../outside.jpg")
