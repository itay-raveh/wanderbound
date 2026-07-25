from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError

from app.core.worker_threads import run_sync
from app.logic.panorama.render import (
    PanoramaDestination,
    PanoramaRenderError,
    PanoramaValidationError,
    render_panorama,
)
from app.models.album_media import PanoramaConfig
from tests.factories import create_test_jpeg


def _config(**updates: object) -> PanoramaConfig:
    values: dict[str, object] = {
        "status": "active",
        "detection": "gpano",
        "source_width": 1600,
        "source_height": 800,
        "captured_fov": 180,
        "yaw": 12,
        "pitch": -3,
        "perspective_fov": 60,
        "zoom": 2,
    }
    return PanoramaConfig.model_validate(values | updates)


def _destination(**updates: object) -> PanoramaDestination:
    values: dict[str, object] = {
        "kind": "grid",
        "aspect_ratio": 2,
        "width_px": 800,
        "height_px": 400,
    }
    return PanoramaDestination.model_validate(values | updates)


async def test_render_uses_perspective_then_separate_zoom_stage(
    tmp_path: Path,
) -> None:
    source = create_test_jpeg(tmp_path / "source.jpg", 1600, 800)
    output = tmp_path / "frame.jpg"
    command: list[object] = []

    class Process:
        returncode = 0

        async def communicate(self) -> tuple[bytes, bytes]:
            await run_sync(Path(command[-1]).write_bytes, b"new frame")
            return b"", b""

    async def create_process(*args: object, **_kwargs: object) -> Process:
        command.extend(args)
        return Process()

    with patch(
        "app.logic.panorama.render.asyncio.create_subprocess_exec",
        side_effect=create_process,
    ):
        await render_panorama(source, _config(), _destination(), output)

    filter_graph = command[command.index("-vf") + 1]
    assert filter_graph == (
        "v360=input=cylindrical:output=flat:ih_fov=180:yaw=12:pitch=-3:"
        "h_fov=60:w=800:h=400,"
        "crop=iw/2:ih/2:(iw-iw/2)/2:(ih-ih/2)/2,"
        "scale=800:400:flags=lanczos"
    )
    assert command[0] == "ffmpeg"
    assert command[command.index("-i") + 1] == str(source)
    assert output.read_bytes() == b"new frame"


async def test_zoom_one_has_no_post_projection_crop(tmp_path: Path) -> None:
    source = create_test_jpeg(tmp_path / "source.jpg", 1600, 800)
    output = tmp_path / "frame.jpg"
    command: list[object] = []

    class Process:
        returncode = 0

        async def communicate(self) -> tuple[bytes, bytes]:
            await run_sync(Path(command[-1]).write_bytes, b"frame")
            return b"", b""

    async def create_process(*args: object, **_kwargs: object) -> Process:
        command.extend(args)
        return Process()

    with patch(
        "app.logic.panorama.render.asyncio.create_subprocess_exec",
        side_effect=create_process,
    ):
        await render_panorama(
            source,
            _config(zoom=1),
            _destination(),
            output,
        )

    filter_graph = command[command.index("-vf") + 1]
    assert filter_graph == (
        "v360=input=cylindrical:output=flat:ih_fov=180:yaw=12:pitch=-3:"
        "h_fov=60:w=800:h=400"
    )


async def test_out_of_bounds_frame_fails_before_subprocess(tmp_path: Path) -> None:
    source = create_test_jpeg(tmp_path / "source.jpg", 1600, 800)
    create_process = AsyncMock()

    with (
        patch(
            "app.logic.panorama.render.asyncio.create_subprocess_exec",
            create_process,
        ),
        pytest.raises(PanoramaValidationError, match="yaw"),
    ):
        await render_panorama(
            source,
            _config(yaw=70),
            _destination(),
            tmp_path / "frame.jpg",
        )

    create_process.assert_not_awaited()


def test_destination_rejects_unsafe_dimensions() -> None:
    with pytest.raises(ValidationError):
        _destination(width_px=20_000)


async def test_failed_render_preserves_existing_output(tmp_path: Path) -> None:
    source = create_test_jpeg(tmp_path / "source.jpg", 1600, 800)
    output = tmp_path / "frame.jpg"
    output.write_bytes(b"previous frame")

    process = AsyncMock()
    process.returncode = 1
    process.communicate.return_value = (b"", b"invalid projection")

    with (
        patch(
            "app.logic.panorama.render.asyncio.create_subprocess_exec",
            AsyncMock(return_value=process),
        ),
        pytest.raises(PanoramaRenderError, match="invalid projection"),
    ):
        await render_panorama(source, _config(), _destination(), output)

    assert output.read_bytes() == b"previous frame"
    assert await run_sync(lambda: list(tmp_path.glob(".frame.*.jpg"))) == []
