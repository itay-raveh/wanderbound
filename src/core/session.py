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
