"""Session management for multi-user web application.

Handles session directory creation, zip extraction, and session cleanup.
"""

from __future__ import annotations

import shutil
import uuid
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING

from src.core.logger import get_logger

if TYPE_CHECKING:
    from nicegui.events import UploadEventArguments

logger = get_logger(__name__)

# Base directory for all session data
SESSIONS_DIR = Path("/var/polarsteps/sessions")


def get_session_id() -> str:
    """Get or create a unique session ID for the current user session."""
    from nicegui import app  # noqa: PLC0415

    session_id: str | None = app.storage.user.get("session_id")
    if session_id is None:
        session_id = str(uuid.uuid4())
        app.storage.user["session_id"] = session_id
    return session_id


def get_session_dir() -> Path:
    """Get the session directory for the current user, creating if needed."""
    session_id = get_session_id()
    session_dir = SESSIONS_DIR / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    return session_dir


def get_trips_dir() -> Path:
    """Get the trips directory for the current session."""
    trips_dir = get_session_dir() / "trips"
    trips_dir.mkdir(parents=True, exist_ok=True)
    return trips_dir


def get_output_dir() -> Path:
    """Get the output directory for the current session."""
    output_dir = get_session_dir() / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


async def extract_zip_upload(event: UploadEventArguments) -> list[str]:
    """Extract uploaded zip file and return list of available trip slugs.

    Args:
        event: NiceGUI upload event containing the zip file

    Returns:
        List of trip slug names (directory names) found in the zip

    Raises:
        ValueError: If the uploaded file is not a valid Polarsteps export zip

    """
    import asyncio  # noqa: PLC0415

    trips_dir = get_trips_dir()

    # Clear any existing trips
    if trips_dir.exists():
        await asyncio.to_thread(shutil.rmtree, trips_dir)
    trips_dir.mkdir(parents=True)

    # Extract the zip
    try:
        with zipfile.ZipFile(event.content, "r") as zf:
            # Validate it's a Polarsteps export (should have trip.json files)
            file_list = zf.namelist()
            trip_jsons = [f for f in file_list if f.endswith("trip.json")]
            if not trip_jsons:
                msg = "Invalid Polarsteps export: no trip.json files found"
                raise ValueError(msg)

            # Extract to trips directory
            await asyncio.to_thread(zf.extractall, trips_dir)
    except zipfile.BadZipFile as e:
        msg = f"Invalid zip file: {e}"
        raise ValueError(msg) from e

    # Find all trip directories (those containing trip.json)
    trips = sorted({path.parent.name for path in trips_dir.rglob("trip.json")})

    logger.info("Extracted %d trips from upload: %s", len(trips), ", ".join(trips))
    return trips


def cleanup_session() -> None:
    """Remove the current session's directory and all its contents."""
    try:
        session_id = get_session_id()
        session_dir = SESSIONS_DIR / session_id
        if session_dir.exists():
            shutil.rmtree(session_dir)
            logger.info("Cleaned up session: %s", session_id)
    except Exception:
        logger.exception("Failed to cleanup session")


def path_to_session_url(path: Path | str) -> str:
    """Convert an absolute file path to a session-based URL.

    Args:
        path: Absolute path to a file within the session directory

    Returns:
        URL in format /api/session/{session_id}/assets/{relative_path}

    Example:
        >>> path_to_session_url("/var/polarsteps/sessions/abc123/trips/MyTrip/photo.jpg")
        "/api/session/abc123/assets/trips/MyTrip/photo.jpg"

    """
    path = Path(path) if isinstance(path, str) else path
    session_id = get_session_id()
    session_dir = SESSIONS_DIR / session_id

    try:
        relative_path = path.relative_to(session_dir)
    except ValueError:
        # Path is not within session directory - return as-is (for external URLs)
        return str(path)

    return f"/api/session/{session_id}/assets/{relative_path}"


# Session cleanup constants
SESSION_MAX_AGE_HOURS = 24
CLEANUP_INTERVAL_HOURS = 1


async def cleanup_old_sessions() -> int:
    """Delete session directories older than SESSION_MAX_AGE_HOURS.

    Returns:
        Number of sessions cleaned up

    """
    import asyncio  # noqa: PLC0415
    import time  # noqa: PLC0415

    if not SESSIONS_DIR.exists():
        return 0

    max_age_seconds = SESSION_MAX_AGE_HOURS * 3600
    now = time.time()
    cleaned = 0

    for session_dir in SESSIONS_DIR.iterdir():
        if not session_dir.is_dir():
            continue

        try:
            # Check modification time of the session directory
            mtime = session_dir.stat().st_mtime
            age = now - mtime

            if age > max_age_seconds:
                await asyncio.to_thread(shutil.rmtree, session_dir)
                logger.info(
                    "Cleaned up old session: %s (age: %.1f hours)", session_dir.name, age / 3600
                )
                cleaned += 1
        except Exception:
            logger.exception("Failed to cleanup session %s", session_dir.name)

    if cleaned:
        logger.info("Session cleanup complete: removed %d old sessions", cleaned)

    return cleaned


async def start_cleanup_task() -> None:
    """Start a background task to periodically cleanup old sessions."""
    import asyncio  # noqa: PLC0415

    while True:
        try:
            await cleanup_old_sessions()
        except Exception:
            logger.exception("Session cleanup task error")

        # Wait for the next cleanup interval
        await asyncio.sleep(CLEANUP_INTERVAL_HOURS * 3600)
