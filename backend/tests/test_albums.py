from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import patch

from app.logic.layout.media import Media
from app.models.album import Album
from app.models.polarsteps import Location, Point
from app.models.segment import Segment, SegmentKind
from app.models.step import Step
from app.models.weather import Weather, WeatherData

from .conftest import sign_in_and_upload

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlmodel.ext.asyncio.session import AsyncSession

LOCATION = Location(
    name="Amsterdam", detail="NH", country_code="nl", lat=52.37, lon=4.89
)
WEATHER = Weather(day=WeatherData(temp=20.0, feels_like=18.0, icon="sun"), night=None)
AID = "trip-1"


def _make_points(times: list[float]) -> list[Point]:
    return [
        Point(lat=52.0 + i * 0.01, lon=4.0 + i * 0.01, time=t)
        for i, t in enumerate(times)
    ]


async def _insert_album(
    session: AsyncSession,
    uid: int,
    aid: str = AID,
) -> Album:
    album = Album(
        uid=uid,
        id=aid,
        title="Test Album",
        subtitle="A subtitle",
        excluded_steps=[],
        maps_ranges=[],
        front_cover_photo="photo1.jpg",
        back_cover_photo="photo2.jpg",
        colors={"nl": "#0000ff"},
        media=[Media(name="photo1.jpg", width=1920, height=1080)],
        font="Assistant",
        body_font="Frank Ruhl Libre",
    )
    session.add(album)
    await session.flush()
    return album


async def _insert_step(
    session: AsyncSession,
    uid: int,
    aid: str = AID,
    step_id: int = 1,
    timestamp: float = 1_700_000_000.0,
) -> Step:
    step = Step(
        uid=uid,
        aid=aid,
        id=step_id,
        name="Test Step",
        description="A test step.",
        cover=None,
        pages=[["photo1.jpg"]],
        unused=["photo2.jpg"],
        timestamp=timestamp,
        timezone_id="Europe/Amsterdam",
        location=LOCATION,
        elevation=0,
        weather=WEATHER,
    )
    session.add(step)
    await session.flush()
    return step


async def _insert_segment(
    session: AsyncSession,
    uid: int,
    aid: str = AID,
    start_time: float = 1_700_000_000.0,
    end_time: float = 1_700_003_600.0,
    kind: SegmentKind = SegmentKind.driving,
    points: list[Point] | None = None,
) -> Segment:
    pts = points or _make_points([start_time, (start_time + end_time) / 2, end_time])
    segment = Segment(
        uid=uid,
        aid=aid,
        start_time=start_time,
        end_time=end_time,
        kind=kind,
        timezone_id="UTC",
        points=pts,
    )
    session.add(segment)
    await session.flush()
    return segment


class TestReadAlbum:
    async def test_cannot_read_other_users_album(
        self, client: AsyncClient, session: AsyncSession, tmp_path: Path
    ) -> None:
        await sign_in_and_upload(client, tmp_path / "users")
        await _insert_album(session, uid=9999, aid="other-trip")

        resp = await client.get("/api/v1/albums/other-trip")
        assert resp.status_code == 404

    async def test_returns_album_meta_without_media(
        self, client: AsyncClient, session: AsyncSession, tmp_path: Path
    ) -> None:
        uid = (await sign_in_and_upload(client, tmp_path / "users"))["id"]
        await _insert_album(session, uid)

        resp = await client.get(f"/api/v1/albums/{AID}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "Test Album"
        assert data["colors"] == {"nl": "#0000ff"}
        assert "media" not in data
        assert "steps" not in data
        assert "segments" not in data


class TestReadSegments:
    async def test_returns_outlines_without_points(
        self, client: AsyncClient, session: AsyncSession, tmp_path: Path
    ) -> None:
        uid = (await sign_in_and_upload(client, tmp_path / "users"))["id"]
        await _insert_album(session, uid)
        await _insert_segment(session, uid)

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


class TestReadSteps:
    async def test_returns_all_steps(
        self, client: AsyncClient, session: AsyncSession, tmp_path: Path
    ) -> None:
        uid = (await sign_in_and_upload(client, tmp_path / "users"))["id"]
        await _insert_album(session, uid)
        await _insert_step(session, uid, step_id=1)
        await _insert_step(session, uid, step_id=2, timestamp=1_700_100_000.0)

        resp = await client.get(f"/api/v1/albums/{AID}/steps")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["name"] == "Test Step"


class TestReadSegmentPoints:
    async def test_returns_segments_with_points_for_time_range(
        self, client: AsyncClient, session: AsyncSession, tmp_path: Path
    ) -> None:
        uid = (await sign_in_and_upload(client, tmp_path / "users"))["id"]
        await _insert_album(session, uid)
        await _insert_segment(
            session, uid, start_time=100.0, end_time=300.0, kind=SegmentKind.driving
        )
        await _insert_segment(
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


class TestUpdateAlbum:
    async def test_update_cover_photos(
        self, client: AsyncClient, session: AsyncSession, tmp_path: Path
    ) -> None:
        uid = (await sign_in_and_upload(client, tmp_path / "users"))["id"]
        await _insert_album(session, uid)

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
        await _insert_album(session, uid)

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
        await _insert_album(session, uid)
        await _insert_step(session, uid)

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
        seg1 = await _insert_segment(
            session,
            uid,
            aid=aid,
            start_time=100.0,
            end_time=300.0,
            kind=SegmentKind.driving,
            points=_make_points([100.0, 200.0, 300.0]),
        )
        seg2 = await _insert_segment(
            session,
            uid,
            aid=aid,
            start_time=300.0,
            end_time=500.0,
            kind=SegmentKind.hike,
            points=_make_points([300.0, 400.0, 500.0]),
        )
        return seg1, seg2

    async def test_segment_not_found(
        self, client: AsyncClient, session: AsyncSession, tmp_path: Path
    ) -> None:
        uid = (await sign_in_and_upload(client, tmp_path / "users"))["id"]
        await _insert_album(session, uid)

        resp = await client.patch(
            f"/api/v1/albums/{AID}/segments/adjust-boundary",
            json={
                "start_time": 999.0,
                "end_time": 1000.0,
                "new_boundary_time": 999.5,
                "handle": "end",
            },
        )
        assert resp.status_code == 404
        assert "Segment not found" in resp.json()["detail"]

    async def test_flight_segment_rejected(
        self, client: AsyncClient, session: AsyncSession, tmp_path: Path
    ) -> None:
        uid = (await sign_in_and_upload(client, tmp_path / "users"))["id"]
        await _insert_album(session, uid)
        await _insert_segment(
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

    async def test_no_adjacent_segment(
        self, client: AsyncClient, session: AsyncSession, tmp_path: Path
    ) -> None:
        uid = (await sign_in_and_upload(client, tmp_path / "users"))["id"]
        await _insert_album(session, uid)
        await _insert_segment(
            session, uid, start_time=100.0, end_time=300.0, kind=SegmentKind.driving
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
        assert resp.status_code == 404
        assert "adjacent" in resp.json()["detail"].lower()

    async def test_adjust_end_handle_success(
        self, client: AsyncClient, session: AsyncSession, tmp_path: Path
    ) -> None:
        uid = (await sign_in_and_upload(client, tmp_path / "users"))["id"]
        await _insert_album(session, uid)
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
        await _insert_album(session, uid)
        # seg1 ends at 200, seg2 starts at 200 (gap-free boundary)
        await _insert_segment(
            session,
            uid,
            start_time=100.0,
            end_time=200.0,
            kind=SegmentKind.driving,
            points=_make_points([100.0, 150.0, 200.0]),
        )
        await _insert_segment(
            session,
            uid,
            start_time=200.0,
            end_time=500.0,
            kind=SegmentKind.hike,
            points=_make_points([200.0, 300.0, 400.0, 500.0]),
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
        await _insert_album(session, uid)
        # Insert segment with a route
        seg = await _insert_segment(
            session, uid, start_time=100.0, end_time=300.0, kind=SegmentKind.driving,
            points=_make_points([100.0, 200.0, 300.0]),
        )
        # Manually set route on the segment
        seg.route = [(4.0, 52.0), (4.01, 52.01)]
        session.add(seg)
        await session.flush()
        await _insert_segment(
            session, uid, start_time=300.0, end_time=500.0, kind=SegmentKind.hike,
            points=_make_points([300.0, 400.0, 500.0]),
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

    async def test_adjacent_flight_skipped(
        self, client: AsyncClient, session: AsyncSession, tmp_path: Path
    ) -> None:
        uid = (await sign_in_and_upload(client, tmp_path / "users"))["id"]
        await _insert_album(session, uid)
        # Target: driving segment
        await _insert_segment(
            session,
            uid,
            start_time=100.0,
            end_time=300.0,
            kind=SegmentKind.driving,
            points=_make_points([100.0, 200.0, 300.0]),
        )
        # Adjacent: flight segment (should be skipped)
        await _insert_segment(
            session,
            uid,
            start_time=300.0,
            end_time=500.0,
            kind=SegmentKind.flight,
            points=_make_points([300.0, 400.0, 500.0]),
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
        # No non-flight adjacent found
        assert resp.status_code == 404
        assert "adjacent" in resp.json()["detail"].lower()


class TestReadMedia:
    async def test_returns_media_list(
        self, client: AsyncClient, session: AsyncSession, tmp_path: Path
    ) -> None:
        uid = (await sign_in_and_upload(client, tmp_path / "users"))["id"]
        await _insert_album(session, uid)

        resp = await client.get(f"/api/v1/albums/{AID}/media")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "photo1.jpg"
        assert data[0]["width"] == 1920
        assert data[0]["height"] == 1080


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
