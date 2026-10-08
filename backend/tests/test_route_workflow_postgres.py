import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from dbos import DBOS, SetWorkflowID
from sqlalchemy import event, text
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import get_settings
from app.logic import segment_routes, session as processing_session
from app.logic.trip_processing import PhaseUpdate, TripStart
from app.logic.workflows import media_hashes
from app.models.album_media import AlbumMedia
from app.models.polarsteps import Point
from app.models.segment import RouteEnrichmentStatus, Segment, SegmentRouteEnrichment
from app.services.mapbox import ROUTE_REQUEST_BATCH_TARGET
from tests.factories import (
    AID,
    DEFAULT_MEDIA_NAME,
    create_test_jpeg,
    insert_album,
    insert_album_media,
    insert_segment,
    make_user,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine


@pytest_asyncio.fixture(loop_scope="function")
async def route_runtime(
    postgres_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[AsyncEngine]:
    schema = "dbos_test_" + uuid4().hex
    DBOS(
        config=cast(
            "Any",
            {
                "name": "wanderbound-route-test",
                "system_database_url": postgres_engine.url.render_as_string(
                    hide_password=False
                ),
                "dbos_system_schema": schema,
                "run_admin_server": False,
                "log_level": "ERROR",
            },
        )
    )
    monkeypatch.setattr(segment_routes, "get_engine", lambda: postgres_engine)
    monkeypatch.setattr("app.core.locks.get_engine", lambda: postgres_engine)
    monkeypatch.setattr(get_settings(), "MAPBOX_TOKEN", "test-token")
    DBOS.launch()
    try:
        yield postgres_engine
    finally:
        DBOS.destroy(workflow_completion_timeout_sec=1)
        async with postgres_engine.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))


async def _seed_routes(engine: AsyncEngine) -> dict[float, list[tuple[float, float]]]:
    expected = {}
    async with AsyncSession(engine) as session:
        session.add(make_user(1, google_sub="route-test"))
        await session.flush()
        await insert_album(session, 1)
        for index in range(ROUTE_REQUEST_BATCH_TARGET + 1):
            start = float(index * 120)
            lon = 4 + index * 0.001
            points = [
                Point(lat=52, lon=lon, time=start),
                Point(lat=52, lon=lon + 0.0001, time=start + 60),
            ]
            await insert_segment(
                session, 1, start_time=start, end_time=start + 60, points=points
            )
            expected[start] = [(point.lon, point.lat) for point in points]
        await session.commit()
    return expected


@pytest.mark.parametrize("outcome", ["matched", "permanent", "transient"])
async def test_route_workflow_persists_batches_and_scopes_failures(
    route_runtime: AsyncEngine, monkeypatch: pytest.MonkeyPatch, outcome: str
) -> None:
    expected = await _seed_routes(route_runtime)

    def provider(request: httpx.Request) -> httpx.Response:
        if outcome == "transient":
            raise httpx.ConnectError("provider unavailable", request=request)
        if outcome == "permanent":
            return httpx.Response(422, json={"code": "InvalidInput"})
        coords = [
            [float(value) for value in pair.split(",")]
            for pair in request.url.path.rsplit("/", 1)[-1].split(";")
        ]
        return httpx.Response(
            200,
            json={
                "code": "Ok",
                "routes": [{"geometry": {"type": "LineString", "coordinates": coords}}],
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(provider)) as http:
        clients = SimpleNamespace(mapbox_matching=http, mapbox_directions=http)
        monkeypatch.setattr(
            segment_routes, "get_route_enrichment_http_clients", lambda: clients
        )
        with SetWorkflowID("test-" + uuid4().hex):
            if outcome == "matched":
                await segment_routes.album_route_enrichment_workflow(
                    {"uid": 1, "aid": AID}
                )
            elif outcome == "permanent":
                with pytest.raises(segment_routes.RouteEnrichmentIncompleteError):
                    await segment_routes.album_route_enrichment_workflow(
                        {"uid": 1, "aid": AID}
                    )
            else:
                with pytest.raises(Exception, match=r"maximum.*retries"):
                    await segment_routes.album_route_enrichment_workflow(
                        {"uid": 1, "aid": AID}
                    )

    async with AsyncSession(route_runtime) as persisted:
        segments = (await persisted.exec(select(Segment))).all()
        states = (await persisted.exec(select(SegmentRouteEnrichment))).all()
        routes = {segment.start_time: segment.route for segment in segments}
        if outcome == "matched":
            assert routes == expected
            assert {state.start_time for state in states} == set(expected)
            assert all(
                state.status == RouteEnrichmentStatus.matched for state in states
            )
        else:
            assert routes == dict.fromkeys(expected)
            attempted = (
                set(expected) if outcome == "permanent" else set(sorted(expected)[:-1])
            )
            assert {state.start_time for state in states} == attempted
            assert all(state.status == RouteEnrichmentStatus.failed for state in states)
            if outcome == "permanent":
                assert {state.error_code for state in states} == {"InvalidInput"}
            else:
                assert all(
                    state.error_code.startswith("retry_exhausted:") for state in states
                )


@pytest.mark.parametrize("retry_succeeds", [True, False])
async def test_terminal_hash_backfill_retries_once_and_persists_hashes(
    route_runtime: AsyncEngine,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    retry_succeeds: bool,
) -> None:
    monkeypatch.setattr(media_hashes, "get_engine", lambda: route_runtime)
    monkeypatch.setattr(get_settings(), "DATA_FOLDER", tmp_path)
    async with AsyncSession(route_runtime) as session:
        session.add(make_user(1))
        await session.flush()
        await insert_album(session, 1)
        row = await insert_album_media(session, 1)
        target = create_test_jpeg(
            get_settings().USERS_FOLDER / "1" / "trip" / AID / row.name, 64, 48
        )
        row.byte_size = target.stat().st_size
        session.add(row)
        await session.commit()
    await DBOS.register_queue_async(media_hashes.MEDIA_HASH_QUEUE, worker_concurrency=1)

    def interrupted_write(
        conn: object,
        _cursor: object,
        statement: str,
        params: object,
        context: object,
        _many: object,
    ) -> None:
        if statement.lstrip().upper().startswith("UPDATE ALBUM_MEDIA"):
            raise OSError("database write interrupted")

    event.listen(route_runtime.sync_engine, "before_cursor_execute", interrupted_write)
    try:
        original = await media_hashes.enqueue_media_hash_backfill(
            1, AID, 1, "test-revision"
        )
        with pytest.raises(Exception, match=r"maximum.*retries"):
            await original.get_result()
    finally:
        event.remove(
            route_runtime.sync_engine, "before_cursor_execute", interrupted_write
        )
    async with AsyncSession(route_runtime) as session:
        assert (
            await session.get_one(AlbumMedia, (1, AID, DEFAULT_MEDIA_NAME))
        ).perceptual_hashes is None
    if not retry_succeeds:
        event.listen(
            route_runtime.sync_engine, "before_cursor_execute", interrupted_write
        )
    try:
        retry = await media_hashes.enqueue_media_hash_backfill(
            1, AID, 1, "test-revision"
        )
        if retry_succeeds:
            await retry.get_result()
        else:
            with pytest.raises(Exception, match=r"maximum.*retries"):
                await retry.get_result()
    finally:
        if not retry_succeeds:
            event.remove(
                route_runtime.sync_engine, "before_cursor_execute", interrupted_write
            )
    async with AsyncSession(route_runtime) as session:
        row = await session.get_one(AlbumMedia, (1, AID, DEFAULT_MEDIA_NAME))
        assert (row.perceptual_hashes is not None) == retry_succeeds
    await media_hashes.enqueue_media_hash_backfill(1, AID, 1, "test-revision")
    runs = await DBOS.list_workflows_async(name="media_hash.backfill")
    assert sorted(run.status for run in runs) == [
        "ERROR",
        "SUCCESS" if retry_succeeds else "ERROR",
    ]


async def test_route_enrichment_persists_after_subscriber_disconnect(
    route_runtime: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = await _seed_routes(route_runtime)
    async with AsyncSession(route_runtime, expire_on_commit=False) as session:
        user = await session.get_one(type(make_user(1)), 1)
        user.album_ids = [AID]
    gate = asyncio.Event()

    async def completed_processing(
        http: object, user: object
    ) -> AsyncIterator[TripStart | PhaseUpdate]:
        yield TripStart(trip_index=0)
        await gate.wait()
        yield PhaseUpdate(phase="layouts", done=1, total=1)

    def provider(request: httpx.Request) -> httpx.Response:
        coords = [
            [float(value) for value in pair.split(",")]
            for pair in request.url.path.rsplit("/", 1)[-1].split(";")
        ]
        return httpx.Response(
            200,
            json={
                "code": "Ok",
                "routes": [{"geometry": {"type": "LineString", "coordinates": coords}}],
            },
        )

    monkeypatch.setattr(processing_session, "run_processing", completed_processing)
    async with httpx.AsyncClient(transport=httpx.MockTransport(provider)) as http:
        clients = SimpleNamespace(mapbox_matching=http, mapbox_directions=http)
        monkeypatch.setattr(
            segment_routes, "get_route_enrichment_http_clients", lambda: clients
        )
        processing_session._sessions.clear()
        stream = processing_session.process_stream(clients, user)
        assert await anext(stream) == TripStart(trip_index=0)
        await stream.aclose()
        gate.set()
        await processing_session._sessions[1]._task
        try:
            async with asyncio.timeout(10):
                while True:
                    async with AsyncSession(route_runtime) as persisted:
                        segments = (await persisted.exec(select(Segment))).all()
                        if {row.start_time: row.route for row in segments} == expected:
                            break
                    await asyncio.sleep(0.01)
        finally:
            processing_session._sessions.clear()
