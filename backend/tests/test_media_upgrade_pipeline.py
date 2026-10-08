import asyncio
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING

import httpx
import pytest
from PIL import Image
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.v1.routes import google_photos_upgrade as routes
from app.core.config import get_settings
from app.core.http_clients import HttpClients
from app.logic.media_upgrade import pipeline, upgrade
from app.logic.media_upgrade.phash_matching import MatchResult
from app.logic.media_upgrade.pipeline import UpgradeCompleted, run_upgrade
from app.models.album_media import AlbumMedia, PhotoEdit
from app.services.google_photos import GooglePhotosOAuth2, _clear_media_items_cache
from tests.factories import (
    AID,
    DEFAULT_MEDIA_NAME,
    MISSING_MEDIA_NAME,
    create_test_jpeg,
    insert_album,
    insert_album_media,
    make_user,
)
from tests.media_upgrade_helpers import (
    make_item,
    match_datetime,
    test_token as _test_token,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

    from app.models.user import User

VIDEO = MISSING_MEDIA_NAME.replace(".jpg", ".mp4")
EDIT = PhotoEdit(angle=0, x=0.2, y=0.2, width=0.4, height=0.4)
HASH = ["0123456789abcdef"]


@pytest.fixture(autouse=True)
def clear_upgrade_caches() -> Iterator[None]:
    pipeline._clear_caches()
    _clear_media_items_cache()
    yield
    pipeline._clear_caches()
    _clear_media_items_cache()


async def _seed_upgrade(
    engine: AsyncEngine,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    names: list[str],
) -> tuple[User, Path, dict[str, bytes]]:
    monkeypatch.setattr(get_settings(), "DATA_FOLDER", tmp_path)
    monkeypatch.setattr(routes, "get_engine", lambda: engine)
    monkeypatch.setattr(upgrade, "get_engine", lambda: engine)
    monkeypatch.setattr("app.core.locks.get_engine", lambda: engine)
    user = make_user(1, google_sub="upgrade-test")
    user.google_photos_refresh_token = "test-refresh"  # noqa: S105 - fake provider credential
    user.google_photos_connected_at = datetime.now(UTC)
    album_dir = user.trips_folder / AID
    originals = {}
    async with AsyncSession(engine, expire_on_commit=False) as session:
        session.add(user)
        await session.flush()
        await insert_album(session, user.id)
        for name in names:
            target = create_test_jpeg(album_dir / name, 1200, 800)
            originals[name] = target.read_bytes()
            row = await insert_album_media(
                session, user.id, name=name, width=1200, height=800
            )
            row.byte_size = len(originals[name])
            row.perceptual_hashes = HASH.copy()
            row.photo_edit = EDIT
            session.add(row)
        await session.commit()
    return user, album_dir, originals


def _photo_bytes(size: tuple[int, int]) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", size, color="blue").save(buffer, "JPEG")
    return buffer.getvalue()


def _clients(http: httpx.AsyncClient) -> HttpClients:
    return HttpClients(
        mapbox_matching=http,
        mapbox_directions=http,
        open_meteo=http,
        overpass=http,
        gphotos_picker=http,
        gphotos_download=http,
        gphotos_token=http,
        gphotos_oauth=GooglePhotosOAuth2("test", "test", http),
    )


class _InterruptedDownload(httpx.AsyncByteStream):
    async def __aiter__(self) -> AsyncIterator[bytes]:
        yield b"incomplete original"
        raise httpx.ReadError("interrupted provider stream")


@pytest.mark.parametrize(
    ("case", "picker_size", "candidate_size", "result"),
    [
        (
            "equal",
            (1200, 800),
            (1600, 1000),
            UpgradeCompleted(replaced=0, skipped=1, failed=0),
        ),
        (
            "metadata-smaller",
            (800, 600),
            (1600, 1000),
            UpgradeCompleted(replaced=0, skipped=1, failed=0),
        ),
        (
            "larger",
            (1600, 1000),
            (1600, 1000),
            UpgradeCompleted(replaced=1, skipped=0, failed=0),
        ),
        (
            "unknown",
            None,
            (1600, 1000),
            UpgradeCompleted(replaced=1, skipped=0, failed=0),
        ),
        (
            "actual-smaller",
            None,
            (800, 600),
            UpgradeCompleted(replaced=0, skipped=1, failed=0),
        ),
        ("invalid", None, None, UpgradeCompleted(replaced=0, skipped=0, failed=1)),
        ("interrupted", None, None, UpgradeCompleted(replaced=0, skipped=0, failed=1)),
    ],
)
async def test_upgrade_preserves_originals_or_persists_valid_replacements(
    postgres_engine: AsyncEngine,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case: str,
    picker_size: tuple[int, int] | None,
    candidate_size: tuple[int, int] | None,
    result: UpgradeCompleted,
) -> None:
    user, album_dir, originals = await _seed_upgrade(
        postgres_engine, tmp_path, monkeypatch, [DEFAULT_MEDIA_NAME]
    )
    (album_dir / VIDEO).write_bytes(b"video-original")
    deleted_sessions = set()

    def provider(request: httpx.Request) -> httpx.Response:
        if request.url.host == "oauth2.googleapis.com":
            return httpx.Response(
                200, json={"access_token": "test-token", "expires_in": 3600}
            )
        if request.url.path == "/v1/mediaItems":
            metadata = (
                {"width": picker_size[0], "height": picker_size[1]}
                if picker_size
                else None
            )
            return httpx.Response(
                200,
                json={
                    "mediaItems": [
                        {
                            "id": "google-photo",
                            "type": "PHOTO",
                            "mediaFile": {
                                "baseUrl": "https://lh3.googleusercontent.com/original",
                                "mediaFileMetadata": metadata,
                            },
                        }
                    ]
                },
            )
        if request.method == "DELETE":
            deleted_sessions.add(request.url.path)
            return httpx.Response(204)
        if request.url.host == "lh3.googleusercontent.com":
            assert case not in {"equal", "metadata-smaller"}, (
                "known smaller candidate was downloaded"
            )
            assert request.url.path == "/original=d", "video must not be upgraded"
            if case == "interrupted":
                return httpx.Response(200, stream=_InterruptedDownload())
            return httpx.Response(
                200,
                content=_photo_bytes(candidate_size)
                if candidate_size
                else b"invalid image",
            )
        raise AssertionError(
            f"unexpected provider request: {request.method} {request.url}"
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(provider)) as http:
        events = [
            event
            async for event in routes.upgrade_media(
                AID,
                routes.UpgradeRequest(
                    session_ids=["picker-1"],
                    matches=[
                        MatchResult(
                            local_name=DEFAULT_MEDIA_NAME,
                            google_id="google-photo",
                            distance=0,
                        ),
                        MatchResult(
                            local_name=VIDEO, google_id="google-video", distance=0
                        ),
                    ],
                ),
                user,
                _clients(http),
            )
        ]
    assert events[-1] == result
    target = album_dir / DEFAULT_MEDIA_NAME
    async with AsyncSession(postgres_engine) as persisted:
        row = await persisted.get_one(AlbumMedia, (user.id, AID, DEFAULT_MEDIA_NAME))
        assert row.photo_edit == EDIT
        assert row.byte_size == target.stat().st_size
        if result.replaced:
            assert target.read_bytes() != originals[DEFAULT_MEDIA_NAME]
            with Image.open(target) as image:
                assert image.size == candidate_size
                pixel = image.getpixel((0, 0))
                assert isinstance(pixel, tuple)
                red, _, blue = pixel
                assert blue > red
            assert (row.width, row.height) == candidate_size
            assert row.perceptual_hashes is None
            assert row.upgrade_candidate is False
        else:
            assert target.read_bytes() == originals[DEFAULT_MEDIA_NAME]
            assert (row.width, row.height) == (1200, 800)
            assert row.perceptual_hashes == HASH
            assert row.upgrade_candidate is True
    assert (album_dir / VIDEO).read_bytes() == b"video-original"
    assert {path.name for path in album_dir.iterdir()} == {DEFAULT_MEDIA_NAME, VIDEO}
    assert deleted_sessions == {"/v1/sessions/picker-1"}


async def test_upgrade_bounds_concurrent_downloads_without_losing_photo_state(
    postgres_engine: AsyncEngine,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(pipeline, "detect_memory_mb", lambda: 2048)
    names = [DEFAULT_MEDIA_NAME, MISSING_MEDIA_NAME]
    user, album_dir, originals = await _seed_upgrade(
        postgres_engine, tmp_path, monkeypatch, names
    )
    first_started = asyncio.Event()
    release_first = asyncio.Event()
    active = peak = 0
    received = set()
    body = _photo_bytes((1600, 1000))

    async def provider(request: httpx.Request) -> httpx.Response:
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        received.add(request.url.path)
        try:
            if request.url.path == "/photo-0=d":
                first_started.set()
                await release_first.wait()
            return httpx.Response(200, content=body)
        finally:
            active -= 1

    async with httpx.AsyncClient(transport=httpx.MockTransport(provider)) as http:

        async def collect() -> list[object]:
            return [
                event
                async for event in run_upgrade(
                    clients=_clients(http),
                    uid=user.id,
                    aid=AID,
                    album_dir=album_dir,
                    matches=[
                        MatchResult(local_name=name, google_id=f"gp-{i}", distance=0)
                        for i, name in enumerate(names)
                    ],
                    google_items_by_id={
                        f"gp-{i}": make_item(
                            f"gp-{i}",
                            match_datetime(10).isoformat(),
                            base_url=f"https://lh3.googleusercontent.com/photo-{i}",
                        )
                        for i in range(2)
                    },
                    upgrade_candidates=set(names),
                    local_dimensions={},
                    tokens=_test_token,
                    session_ids=[],
                )
            ]

        task = asyncio.create_task(collect())
        try:
            await asyncio.wait_for(first_started.wait(), timeout=5)
            await asyncio.sleep(0)
        finally:
            release_first.set()
        events = await task
    assert peak == 1
    assert received == {"/photo-0=d", "/photo-1=d"}
    assert events[-1] == UpgradeCompleted(replaced=2, skipped=0, failed=0)
    async with AsyncSession(postgres_engine) as persisted:
        rows = (await persisted.exec(select(AlbumMedia))).all()
        assert {row.name for row in rows} == set(names)
        assert all(
            not row.upgrade_candidate
            and row.perceptual_hashes is None
            and row.photo_edit == EDIT
            for row in rows
        )
    assert all(
        (album_dir / name).read_bytes() != original
        for name, original in originals.items()
    )
    assert {path.name for path in album_dir.iterdir()} == set(names)
