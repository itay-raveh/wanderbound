from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

from app.logic.media_upgrade.phash_matching import (
    MatchResult,
)
from app.logic.media_upgrade.pipeline import (
    _needs_upgrade,
)
from app.logic.media_upgrade.upgrade import _persist_upgrade_in_session
from app.models.album_media import PanoramaConfig

from .factories import AID, create_test_jpeg, insert_album, insert_album_media


class TestNeedsUpgrade:
    @pytest.mark.parametrize(
        ("upgrade_candidates", "expected"),
        [
            ({"photo.jpg"}, True),
            (set(), False),
        ],
    )
    def test_needs_upgrade(
        self, upgrade_candidates: set[str], *, expected: bool
    ) -> None:
        match = MatchResult(local_name="photo.jpg", google_id="gid-A", distance=0)
        assert _needs_upgrade(match, upgrade_candidates) is expected


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
