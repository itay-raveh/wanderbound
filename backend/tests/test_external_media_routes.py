from __future__ import annotations

from inspect import signature
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

from app.api.v1.routes.external_media import add_google_media
from app.models.album_media import AlbumMedia, StepUnusedMedia
from app.models.user import User

from .factories import (
    AID,
    DEFAULT_MEDIA_NAME,
    MISSING_MEDIA_NAME,
)
from .helpers.external_media import (
    AlbumMediaFactory,
    ExternalMediaRoutes,
    download_guard,
    jpeg_bytes,
)
from .helpers.google_photos import picked_item

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession


async def test_device_add_to_step_prepends_unused(
    session: AsyncSession,
    album_media_scenario: AlbumMediaFactory,
    external_media: ExternalMediaRoutes,
) -> None:
    scenario = await album_media_scenario()

    resp = await external_media.add_device(context="step", step_id=1)

    assert resp.status_code == 200
    imported = resp.json()["names"]
    assert len(imported) == 1

    unused = await session.get_one(StepUnusedMedia, (scenario.uid, AID, 1, 0))
    assert unused.media_name == imported[0]

    row = await session.get_one(AlbumMedia, (scenario.uid, AID, imported[0]))
    assert row.kind == "photo"
    assert row.upgrade_candidate is False
    assert row.byte_size > 0


def test_google_add_stream_route_does_not_depend_on_request_db_session() -> None:
    params = signature(add_google_media).parameters
    assert "session" not in params
    assert "user" not in params


async def test_device_add_to_cover_does_not_select_cover(
    session: AsyncSession,
    album_media_scenario: AlbumMediaFactory,
    external_media: ExternalMediaRoutes,
) -> None:
    scenario = await album_media_scenario()

    resp = await external_media.add_device(
        context="cover", filename="cover.jpg", width=900, height=600
    )

    assert resp.status_code == 200
    imported = resp.json()["names"][0]
    row = await session.get_one(AlbumMedia, (scenario.uid, AID, imported))
    assert row.width == 900
    assert row.height == 600


async def test_device_replace_updates_existing_media(
    session: AsyncSession,
    album_media_scenario: AlbumMediaFactory,
    external_media: ExternalMediaRoutes,
) -> None:
    scenario = await album_media_scenario(write_media=True)

    resp = await external_media.replace_device(scenario.media_name)

    assert resp.status_code == 200
    row = await session.get_one(AlbumMedia, (scenario.uid, AID, scenario.media_name))
    assert row.width == 1200
    assert row.height == 800


async def test_device_replace_schedules_undo_snapshot_prune(
    session: AsyncSession,
    album_media_scenario: AlbumMediaFactory,
    external_media: ExternalMediaRoutes,
) -> None:
    scenario = await album_media_scenario(write_media=True)

    with patch(
        "app.api.v1.routes.external_media.enqueue_undo_snapshot_prune",
    ) as enqueue_prune:
        resp = await external_media.replace_device(scenario.media_name)

    assert resp.status_code == 200
    enqueue_prune.assert_called_once()
    _, scheduled_uid, scheduled_aid, scheduled_dir = enqueue_prune.call_args.args
    assert (scheduled_uid, scheduled_aid, scheduled_dir) == (
        scenario.uid,
        AID,
        scenario.album_dir,
    )


async def test_device_replace_oversized_upload_returns_413(
    session: AsyncSession,
    album_media_scenario: AlbumMediaFactory,
    external_media: ExternalMediaRoutes,
) -> None:
    await album_media_scenario()

    with patch(
        "app.api.v1.routes.external_media.save_uploads",
        AsyncMock(side_effect=OverflowError("Import is too large")),
    ):
        resp = await external_media.replace_device(
            DEFAULT_MEDIA_NAME, content=b"too large"
        )

    assert resp.status_code == 413
    assert resp.json()["detail"] == "Import is too large"


async def test_device_replace_missing_media_returns_404(
    session: AsyncSession,
    album_media_scenario: AlbumMediaFactory,
    external_media: ExternalMediaRoutes,
) -> None:
    await album_media_scenario()
    save_uploads = AsyncMock(side_effect=AssertionError("should not save upload"))

    with patch("app.api.v1.routes.external_media.save_uploads", save_uploads):
        resp = await external_media.replace_device(MISSING_MEDIA_NAME)

    assert resp.status_code == 404
    assert resp.json()["detail"] == "Media not found"
    save_uploads.assert_not_awaited()


async def test_undo_replacement_restores_previous_dimensions(
    session: AsyncSession,
    album_media_scenario: AlbumMediaFactory,
    external_media: ExternalMediaRoutes,
) -> None:
    scenario = await album_media_scenario(write_media=True)

    replace_resp = await external_media.replace_device(scenario.media_name)
    assert replace_resp.status_code == 200

    undo_resp = await external_media.undo_replacement(scenario.media_name)

    assert undo_resp.status_code == 200
    row = await session.get_one(AlbumMedia, (scenario.uid, AID, scenario.media_name))
    assert row.width == 640
    assert row.height == 480


async def test_undo_after_repeated_replacement_restores_immediate_previous_file(
    session: AsyncSession,
    album_media_scenario: AlbumMediaFactory,
    external_media: ExternalMediaRoutes,
) -> None:
    scenario = await album_media_scenario(write_media=True)

    first_replace = await external_media.replace_device(scenario.media_name)
    assert first_replace.status_code == 200

    second_replace = await external_media.replace_device(
        scenario.media_name, width=1600, height=900
    )
    assert second_replace.status_code == 200

    undo_resp = await external_media.undo_replacement(scenario.media_name)

    assert undo_resp.status_code == 200
    row = await session.get_one(AlbumMedia, (scenario.uid, AID, scenario.media_name))
    assert row.width == 1200
    assert row.height == 800


async def test_undo_replacement_restores_previous_upgrade_candidate(
    session: AsyncSession,
    album_media_scenario: AlbumMediaFactory,
    external_media: ExternalMediaRoutes,
) -> None:
    scenario = await album_media_scenario(write_media=True)
    row = await session.get_one(AlbumMedia, (scenario.uid, AID, scenario.media_name))
    row.upgrade_candidate = True
    session.add(row)
    await session.commit()

    replace_resp = await external_media.replace_device(scenario.media_name)
    assert replace_resp.status_code == 200
    row = await session.get_one(AlbumMedia, (scenario.uid, AID, scenario.media_name))
    assert row.upgrade_candidate is False

    undo_resp = await external_media.undo_replacement(scenario.media_name)

    assert undo_resp.status_code == 200
    row = await session.get_one(AlbumMedia, (scenario.uid, AID, scenario.media_name))
    assert row.upgrade_candidate is True


async def test_google_replace_requires_one_selected_item(
    session: AsyncSession,
    google_album_media_scenario: AlbumMediaFactory,
    external_media: ExternalMediaRoutes,
) -> None:
    await google_album_media_scenario()

    with patch(
        "app.logic.external_media.operations.get_media_items",
        AsyncMock(return_value=[]),
    ):
        resp = await external_media.replace_google()

    assert resp.status_code == 400
    assert resp.json()["detail"] == "Select exactly one replacement"


async def test_google_replace_rejects_multiple_items_before_download(
    session: AsyncSession,
    google_album_media_scenario: AlbumMediaFactory,
    external_media: ExternalMediaRoutes,
) -> None:
    await google_album_media_scenario()
    items = [
        picked_item("google-1", filename="one.jpg"),
        picked_item(
            "google-2",
            filename="two.jpg",
            base_url="https://lh3.googleusercontent.com/two",
        ),
    ]

    with (
        patch(
            "app.logic.external_media.operations.get_media_items",
            AsyncMock(return_value=items),
        ),
        patch(
            "app.logic.external_media.operations.download_media_to_file",
            AsyncMock(),
        ) as download,
    ):
        resp = await external_media.replace_google()

    assert resp.status_code == 400
    assert resp.json()["detail"] == "Select exactly one replacement"
    download.assert_not_awaited()


async def test_google_add_validates_step_before_download(
    session: AsyncSession,
    google_album_media_scenario: AlbumMediaFactory,
    external_media: ExternalMediaRoutes,
) -> None:
    await google_album_media_scenario()
    fail_if_downloaded, downloaded = download_guard()

    with (
        patch(
            "app.api.v1.routes.external_media.download_google_items_to_saved",
            fail_if_downloaded,
        ),
        patch("app.api.v1.routes.external_media.get_engine", return_value=session.bind),
    ):
        resp = await external_media.add_google(context="step", step_id=999)

    assert resp.status_code == 200
    assert "Step not found" in resp.text
    assert not downloaded()


async def test_google_add_collapses_lost_token_to_disconnected(
    session: AsyncSession,
    google_album_media_scenario: AlbumMediaFactory,
    external_media: ExternalMediaRoutes,
) -> None:
    scenario = await google_album_media_scenario()
    user = await session.get_one(User, scenario.uid)
    user.google_photos_refresh_token = None
    session.add(user)
    await session.commit()

    with patch(
        "app.api.v1.routes.external_media.get_engine", return_value=session.bind
    ):
        resp = await external_media.add_google(context="cover")

    assert resp.status_code == 400
    assert "Google Photos not connected" in resp.text
    await session.refresh(user)
    assert user.google_photos_connected_at is None


async def test_google_replace_validates_media_before_download(
    session: AsyncSession,
    google_album_media_scenario: AlbumMediaFactory,
    external_media: ExternalMediaRoutes,
) -> None:
    await google_album_media_scenario()
    fail_if_downloaded, downloaded = download_guard()

    with patch(
        "app.api.v1.routes.external_media.download_google_items_to_saved",
        fail_if_downloaded,
    ):
        resp = await external_media.replace_google(media_name=MISSING_MEDIA_NAME)

    assert resp.status_code == 404
    assert not downloaded()


async def test_google_replace_marks_media_upgraded(
    session: AsyncSession,
    google_album_media_scenario: AlbumMediaFactory,
    external_media: ExternalMediaRoutes,
) -> None:
    scenario = await google_album_media_scenario(write_media=True)

    async def fake_download(*args: object, **kwargs: object) -> None:
        dest = args[3]
        assert isinstance(dest, Path)
        dest.write_bytes(jpeg_bytes(1200, 800))

    with (
        patch(
            "app.logic.external_media.operations.get_media_items",
            AsyncMock(return_value=[picked_item()]),
        ),
        patch(
            "app.logic.external_media.operations.download_media_to_file",
            AsyncMock(side_effect=fake_download),
        ),
    ):
        resp = await external_media.replace_google(media_name=scenario.media_name)

    assert resp.status_code == 200
    row = await session.get_one(AlbumMedia, (scenario.uid, AID, scenario.media_name))
    assert row.upgrade_candidate is False
