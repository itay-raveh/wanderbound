from typing import TYPE_CHECKING

from app.core.config import get_settings

from .factories import AID, insert_album, insert_album_media, sign_in_and_upload

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlmodel.ext.asyncio.session import AsyncSession


async def test_read_media_returns_album_media_rows(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    user_data = await sign_in_and_upload(
        client, get_settings().USERS_FOLDER, provider="google"
    )
    uid = user_data["id"]
    await insert_album(session, uid)
    media = await insert_album_media(
        session,
        uid,
        name="11111111-1111-4111-8111-111111111111_22222222-2222-4222-8222-222222222222.jpg",
    )
    await session.commit()

    resp = await client.get(f"/api/v1/albums/{AID}/media")

    assert resp.status_code == 200
    assert resp.json() == [
        {
            "uid": uid,
            "aid": AID,
            "name": media.name,
            "kind": "photo",
            "storage_path": media.storage_path,
            "width": 1920,
            "height": 1080,
            "byte_size": 1234,
            "source_ref_id": None,
            "created_at": media.created_at.isoformat().replace("+00:00", "Z"),
            "updated_at": media.updated_at.isoformat().replace("+00:00", "Z"),
        }
    ]
