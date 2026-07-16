from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

from app.api.v1.deps import _get_upload_store
from app.core.config import get_settings
from app.main import app
from app.models.processing import UploadSession
from app.models.upload import UploadResult
from app.models.user import UserPublic
from tests.factories import make_user, sign_in

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlmodel.ext.asyncio.session import AsyncSession


def _payload(size_bytes: int = 1) -> dict[str, object]:
    return {
        "filename": "polarsteps.zip",
        "type": "application/zip",
        "metadata": {"size_bytes": str(size_bytes)},
    }


async def test_multipart_routes_require_an_upload_owner(client: AsyncClient) -> None:
    store = MagicMock()

    def override_store() -> MagicMock:
        return store

    app.dependency_overrides[_get_upload_store] = override_store

    response = await client.post("/api/v1/users/uploads/s3/multipart", json=_payload())

    assert response.status_code == 401


async def test_upload_size_limit_uses_settings(
    client: AsyncClient, session: AsyncSession
) -> None:
    store = MagicMock()
    store.create.return_value = "provider-id"
    app.dependency_overrides[_get_upload_store] = lambda: store
    await sign_in(client)
    maximum = get_settings().MAX_UPLOAD_SIZE_BYTES

    accepted = await client.post(
        "/api/v1/users/uploads/s3/multipart", json=_payload(maximum)
    )
    rejected = await client.post(
        "/api/v1/users/uploads/s3/multipart", json=_payload(maximum + 1)
    )

    assert accepted.status_code == 201
    assert rejected.status_code == 400


async def test_uppy_multipart_contract(
    client: AsyncClient, session: AsyncSession
) -> None:
    store = MagicMock()
    store.create.return_value = "provider-id"
    store.sign_part.return_value = "https://storage.example/signed"
    store.list_parts.return_value = [{"PartNumber": 1, "Size": 1, "ETag": '"etag"'}]
    app.dependency_overrides[_get_upload_store] = lambda: store
    await sign_in(client)

    created = await client.post("/api/v1/users/uploads/s3/multipart", json=_payload())

    assert created.status_code == 201
    upload_id = created.json()["uploadId"]
    key = f"uploads/{upload_id}.zip"
    assert created.json() == {"uploadId": upload_id, "key": key}
    row = await session.get(UploadSession, upload_id)
    assert row is not None

    signed = await client.get(
        f"/api/v1/users/uploads/s3/multipart/{upload_id}/1",
        params={"key": key},
    )
    assert signed.json() == {
        "method": "PUT",
        "url": "https://storage.example/signed",
        "headers": {},
    }

    listed = await client.get(
        f"/api/v1/users/uploads/s3/multipart/{upload_id}", params={"key": key}
    )
    assert listed.json() == [{"PartNumber": 1, "Size": 1, "ETag": '"etag"'}]

    aborted = await client.delete(
        f"/api/v1/users/uploads/s3/multipart/{upload_id}", params={"key": key}
    )
    assert aborted.status_code == 200
    assert aborted.json() == {}
    store.abort.assert_called_once_with(key, "provider-id")


async def test_completion_starts_finalization(
    client: AsyncClient, session: AsyncSession
) -> None:
    store = MagicMock()
    store.create.return_value = "provider-id"
    store.head.return_value = 1
    store.list_parts.return_value = [{"PartNumber": 1, "Size": 1, "ETag": '"etag"'}]
    app.dependency_overrides[_get_upload_store] = lambda: store
    await sign_in(client)
    created = await client.post("/api/v1/users/uploads/s3/multipart", json=_payload())
    upload_id = created.json()["uploadId"]
    key = created.json()["key"]

    with patch(
        "app.api.v1.routes.uploads.start_upload_workflow", new_callable=AsyncMock
    ) as start:
        completed = await client.post(
            f"/api/v1/users/uploads/s3/multipart/{upload_id}/complete",
            params={"key": key},
            json={"parts": [{"PartNumber": 1, "ETag": '"etag"'}]},
        )

    assert completed.status_code == 200, completed.text
    assert completed.json() == {"location": key}
    store.complete.assert_called_once_with(
        key,
        "provider-id",
        [{"PartNumber": 1, "ETag": '"etag"'}],
    )
    start.assert_awaited_once_with(upload_id)

    row = await session.get(UploadSession, upload_id)
    assert row is not None
    assert row.status == "processing"


async def test_uploads_are_scoped_to_the_owner(
    client: AsyncClient, session: AsyncSession
) -> None:
    store = MagicMock()
    store.create.return_value = "provider-id"
    app.dependency_overrides[_get_upload_store] = lambda: store
    await sign_in(client)
    created = await client.post("/api/v1/users/uploads/s3/multipart", json=_payload())
    row = await session.get(UploadSession, created.json()["uploadId"])
    assert row is not None

    row.owner = "google:somebody-else"
    session.add(row)
    await session.commit()

    response = await client.get(
        f"/api/v1/users/uploads/s3/multipart/{row.upload_id}",
        params={"key": row.object_key},
    )
    assert response.status_code == 404


async def test_upload_progress_stream_replays_counters_and_failure(
    client: AsyncClient, session: AsyncSession
) -> None:
    store = MagicMock()
    store.create.return_value = "provider-id"
    app.dependency_overrides[_get_upload_store] = lambda: store
    await sign_in(client)
    created = await client.post("/api/v1/users/uploads/s3/multipart", json=_payload())
    row = await session.get(UploadSession, created.json()["uploadId"])
    assert row is not None
    row.status = "processing"
    session.add(row)
    await session.commit()

    events = [
        {
            "type": "progress",
            "phase": "downloading",
            "done": 50,
            "total": 100,
        },
        {
            "type": "progress",
            "phase": "validating",
            "done": 25,
            "total": 50,
        },
        {"type": "error", "error_code": "upload_invalid_zip"},
    ]

    async def stream_events() -> AsyncIterator[object]:
        for event in events:
            yield event

    with patch(
        "app.api.v1.routes.uploads.DBOS.read_stream_async",
        new=MagicMock(return_value=stream_events()),
    ) as read:
        response = await client.get(f"/api/v1/users/uploads/{row.upload_id}/stream")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert [
        json.loads(line.removeprefix("data: "))
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ] == [
        {
            "type": "progress",
            "phase": "downloading",
            "done": 50,
            "total": 100,
        },
        {
            "type": "progress",
            "phase": "validating",
            "done": 25,
            "total": 50,
        },
        {"type": "error", "error_code": "upload_invalid_zip"},
    ]
    read.assert_called_once_with(f"upload:{row.upload_id}", "progress")


async def test_complete_ingestion_claims_pending_signup_before_response_headers(
    client: AsyncClient, session: AsyncSession
) -> None:
    store = MagicMock()
    store.create.return_value = "provider-id"
    app.dependency_overrides[_get_upload_store] = lambda: store
    await sign_in(client)
    created = await client.post("/api/v1/users/uploads/s3/multipart", json=_payload())
    row = await session.get(UploadSession, created.json()["uploadId"])
    assert row is not None

    user = make_user(uid=42, google_sub="google-123")
    session.add(user)
    await session.flush()
    row.status = "succeeded"
    row.result = UploadResult(user=UserPublic.model_validate(user), trips=[])
    session.add(row)
    await session.commit()
    pending_cookie = client.cookies.get("session")
    assert pending_cookie is not None

    completed = await client.post(f"/api/v1/users/uploads/{row.upload_id}/complete")

    assert completed.status_code == 200, completed.text
    client.cookies.clear()
    client.cookies.set("session", pending_cookie)
    retried = await client.post(f"/api/v1/users/uploads/{row.upload_id}/complete")
    assert retried.status_code == 200, retried.text
    auth = await client.get("/api/v1/auth/state")
    assert auth.json()["state"] == "authenticated"
    assert auth.json()["user"]["id"] == 42
