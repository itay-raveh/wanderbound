from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

from app.core.worker_threads import run_sync
from app.logic.panorama.render import PanoramaRenderError
from app.models.album_media import AlbumMedia, PanoramaConfig
from tests.factories import AID, sign_in_with_album_media

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlmodel.ext.asyncio.session import AsyncSession


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

    response = await client.get(
        f"/api/v1/albums/{AID}/media/{row.name}/panorama-source"
    )

    assert response.status_code == 200
    preview = album_dir / ".panoramas" / "preview" / f"{Path(row.name).stem}.jpg"
    assert preview.is_file()
    assert response.content == preview.read_bytes()
