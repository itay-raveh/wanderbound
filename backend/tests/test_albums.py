from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from app.models.segment import Segment, SegmentKind

from .factories import (
    AID,
    AlbumScenario,
    insert_album,
    insert_album_media,
    insert_segment,
    insert_step,
    make_points,
    sign_in_and_upload,
)
from .helpers.albums import AlbumRoutes

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlmodel.ext.asyncio.session import AsyncSession


class TestReadAlbum:
    async def test_cannot_read_other_users_album(
        self,
        client: AsyncClient,
        session: AsyncSession,
        album_routes: AlbumRoutes,
        tmp_path: Path,
    ) -> None:
        await sign_in_and_upload(client, tmp_path / "users")
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

        resp, mock_enqueue = await album_routes.get_segment_points(
            from_time=50.0, to_time=400.0
        )
        mock_enqueue.assert_not_called()
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["kind"] == "driving"
        assert len(data[0]["points"]) == 3


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

        resp, mock_enqueue = await album_routes.get_segment_points()

        mock_enqueue.assert_not_called()
        assert resp.status_code == 200
        data = resp.json()
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

        resp, mock_enqueue = await album_routes.get_segment_points()

        mock_enqueue.assert_not_called()
        assert resp.json()[0]["route"] == [[4.0, 52.0], [4.01, 52.01]]


@pytest.mark.usefixtures("signed_album")
class TestUpdateAlbum:
    async def test_update_cover_photos(self, album_routes: AlbumRoutes) -> None:
        resp = await album_routes.update_album(
            front_cover_photo="new_front.jpg",
            back_cover_photo="new_back.jpg",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["front_cover_photo"] == "new_front.jpg"
        assert data["back_cover_photo"] == "new_back.jpg"

    async def test_partial_update_preserves_other_fields(
        self, album_routes: AlbumRoutes
    ) -> None:
        resp = await album_routes.update_album(title="Changed")
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "Changed"
        assert data["subtitle"] == "A subtitle"
        assert data["front_cover_photo"] == "photo1.jpg"


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
        for name in ("a.jpg", "b.jpg", "c.jpg", "cover.jpg", "unused.jpg"):
            await insert_album_media(session, signed_album.uid, name=name)
        await insert_step(session, signed_album.uid)
        await session.commit()

        resp = await album_routes.update_media_layout(
            cover="cover.jpg",
            pages=[["a.jpg", "b.jpg"], ["c.jpg"]],
            unused=["unused.jpg"],
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["cover"] == "cover.jpg"
        assert data["pages"] == [["a.jpg", "b.jpg"], ["c.jpg"]]
        assert data["unused"] == ["unused.jpg"]

        get_resp = await album_routes.get_steps()
        assert get_resp.status_code == 200
        assert get_resp.json()[0]["cover"] == "cover.jpg"
        assert get_resp.json()[0]["pages"] == [["a.jpg", "b.jpg"], ["c.jpg"]]
        assert get_resp.json()[0]["unused"] == ["unused.jpg"]

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
            resp = await album_routes.adjust_boundary()
        assert resp.status_code == 200
        mock_enqueue.assert_called_once()
        _, _, called_uid, called_aid = mock_enqueue.call_args.args
        assert (called_uid, called_aid) == (signed_album.uid, AID)
        data = resp.json()
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

        resp = await album_routes.adjust_boundary(
            start_time=200.0,
            end_time=500.0,
            new_boundary_time=300.0,
            handle="start",
        )
        assert resp.status_code == 200
        data = resp.json()
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

        resp = await album_routes.adjust_boundary()
        assert resp.status_code == 200
        data = resp.json()
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
            return_value=(pdf_path, "my-album"),
        ):
            resp = await album_routes.download_pdf("valid-token")

        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/pdf"
        assert "my-album.pdf" in resp.headers.get("content-disposition", "")
        assert resp.content == b"%PDF-1.4 fake content"
        assert not pdf_path.exists()
