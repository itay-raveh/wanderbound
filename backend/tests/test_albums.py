from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import pytest

from app.logic.pdf import PdfArtifact, PdfDone, PdfEvent
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
    pages: list[list[str]],
    unused: list[str],
) -> None:
    assert data["cover"] == cover
    assert data["pages"] == pages
    assert data["unused"] == unused


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

    @pytest.mark.usefixtures("signed_album")
    async def test_returns_album_meta_without_media(
        self, album_routes: AlbumRoutes
    ) -> None:
        resp = await album_routes.get_album()
        assert resp.status_code == 200
        data = resp.json()
        assert "media" not in data
        assert "steps" not in data
        assert "segments" not in data

    async def test_read_backfills_default_chapter_for_legacy_album(
        self,
        session: AsyncSession,
        signed_album: AlbumScenario,
        album_routes: AlbumRoutes,
    ) -> None:
        await insert_step(session, signed_album.uid, step_id=2, timestamp=200.0)
        await insert_step(session, signed_album.uid, step_id=1, timestamp=100.0)
        await session.commit()

        resp = await album_routes.get_album()

        assert resp.status_code == 200
        assert resp.json()["chapters"] == [
            {
                "id": "chapter-1",
                "title": None,
                "subtitle": None,
                "step_ids": [1, 2],
                "front_cover_photo": "photo1.jpg",
                "back_cover_photo": "photo2.jpg",
            }
        ]


class TestReadSegments:
    async def test_returns_outlines_without_points(
        self,
        session: AsyncSession,
        signed_album: AlbumScenario,
        album_routes: AlbumRoutes,
    ) -> None:
        await insert_segment(session, signed_album.uid)

        resp = await album_routes.get_segments()
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        outline = data[0]
        assert outline["kind"] == "driving"
        assert "start_coord" in outline
        assert "end_coord" in outline
        assert "points" not in outline
        assert "route" not in outline


class TestReadSegmentPoints:
    async def test_returns_segments_with_points_for_time_range(
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
            kind=SegmentKind.driving,
        )
        await insert_segment(
            session,
            signed_album.uid,
            start_time=500.0,
            end_time=700.0,
            kind=SegmentKind.hike,
        )

        data, mock_enqueue = await album_routes.get_segment_points_ok(
            from_time=50.0, to_time=400.0
        )
        mock_enqueue.assert_not_called()
        assert len(data) == 1
        assert data[0]["kind"] == "driving"
        assert len(data[0]["points"]) == 3


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
            title="Whole Trip",
            subtitle="Full route",
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
                    "title": None,
                    "subtitle": None,
                    "step_ids": [3],
                    "front_cover_photo": "chapter-front.jpg",
                    "back_cover_photo": "chapter-back.jpg",
                },
            ],
        )

        resp = await album_routes.print_bundle(chapter="chapter-1")

        assert resp.status_code == 200
        data = resp.json()
        assert data["album"]["title"] == "First Chapter"
        assert data["album"]["subtitle"] == ""
        assert data["album"]["front_cover_photo"] == "chapter-front.jpg"
        assert data["album"]["back_cover_photo"] == "chapter-back.jpg"
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
                    "step_ids": [1],
                    "front_cover_photo": "front.jpg",
                    "back_cover_photo": "back.jpg",
                }
            ],
        )

        resp = await album_routes.print_bundle(chapter="missing")

        assert resp.status_code == 404
        assert resp.json()["detail"] == "Chapter not found"


class TestSegmentPointsReadOnly:
    @pytest.mark.parametrize("kind", [SegmentKind.driving, SegmentKind.hike])
    async def test_segment_returns_stored_null_route(
        self,
        session: AsyncSession,
        signed_album: AlbumScenario,
        album_routes: AlbumRoutes,
        kind: SegmentKind,
    ) -> None:
        await insert_segment(
            session,
            signed_album.uid,
            start_time=100.0,
            end_time=300.0,
            kind=kind,
        )

        data, mock_enqueue = await album_routes.get_segment_points_ok()

        mock_enqueue.assert_not_called()
        assert len(data) == 1
        assert data[0]["route"] is None

    async def test_already_matched_route_returned_as_stored(
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
        )
        seg.route = [(4.0, 52.0), (4.01, 52.01)]
        session.add(seg)
        await session.flush()

        data, mock_enqueue = await album_routes.get_segment_points_ok()

        mock_enqueue.assert_not_called()
        assert data[0]["route"] == [[4.0, 52.0], [4.01, 52.01]]


@pytest.mark.usefixtures("signed_album")
class TestUpdateAlbum:
    async def test_update_cover_photos(self, album_routes: AlbumRoutes) -> None:
        data = await album_routes.update_album_ok(
            front_cover_photo="new_front.jpg",
            back_cover_photo="new_back.jpg",
        )
        assert data["front_cover_photo"] == "new_front.jpg"
        assert data["back_cover_photo"] == "new_back.jpg"

    async def test_partial_update_preserves_other_fields(
        self, album_routes: AlbumRoutes
    ) -> None:
        data = await album_routes.update_album_ok(title="Changed")
        assert data["title"] == "Changed"
        assert data["subtitle"] == "A subtitle"
        assert data["front_cover_photo"] == "photo1.jpg"

    async def test_update_chapters_persists_manual_step_groups(
        self,
        session: AsyncSession,
        signed_album: AlbumScenario,
        album_routes: AlbumRoutes,
    ) -> None:
        await insert_step(session, signed_album.uid, step_id=1)
        await insert_step(session, signed_album.uid, step_id=2)
        await session.commit()

        data = await album_routes.update_album_ok(
            chapters=[
                {
                    "id": "andes",
                    "title": "The Andes",
                    "subtitle": None,
                    "step_ids": [1, 2],
                    "front_cover_photo": "front.jpg",
                    "back_cover_photo": "back.jpg",
                }
            ]
        )

        assert data["chapters"] == [
            {
                "id": "andes",
                "title": "The Andes",
                "subtitle": None,
                "step_ids": [1, 2],
                "front_cover_photo": "front.jpg",
                "back_cover_photo": "back.jpg",
            }
        ]

        resp = await album_routes.get_album()
        assert resp.status_code == 200
        assert resp.json()["chapters"] == data["chapters"]

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
                    "step_ids": [1, 2],
                    "front_cover_photo": "front.jpg",
                    "back_cover_photo": "back.jpg",
                },
                {
                    "id": "south",
                    "step_ids": [2],
                    "front_cover_photo": "front.jpg",
                    "back_cover_photo": "back.jpg",
                },
            ]
        )

        assert resp.status_code == 400
        assert "Step 2 is already assigned to another chapter" in resp.json()["detail"]

    async def test_update_chapters_rejects_empty_chapters(
        self,
        album_routes: AlbumRoutes,
    ) -> None:
        resp = await album_routes.update_album(
            chapters=[
                {
                    "id": "empty",
                    "step_ids": [],
                    "front_cover_photo": "front.jpg",
                    "back_cover_photo": "back.jpg",
                },
            ]
        )

        assert resp.status_code == 400
        assert "Chapter empty has no steps" in resp.json()["detail"]

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
                    "step_ids": [1, 999],
                    "front_cover_photo": "front.jpg",
                    "back_cover_photo": "back.jpg",
                }
            ]
        )

        assert resp.status_code == 400
        assert "Unknown chapter step IDs: 999" in resp.json()["detail"]

    async def test_update_chapters_rejects_missing_steps(
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
                    "id": "partial",
                    "step_ids": [1],
                    "front_cover_photo": "front.jpg",
                    "back_cover_photo": "back.jpg",
                }
            ]
        )

        assert resp.status_code == 400
        assert "Missing chapter step IDs: 2" in resp.json()["detail"]


class TestUpdateStep:
    async def test_partial_update_preserves_other_fields(
        self,
        session: AsyncSession,
        signed_album: AlbumScenario,
        album_routes: AlbumRoutes,
    ) -> None:
        await insert_step(session, signed_album.uid)

        resp = await album_routes.update_step(name="New Name")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "New Name"
        assert data["pages"] == [["photo1.jpg"]]
        assert data["unused"] == ["photo2.jpg"]
        assert data["description"] == "A test step."
        assert data["cover"] is None

    async def test_media_layout_update_rewrites_step_placements(
        self,
        session: AsyncSession,
        signed_album: AlbumScenario,
        album_routes: AlbumRoutes,
    ) -> None:
        expected_layout = {
            "cover": "cover.jpg",
            "pages": [["a.jpg", "b.jpg"], ["c.jpg"]],
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

    async def test_media_layout_update_rejects_missing_album_media(
        self,
        session: AsyncSession,
        signed_album: AlbumScenario,
        album_routes: AlbumRoutes,
    ) -> None:
        await insert_step(session, signed_album.uid)
        await session.commit()

        resp = await album_routes.update_media_layout(
            cover=None, pages=[["missing.jpg"]], unused=[]
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

    async def test_adjust_end_handle_success(
        self,
        session: AsyncSession,
        signed_album: AlbumScenario,
        album_routes: AlbumRoutes,
    ) -> None:
        await self._setup_adjacent_segments(session, signed_album.uid)

        with patch(
            "app.api.v1.routes.albums.enqueue_album_route_enrichment",
            create=True,
        ) as mock_enqueue:
            data = await album_routes.adjust_boundary_ok()
        mock_enqueue.assert_called_once()
        _, _, called_uid, called_aid = mock_enqueue.call_args.args
        assert (called_uid, called_aid) == (signed_album.uid, AID)
        assert isinstance(data, list)
        assert len(data) == 2
        assert "start_coord" in data[0]
        assert "end_coord" in data[0]
        assert "points" not in data[0]

    async def test_adjust_start_handle_success(
        self,
        session: AsyncSession,
        signed_album: AlbumScenario,
        album_routes: AlbumRoutes,
    ) -> None:
        await insert_segment(
            session,
            signed_album.uid,
            start_time=100.0,
            end_time=200.0,
            kind=SegmentKind.driving,
            points=make_points([100.0, 150.0, 200.0]),
        )
        await insert_segment(
            session,
            signed_album.uid,
            start_time=200.0,
            end_time=500.0,
            kind=SegmentKind.hike,
            points=make_points([200.0, 300.0, 400.0, 500.0]),
        )

        data = await album_routes.adjust_boundary_ok(
            start_time=200.0,
            end_time=500.0,
            new_boundary_time=300.0,
            handle="start",
        )
        assert isinstance(data, list)
        assert len(data) == 2

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


class TestPrintBundle:
    async def test_returns_full_bundle(
        self,
        session: AsyncSession,
        signed_album: AlbumScenario,
        album_routes: AlbumRoutes,
    ) -> None:
        await insert_step(session, signed_album.uid)
        await insert_segment(session, signed_album.uid)

        resp = await album_routes.print_bundle()
        assert resp.status_code == 200
        data = resp.json()
        assert "album" in data
        assert "steps" in data
        assert "segments" in data
        assert "total_distance_km" in data
        assert "media" in data["album"]
        assert data["album"]["media"][0]["uid"] == signed_album.uid
        assert data["album"]["media"][0]["aid"] == AID
        assert data["album"]["media"][0]["byte_size"] == 1234
        assert "updated_at" in data["album"]["media"][0]
        assert len(data["steps"]) == 1
        assert len(data["segments"]) == 1
        assert isinstance(data["total_distance_km"], float)


class TestDownloadPdf:
    async def test_valid_token_returns_file(
        self, album_routes: AlbumRoutes, tmp_path: Path
    ) -> None:
        pdf_path = tmp_path / "test.pdf"
        pdf_path.write_bytes(b"%PDF-1.4 fake content")

        with patch(
            "app.api.v1.routes.albums.pop_pdf_token",
            new=AsyncMock(
                return_value=PdfArtifact(
                    path=pdf_path,
                    filename="my-album.pdf",
                    media_type="application/pdf",
                )
            ),
        ):
            resp = await album_routes.download_pdf("valid-token")

        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/pdf"
        assert "my-album.pdf" in resp.headers.get("content-disposition", "")
        assert resp.content == b"%PDF-1.4 fake content"
        assert not pdf_path.exists()

    async def test_valid_zip_token_returns_zip_file(
        self, album_routes: AlbumRoutes, tmp_path: Path
    ) -> None:
        zip_path = tmp_path / "chapters.zip"
        zip_path.write_bytes(b"fake zip")

        with patch(
            "app.api.v1.routes.albums.pop_pdf_token",
            new=AsyncMock(
                return_value=PdfArtifact(
                    path=zip_path,
                    filename="my-album-chapters.zip",
                    media_type="application/zip",
                )
            ),
        ):
            resp = await album_routes.download_pdf("valid-token")

        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/zip"
        assert "my-album-chapters.zip" in resp.headers.get("content-disposition", "")
        assert resp.content == b"fake zip"
        assert not zip_path.exists()


class TestGenerateChapterPdf:
    async def test_generate_chapters_pdf_uses_saved_chapter_order(
        self,
        session: AsyncSession,
        signed_album: AlbumScenario,
        album_routes: AlbumRoutes,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        await insert_step(session, signed_album.uid, step_id=1)
        await insert_step(session, signed_album.uid, step_id=2)
        await album_routes.update_album_ok(
            chapters=[
                {
                    "id": "first",
                    "step_ids": [1],
                    "front_cover_photo": "front.jpg",
                    "back_cover_photo": "back.jpg",
                },
                {
                    "id": "second",
                    "step_ids": [2],
                    "front_cover_photo": "front.jpg",
                    "back_cover_photo": "back.jpg",
                },
            ],
        )
        captured: dict[str, object] = {}

        async def render_zip(
            *args: object, **kwargs: object
        ) -> AsyncIterator[PdfEvent]:
            captured["args"] = args
            captured["kwargs"] = kwargs
            download_id = "zip-token"
            yield PdfDone(token=download_id)

        monkeypatch.setattr(
            app.state,
            "browser_manager",
            SimpleNamespace(get=AsyncMock(return_value=object())),
            raising=False,
        )
        with patch(
            "app.api.v1.routes.albums.render_album_chapters_zip_stream",
            render_zip,
        ):
            resp = await album_routes.generate_chapters_pdf()

        assert resp.status_code == 200
        args = captured["args"]
        assert isinstance(args, tuple)
        assert args[3] == ["first", "second"]

    async def test_generate_pdf_rejects_unknown_chapter_before_rendering(
        self,
        session: AsyncSession,
        signed_album: AlbumScenario,
        album_routes: AlbumRoutes,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        await insert_step(session, signed_album.uid, step_id=1)
        await album_routes.update_album_ok(
            chapters=[
                {
                    "id": "first",
                    "step_ids": [1],
                    "front_cover_photo": "front.jpg",
                    "back_cover_photo": "back.jpg",
                }
            ],
        )
        monkeypatch.setattr(
            app.state,
            "browser_manager",
            SimpleNamespace(get=AsyncMock(return_value=object())),
            raising=False,
        )

        resp = await album_routes.client.post(
            f"/api/v1/albums/{AID}/pdf/generate",
            params={"chapter": "missing"},
        )

        assert resp.status_code == 404
        assert resp.json()["detail"] == "Chapter not found"
