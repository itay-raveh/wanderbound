from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

from app.api.v1.deps import _get_upload_store
from app.main import app
from app.models.processing import UploadSession
from tests.factories import sign_in

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlmodel.ext.asyncio.session import AsyncSession


def _payload() -> dict[str, object]:
    return {
        "filename": "polarsteps.zip",
        "type": "application/zip",
        "metadata": {"size_bytes": "1"},
    }


async def test_multipart_routes_require_an_upload_owner(client: AsyncClient) -> None:
    store = MagicMock()

    def override_store() -> MagicMock:
        return store

    app.dependency_overrides[_get_upload_store] = override_store

    response = await client.post("/api/v1/users/uploads/s3/multipart", json=_payload())

    assert response.status_code == 401


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


async def test_completion_starts_finalization_and_exposes_status(
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
    status = await client.get(f"/api/v1/users/uploads/{upload_id}")
    assert status.status_code == 200
    assert status.json() == {
        "status": "processing",
        "error_code": None,
        "result": None,
    }


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
