from __future__ import annotations

import asyncio
from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock, patch

import pytest
from PIL import Image, ImageDraw
from pydantic import ValidationError

from app.core.worker_threads import run_sync
from app.logic.panorama.render import (
    PanoramaDestination,
    PanoramaFrameUpdate,
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
        "v360=input=cylindrical:output=flat:ih_fov=180:iv_fov=76.2921:"
        "yaw=12:pitch=-3:h_fov=60:v_fov=32.2042:w=800:h=400,"
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
        "v360=input=cylindrical:output=flat:ih_fov=180:iv_fov=76.2921:"
        "yaw=12:pitch=-3:h_fov=60:v_fov=32.2042:w=800:h=400"
    )


@pytest.mark.parametrize(
    ("cropped_top", "pitch", "expected_vertical_options"),
    [
        (
            0,
            -20,
            "format=gbrp,pad=width=iw:height=200:x=0:y=100:color=black,"
            "fillborders=top=100:bottom=0:mode=smear,"
            "v360=input=cylindrical:output=flat:ih_fov=270:iv_fov=115.037:"
            "yaw=12:pitch=-20:h_fov=30:v_fov=15.2615:w=800:h=400",
        ),
        (
            -25,
            0,
            "format=gbrp,pad=width=iw:height=150:x=0:y=50:color=black,"
            "fillborders=top=50:bottom=0:mode=smear,"
            "v360=input=cylindrical:output=flat:ih_fov=270:iv_fov=99.349:"
            "yaw=12:pitch=0:h_fov=30:v_fov=15.2615:w=800:h=400",
        ),
    ],
)
async def test_gpano_crop_position_sets_virtual_canvas_and_vertical_fov(
    tmp_path: Path,
    cropped_top: int,
    pitch: float,
    expected_vertical_options: str,
) -> None:
    source = create_test_jpeg(tmp_path / "source.jpg", 300, 100)
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

    config = _config(
        source_width=300,
        source_height=100,
        cropped_area_width=300,
        cropped_area_height=100,
        cropped_area_top=cropped_top,
        full_pano_width=400,
        full_pano_height=None,
        captured_fov=270,
        pitch=pitch,
        perspective_fov=30,
        zoom=1,
    )
    with patch(
        "app.logic.panorama.render.asyncio.create_subprocess_exec",
        side_effect=create_process,
    ):
        await render_panorama(source, config, _destination(), output)

    filter_graph = command[command.index("-vf") + 1]
    assert filter_graph == expected_vertical_options


async def test_gpano_world_horizon_maps_to_viewport_center_without_padding(
    tmp_path: Path,
) -> None:
    source = tmp_path / "calibrated.jpg"
    image = Image.new("RGB", (300, 101), color=(30, 220, 30))
    ImageDraw.Draw(image).rectangle((0, 22, 299, 28), fill=(240, 20, 240))
    image.save(source, quality=100, subsampling=2)
    output = tmp_path / "frame.jpg"
    config = _config(
        source_width=300,
        source_height=101,
        cropped_area_width=300,
        cropped_area_height=101,
        cropped_area_top=-25,
        full_pano_width=400,
        full_pano_height=None,
        captured_fov=270,
        yaw=0,
        pitch=0,
        perspective_fov=10,
        zoom=1,
    )

    await render_panorama(
        source,
        config,
        _destination(aspect_ratio=1, width_px=101, height_px=101),
        output,
    )

    with Image.open(output) as rendered:
        center = cast("tuple[int, int, int]", rendered.getpixel((50, 50)))
        assert center[0] > 180
        assert center[1] < 80
        assert center[2] > 180
        assert min(max(pixel) for pixel in rendered.get_flattened_data()) > 100


@pytest.mark.parametrize(
    ("cropped_top", "pitch", "sample_y"),
    [
        pytest.param(-25, -45.04851935710306, 100, id="odd-offset-min"),
        pytest.param(-25, 16.43989050175506, 0, id="odd-offset-max"),
        pytest.param(-76, -16.43989050175506, 100, id="bottom-padding-min"),
        pytest.param(-76, 45.04851935710306, 0, id="bottom-padding-max"),
    ],
)
async def test_gpano_pitch_boundary_preserves_source_edge_color(
    tmp_path: Path,
    cropped_top: int,
    pitch: float,
    sample_y: int,
) -> None:
    source = tmp_path / "uniform.jpg"
    Image.new("RGB", (300, 101), color=(40, 220, 40)).save(
        source,
        quality=100,
        subsampling=2,
    )
    output = tmp_path / "frame.jpg"
    config = _config(
        source_width=300,
        source_height=101,
        cropped_area_width=300,
        cropped_area_height=101,
        cropped_area_top=cropped_top,
        full_pano_width=400,
        full_pano_height=None,
        captured_fov=270,
        yaw=0,
        pitch=pitch,
        perspective_fov=10,
        zoom=1,
    )

    await render_panorama(
        source,
        config,
        _destination(aspect_ratio=1, width_px=101, height_px=101),
        output,
    )

    with Image.open(output) as rendered:
        edge = cast("tuple[int, int, int]", rendered.getpixel((50, sample_y)))
        assert all(
            abs(actual - expected) <= 15
            for actual, expected in zip(edge, (40, 220, 40), strict=True)
        ), edge


async def test_gpano_crop_position_enforces_asymmetric_pitch_bounds(
    tmp_path: Path,
) -> None:
    source = create_test_jpeg(tmp_path / "source.jpg", 300, 100)
    create_process = AsyncMock()

    with (
        patch(
            "app.logic.panorama.render.asyncio.create_subprocess_exec",
            create_process,
        ),
        pytest.raises(PanoramaValidationError, match="pitch"),
    ):
        await render_panorama(
            source,
            _config(
                source_width=300,
                source_height=100,
                cropped_area_width=300,
                cropped_area_height=100,
                cropped_area_top=0,
                full_pano_width=400,
                full_pano_height=None,
                captured_fov=270,
                pitch=0,
                perspective_fov=30,
            ),
            _destination(),
            tmp_path / "frame.jpg",
        )

    create_process.assert_not_awaited()


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


def test_frame_rejects_zoom_above_finite_limit() -> None:
    with pytest.raises(ValidationError):
        PanoramaFrameUpdate(
            yaw=0,
            pitch=0,
            perspective_fov=60,
            zoom=8193,
        )


async def test_zoom_rejects_non_positive_crop_before_subprocess(
    tmp_path: Path,
) -> None:
    source = create_test_jpeg(tmp_path / "source.jpg", 1600, 800)
    create_process = AsyncMock()

    with (
        patch(
            "app.logic.panorama.render.asyncio.create_subprocess_exec",
            create_process,
        ),
        pytest.raises(PanoramaValidationError, match="zoom"),
    ):
        await render_panorama(
            source,
            _config(zoom=401),
            _destination(),
            tmp_path / "frame.jpg",
        )

    create_process.assert_not_awaited()


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


async def test_cancelled_render_kills_and_reaps_subprocess(tmp_path: Path) -> None:
    source = create_test_jpeg(tmp_path / "source.jpg", 1600, 800)
    output = tmp_path / "frame.jpg"
    output.write_bytes(b"previous frame")
    started = asyncio.Event()

    class Process:
        returncode: int | None = None
        communicate_calls = 0
        killed = False
        reaped = False

        async def communicate(self) -> tuple[bytes, bytes]:
            self.communicate_calls += 1
            if self.communicate_calls == 1:
                started.set()
                await asyncio.Event().wait()
            self.reaped = True
            return b"", b""

        def kill(self) -> None:
            self.killed = True
            self.returncode = -9

    process = Process()
    with patch(
        "app.logic.panorama.render.asyncio.create_subprocess_exec",
        AsyncMock(return_value=process),
    ):
        task = asyncio.create_task(
            render_panorama(source, _config(), _destination(), output)
        )
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    assert process.killed
    assert process.reaped
    assert output.read_bytes() == b"previous frame"
    assert await run_sync(lambda: list(tmp_path.glob(".frame.*.jpg"))) == []
