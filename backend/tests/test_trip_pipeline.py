"""Regression tests for the processing pipeline."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.http_clients import HttpClients
from app.logic.trip_pipeline import _process_trip, _save_reupload
from app.logic.trip_processing import PhaseUpdate, SegmentsFound
from app.models.album import Album
from app.models.polarsteps import Location
from app.models.segment import Segment, SegmentKind
from app.models.step import Step
from app.models.user import User
from app.models.weather import Weather, WeatherData
from tests.factories import collect_async, make_points

AID = "test-trip"
UID = 1
_MOCK_HTTP = MagicMock(spec=HttpClients)


class TestProcessTripSegmentEvents:
    async def test_emits_segment_phase_and_counts(self, tmp_path: Path) -> None:
        trip_dir = tmp_path / AID
        trip_dir.mkdir()
        location = Location(
            name="Start",
            detail="",
            country_code="nl",
            lat=52.0,
            lon=4.0,
        )
        trip = SimpleNamespace(
            title="Test Trip",
            step_count=1,
            all_steps=[SimpleNamespace(location=location)],
        )
        user = User(
            id=UID,
            first_name="Test",
            locale="en-US",
            unit_is_km=True,
            temperature_is_celsius=True,
            google_sub="test-sub",
        )
        segments = [
            Segment(
                uid=UID,
                aid=AID,
                start_time=100.0,
                end_time=200.0,
                kind=SegmentKind.driving,
                timezone_id="UTC",
                points=make_points([100.0, 200.0]),
            ),
            Segment(
                uid=UID,
                aid=AID,
                start_time=300.0,
                end_time=400.0,
                kind=SegmentKind.walking,
                timezone_id="UTC",
                points=make_points([300.0, 400.0]),
            ),
        ]
        db_out: list = []

        with (
            patch(
                "app.logic.trip_pipeline.load_trip_data",
                return_value=(trip, []),
            ),
            patch("app.logic.trip_pipeline.cover_name_from_trip", return_value=""),
            patch(
                "app.logic.trip_pipeline.run_elevations",
                new=AsyncMock(return_value=[0.0]),
            ),
            patch(
                "app.logic.trip_pipeline.run_weather",
                new=AsyncMock(return_value={}),
            ),
            patch(
                "app.logic.trip_pipeline._media_pipeline",
                new=AsyncMock(return_value=({}, "")),
            ),
            patch(
                "app.logic.trip_pipeline.build_trip_objects",
                return_value=segments,
            ),
        ):
            events = await collect_async(
                _process_trip(_MOCK_HTTP, user, trip_dir, db_out)
            )

        assert PhaseUpdate(phase="segments", done=0, total=1) in events
        assert PhaseUpdate(phase="segments", done=1, total=1) in events
        assert SegmentsFound(hikes=0, walks=1, drives=1, flights=0) in events
        assert db_out == segments


class TestSaveReuploadDeletesSegments:
    """Regression for stale Segments on reupload.

    _save_reupload deleted Steps for reconciled albums but left stale Segments
    in the DB.  Segments FK-cascade from Album, not Step, so deleting Steps
    alone had no effect on Segments.
    """

    async def test_reconciled_album_segments_are_deleted(self, tmp_path: Path) -> None:
        engine = create_async_engine(
            "sqlite+aiosqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        async with engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)

        # Seed: user, album, step, and segment.
        async with AsyncSession(engine) as session:
            user = User(
                id=UID,
                first_name="Test",
                locale="en-US",
                unit_is_km=True,
                temperature_is_celsius=True,
                google_sub="test-sub",
            )
            session.add(user)
            album = Album(
                uid=UID,
                id=AID,
                title="Old Trip",
                subtitle="",
                hidden_steps=[],
                maps_ranges=[],
                front_cover_photo="a.jpg",
                back_cover_photo="b.jpg",
                colors={},
                media=[],
                font="Assistant",
                body_font="Frank Ruhl Libre",
            )
            session.add(album)
            step = Step(
                uid=UID,
                aid=AID,
                id=1,
                name="Old Step",
                description="",
                cover=None,
                pages=[],
                unused=[],
                timestamp=1_000_000.0,
                timezone_id="UTC",
                location=None,
                elevation=0,
                weather=Weather(
                    day=WeatherData(temp=20.0, feels_like=18.0, icon="sun"),
                    night=None,
                ),
            )
            session.add(step)
            segment = Segment(
                uid=UID,
                aid=AID,
                start_time=100.0,
                end_time=500.0,
                kind=SegmentKind.driving,
                timezone_id="UTC",
                points=make_points([100.0, 300.0, 500.0]),
            )
            session.add(segment)
            await session.commit()

        # New objects for the reupload (new step, no new segments - they'd
        # normally be regenerated by the segment pipeline, but the reconcile
        # path doesn't produce them).
        new_album = Album(
            uid=UID,
            id=AID,
            title="Reconciled Trip",
            subtitle="",
            hidden_steps=[],
            maps_ranges=[],
            front_cover_photo="c.jpg",
            back_cover_photo="d.jpg",
            colors={},
            media=[],
            body_font="Frank Ruhl Libre",
        )
        new_step = Step(
            uid=UID,
            aid=AID,
            id=2,
            name="New Step",
            description="",
            cover=None,
            pages=[],
            unused=[],
            timestamp=2_000_000.0,
            timezone_id="UTC",
            location=None,
            elevation=0,
            weather=Weather(
                day=WeatherData(temp=25.0, feels_like=23.0, icon="cloud"),
                night=None,
            ),
        )

        trip_dir = tmp_path / AID
        trip_dir.mkdir()

        with patch("app.logic.trip_pipeline.get_engine", return_value=engine):
            await _save_reupload(
                uid=UID,
                objects=[new_album, new_step],
                reconciled_aids={AID},
                existing_albums={AID: album},
                trip_dirs=[trip_dir],
            )

        # Verify: old segment must be gone, old step must be gone.
        async with AsyncSession(engine) as session:
            segments = (await session.exec(select(Segment))).all()
            steps = (await session.exec(select(Step))).all()
            albums = (await session.exec(select(Album))).all()

        assert len(segments) == 0, f"Stale segments remain: {segments}"
        assert len(steps) == 1
        assert steps[0].name == "New Step"
        assert len(albums) == 1
        assert albums[0].title == "Reconciled Trip"
