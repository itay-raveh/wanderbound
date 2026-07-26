from __future__ import annotations

import asyncio
import hashlib
import json
import math
import secrets
from contextlib import suppress
from pathlib import Path

from pydantic import BaseModel, Field, model_validator

from app.core.locks import file_generation_lock
from app.core.worker_threads import run_sync
from app.logic.layout.media import media_limiter
from app.models.album_media import MAX_CAPTURED_FOV, MIN_CAPTURED_FOV, PanoramaConfig

_MAX_OUTPUT_DIMENSION = 8192
_MAX_OUTPUT_PIXELS = 8192 * 4096
_PREVIEW_MAX_WIDTH = 2048
_PREVIEW_FORMAT_VERSION = 2
_RENDER_TIMEOUT_SECONDS = 60


class PanoramaRenderError(RuntimeError):
    pass


class PanoramaValidationError(ValueError):
    pass


class PanoramaFrameUpdate(BaseModel):
    yaw: float = Field(ge=-360, le=360)
    pitch: float = Field(ge=-90, le=90)
    perspective_fov: float = Field(gt=0, lt=180)
    zoom: float = Field(ge=1, le=_MAX_OUTPUT_DIMENSION)
    captured_fov: int | None = Field(
        default=None,
        ge=MIN_CAPTURED_FOV,
        le=MAX_CAPTURED_FOV,
    )


class PanoramaDestination(BaseModel):
    kind: str = Field(min_length=1, max_length=32)
    aspect_ratio: float = Field(gt=0, le=10)
    width_px: int = Field(gt=0, le=_MAX_OUTPUT_DIMENSION)
    height_px: int = Field(gt=0, le=_MAX_OUTPUT_DIMENSION)

    @model_validator(mode="after")
    def validate_output_area(self) -> PanoramaDestination:
        if self.width_px * self.height_px > _MAX_OUTPUT_PIXELS:
            raise ValueError("Panorama output exceeds the pixel limit")
        actual = self.width_px / self.height_px
        if not math.isclose(actual, self.aspect_ratio, rel_tol=0.02):
            raise ValueError("Panorama destination aspect ratio is inconsistent")
        return self


def validate_panorama_frame(
    config: PanoramaConfig,
    destination: PanoramaDestination,
) -> None:
    if config.status != "active":
        raise PanoramaValidationError("Panorama projection is not active")
    if config.perspective_fov > config.captured_fov:
        raise PanoramaValidationError("Perspective FOV exceeds the captured panorama")

    horizontal_margin = (config.captured_fov - config.perspective_fov) / 2
    if abs(config.yaw) > horizontal_margin:
        raise PanoramaValidationError("Panorama yaw is outside the captured bounds")

    top_elevation, bottom_elevation = _source_vertical_bounds(config)
    output_vertical_half_fov = _output_vertical_fov(config, destination) / 2
    minimum_pitch = bottom_elevation + output_vertical_half_fov
    maximum_pitch = top_elevation - output_vertical_half_fov
    if not minimum_pitch <= config.pitch <= maximum_pitch:
        raise PanoramaValidationError("Panorama pitch is outside the captured bounds")
    if config.zoom > min(destination.width_px, destination.height_px):
        raise PanoramaValidationError("Panorama zoom produces an empty crop")


def panorama_render_path(
    album_dir: Path,
    media_name: str,
    revision: int,
    width_px: int,
    height_px: int,
) -> Path:
    return (
        album_dir
        / ".panoramas"
        / "rendered"
        / Path(media_name).stem
        / str(revision)
        / f"{width_px}x{height_px}.jpg"
    )


def panorama_preview_path(
    album_dir: Path,
    media_name: str,
    source: Path,
    config: PanoramaConfig,
) -> Path:
    source_stat = source.stat()
    geometry = {
        key: value
        for key, value in config.model_dump().items()
        if key
        in {
            "detection",
            "source_width",
            "source_height",
            "cropped_area_width",
            "cropped_area_height",
            "cropped_area_top",
            "full_pano_width",
            "full_pano_height",
            "captured_fov",
        }
    }
    cache_input = json.dumps(
        {
            "source": str(source.resolve()),
            "source_size": source_stat.st_size,
            "source_mtime_ns": source_stat.st_mtime_ns,
            "preview_format": _PREVIEW_FORMAT_VERSION,
            "geometry": geometry,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    digest = hashlib.sha256(cache_input).hexdigest()[:24]
    return (
        album_dir / ".panoramas" / "preview" / Path(media_name).stem / f"{digest}.jpg"
    )


def resolve_panorama_source(
    album_dir: Path,
    media_name: str,
    config: PanoramaConfig,
) -> Path:
    relative = Path(config.original_path or media_name)
    source = (album_dir / relative).resolve()
    if not source.is_relative_to(album_dir.resolve()) or not source.is_file():
        fallback = (album_dir / media_name).resolve()
        if not fallback.is_relative_to(album_dir.resolve()) or not fallback.is_file():
            raise FileNotFoundError(media_name)
        return fallback
    return source


async def render_panorama(
    source: Path,
    config: PanoramaConfig,
    destination: PanoramaDestination,
    output: Path,
) -> None:
    validate_panorama_frame(config, destination)
    if not await run_sync(source.is_file):
        raise PanoramaValidationError("Panorama source does not exist")

    filter_graph = _filter_graph(config, destination)
    await _render_image(source, filter_graph, output)


async def _render_image(source: Path, filter_graph: str, output: Path) -> None:
    async with media_limiter:
        await _run_ffmpeg_image(source, filter_graph, output)


async def _run_ffmpeg_image(source: Path, filter_graph: str, output: Path) -> None:
    await run_sync(output.parent.mkdir, parents=True, exist_ok=True)
    temporary = output.parent / f".{output.stem}.{secrets.token_hex(8)}.jpg"
    process: asyncio.subprocess.Process | None = None
    try:
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
            if process.returncode != 0:
                detail = stderr.decode(errors="replace").strip()
                raise PanoramaRenderError(detail or "FFmpeg failed to render panorama")
            if not await run_sync(temporary.is_file):
                raise PanoramaRenderError("FFmpeg did not produce a panorama image")
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


def _filter_graph(
    config: PanoramaConfig,
    destination: PanoramaDestination,
) -> str:
    virtual_height, source_y, input_vertical_fov = _virtual_input_geometry(config)
    output_vertical_fov = _output_vertical_fov(config, destination)
    projection = (
        "v360=input=cylindrical:output=flat:"
        f"ih_fov={_number(config.captured_fov)}:"
        f"iv_fov={_number(input_vertical_fov)}:"
        f"yaw={_number(config.yaw)}:"
        f"pitch={_number(config.pitch)}:"
        f"h_fov={_number(config.perspective_fov)}:"
        f"v_fov={_number(output_vertical_fov)}:"
        f"w={destination.width_px}:h={destination.height_px}"
    )
    source_height = config.cropped_area_height or config.source_height
    if virtual_height != source_height or source_y != 0:
        bottom_padding = virtual_height - source_y - source_height
        projection = (
            "format=gbrp,"
            f"pad=width=iw:height={virtual_height}:x=0:y={source_y}:color=black,"
            f"fillborders=top={source_y}:bottom={bottom_padding}:mode=smear,"
            f"{projection}"
        )
    if config.zoom == 1:
        return projection
    zoom = _number(config.zoom)
    return (
        f"{projection},"
        f"crop=iw/{zoom}:ih/{zoom}:(iw-iw/{zoom})/2:(ih-ih/{zoom})/2,"
        f"scale={destination.width_px}:{destination.height_px}:flags=lanczos"
    )


def _source_vertical_bounds(config: PanoramaConfig) -> tuple[float, float]:
    top, bottom, focal_length = _source_pixel_geometry(config)
    top_elevation = math.degrees(math.atan(-top / focal_length))
    bottom_elevation = math.degrees(math.atan(-bottom / focal_length))
    return top_elevation, bottom_elevation


def _virtual_input_geometry(config: PanoramaConfig) -> tuple[int, int, float]:
    top, bottom, focal_length = _source_pixel_geometry(config)
    half = max(abs(top), abs(bottom))
    virtual_height = max(1, int(2 * half))
    source_y = int(half + top)
    vertical_fov = 2 * math.degrees(math.atan(half / focal_length))
    return virtual_height, source_y, vertical_fov


def _source_pixel_geometry(config: PanoramaConfig) -> tuple[float, float, float]:
    source_width = config.cropped_area_width or config.source_width
    source_height = config.cropped_area_height or config.source_height
    top = (
        config.cropped_area_top
        if config.cropped_area_top is not None
        else -source_height / 2
    )
    bottom = top + source_height
    focal_length = source_width / math.radians(config.captured_fov)
    return top, bottom, focal_length


def _output_vertical_fov(
    config: PanoramaConfig,
    destination: PanoramaDestination,
) -> float:
    return 2 * math.degrees(
        math.atan(
            math.tan(math.radians(config.perspective_fov / 2))
            / destination.aspect_ratio
        )
    )


async def _kill_and_reap(process: asyncio.subprocess.Process | None) -> None:
    if process is None or process.returncode is not None:
        return
    with suppress(ProcessLookupError):
        process.kill()
    await process.communicate()


def _number(value: float) -> str:
    return format(value, "g")


def _preview_size(source_width: int, captured_fov: float) -> tuple[int, int]:
    full_width = round(source_width * 360 / captured_fov)
    width = max(2, min(full_width, _PREVIEW_MAX_WIDTH))
    if width % 2:
        width -= 1
    return width, width // 2


def _preview_filter_graph(config: PanoramaConfig) -> str:
    virtual_height, source_y, input_vertical_fov = _virtual_input_geometry(config)
    source_width = config.cropped_area_width or config.source_width
    source_height = config.cropped_area_height or config.source_height
    width, height = _preview_size(source_width, config.captured_fov)
    projection = (
        "v360=input=cylindrical:output=equirect:"
        f"ih_fov={_number(config.captured_fov)}:"
        f"iv_fov={_number(input_vertical_fov)}:"
        f"w={width}:h={height}"
    )
    if virtual_height == source_height and source_y == 0:
        return projection
    bottom_padding = virtual_height - source_y - source_height
    return (
        "format=gbrp,"
        f"pad=width=iw:height={virtual_height}:x=0:y={source_y}:color=black,"
        f"fillborders=top={source_y}:bottom={bottom_padding}:mode=smear,"
        f"{projection}"
    )


async def create_panorama_preview(
    source: Path,
    config: PanoramaConfig,
    output: Path,
) -> None:
    async with file_generation_lock(output):
        if await run_sync(output.is_file):
            return
        await _render_image(source, _preview_filter_graph(config), output)
