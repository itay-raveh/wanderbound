from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from app.main import app
from app.models.segment import Segment, SegmentKind

from .factories import (
    AID,
    AlbumScenario,
    insert_album,
    insert_album_media,
    insert_segment,
    insert_step,
    make_points,
)
from .helpers.albums import AlbumRoutes

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession


def _assert_step_layout(
    data: dict[str, object],
    *,
    cover: str | None,
    pages: list[dict[str, object]],
    unused: list[str],
) -> None:
    assert data["cover"] == cover
    assert data["pages"] == pages
    assert data["unused"] == unused


async def _save_chapters(
    session: AsyncSession,
    signed_album: AlbumScenario,
    album_routes: AlbumRoutes,
    chapter_ids: list[str],
) -> None:
    for step_id in range(1, len(chapter_ids) + 1):
        await insert_step(session, signed_album.uid, step_id=step_id)
    await album_routes.update_album_ok(
        chapters=[
            {
                "id": chapter_id,
                "title": chapter_id.title(),
                "subtitle": "",
                "step_ids": [step_id],
                "front_cover_photo": "front.jpg",
                "back_cover_photo": "back.jpg",
            }
            for step_id, chapter_id in enumerate(chapter_ids, start=1)
        ]
    )


@asynccontextmanager
async def _browser_lease() -> AsyncIterator[object]:
    yield object()


def _browser_manager() -> SimpleNamespace:
    return SimpleNamespace(acquire=_browser_lease)


class TestReadAlbum:
    @pytest.mark.usefixtures("uploaded_user")
    async def test_cannot_read_other_users_album(
        self,
        session: AsyncSession,
        album_routes: AlbumRoutes,
    ) -> None:
        await insert_album(session, uid=9999, aid="other-trip")

        resp = await album_routes.get_album("other-trip")
        assert resp.status_code == 404


class TestChapterPrintBundle:
    async def test_chapter_print_bundle_filters_steps_segments_and_album_fields(
        self,
        session: AsyncSession,
        signed_album: AlbumScenario,
        album_routes: AlbumRoutes,
    ) -> None:
        await insert_step(session, signed_album.uid, step_id=1, timestamp=100.0)
        await insert_step(session, signed_album.uid, step_id=2, timestamp=200.0)
        await insert_step(session, signed_album.uid, step_id=3, timestamp=300.0)
        await insert_segment(
            session,
            signed_album.uid,
            start_time=90.0,
            end_time=210.0,
        )
        await insert_segment(
            session,
            signed_album.uid,
            start_time=250.0,
            end_time=350.0,
        )
        await album_routes.update_album_ok(
            maps_ranges=[["1970-01-01", "1970-01-01"]],
            chapters=[
                {
                    "id": "chapter-1",
                    "title": "First Chapter",
                    "subtitle": "",
                    "step_ids": [1, 2],
                    "front_cover_photo": "chapter-front.jpg",
                    "back_cover_photo": "chapter-back.jpg",
                },
                {
                    "id": "chapter-2",
                    "title": "Second Chapter",
                    "subtitle": "",
                    "step_ids": [3],
                    "front_cover_photo": "chapter-front.jpg",
                    "back_cover_photo": "chapter-back.jpg",
                },
            ],
        )

        resp = await album_routes.print_bundle(chapter="chapter-1")

        assert resp.status_code == 200
        data = resp.json()
        assert data["album"]["chapters"][0]["title"] == "First Chapter"
        assert data["album"]["chapters"][0]["subtitle"] == ""
        assert data["album"]["chapters"][0]["front_cover_photo"] == "chapter-front.jpg"
        assert data["album"]["chapters"][0]["back_cover_photo"] == "chapter-back.jpg"
        assert [step["id"] for step in data["steps"]] == [1, 2]
        assert [segment["start_time"] for segment in data["segments"]] == [90.0]
        assert data["album"]["maps_ranges"] == [["1970-01-01", "1970-01-01"]]

    async def test_chapter_print_bundle_rejects_unknown_chapter(
        self,
        session: AsyncSession,
        signed_album: AlbumScenario,
        album_routes: AlbumRoutes,
    ) -> None:
        await insert_step(session, signed_album.uid, step_id=1)
        await album_routes.update_album_ok(
            chapters=[
                {
                    "id": "chapter-1",
                    "title": "Chapter",
                    "subtitle": "",
                    "step_ids": [1],
                    "front_cover_photo": "front.jpg",
                    "back_cover_photo": "back.jpg",
                }
            ],
        )

        resp = await album_routes.print_bundle(chapter="missing")

        assert resp.status_code == 404
        assert resp.json()["detail"] == "Chapter not found"


class TestUpdateAlbum:
    async def test_update_chapters_rejects_overlapping_steps(
        self,
        session: AsyncSession,
        signed_album: AlbumScenario,
        album_routes: AlbumRoutes,
    ) -> None:
        await insert_step(session, signed_album.uid, step_id=1)
        await insert_step(session, signed_album.uid, step_id=2)
        await session.commit()

        resp = await album_routes.update_album(
            chapters=[
                {
                    "id": "north",
                    "title": "North",
                    "subtitle": "",
                    "step_ids": [1, 2],
                    "front_cover_photo": "front.jpg",
                    "back_cover_photo": "back.jpg",
                },
                {
                    "id": "south",
                    "title": "South",
                    "subtitle": "",
                    "step_ids": [2],
                    "front_cover_photo": "front.jpg",
                    "back_cover_photo": "back.jpg",
                },
            ]
        )

        assert resp.status_code == 400
        assert "Step 2 is already assigned to another chapter" in resp.json()["detail"]

    async def test_update_chapters_rejects_unknown_steps(
        self,
        session: AsyncSession,
        signed_album: AlbumScenario,
        album_routes: AlbumRoutes,
    ) -> None:
        await insert_step(session, signed_album.uid, step_id=1)
        await session.commit()

        resp = await album_routes.update_album(
            chapters=[
                {
                    "id": "ghost",
                    "title": "Ghost",
                    "subtitle": "",
                    "step_ids": [1, 999],
                    "front_cover_photo": "front.jpg",
                    "back_cover_photo": "back.jpg",
                }
            ]
        )

        assert resp.status_code == 400
        assert "Unknown chapter step IDs: 999" in resp.json()["detail"]


class TestUpdateStep:
    async def test_media_layout_update_rewrites_step_placements(
        self,
        session: AsyncSession,
        signed_album: AlbumScenario,
        album_routes: AlbumRoutes,
    ) -> None:
        expected_layout = {
            "cover": "cover.jpg",
            "pages": [
                {"kind": "grid", "media": ["a.jpg", "b.jpg"]},
                {"kind": "panorama_spread", "media": ["c.jpg"]},
            ],
            "unused": ["unused.jpg"],
        }
        for name in ("a.jpg", "b.jpg", "c.jpg", "cover.jpg", "unused.jpg"):
            await insert_album_media(session, signed_album.uid, name=name)
        await insert_step(session, signed_album.uid)
        await session.commit()

        resp = await album_routes.update_media_layout(**expected_layout)
        assert resp.status_code == 200
        data = resp.json()
        _assert_step_layout(data, **expected_layout)

        get_resp = await album_routes.get_steps()
        assert get_resp.status_code == 200
        _assert_step_layout(get_resp.json()[0], **expected_layout)

    @pytest.mark.usefixtures("signed_album")
    @pytest.mark.parametrize("media", [[], ["a.jpg", "b.jpg"]])
    async def test_panorama_spread_requires_one_media(
        self,
        album_routes: AlbumRoutes,
        media: list[str],
    ) -> None:
        resp = await album_routes.update_media_layout(
            cover=None,
            pages=[{"kind": "panorama_spread", "media": media}],
            unused=[],
        )

        assert resp.status_code == 422

    async def test_media_layout_update_rejects_missing_album_media(
        self,
        session: AsyncSession,
        signed_album: AlbumScenario,
        album_routes: AlbumRoutes,
    ) -> None:
        await insert_step(session, signed_album.uid)
        await session.commit()

        resp = await album_routes.update_media_layout(
            cover=None,
            pages=[{"kind": "grid", "media": ["missing.jpg"]}],
            unused=[],
        )

        assert resp.status_code == 400
        assert "missing.jpg" in resp.json()["detail"]


class TestAdjustSegmentBoundary:
    async def _setup_adjacent_segments(
        self,
        session: AsyncSession,
        uid: int,
        aid: str = AID,
    ) -> tuple[Segment, Segment]:
        seg1 = await insert_segment(
            session,
            uid,
            aid=aid,
            start_time=100.0,
            end_time=300.0,
            kind=SegmentKind.driving,
            points=make_points([100.0, 200.0, 300.0]),
        )
        seg2 = await insert_segment(
            session,
            uid,
            aid=aid,
            start_time=300.0,
            end_time=500.0,
            kind=SegmentKind.hike,
            points=make_points([300.0, 400.0, 500.0]),
        )
        return seg1, seg2

    async def test_flight_segment_rejected(
        self,
        session: AsyncSession,
        signed_album: AlbumScenario,
        album_routes: AlbumRoutes,
    ) -> None:
        await insert_segment(
            session,
            signed_album.uid,
            start_time=100.0,
            end_time=300.0,
            kind=SegmentKind.flight,
        )

        with patch(
            "app.api.v1.routes.albums.enqueue_album_route_enrichment",
            create=True,
        ) as mock_enqueue:
            resp = await album_routes.adjust_boundary()
        assert resp.status_code == 400
        assert "flight" in resp.json()["detail"].lower()
        mock_enqueue.assert_not_called()

    async def test_route_reset_after_boundary_adjust(
        self,
        session: AsyncSession,
        signed_album: AlbumScenario,
        album_routes: AlbumRoutes,
    ) -> None:
        seg = await insert_segment(
            session,
            signed_album.uid,
            start_time=100.0,
            end_time=300.0,
            kind=SegmentKind.driving,
            points=make_points([100.0, 200.0, 300.0]),
        )
        seg.route = [(4.0, 52.0), (4.01, 52.01)]
        session.add(seg)
        await session.flush()
        await insert_segment(
            session,
            signed_album.uid,
            start_time=300.0,
            end_time=500.0,
            kind=SegmentKind.hike,
            points=make_points([300.0, 400.0, 500.0]),
        )

        data = await album_routes.adjust_boundary_ok()
        for seg_data in data:
            assert seg_data.get("route") is None


class TestGenerateChapterPdf:
    async def test_generate_chapters_pdf_rejects_unknown_selected_chapter(
        self,
        session: AsyncSession,
        signed_album: AlbumScenario,
        album_routes: AlbumRoutes,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        await _save_chapters(session, signed_album, album_routes, ["first"])
        monkeypatch.setattr(
            app.state,
            "browser_manager",
            _browser_manager(),
            raising=False,
        )

        resp = await album_routes.generate_chapters_pdf(chapters=["missing"])

        assert resp.status_code == 404
        assert resp.json()["detail"] == "Chapter not found"

        assert resp.json()["detail"] == "Chapter not found"
