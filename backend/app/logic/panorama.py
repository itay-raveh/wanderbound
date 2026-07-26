from __future__ import annotations

import asyncio
import hashlib
import math
import secrets
import shutil
from contextlib import suppress
from pathlib import Path

from app.core.worker_threads import run_sync
from app.logic.layout.media import media_limiter
from app.models.album_media import PanoramaConfig, panorama_captured_fov

MAX_PANORAMA_DIMENSION = 8192
_PREVIEW_MAX_WIDTH = 2048
_RENDER_TIMEOUT_SECONDS = 60


class PanoramaRenderError(RuntimeError):
    pass


class PanoramaValidationError(ValueError):
    pass


def resolve_panorama_source(album_dir: Path, media_name: str) -> Path:
    source = (album_dir / media_name).resolve()
    if not source.is_relative_to(album_dir.resolve()) or not source.is_file():
        raise FileNotFoundError(media_name)
    return source


def panorama_source_path(
    album_dir: Path,
    media_name: str,
    source: Path,
) -> Path:
    return _panorama_dir(album_dir, media_name) / f"source-{_source_key(source)}.jpg"


def panorama_render_path(
    album_dir: Path,
    media_name: str,
    source: Path,
    config: PanoramaConfig,
) -> Path:
    key = hashlib.sha256(
        f"{_source_key(source)}:{config.model_dump_json()}".encode()
    ).hexdigest()[:16]
    return _panorama_dir(album_dir, media_name) / f"poster-{key}.jpg"


def remove_panorama_derivatives(album_dir: Path, media_name: str) -> None:
    shutil.rmtree(_panorama_dir(album_dir, media_name), ignore_errors=True)


def remove_other_panorama_files(keep: Path) -> None:
    prefix = keep.name.split("-", 1)[0]
    for path in keep.parent.glob(f"{prefix}-*.jpg"):
        if path != keep:
            path.unlink(missing_ok=True)


async def render_panorama(
    source: Path,
    config: PanoramaConfig,
    output: Path,
    source_size: tuple[int, int],
) -> None:
    source_width, source_height = source_size
    output_size = _output_size(source_width, config.aspect_ratio)
    _validate_frame(config, source_width, source_height, output_size)
    await _render_image(
        source,
        _filter_graph(config, source_width, source_height, output_size),
        output,
    )


async def create_panorama_source(
    source: Path,
    output: Path,
    source_width: int,
    source_height: int,
) -> None:
    captured_fov = panorama_captured_fov(source_width, source_height)
    width = min(_PREVIEW_MAX_WIDTH, round(source_width * 360 / captured_fov))
    width -= width % 2
    vertical_fov = 2 * _source_vertical_half_fov(
        source_width,
        source_height,
        captured_fov,
    )
    await _render_image(
        source,
        (
            "v360=input=cylindrical:output=equirect:"
            f"ih_fov={_number(captured_fov)}:"
            f"iv_fov={_number(vertical_fov)}:"
            f"w={width}:h={width // 2}"
        ),
        output,
    )


def _panorama_dir(album_dir: Path, media_name: str) -> Path:
    return album_dir / ".panoramas" / Path(media_name).stem


def _source_key(source: Path) -> str:
    stat = source.stat()
    return f"{stat.st_size:x}-{stat.st_mtime_ns:x}"


def _output_size(source_width: int, aspect_ratio: float) -> tuple[int, int]:
    width = min(source_width, MAX_PANORAMA_DIMENSION)
    height = round(width / aspect_ratio)
    if height > MAX_PANORAMA_DIMENSION:
        height = MAX_PANORAMA_DIMENSION
        width = round(height * aspect_ratio)
    return max(2, width - width % 2), max(2, height - height % 2)


def _validate_frame(
    config: PanoramaConfig,
    source_width: int,
    source_height: int,
    output_size: tuple[int, int],
) -> None:
    captured_fov = panorama_captured_fov(source_width, source_height)
    if config.perspective_fov > captured_fov:
        raise PanoramaValidationError("Perspective FOV exceeds the captured panorama")
    if abs(config.yaw) > (captured_fov - config.perspective_fov) / 2:
        raise PanoramaValidationError("Panorama yaw is outside the captured bounds")

    source_vertical_half = _source_vertical_half_fov(
        source_width,
        source_height,
        captured_fov,
    )
    output_vertical_half = _output_vertical_fov(config) / 2
    if abs(config.pitch) > source_vertical_half - output_vertical_half:
        raise PanoramaValidationError("Panorama pitch is outside the captured bounds")
    if config.zoom > min(output_size):
        raise PanoramaValidationError("Panorama zoom produces an empty crop")


def _filter_graph(
    config: PanoramaConfig,
    source_width: int,
    source_height: int,
    output_size: tuple[int, int],
) -> str:
    width, height = output_size
    captured_fov = panorama_captured_fov(source_width, source_height)
    vertical_fov = 2 * _source_vertical_half_fov(
        source_width,
        source_height,
        captured_fov,
    )
    projection = (
        "v360=input=cylindrical:output=flat:"
        f"ih_fov={_number(captured_fov)}:"
        f"iv_fov={_number(vertical_fov)}:"
        f"yaw={_number(-config.yaw)}:"
        f"pitch={_number(config.pitch)}:"
        f"h_fov={_number(config.perspective_fov)}:"
        f"v_fov={_number(_output_vertical_fov(config))}:"
        f"w={width}:h={height}"
    )
    if config.zoom == 1:
        return projection
    zoom = _number(config.zoom)
    return (
        f"{projection},"
        f"crop=iw/{zoom}:ih/{zoom}:(iw-iw/{zoom})/2:(ih-ih/{zoom})/2,"
        f"scale={width}:{height}:flags=lanczos"
    )


def _source_vertical_half_fov(
    source_width: int,
    source_height: int,
    captured_fov: float,
) -> float:
    focal_length = source_width / math.radians(captured_fov)
    return math.degrees(math.atan(source_height / 2 / focal_length))


def _output_vertical_fov(config: PanoramaConfig) -> float:
    return 2 * math.degrees(
        math.atan(
            math.tan(math.radians(config.perspective_fov / 2)) / config.aspect_ratio
        )
    )


async def _render_image(source: Path, filter_graph: str, output: Path) -> None:
    async with media_limiter:
        await run_sync(output.parent.mkdir, parents=True, exist_ok=True)
        temporary = output.parent / f".{output.stem}.{secrets.token_hex(8)}.jpg"
        process: asyncio.subprocess.Process | None = None
        try:
            process = await asyncio.create_subprocess_exec(
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-nostdin",
                "-y",
                "-i",
                str(source),
                "-frames:v",
                "1",
                "-vf",
                filter_graph,
                "-q:v",
                "2",
                str(temporary),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                _stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=_RENDER_TIMEOUT_SECONDS,
                )
            except TimeoutError as error:
                raise PanoramaRenderError("Panorama rendering timed out") from error
            await _check_render_result(process, stderr, temporary)
            await run_sync(temporary.replace, output)
        except OSError as error:
            raise PanoramaRenderError(
                "Unable to run FFmpeg panorama rendering"
            ) from error
        except BaseException:
            await _kill_and_reap(process)
            raise
        finally:
            await run_sync(temporary.unlink, missing_ok=True)


async def _kill_and_reap(process: asyncio.subprocess.Process | None) -> None:
    if process is None or process.returncode is not None:
        return
    with suppress(ProcessLookupError):
        process.kill()
    await process.communicate()


async def _check_render_result(
    process: asyncio.subprocess.Process,
    stderr: bytes,
    output: Path,
) -> None:
    if process.returncode != 0:
        detail = stderr.decode(errors="replace").strip()
        raise PanoramaRenderError(detail or "FFmpeg failed to render panorama")
    if not await run_sync(output.is_file):
        raise PanoramaRenderError("FFmpeg did not produce a panorama image")


def _number(value: float) -> str:
    return format(value, "g")
