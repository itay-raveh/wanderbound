from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

from app.api.v1.routes.users import process_user
from app.core.http_clients import HttpClients
from app.logic.trip_processing import ProcessingEvent, TripStart
from app.models.user import User


def _mock_user(uid: int = 1) -> User:
    user = AsyncMock(spec=User)
    user.id = uid
    return user


async def test_process_route_passes_db_session_to_stream() -> None:
    user = _mock_user()
    http = MagicMock(spec=HttpClients)
    db_session = object()

    async def fake_process_stream(
        stream_http: HttpClients, stream_user: User, stream_session: object
    ) -> AsyncIterator[ProcessingEvent]:
        assert stream_http is http
        assert stream_user is user
        assert stream_session is db_session
        yield TripStart(trip_index=0)

    with patch("app.api.v1.routes.users.process_stream", fake_process_stream):
        events = [event async for event in process_user(user, http, db_session)]

    assert events == [TripStart(trip_index=0)]
