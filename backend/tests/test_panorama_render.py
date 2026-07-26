from __future__ import annotations

import asyncio
from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock, patch

import anyio
import pytest
from PIL import Image, ImageChops, ImageDraw, ImageStat
from pydantic import ValidationError

from app.core.worker_threads import run_sync
from app.logic.panorama.render import (
    PanoramaDestination,
    PanoramaFrameUpdate,
    PanoramaRenderError,
    PanoramaValidationError,
    create_panorama_preview,
    panorama_preview_path,
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


async def test_preview_is_full_equirectangular_for_sphere_projection(
    tmp_path: Path,
) -> None:
    source = create_test_jpeg(tmp_path / "source.jpg", 300, 64)
    output = tmp_path / "preview.jpg"
    config = _config(
        source_width=300,
        source_height=64,
        cropped_area_width=300,
        cropped_area_height=64,
        cropped_area_top=-32,
        captured_fov=270,
    )

    await create_panorama_preview(source, config, output)

    with Image.open(output) as preview:
        assert preview.size == (400, 200)


async def test_preview_keeps_tall_source_edges_outside_partial_cylinder_height(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.png"
    image = Image.new("RGB", (400, 200), color=(30, 220, 30))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 399, 19), fill=(240, 20, 20))
    draw.rectangle((0, 180, 399, 199), fill=(20, 20, 240))
    image.save(source)
    output = tmp_path / "preview.jpg"
    config = _config(
        detection="dimensions",
        source_width=400,
        source_height=200,
        captured_fov=180,
    )

    await create_panorama_preview(source, config, output)

    with Image.open(output) as preview:
        assert preview.size == (800, 400)
        center_column = [
            cast("tuple[int, int, int]", preview.getpixel((400, y)))
            for y in range(preview.height)
        ]
        assert any(
            red > 180 and green < 80 and blue < 80 for red, green, blue in center_column
        )
        assert any(
            blue > 180 and red < 80 and green < 80 for red, green, blue in center_column
        )


async def test_preview_reprojects_to_the_same_allowed_frame_as_source(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.png"
    image = Image.new("RGB", (400, 200), color=(30, 220, 30))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 199, 99), fill=(240, 20, 20))
    draw.rectangle((200, 100, 399, 199), fill=(20, 20, 240))
    image.save(source)
    preview = tmp_path / "preview.jpg"
    direct = tmp_path / "direct.jpg"
    through_preview = tmp_path / "through-preview.jpg"
    config = _config(
        detection="dimensions",
        source_width=400,
        source_height=200,
        captured_fov=180,
        yaw=-20,
        pitch=8,
        perspective_fov=60,
        zoom=1,
    )
    destination = _destination(width_px=200, height_px=100)

    await create_panorama_preview(source, config, preview)
    await render_panorama(source, config, destination, direct)
    process = await asyncio.create_subprocess_exec(
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        "-y",
        "-i",
        str(preview),
        "-frames:v",
        "1",
        "-vf",
        "v360=input=equirect:output=flat:yaw=-20:pitch=8:"
        "h_fov=60:v_fov=32.2042:w=200:h=100",
        str(through_preview),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _stdout, stderr = await process.communicate()
    assert process.returncode == 0, stderr.decode(errors="replace")

    with Image.open(direct) as expected, Image.open(through_preview) as actual:
        difference = ImageChops.difference(
            expected.convert("RGB"),
            actual.convert("RGB"),
        )
        assert max(ImageStat.Stat(difference).mean) < 8


async def test_preview_ffmpeg_processes_obey_media_concurrency_limit(
    tmp_path: Path,
) -> None:
    source = create_test_jpeg(tmp_path / "source.jpg", 400, 200)
    release = asyncio.Event()
    first_started = asyncio.Event()
    commands: list[tuple[object, ...]] = []

    class Process:
        returncode = 0

        def __init__(self, output: Path) -> None:
            self.output = output

        async def communicate(self) -> tuple[bytes, bytes]:
            first_started.set()
            await release.wait()
            await run_sync(self.output.write_bytes, b"preview")
            return b"", b""

    async def create_process(*args: object, **_kwargs: object) -> Process:
        commands.append(args)
        return Process(Path(cast("str", args[-1])))

    with (
        patch(
            "app.logic.panorama.render.asyncio.create_subprocess_exec",
            side_effect=create_process,
        ),
        patch(
            "app.logic.panorama.render.media_limiter",
            anyio.CapacityLimiter(1),
            create=True,
        ),
    ):
        tasks = [
            asyncio.create_task(
                create_panorama_preview(
                    source,
                    _config(source_width=400, source_height=200),
                    tmp_path / f"preview-{index}.jpg",
                )
            )
            for index in range(2)
        ]
        try:
            await first_started.wait()
            await asyncio.sleep(0)
            assert len(commands) == 1
        finally:
            release.set()
            await asyncio.gather(*tasks)

    assert len(commands) == 2


async def test_duplicate_preview_misses_share_one_render(tmp_path: Path) -> None:
    source = create_test_jpeg(tmp_path / "source.jpg", 400, 200)
    output = tmp_path / "preview.jpg"
    started = asyncio.Event()
    release = asyncio.Event()
    renders = 0

    async def render(_source: Path, _filter: str, target: Path) -> None:
        nonlocal renders
        renders += 1
        started.set()
        await release.wait()
        await run_sync(target.write_bytes, b"preview")

    with patch("app.logic.panorama.render._render_image", side_effect=render):
        tasks = [
            asyncio.create_task(
                create_panorama_preview(
                    source,
                    _config(source_width=400, source_height=200),
                    output,
                )
            )
            for _index in range(2)
        ]
        try:
            await started.wait()
            await asyncio.sleep(0)
        finally:
            release.set()
            await asyncio.gather(*tasks)

    assert renders == 1
    assert output.read_bytes() == b"preview"


async def test_preview_places_gpano_horizon_at_canvas_center(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    image = Image.new("RGB", (300, 101), color=(30, 220, 30))
    ImageDraw.Draw(image).rectangle((0, 22, 299, 28), fill=(240, 20, 240))
    image.save(source)
    output = tmp_path / "preview.jpg"
    config = _config(
        source_width=300,
        source_height=101,
        cropped_area_width=300,
        cropped_area_height=101,
        cropped_area_top=-25,
        captured_fov=270,
    )

    await create_panorama_preview(source, config, output)

    with Image.open(output) as preview:
        center = cast(
            "tuple[int, int, int]", preview.getpixel((150, preview.height // 2))
        )
        assert center[0] > 180
        assert center[1] < 80
        assert center[2] > 180


async def test_preview_extends_source_edges_into_vertical_padding(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.png"
    Image.new("RGB", (300, 21), color=(40, 220, 40)).save(source)
    output = tmp_path / "preview.jpg"
    config = _config(
        source_width=300,
        source_height=21,
        cropped_area_width=300,
        cropped_area_height=21,
        cropped_area_top=-10,
        captured_fov=270,
    )

    await create_panorama_preview(source, config, output)

    with Image.open(output) as preview:
        for y in (0, preview.height - 1):
            edge = cast("tuple[int, int, int]", preview.getpixel((150, y)))
            assert all(
                abs(actual - expected) <= 15
                for actual, expected in zip(edge, (40, 220, 40), strict=True)
            )


def test_preview_cache_key_tracks_source_and_projection_config(tmp_path: Path) -> None:
    source = create_test_jpeg(tmp_path / "source.jpg", 300, 64)
    album_dir = tmp_path / "album"
    config = _config(source_width=300, source_height=64, captured_fov=180)

    initial = panorama_preview_path(album_dir, "source.jpg", source, config)
    coverage_changed = panorama_preview_path(
        album_dir,
        "source.jpg",
        source,
        config.model_copy(update={"captured_fov": 270}),
    )
    source.write_bytes(source.read_bytes() + b"changed")
    source_changed = panorama_preview_path(album_dir, "source.jpg", source, config)

    assert initial != coverage_changed
    assert initial != source_changed


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


def test_frame_rejects_fractional_captured_fov() -> None:
    with pytest.raises(ValidationError):
        PanoramaFrameUpdate(
            yaw=0,
            pitch=0,
            perspective_fov=60,
            zoom=1,
            captured_fov=180.5,
        )


def test_persisted_config_canonicalizes_fractional_captured_fov() -> None:
    config = _config(captured_fov=180.5)

    assert config.captured_fov == 181
    assert isinstance(config.captured_fov, int)


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
