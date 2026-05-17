from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from app.models.segment import Segment, SegmentKind

from .factories import (
    AID,
    insert_album,
    insert_album_media,
    insert_segment,
    insert_step,
    make_points,
    sign_in_and_upload,
    sign_in_with_album,
)

if TYPE_CHECKING:
    from httpx import AsyncClient, Response
    from sqlmodel.ext.asyncio.session import AsyncSession


async def _get_segment_points(
    client: AsyncClient,
    *,
    from_time: float = 0.0,
    to_time: float = 1000.0,
) -> tuple[Response, MagicMock]:
    with patch(
        "app.api.v1.routes.albums.enqueue_album_route_enrichment",
    ) as mock_enqueue:
        resp = await client.get(
            f"/api/v1/albums/{AID}/segments/points",
            params={"from_time": from_time, "to_time": to_time},
        )
    return resp, mock_enqueue


async def _adjust_boundary(
    client: AsyncClient,
    *,
    start_time: float = 100.0,
    end_time: float = 300.0,
    new_boundary_time: float = 200.0,
    handle: str = "end",
) -> Response:
    return await client.patch(
        f"/api/v1/albums/{AID}/segments/adjust-boundary",
        json={
            "start_time": start_time,
            "end_time": end_time,
            "new_boundary_time": new_boundary_time,
            "handle": handle,
        },
    )


class TestReadAlbum:
    async def test_cannot_read_other_users_album(
        self, client: AsyncClient, session: AsyncSession, tmp_path: Path
    ) -> None:
        await sign_in_and_upload(client, tmp_path / "users")
        await insert_album(session, uid=9999, aid="other-trip")

        resp = await client.get("/api/v1/albums/other-trip")
        assert resp.status_code == 404

    async def test_returns_album_meta_without_media(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        await sign_in_with_album(client, session)

        resp = await client.get(f"/api/v1/albums/{AID}")
        assert resp.status_code == 200
        data = resp.json()
        assert "media" not in data
        assert "steps" not in data
        assert "segments" not in data


class TestReadSegments:
    async def test_returns_outlines_without_points(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        album = await sign_in_with_album(client, session)
        await insert_segment(session, album.uid)

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
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        album = await sign_in_with_album(client, session)
        await insert_segment(
            session,
            album.uid,
            start_time=100.0,
            end_time=300.0,
            kind=SegmentKind.driving,
        )
        await insert_segment(
            session,
            album.uid,
            start_time=500.0,
            end_time=700.0,
            kind=SegmentKind.hike,
        )

        resp, mock_enqueue = await _get_segment_points(
            client, from_time=50.0, to_time=400.0
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
        self, client: AsyncClient, session: AsyncSession, kind: SegmentKind
    ) -> None:
        album = await sign_in_with_album(client, session)
        await insert_segment(
            session,
            album.uid,
            start_time=100.0,
            end_time=300.0,
            kind=kind,
        )

        resp, mock_enqueue = await _get_segment_points(client)

        mock_enqueue.assert_not_called()
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["route"] is None

    async def test_already_matched_route_returned_as_stored(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        album = await sign_in_with_album(client, session)
        seg = await insert_segment(
            session,
            album.uid,
            start_time=100.0,
            end_time=300.0,
            kind=SegmentKind.driving,
        )
        seg.route = [(4.0, 52.0), (4.01, 52.01)]
        session.add(seg)
        await session.flush()

        resp, mock_enqueue = await _get_segment_points(client)

        mock_enqueue.assert_not_called()
        assert resp.json()[0]["route"] == [[4.0, 52.0], [4.01, 52.01]]


class TestUpdateAlbum:
    async def test_update_cover_photos(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        await sign_in_with_album(client, session)

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
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        await sign_in_with_album(client, session)

        resp = await client.patch(f"/api/v1/albums/{AID}", json={"title": "Changed"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "Changed"
        assert data["subtitle"] == "A subtitle"
        assert data["front_cover_photo"] == "photo1.jpg"


class TestUpdateStep:
    async def test_partial_update_preserves_other_fields(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        album = await sign_in_with_album(client, session)
        await insert_step(session, album.uid)

        resp = await client.patch(
            f"/api/v1/albums/{AID}/steps/1",
            json={"name": "New Name"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "New Name"
        assert data["pages"] == [["photo1.jpg"]]
        assert data["unused"] == ["photo2.jpg"]
        assert data["description"] == "A test step."
        assert data["cover"] is None

    async def test_media_layout_update_rewrites_step_placements(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        album = await sign_in_with_album(client, session)
        for name in ("a.jpg", "b.jpg", "c.jpg", "cover.jpg", "unused.jpg"):
            await insert_album_media(session, album.uid, name=name)
        await insert_step(session, album.uid)
        await session.commit()

        resp = await client.put(
            f"/api/v1/albums/{AID}/steps/1/media-layout",
            json={
                "cover": "cover.jpg",
                "pages": [["a.jpg", "b.jpg"], ["c.jpg"]],
                "unused": ["unused.jpg"],
            },
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["cover"] == "cover.jpg"
        assert data["pages"] == [["a.jpg", "b.jpg"], ["c.jpg"]]
        assert data["unused"] == ["unused.jpg"]

        get_resp = await client.get(f"/api/v1/albums/{AID}/steps")
        assert get_resp.status_code == 200
        assert get_resp.json()[0]["cover"] == "cover.jpg"
        assert get_resp.json()[0]["pages"] == [["a.jpg", "b.jpg"], ["c.jpg"]]
        assert get_resp.json()[0]["unused"] == ["unused.jpg"]

    async def test_media_layout_update_rejects_missing_album_media(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        album = await sign_in_with_album(client, session)
        await insert_step(session, album.uid)
        await session.commit()

        resp = await client.put(
            f"/api/v1/albums/{AID}/steps/1/media-layout",
            json={"cover": None, "pages": [["missing.jpg"]], "unused": []},
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
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        album = await sign_in_with_album(client, session)
        await insert_segment(
            session,
            album.uid,
            start_time=100.0,
            end_time=300.0,
            kind=SegmentKind.flight,
        )

        with patch(
            "app.api.v1.routes.albums.enqueue_album_route_enrichment",
            create=True,
        ) as mock_enqueue:
            resp = await _adjust_boundary(client)
        assert resp.status_code == 400
        assert "flight" in resp.json()["detail"].lower()
        mock_enqueue.assert_not_called()

    async def test_adjust_end_handle_success(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        album = await sign_in_with_album(client, session)
        await self._setup_adjacent_segments(session, album.uid)

        with patch(
            "app.api.v1.routes.albums.enqueue_album_route_enrichment",
            create=True,
        ) as mock_enqueue:
            resp = await _adjust_boundary(client)
        assert resp.status_code == 200
        mock_enqueue.assert_called_once()
        _, _, called_uid, called_aid = mock_enqueue.call_args.args
        assert (called_uid, called_aid) == (album.uid, AID)
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 2
        assert "start_coord" in data[0]
        assert "end_coord" in data[0]
        assert "points" not in data[0]

    async def test_adjust_start_handle_success(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        album = await sign_in_with_album(client, session)
        await insert_segment(
            session,
            album.uid,
            start_time=100.0,
            end_time=200.0,
            kind=SegmentKind.driving,
            points=make_points([100.0, 150.0, 200.0]),
        )
        await insert_segment(
            session,
            album.uid,
            start_time=200.0,
            end_time=500.0,
            kind=SegmentKind.hike,
            points=make_points([200.0, 300.0, 400.0, 500.0]),
        )

        resp = await _adjust_boundary(
            client,
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
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        album = await sign_in_with_album(client, session)
        seg = await insert_segment(
            session,
            album.uid,
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
            album.uid,
            start_time=300.0,
            end_time=500.0,
            kind=SegmentKind.hike,
            points=make_points([300.0, 400.0, 500.0]),
        )

        resp = await _adjust_boundary(client)
        assert resp.status_code == 200
        data = resp.json()
        for seg_data in data:
            assert seg_data.get("route") is None


class TestPrintBundle:
    async def test_returns_full_bundle(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        album = await sign_in_with_album(client, session)
        await insert_step(session, album.uid)
        await insert_segment(session, album.uid)

        resp = await client.get(f"/api/v1/albums/{AID}/print-bundle")
        assert resp.status_code == 200
        data = resp.json()
        assert "album" in data
        assert "steps" in data
        assert "segments" in data
        assert "total_distance_km" in data
        assert "media" in data["album"]
        assert data["album"]["media"][0]["uid"] == album.uid
        assert data["album"]["media"][0]["aid"] == AID
        assert data["album"]["media"][0]["byte_size"] == 1234
        assert "updated_at" in data["album"]["media"][0]
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
        assert not pdf_path.exists()
