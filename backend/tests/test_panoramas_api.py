from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.worker_threads import run_sync
from app.logic.panorama import PanoramaRenderError
from app.models.album_media import AlbumMedia, PanoramaConfig
from tests.factories import AID, sign_in_with_album_media

if TYPE_CHECKING:
    from httpx import AsyncClient


def _body() -> dict[str, Any]:
    return {
        "yaw": 10,
        "pitch": 2,
        "perspective_fov": 55,
        "zoom": 1.5,
        "aspect_ratio": 2,
    }


async def _scenario(
    client: AsyncClient,
    session: AsyncSession,
    *,
    width: int = 1600,
    height: int = 800,
) -> tuple[AlbumMedia, Path]:
    scenario = await sign_in_with_album_media(
        client,
        session,
        width=width,
        height=height,
        write_media=True,
    )
    row = await session.get_one(
        AlbumMedia,
        (scenario.uid, AID, scenario.media_name),
    )
    return row, scenario.album_dir


async def _write_render(
    _source: Path,
    _config: PanoramaConfig,
    output: Path,
    _source_size: tuple[int, int],
) -> None:
    await run_sync(output.parent.mkdir, parents=True, exist_ok=True)
    await run_sync(output.write_bytes, b"rendered")


async def test_put_saves_one_global_poster(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    row, album_dir = await _scenario(client, session)

    with patch(
        "app.api.v1.routes.panoramas.render_panorama", side_effect=_write_render
    ) as render:
        response = await client.put(
            f"/api/v1/albums/{AID}/media/{row.name}/panorama",
            json=_body(),
        )
        poster = await client.get(
            f"/api/v1/albums/{AID}/media/{row.name}/panorama-render"
        )

    assert response.status_code == 200
    assert response.json()["panorama"] == _body()
    assert poster.status_code == 200
    assert poster.content == b"rendered"
    assert render.call_count == 1
    assert len(list((album_dir / ".panoramas").rglob("poster-*.jpg"))) == 1


async def test_put_rejects_zoom_above_slider_range(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    row, _album_dir = await _scenario(client, session)

    response = await client.put(
        f"/api/v1/albums/{AID}/media/{row.name}/panorama",
        json=_body() | {"zoom": 2.1},
    )

    assert response.status_code == 422


async def test_failed_put_preserves_saved_frame(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    row, _album_dir = await _scenario(client, session)
    row.panorama = PanoramaConfig(aspect_ratio=2)
    key = (row.uid, row.aid, row.name)
    session.add(row)
    await session.commit()

    with patch(
        "app.api.v1.routes.panoramas.render_panorama",
        side_effect=PanoramaRenderError("failed"),
    ):
        response = await client.put(
            f"/api/v1/albums/{AID}/media/{row.name}/panorama",
            json=_body(),
        )

    assert response.status_code == 500
    async with AsyncSession(
        bind=session.bind,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    ) as check_session:
        stored = await check_session.get_one(AlbumMedia, key)
    assert stored.panorama == PanoramaConfig(aspect_ratio=2)


async def test_source_is_available_before_a_frame_is_saved(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    row, album_dir = await _scenario(client, session)

    response = await client.get(
        f"/api/v1/albums/{AID}/media/{row.name}/panorama-source"
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert next((album_dir / ".panoramas").rglob("source-*.jpg")).is_file()


async def test_delete_returns_panorama_to_normal_photo(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    row, album_dir = await _scenario(client, session)
    row.panorama = PanoramaConfig(aspect_ratio=2)
    session.add(row)
    await session.commit()
    derivatives = album_dir / ".panoramas" / Path(row.name).stem
    derivatives.mkdir(parents=True)
    (derivatives / "poster-old.jpg").write_bytes(b"rendered")

    response = await client.delete(f"/api/v1/albums/{AID}/media/{row.name}/panorama")

    assert response.status_code == 200
    assert response.json()["panorama"] is None
    assert not derivatives.exists()
    assert (album_dir / row.name).is_file()


async def test_regular_photo_is_not_a_panorama_candidate(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    row, _album_dir = await _scenario(client, session, width=1200, height=800)

    source = await client.get(f"/api/v1/albums/{AID}/media/{row.name}/panorama-source")
    update = await client.put(
        f"/api/v1/albums/{AID}/media/{row.name}/panorama",
        json=_body(),
    )

    assert source.status_code == 400
    assert update.status_code == 400
