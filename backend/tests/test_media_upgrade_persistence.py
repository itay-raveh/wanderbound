from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from PIL import Image

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlmodel.ext.asyncio.session import AsyncSession

from app.logic.media_upgrade.phash_matching import (
    MatchResult,
)
from app.logic.media_upgrade.upgrade import _persist_upgrade_in_session
from app.logic.photo_edit import validate_photo_edit
from app.models.album_media import AlbumMedia, PanoramaConfig, PhotoEdit

from .factories import (
    AID,
    create_test_jpeg,
    insert_album,
    insert_album_media,
    sign_in_with_album_media,
)


class TestPersistUpgrade:
    async def test_updates_metadata_and_invalidates_hash_for_replaced_media(
        self,
        session: AsyncSession,
        tmp_path: Path,
    ) -> None:
        uid = 1
        await insert_album(session, uid)
        media = await insert_album_media(session, uid, name="photo.jpg")
        media.byte_size = 1
        media.width = 4000
        media.height = 1000
        media.panorama = PanoramaConfig(aspect_ratio=2)
        media.perceptual_hashes = ["0123456789abcdef"]
        session.add(media)
        target = create_test_jpeg(tmp_path / "photo.jpg", 3200, 1000)
        await session.commit()

        await _persist_upgrade_in_session(
            session,
            uid=uid,
            aid=AID,
            album_dir=tmp_path,
            matches=[
                MatchResult(local_name="photo.jpg", google_id="google-1", distance=0)
            ],
            succeeded={"photo.jpg"},
        )
        await session.refresh(media)

        assert media.byte_size == target.stat().st_size
        assert media.panorama == PanoramaConfig(aspect_ratio=2)
        assert media.perceptual_hashes is None
        assert media.upgrade_candidate is False

    @pytest.mark.parametrize("edge_clamped", [False, True])
    async def test_quality_upgrade_preserves_crop_and_keeps_media_renderable(
        self,
        client: AsyncClient,
        session: AsyncSession,
        *,
        edge_clamped: bool,
    ) -> None:
        album = await sign_in_with_album_media(
            client, session, width=1000, height=667, write_media=True
        )
        base = f"/api/v1/albums/{AID}/media/{album.media_name}"
        # A valid free-angle crop dragged against the right edge of the photo.
        edit = PhotoEdit(
            angle=30,
            x=0.24526177829903595,
            y=0.3092192924887657,
            width=0.5139281951109125,
            height=0.38156141502246865,
        )
        if not edge_clamped:
            edit = PhotoEdit(angle=30, x=0.35, y=0.35, width=0.3, height=0.3)
        saved = await client.put(f"{base}/photo-edit", json=edit.model_dump())
        assert saved.status_code == 200
        assert (await client.get(base)).status_code == 200
        create_test_jpeg(album.album_dir / album.media_name, 3000, 2000)

        await _persist_upgrade_in_session(
            session,
            uid=album.uid,
            aid=AID,
            album_dir=album.album_dir,
            matches=[
                MatchResult(
                    local_name=album.media_name, google_id="google-1", distance=0
                )
            ],
            succeeded={album.media_name},
        )
        media = await session.get_one(AlbumMedia, (album.uid, AID, album.media_name))
        assert (media.width, media.height) == (3000, 2000)
        assert media.photo_edit is not None
        validate_photo_edit(media.photo_edit, media.width, media.height)
        if not edge_clamped:
            assert media.photo_edit == edit
        else:
            assert media.photo_edit.angle == edit.angle
            for field in ("x", "y", "width", "height"):
                assert getattr(media.photo_edit, field) == pytest.approx(
                    getattr(edit, field), abs=0.005
                )
        rendered = await client.get(base)
        thumb = await client.get(f"{base}?w=200")
        assert rendered.status_code == thumb.status_code == 200
        with Image.open(BytesIO(rendered.content)) as image:
            assert image.width > 1000
            assert image.height > 700
