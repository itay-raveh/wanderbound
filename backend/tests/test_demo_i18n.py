"""Tests for demo_i18n: overlay loading and application."""

import json
from pathlib import Path

import pytest

from app.logic.demo_i18n import apply_overlay, load_overlay
from app.models.album import Album
from app.models.polarsteps import Location
from app.models.step import Step
from app.models.weather import Weather, WeatherData

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

HEBREW_OVERLAY = {
    "album": {"title": "כותרת", "subtitle": "כותרת משנה"},
    "steps": {
        "42": {
            "name": "שם צעד",
            "location_name": "מקום",
            "location_detail": "מדינה",
        }
    },
}

WEATHER = Weather(day=WeatherData(temp=20.0, feels_like=18.0, icon="sun"))
LOCATION = Location(
    name="Amsterdam",
    detail="NL",
    country_code="nl",
    lat=52.37,
    lon=4.89,
)


def make_album(**kwargs: object) -> Album:
    defaults: dict[str, object] = {
        "uid": 1,
        "id": "trip-1",
        "title": "Original Title",
        "subtitle": "Original Subtitle",
        "hidden_steps": [],
        "hidden_headers": [],
        "maps_ranges": [],
        "front_cover_photo": "",
        "back_cover_photo": "",
        "colors": {},
        "media": [],
    }
    return Album(**(defaults | kwargs))


def make_step(step_id: int = 1, **kwargs: object) -> Step:
    defaults: dict[str, object] = {
        "uid": 1,
        "aid": "trip-1",
        "id": step_id,
        "name": "Original Name",
        "description": "",
        "cover": None,
        "pages": [],
        "unused": [],
        "timestamp": 1_700_000_000.0,
        "timezone_id": "UTC",
        "location": LOCATION,
        "elevation": 0,
        "weather": WEATHER,
    }
    return Step(**(defaults | kwargs))


@pytest.fixture
def fixtures_dir(tmp_path: Path) -> Path:
    i18n_dir = tmp_path / "i18n"
    i18n_dir.mkdir()
    # Write "he-IL" full locale file
    (i18n_dir / "he-IL.json").write_text(json.dumps(HEBREW_OVERLAY), encoding="utf-8")
    # Write language-only "he" file (same content for simplicity)
    (i18n_dir / "he.json").write_text(json.dumps(HEBREW_OVERLAY), encoding="utf-8")
    return tmp_path


# ---------------------------------------------------------------------------
# load_overlay tests
# ---------------------------------------------------------------------------


class TestLoadOverlay:
    def test_loads_full_locale(self, fixtures_dir: Path) -> None:
        overlay = load_overlay("he-IL", fixtures_dir)
        assert overlay is not None
        assert overlay["album"]["title"] == "כותרת"

    def test_loads_language_prefix(self, fixtures_dir: Path) -> None:
        # "he" file exists but "he-XX" (no full match) → falls back to "he"
        overlay = load_overlay("he-XX", fixtures_dir)
        assert overlay is not None
        assert overlay["album"]["title"] == "כותרת"


# ---------------------------------------------------------------------------
# apply_overlay tests
# ---------------------------------------------------------------------------


class TestApplyOverlay:
    def test_patches_album_title_and_subtitle(self) -> None:
        overlay = {"album": {"title": "New Title", "subtitle": "New Sub"}, "steps": {}}
        album = make_album()
        apply_overlay(overlay, album, [])
        assert album.title == "New Title"
        assert album.subtitle == "New Sub"

    def test_patches_step_name_and_location(self) -> None:
        overlay = {
            "album": {},
            "steps": {
                "42": {
                    "name": "שם צעד",
                    "location_name": "מקום",
                    "location_detail": "מדינה",
                }
            },
        }
        album = make_album()
        step = make_step(step_id=42)
        apply_overlay(overlay, album, [step])

        assert step.name == "שם צעד"
        assert step.location.name == "מקום"
        assert step.location.detail == "מדינה"
        # Preserves original geo fields
        assert step.location.country_code == "nl"
        assert step.location.lat == pytest.approx(52.37)
        assert step.location.lon == pytest.approx(4.89)

    def test_partial_album_patch(self) -> None:
        # Only title present — subtitle untouched
        overlay = {"album": {"title": "Only Title"}, "steps": {}}
        album = make_album()
        apply_overlay(overlay, album, [])
        assert album.title == "Only Title"
        assert album.subtitle == "Original Subtitle"
