from datetime import UTC, datetime, timedelta
from secrets import token_urlsafe
from typing import TYPE_CHECKING

import pytest
from sqlmodel import select

from app.core.config import get_settings
from app.models.processing import ArtifactToken

if TYPE_CHECKING:
    from pathlib import Path

    from httpx import AsyncClient
    from sqlmodel.ext.asyncio.session import AsyncSession


@pytest.mark.parametrize(
    ("namespace", "route"),
    [
        ("wanderbound-export", "/api/v1/users/export/download"),
        ("wanderbound-pdf", "/api/v1/albums/pdf/download"),
    ],
)
@pytest.mark.parametrize(
    "headers",
    [
        [("Early-Data", "1")],
        [("Early-Data", "")],
        [("Early-Data", "0")],
        [("Early-Data", "invalid")],
        [("Early-Data", "0"), ("Early-Data", "1")],
    ],
)
async def test_early_download_preserves_token_for_retry(
    client: AsyncClient,
    session: AsyncSession,
    tmp_path: Path,
    namespace: str,
    route: str,
    headers: list[tuple[str, str]],
) -> None:
    artifact = tmp_path / "export.bin"
    artifact.write_bytes(b"export contents")
    token = token_urlsafe()
    session.add(
        ArtifactToken(
            token=token,
            namespace=namespace,
            path=str(artifact),
            payload={
                "path": str(artifact),
                "filename": artifact.name,
                "media_type": "application/pdf",
            },
            expires_at=datetime.now(UTC) + timedelta(minutes=5),
        )
    )
    await session.commit()
    url = f"{route}/{token}"

    for _ in range(2):
        rejected = await client.get(url, headers=headers)
        assert rejected.status_code == 425
        assert rejected.headers["cache-control"] == "no-store"
        assert artifact.exists()

    downloaded = await client.get(url)
    assert downloaded.status_code == 200
    assert downloaded.content == b"export contents"
    assert not artifact.exists()


@pytest.mark.usefixtures("uploaded_user")
async def test_early_export_does_not_create_an_artifact(
    client: AsyncClient, session: AsyncSession
) -> None:
    rejected = await client.get("/api/v1/users/export", headers={"Early-Data": "1"})
    assert rejected.status_code == 425
    assert "set-cookie" not in rejected.headers
    assert not (await session.exec(select(ArtifactToken))).all()
    assert not (get_settings().DATA_FOLDER / "tokens").exists()

    retry = await client.get("/api/v1/users/export")
    assert retry.status_code == 200
    assert len((await session.exec(select(ArtifactToken))).all()) == 1


async def test_early_data_does_not_block_public_pages(client: AsyncClient) -> None:
    response = await client.get("/docs", headers={"Early-Data": "1"})
    assert response.status_code == 200
