from typing import TYPE_CHECKING

from .factories import AID, AlbumScenario, insert_album_media
from .helpers.albums import AlbumRoutes

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession


async def test_read_media_returns_album_media_rows(
    session: AsyncSession,
    signed_album: AlbumScenario,
    album_routes: AlbumRoutes,
) -> None:
    uid = signed_album.uid
    media = await insert_album_media(
        session,
        uid,
        name="11111111-1111-4111-8111-111111111111_22222222-2222-4222-8222-222222222222.jpg",
    )
    await session.commit()

    resp = await album_routes.get_media()
    assert resp.status_code == 200
    assert resp.json() == [
        {
            "uid": uid,
            "aid": AID,
            "name": media.name,
            "kind": "photo",
            "width": 1920,
            "height": 1080,
            "byte_size": 1234,
            "upgrade_candidate": True,
            "created_at": media.created_at.isoformat().replace("+00:00", "Z"),
            "updated_at": media.updated_at.isoformat().replace("+00:00", "Z"),
        }
    ]
