from __future__ import annotations

import asyncio
import math
from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

import pytest
from PIL import Image
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.v1.routes.panoramas import PanoramaApply, update_panorama
from app.core.worker_threads import run_sync
from app.logic.panorama.render import PanoramaRenderError
from app.models.album_media import AlbumMedia, PanoramaConfig
from app.models.user import User
from tests.factories import AID, sign_in_with_album_media

if TYPE_CHECKING:
    from httpx import AsyncClient


def _panorama(media_name: str, *, revision: int = 3) -> PanoramaConfig:
    return PanoramaConfig(
        status="active",
        detection="gpano",
        source_width=1600,
        source_height=800,
        captured_fov=180,
        yaw=0,
        pitch=0,
        perspective_fov=60,
        zoom=1,
        original_path=media_name,
        revision=revision,
    )


def _body() -> dict[str, Any]:
    return {
        "frame": {
            "yaw": 10,
            "pitch": 2,
            "perspective_fov": 55,
            "zoom": 1.5,
        },
        "destination": {
            "kind": "grid",
            "aspect_ratio": 2,
            "width_px": 800,
            "height_px": 400,
        },
    }


async def _scenario(
    client: AsyncClient,
    session: AsyncSession,
) -> tuple[AlbumMedia, Path]:
    scenario = await sign_in_with_album_media(
        client,
        session,
        width=1600,
        height=800,
        write_media=True,
    )
    row = await session.get_one(
        AlbumMedia,
        (scenario.uid, AID, scenario.media_name),
    )
    row.panorama = _panorama(scenario.media_name)
    session.add(row)
    await session.commit()
    return row, scenario.album_dir


async def test_put_commits_frame_only_after_derivative_exists(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    row, album_dir = await _scenario(client, session)

    async def render(
        _source: Path,
        _config: PanoramaConfig,
        _destination: object,
        output: Path,
    ) -> None:
        await run_sync(output.parent.mkdir, parents=True, exist_ok=True)
        await run_sync(output.write_bytes, b"rendered")

    with patch("app.api.v1.routes.panoramas.render_panorama", side_effect=render):
        response = await client.put(
            f"/api/v1/albums/{AID}/media/{row.name}/panorama",
            json=_body(),
        )

    assert response.status_code == 200
    panorama = response.json()["panorama"]
    assert panorama["status"] == "active"
    assert panorama["yaw"] == 10
    assert panorama["pitch"] == 2
    assert panorama["perspective_fov"] == 55
    assert panorama["zoom"] == 1.5
    assert panorama["revision"] == 4
    derivative = (
        album_dir
        / ".panoramas"
        / "rendered"
        / Path(row.name).stem
        / "4"
        / "800x400.jpg"
    )
    assert derivative.read_bytes() == b"rendered"

    await session.refresh(row)
    assert row.panorama == PanoramaConfig.model_validate(panorama)


async def test_failed_put_preserves_configuration_and_derivative(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    row, album_dir = await _scenario(client, session)
    previous = (
        album_dir
        / ".panoramas"
        / "rendered"
        / Path(row.name).stem
        / "3"
        / "800x400.jpg"
    )
    previous.parent.mkdir(parents=True)
    previous.write_bytes(b"previous")

    with patch(
        "app.api.v1.routes.panoramas.render_panorama",
        side_effect=PanoramaRenderError("ffmpeg failed"),
    ):
        response = await client.put(
            f"/api/v1/albums/{AID}/media/{row.name}/panorama",
            json=_body(),
        )

    assert response.status_code == 500
    assert previous.read_bytes() == b"previous"
    await session.refresh(row)
    assert row.panorama == _panorama(row.name)
    assert not previous.parents[1].joinpath("4").exists()


async def test_cancelled_put_removes_uncommitted_derivative(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    row, album_dir = await _scenario(client, session)
    derivative = (
        album_dir
        / ".panoramas"
        / "rendered"
        / Path(row.name).stem
        / "4"
        / "800x400.jpg"
    )

    async def cancelled_render(
        _source: Path,
        _config: PanoramaConfig,
        _destination: object,
        output: Path,
    ) -> None:
        await run_sync(output.parent.mkdir, parents=True, exist_ok=True)
        await run_sync(output.write_bytes, b"uncommitted")
        raise asyncio.CancelledError

    with (
        patch(
            "app.api.v1.routes.panoramas.render_panorama",
            side_effect=cancelled_render,
        ),
        pytest.raises(asyncio.CancelledError),
    ):
        await update_panorama(
            AID,
            row.name,
            PanoramaApply.model_validate(_body()),
            await session.get_one(User, row.uid),
            session,
        )

    assert not derivative.exists()
    await session.refresh(row)
    assert row.panorama == _panorama(row.name)


async def test_non_database_commit_error_removes_uncommitted_derivative(
    client: AsyncClient,
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row, album_dir = await _scenario(client, session)
    derivative = (
        album_dir
        / ".panoramas"
        / "rendered"
        / Path(row.name).stem
        / "4"
        / "800x400.jpg"
    )

    async def render(
        _source: Path,
        _config: PanoramaConfig,
        _destination: object,
        output: Path,
    ) -> None:
        await run_sync(output.parent.mkdir, parents=True, exist_ok=True)
        await run_sync(output.write_bytes, b"uncommitted")

    async def fail_commit() -> None:
        raise RuntimeError("commit interrupted")

    async with AsyncSession(
        bind=session.bind,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    ) as update_session:
        monkeypatch.setattr(update_session, "commit", fail_commit)
        with (
            patch("app.api.v1.routes.panoramas.render_panorama", side_effect=render),
            pytest.raises(RuntimeError, match="commit interrupted"),
        ):
            await update_panorama(
                AID,
                row.name,
                PanoramaApply.model_validate(_body()),
                await update_session.get_one(User, row.uid),
                update_session,
            )

    assert not derivative.exists()
    await session.refresh(row)
    assert row.panorama == _panorama(row.name)


async def test_put_rejects_frame_outside_captured_bounds(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    row, _album_dir = await _scenario(client, session)
    body = _body()
    body["frame"]["yaw"] = 80

    with patch("app.api.v1.routes.panoramas.render_panorama") as render:
        response = await client.put(
            f"/api/v1/albums/{AID}/media/{row.name}/panorama",
            json=body,
        )

    assert response.status_code == 400
    render.assert_not_awaited()


async def test_delete_disables_projection_without_removing_source(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    row, album_dir = await _scenario(client, session)

    response = await client.delete(f"/api/v1/albums/{AID}/media/{row.name}/panorama")

    assert response.status_code == 200
    panorama = response.json()["panorama"]
    assert panorama["status"] == "disabled"
    assert panorama["revision"] == 4
    assert (album_dir / row.name).is_file()


async def test_panorama_source_is_normalized_and_cached(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    row, album_dir = await _scenario(client, session)

    url = f"/api/v1/albums/{AID}/media/{row.name}/panorama-source"
    response = await client.get(url)
    repeated = await client.get(url)

    assert response.status_code == 200
    assert repeated.status_code == 200
    previews = list((album_dir / ".panoramas" / "preview").rglob("*.jpg"))
    assert len(previews) == 1
    preview = previews[0]
    assert response.content == preview.read_bytes()
    assert repeated.content == response.content
    with Image.open(preview) as normalized:
        assert math.isclose(
            normalized.width / normalized.height,
            math.radians(180),
            rel_tol=0.01,
        )


async def test_panorama_source_accepts_validated_metadata_free_coverage(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    row, album_dir = await _scenario(client, session)
    assert row.panorama is not None
    row.panorama = row.panorama.model_copy(update={"detection": "dimensions"})
    session.add(row)
    await session.commit()
    url = f"/api/v1/albums/{AID}/media/{row.name}/panorama-source"

    default = await client.get(url)
    proposed = await client.get(url, params={"captured_fov": 270})
    invalid = await client.get(url, params={"captured_fov": 360})

    assert default.status_code == 200
    assert proposed.status_code == 200
    assert invalid.status_code == 422
    previews = list((album_dir / ".panoramas" / "preview").rglob("*.jpg"))
    assert len(previews) == 2
    with Image.open(previews[0]) as first, Image.open(previews[1]) as second:
        ratios = sorted((first.width / first.height, second.width / second.height))
    assert math.isclose(ratios[0], math.radians(180), rel_tol=0.01)
    assert math.isclose(ratios[1], math.radians(270), rel_tol=0.01)
    await session.refresh(row)
    assert row.panorama is not None
    assert row.panorama.captured_fov == 180


async def test_panorama_source_rejects_gpano_coverage_override(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    row, _album_dir = await _scenario(client, session)

    response = await client.get(
        f"/api/v1/albums/{AID}/media/{row.name}/panorama-source",
        params={"captured_fov": 270},
    )

    assert response.status_code == 400
