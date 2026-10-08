from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from dbos import DBOS, SetWorkflowID
from sqlalchemy import text
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import get_settings
from app.logic import segment_routes
from app.models.polarsteps import Point
from app.models.segment import RouteEnrichmentStatus, Segment, SegmentRouteEnrichment
from app.services.mapbox import ROUTE_REQUEST_BATCH_TARGET
from tests.factories import AID, insert_album, insert_segment, make_user

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
