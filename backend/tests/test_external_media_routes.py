from __future__ import annotations

import io
from typing import TYPE_CHECKING

from PIL import Image

from app.core.config import get_settings
from app.models.album_media import AlbumMedia
from app.models.step import Step

from .factories import (
    AID,
    insert_album,
    insert_album_media,
    insert_step,
    sign_in_and_upload,
)

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlmodel.ext.asyncio.session import AsyncSession


def _jpeg_bytes(width: int = 640, height: int = 480) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color="red").save(buf, "JPEG")
    return buf.getvalue()


async def _signed_in_album(client: AsyncClient, session: AsyncSession) -> int:
    user_data = await sign_in_and_upload(
        client,
        get_settings().USERS_FOLDER,
        provider="google",
    )
    uid = user_data["id"]
    await insert_album(session, uid)
    await insert_album_media(
        session,
        uid,
        name="11111111-1111-4111-8111-111111111111_22222222-2222-4222-8222-222222222222.jpg",
    )
    await insert_step(session, uid)
    (get_settings().USERS_FOLDER / str(uid) / "trip" / AID).mkdir(
        parents=True,
        exist_ok=True,
    )
    await session.commit()
    return uid


async def test_device_add_to_step_prepends_unused(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    uid = await _signed_in_album(client, session)

    resp = await client.post(
        f"/api/v1/albums/{AID}/external-media/add/device",
        data={"context": "step", "step_id": "1"},
        files=[("files", ("holiday.jpg", _jpeg_bytes(), "image/jpeg"))],
    )

    assert resp.status_code == 200
    imported = resp.json()["names"]
    assert len(imported) == 1

    step = await session.get_one(Step, (uid, AID, 1))
    assert step.unused[0] == imported[0]

    row = await session.get_one(AlbumMedia, (uid, AID, imported[0]))
    assert row.kind == "photo"
    assert row.storage_path == imported[0]


async def test_device_add_to_cover_does_not_select_cover(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    uid = await _signed_in_album(client, session)

    resp = await client.post(
        f"/api/v1/albums/{AID}/external-media/add/device",
        data={"context": "cover"},
        files=[("files", ("cover.jpg", _jpeg_bytes(900, 600), "image/jpeg"))],
    )

    assert resp.status_code == 200
    imported = resp.json()["names"][0]
    row = await session.get_one(AlbumMedia, (uid, AID, imported))
    assert row.width == 900
    assert row.height == 600
