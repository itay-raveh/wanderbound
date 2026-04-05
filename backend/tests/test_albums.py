from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import patch

from app.models.segment import Segment, SegmentKind

from .factories import (
    AID,
    insert_album,
    insert_segment,
    insert_step,
    make_points,
    sign_in_and_upload,
)

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlmodel.ext.asyncio.session import AsyncSession


class TestReadAlbum:
    async def test_cannot_read_other_users_album(
        self, client: AsyncClient, session: AsyncSession, tmp_path: Path
    ) -> None:
        await sign_in_and_upload(client, tmp_path / "users")
        await insert_album(session, uid=9999, aid="other-trip")

        resp = await client.get("/api/v1/albums/other-trip")
        assert resp.status_code == 404

    async def test_returns_album_meta_without_media(
        self, client: AsyncClient, session: AsyncSession, tmp_path: Path
    ) -> None:
        uid = (await sign_in_and_upload(client, tmp_path / "users"))["id"]
        await insert_album(session, uid)

        resp = await client.get(f"/api/v1/albums/{AID}")
        assert resp.status_code == 200
        data = resp.json()
        # AlbumMeta excludes heavy fields — only meta returned
        assert "media" not in data
        assert "steps" not in data
        assert "segments" not in data


class TestReadSegments:
    async def test_returns_outlines_without_points(
        self, client: AsyncClient, session: AsyncSession, tmp_path: Path
    ) -> None:
        uid = (await sign_in_and_upload(client, tmp_path / "users"))["id"]
        await insert_album(session, uid)
        await insert_segment(session, uid)

        resp = await client.get(f"/api/v1/albums/{AID}/segments")
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
        self, client: AsyncClient, session: AsyncSession, tmp_path: Path
    ) -> None:
        uid = (await sign_in_and_upload(client, tmp_path / "users"))["id"]
        await insert_album(session, uid)
        await insert_segment(
            session, uid, start_time=100.0, end_time=300.0, kind=SegmentKind.driving
        )
        await insert_segment(
            session, uid, start_time=500.0, end_time=700.0, kind=SegmentKind.hike
        )

        # Request range that only covers the first segment
        resp = await client.get(
            f"/api/v1/albums/{AID}/segments/points",
            params={"from_time": 50.0, "to_time": 400.0},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["kind"] == "driving"
        assert len(data[0]["points"]) == 3


class TestSegmentPointsAutoMatch:
    async def test_driving_segment_gets_matched(
        self, client: AsyncClient, session: AsyncSession, tmp_path: Path
    ) -> None:
        uid = (await sign_in_and_upload(client, tmp_path / "users"))["id"]
        await insert_album(session, uid)
        await insert_segment(
            session, uid, start_time=100.0, end_time=300.0, kind=SegmentKind.driving
        )

        matched_route = [(4.0, 52.0), (4.01, 52.01), (4.02, 52.02)]
        with patch(
            "app.api.v1.routes.albums.match_segments",
            return_value=[matched_route],
        ):
            resp = await client.get(
                f"/api/v1/albums/{AID}/segments/points",
                params={"from_time": 0.0, "to_time": 1000.0},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        # JSON serializes tuples as arrays
        assert data[0]["route"] == [[4.0, 52.0], [4.01, 52.01], [4.02, 52.02]]

    async def test_hike_segment_not_matched(
        self, client: AsyncClient, session: AsyncSession, tmp_path: Path
    ) -> None:
        uid = (await sign_in_and_upload(client, tmp_path / "users"))["id"]
        await insert_album(session, uid)
        await insert_segment(
            session, uid, start_time=100.0, end_time=300.0, kind=SegmentKind.hike
        )

        with patch(
            "app.api.v1.routes.albums.match_segments",
        ) as mock_match:
            resp = await client.get(
                f"/api/v1/albums/{AID}/segments/points",
                params={"from_time": 0.0, "to_time": 1000.0},
            )

        mock_match.assert_not_called()
        data = resp.json()
        assert data[0]["route"] is None

    async def test_already_matched_not_re_matched(
        self, client: AsyncClient, session: AsyncSession, tmp_path: Path
    ) -> None:
        uid = (await sign_in_and_upload(client, tmp_path / "users"))["id"]
        await insert_album(session, uid)
        seg = await insert_segment(
            session, uid, start_time=100.0, end_time=300.0, kind=SegmentKind.driving
        )
        seg.route = [(4.0, 52.0), (4.01, 52.01)]
        session.add(seg)
        await session.flush()

        with patch(
            "app.api.v1.routes.albums.match_segments",
        ) as mock_match:
            resp = await client.get(
                f"/api/v1/albums/{AID}/segments/points",
                params={"from_time": 0.0, "to_time": 1000.0},
            )

        mock_match.assert_not_called()
        assert resp.json()[0]["route"] == [[4.0, 52.0], [4.01, 52.01]]


class TestUpdateAlbum:
    async def test_update_cover_photos(
        self, client: AsyncClient, session: AsyncSession, tmp_path: Path
    ) -> None:
        uid = (await sign_in_and_upload(client, tmp_path / "users"))["id"]
        await insert_album(session, uid)

        resp = await client.patch(
            f"/api/v1/albums/{AID}",
            json={
                "front_cover_photo": "new_front.jpg",
                "back_cover_photo": "new_back.jpg",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["front_cover_photo"] == "new_front.jpg"
        assert data["back_cover_photo"] == "new_back.jpg"

    async def test_partial_update_preserves_other_fields(
        self, client: AsyncClient, session: AsyncSession, tmp_path: Path
    ) -> None:
        uid = (await sign_in_and_upload(client, tmp_path / "users"))["id"]
        await insert_album(session, uid)

        resp = await client.patch(f"/api/v1/albums/{AID}", json={"title": "Changed"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "Changed"
        assert data["subtitle"] == "A subtitle"
        assert data["front_cover_photo"] == "photo1.jpg"


class TestUpdateStep:
    async def test_partial_update_preserves_other_fields(
        self, client: AsyncClient, session: AsyncSession, tmp_path: Path
    ) -> None:
        uid = (await sign_in_and_upload(client, tmp_path / "users"))["id"]
        await insert_album(session, uid)
        await insert_step(session, uid)

        new_pages = [["a.jpg", "b.jpg"], ["c.jpg"]]
        resp = await client.patch(
            f"/api/v1/albums/{AID}/steps/1",
            json={"name": "New Name", "pages": new_pages, "unused": ["x.jpg"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "New Name"
        assert data["pages"] == new_pages
        assert data["unused"] == ["x.jpg"]
        assert data["description"] == "A test step."
        assert data["cover"] is None


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
        self, client: AsyncClient, session: AsyncSession, tmp_path: Path
    ) -> None:
        uid = (await sign_in_and_upload(client, tmp_path / "users"))["id"]
        await insert_album(session, uid)
        await insert_segment(
            session, uid, start_time=100.0, end_time=300.0, kind=SegmentKind.flight
        )

        resp = await client.patch(
            f"/api/v1/albums/{AID}/segments/adjust-boundary",
            json={
                "start_time": 100.0,
                "end_time": 300.0,
                "new_boundary_time": 200.0,
                "handle": "end",
            },
        )
        assert resp.status_code == 400
        assert "flight" in resp.json()["detail"].lower()

    async def test_adjust_end_handle_success(
        self, client: AsyncClient, session: AsyncSession, tmp_path: Path
    ) -> None:
        uid = (await sign_in_and_upload(client, tmp_path / "users"))["id"]
        await insert_album(session, uid)
        await self._setup_adjacent_segments(session, uid)

        resp = await client.patch(
            f"/api/v1/albums/{AID}/segments/adjust-boundary",
            json={
                "start_time": 100.0,
                "end_time": 300.0,
                "new_boundary_time": 200.0,
                "handle": "end",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        # Response is now a flat list of SegmentOutline objects
        assert isinstance(data, list)
        assert len(data) == 2
        assert "start_coord" in data[0]
        assert "end_coord" in data[0]
        assert "points" not in data[0]

    async def test_adjust_start_handle_success(
        self, client: AsyncClient, session: AsyncSession, tmp_path: Path
    ) -> None:
        uid = (await sign_in_and_upload(client, tmp_path / "users"))["id"]
        await insert_album(session, uid)
        # seg1 ends at 200, seg2 starts at 200 (gap-free boundary)
        await insert_segment(
            session,
            uid,
            start_time=100.0,
            end_time=200.0,
            kind=SegmentKind.driving,
            points=make_points([100.0, 150.0, 200.0]),
        )
        await insert_segment(
            session,
            uid,
            start_time=200.0,
            end_time=500.0,
            kind=SegmentKind.hike,
            points=make_points([200.0, 300.0, 400.0, 500.0]),
        )

        # Move the hike's start boundary forward (shrink it)
        resp = await client.patch(
            f"/api/v1/albums/{AID}/segments/adjust-boundary",
            json={
                "start_time": 200.0,
                "end_time": 500.0,
                "new_boundary_time": 300.0,
                "handle": "start",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 2

    async def test_route_reset_after_boundary_adjust(
        self, client: AsyncClient, session: AsyncSession, tmp_path: Path
    ) -> None:
        uid = (await sign_in_and_upload(client, tmp_path / "users"))["id"]
        await insert_album(session, uid)
        # Insert segment with a route
        seg = await insert_segment(
            session,
            uid,
            start_time=100.0,
            end_time=300.0,
            kind=SegmentKind.driving,
            points=make_points([100.0, 200.0, 300.0]),
        )
        # Manually set route on the segment
        seg.route = [(4.0, 52.0), (4.01, 52.01)]
        session.add(seg)
        await session.flush()
        await insert_segment(
            session,
            uid,
            start_time=300.0,
            end_time=500.0,
            kind=SegmentKind.hike,
            points=make_points([300.0, 400.0, 500.0]),
        )

        resp = await client.patch(
            f"/api/v1/albums/{AID}/segments/adjust-boundary",
            json={
                "start_time": 100.0,
                "end_time": 300.0,
                "new_boundary_time": 200.0,
                "handle": "end",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        # Both new segments should have route=None (reset by split_segments)
        for seg_data in data:
            assert seg_data.get("route") is None


class TestPrintBundle:
    async def test_returns_full_bundle(
        self, client: AsyncClient, session: AsyncSession, tmp_path: Path
    ) -> None:
        uid = (await sign_in_and_upload(client, tmp_path / "users"))["id"]
        await insert_album(session, uid)
        await insert_step(session, uid)
        await insert_segment(session, uid)

        resp = await client.get(f"/api/v1/albums/{AID}/print-bundle")
        assert resp.status_code == 200
        data = resp.json()
        assert "album" in data
        assert "steps" in data
        assert "segments" in data
        assert "total_distance_km" in data
        # Album should include media (full Album, not AlbumMeta)
        assert "media" in data["album"]
        assert len(data["steps"]) == 1
        assert len(data["segments"]) == 1
        assert isinstance(data["total_distance_km"], float)


class TestDownloadPdf:
    async def test_valid_token_returns_file(
        self, client: AsyncClient, tmp_path: Path
    ) -> None:
        pdf_path = tmp_path / "test.pdf"
        pdf_path.write_bytes(b"%PDF-1.4 fake content")

        with patch(
            "app.api.v1.routes.albums.pop_pdf_token",
            return_value=(pdf_path, "my-album"),
        ):
            resp = await client.get("/api/v1/albums/pdf/download/valid-token")

        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/pdf"
        assert "my-album.pdf" in resp.headers.get("content-disposition", "")
        assert resp.content == b"%PDF-1.4 fake content"
