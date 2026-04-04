import json
from functools import cache
from pathlib import Path
from typing import Any

from app.models.album import Album
from app.models.polarsteps import Location
from app.models.step import Step

type Overlay = dict[str, Any]


@cache
def load_overlay(locale: str, fixtures_dir: Path) -> Overlay | None:
    """Return the i18n overlay for *locale*, or None if no file exists.

    Tries ``{fixtures_dir}/i18n/{locale}.json`` first (e.g. "he-IL"), then
    the language-only prefix ``{fixtures_dir}/i18n/{lang}.json`` (e.g. "he").
    """
    i18n_dir = fixtures_dir / "i18n"
    for candidate in (locale, locale.split("-", maxsplit=1)[0]):
        path = i18n_dir / f"{candidate}.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    return None


def apply_overlay(overlay: Overlay, album: Album, steps: list[Step]) -> None:
    """Patch *album* and *steps* in place from *overlay*."""
    album_patch: dict[str, Any] = overlay.get("album", {})
    if "title" in album_patch:
        album.title = album_patch["title"]
    if "subtitle" in album_patch:
        album.subtitle = album_patch["subtitle"]

    step_patches: dict[str, Any] = overlay.get("steps", {})
    for step in steps:
        patch = step_patches.get(str(step.id))
        if patch is None:
            continue
        if "name" in patch:
            step.name = patch["name"]
        if "description" in patch:
            step.description = patch["description"]
        if "location_name" in patch or "location_detail" in patch:
            step.location = Location(
                name=patch.get("location_name", step.location.name),
                detail=patch.get("location_detail", step.location.detail),
                country_code=step.location.country_code,
                lat=step.location.lat,
                lon=step.location.lon,
            )
