from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from PIL import Image

from app.logic.photo_edit import fit_photo_edit, render_photo_edit, validate_photo_edit
from app.models.album_media import PhotoEdit
from tests.factories import sign_in_with_album_media

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlmodel.ext.asyncio.session import AsyncSession


@pytest.mark.asyncio
async def test_rotation_crop_has_no_empty_corners_and_keeps_source(
    tmp_path: Path,
) -> None:
    source = tmp_path / "photo.jpg"
    Image.new("RGB", (160, 100), "red").save(source)
    original = source.read_bytes()
    edit = PhotoEdit(angle=45, x=0.35, y=0.35, width=0.3, height=0.3)

    rendered = await render_photo_edit(tmp_path, source, edit)

    with Image.open(rendered) as result:
        assert result.width == result.height
        for corner in ((0, 0), (result.width - 1, 0), (0, result.height - 1)):
            pixel = result.getpixel(corner)
            assert isinstance(pixel, tuple)
            assert pixel[0] > 240
            assert pixel[1] < 15
            assert pixel[2] < 15
    assert source.read_bytes() == original
    invalid = PhotoEdit(angle=45, x=0, y=0, width=1, height=1)
    with pytest.raises(ValueError, match="empty space"):
        validate_photo_edit(invalid, 160, 100)
    validate_photo_edit(fit_photo_edit(invalid, 100, 160), 100, 160)


@pytest.mark.asyncio
async def test_full_quarter_turn_changes_photo_orientation(tmp_path: Path) -> None:
    source = tmp_path / "photo.jpg"
    Image.new("RGB", (160, 100), "blue").save(source)
    edit = PhotoEdit(angle=90, x=0, y=0, width=1, height=1)

    rendered = await render_photo_edit(tmp_path, source, edit)

    with Image.open(rendered) as result:
        assert result.size == (100, 160)


@pytest.mark.asyncio
async def test_album_media_uses_edit_while_source_stays_unchanged(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    album = await sign_in_with_album_media(
        client, session, width=400, height=250, write_media=True
    )
    source = album.album_dir / album.media_name
    original = source.read_bytes()
    base = f"/api/v1/albums/{album.album_dir.name}/media/{album.media_name}"
    before = await client.get(f"{base}?w=200")

    saved = await client.put(
        f"{base}/photo-edit",
        json={"angle": 90, "x": 0, "y": 0, "width": 1, "height": 1},
    )
    edited = await client.get(base)
    thumb = await client.get(f"{base}?w=200")
    raw = await client.get(f"{base}/photo-source")

    assert before.status_code == saved.status_code == 200
    assert edited.status_code == thumb.status_code == raw.status_code == 200
    with Image.open(BytesIO(edited.content)) as image:
        assert image.size == (250, 400)
    with Image.open(BytesIO(raw.content)) as image:
        assert image.size == (400, 250)
    with Image.open(BytesIO(thumb.content)) as image:
        assert image.size == (200, 320)
    assert source.read_bytes() == original
