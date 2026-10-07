from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast
from unittest.mock import patch
from uuid import uuid4

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
    assert [
        {"kind": page["kind"], "media": page["media"]}
        for page in cast("list[dict[str, object]]", data["pages"])
    ] == pages
    assert data["unused"] == unused


def _api_page(kind: str, media: list[str]) -> dict[str, object]:
    return {
        "id": str(uuid4()),
        "kind": kind,
        "slots": [
            {"id": str(uuid4()), "kind": "photo", "media_name": name} for name in media
        ],
    }


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
    @pytest.mark.usefixtures("signed_album")
    @pytest.mark.parametrize(
        "colors",
        [
            None,
            {"nl": "red"},
            {"nl": "#12345678"},
            {"nl": "prefix#123456"},
            {"netherlands": "#123456"},
        ],
    )
    async def test_invalid_colors_leave_album_unchanged(
        self,
        album_routes: AlbumRoutes,
        colors: object,
    ) -> None:
        before = (await album_routes.get_album()).json()
        response = await album_routes.update_album(colors=colors, font="Georgia")
        assert response.status_code == 422
        assert (await album_routes.get_album()).json() == before

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

        resp = await album_routes.update_media_layout(
            cover=expected_layout["cover"],
            pages=[
                _api_page(page["kind"], page["media"])
                for page in expected_layout["pages"]
            ],
            unused=expected_layout["unused"],
        )
        assert resp.status_code == 200
        data = resp.json()
        _assert_step_layout(data, **expected_layout)

        get_resp = await album_routes.get_steps()
        assert get_resp.status_code == 200
        _assert_step_layout(get_resp.json()[0], **expected_layout)

    async def test_reorder_and_text_keep_page_and_slot_identity(
        self,
        session: AsyncSession,
        signed_album: AlbumScenario,
        album_routes: AlbumRoutes,
    ) -> None:
        for name in ("a.jpg", "b.jpg"):
            await insert_album_media(session, signed_album.uid, name=name)
        await insert_step(session, signed_album.uid)
        await session.commit()
        first = (
            await album_routes.update_media_layout(
                cover=None,
                pages=[
                    _api_page("grid", ["a.jpg"]),
                    _api_page("grid", ["b.jpg"]),
                ],
                unused=[],
            )
        ).json()
        pages = first["pages"]
        slot_id = pages[0]["slots"][0]["id"]
        pages[0]["slots"][0] = {
            "id": slot_id,
            "kind": "text",
            "text": "A day in Lima",
            "frame_orientation": "landscape",
        }
        response = await album_routes.update_media_layout(
            cover=None, pages=pages[::-1], unused=["a.jpg"]
        )
        assert response.status_code == 200
        saved = (await album_routes.get_steps()).json()[0]
        assert [page["id"] for page in saved["pages"]] == [
            pages[1]["id"],
            pages[0]["id"],
        ]
        assert saved["pages"][1]["slots"][0]["id"] == slot_id
        assert saved["pages"][1]["slots"][0]["text"] == "A day in Lima"
        assert saved["unused"] == ["a.jpg"]
        for legacy_pages in ([], [{"kind": "grid", "media": ["b.jpg"]}]):
            legacy = await album_routes.client.put(
                f"/api/v1/albums/{signed_album.aid}/steps/1/media-layout",
                json={"cover": None, "pages": legacy_pages, "unused": ["a.jpg"]},
            )
            assert legacy.status_code == 422
            assert (await album_routes.get_steps()).json()[0]["pages"] == saved["pages"]
        cleared = await album_routes.update_media_layout(
            cover=None, pages=[], unused=["a.jpg", "b.jpg"]
        )
        assert cleared.status_code == 200
        assert (await album_routes.get_steps()).json()[0]["pages"] == []

    @pytest.mark.usefixtures("signed_album")
    @pytest.mark.parametrize("media", [[], ["a.jpg", "b.jpg"]])
    async def test_panorama_spread_requires_one_media(
        self,
        album_routes: AlbumRoutes,
        media: list[str],
    ) -> None:
        resp = await album_routes.update_media_layout(
            cover=None,
            pages=[_api_page("panorama_spread", media)],
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
            pages=[_api_page("grid", ["missing.jpg"])],
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
