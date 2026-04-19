"""Tests for _apply_demo_i18n: applies overlay to in-memory objects before save."""

import re

from app.logic.trip_pipeline import _apply_demo_i18n
from app.models.user import User

from .test_demo_i18n import make_album, make_step

HEBREW_RE = re.compile(r"[\u0590-\u05FF]")

DEMO_AID = "south-america-2024-2025_14232450"
HEBREW_STEP_ID = 149050611  # Pantanal in he.json


def _make_demo_user(locale: str = "he") -> User:
    return User(
        id=42,
        first_name="Demo",
        locale=locale,
        unit_is_km=True,
        temperature_is_celsius=True,
        album_ids=[DEMO_AID],
        is_demo=True,
    )


class TestApplyDemoI18n:
    def test_patches_album_and_step(self) -> None:
        album = make_album(uid=42, id=DEMO_AID)
        step = make_step(step_id=HEBREW_STEP_ID, aid=DEMO_AID)

        _apply_demo_i18n(_make_demo_user(), [album, step])

        assert HEBREW_RE.search(album.title)
        assert HEBREW_RE.search(album.subtitle)
        assert HEBREW_RE.search(step.name)
        assert HEBREW_RE.search(step.location.name)
        assert HEBREW_RE.search(step.location.detail)
        # Geo fields preserved
        assert step.location.country_code == "nl"

    def test_skips_non_demo_user(self) -> None:
        album = make_album(uid=42, id=DEMO_AID)

        user = User(
            id=42,
            first_name="Real",
            locale="he",
            unit_is_km=True,
            temperature_is_celsius=True,
            google_sub="g-42",
            album_ids=[DEMO_AID],
            is_demo=False,
        )
        _apply_demo_i18n(user, [album])

        assert album.title == "Original Title"  # Unchanged

    def test_skips_locale_without_overlay(self) -> None:
        album = make_album(uid=42, id=DEMO_AID)

        _apply_demo_i18n(_make_demo_user(locale="en"), [album])

        assert album.title == "Original Title"  # No en overlay exists
