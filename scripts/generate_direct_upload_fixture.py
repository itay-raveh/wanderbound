import json
from pathlib import Path
from sys import argv
from zipfile import ZIP_STORED, ZipFile

from app.core.config import get_settings


PAYLOAD_SIZE = 2 * get_settings().UPLOAD_PART_SIZE_BYTES + 1024 * 1024
WRITE_SIZE = 1024 * 1024


def generate_fixture(destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    user = {
        "id": 1,
        "first_name": "Integration",
        "last_name": "Test",
        "locale": "en_US",
        "unit_is_km": True,
        "temperature_is_celsius": True,
    }
    trip = {
        "id": 100,
        "slug": "integration-trip",
        "name": "Integration Trip",
        "summary": "",
        "cover_photo_path": "https://example.com/cover.jpg",
        "step_count": 1,
        "all_steps": [
            {
                "id": 1,
                "display_name": "Integration Step",
                "display_slug": "integration-step",
                "description": "",
                "start_time": 1_700_000_001.0,
                "timezone_id": "UTC",
                "location": {
                    "name": "Place",
                    "detail": "",
                    "country_code": "us",
                    "lat": 0.0,
                    "lon": 0.0,
                },
            }
        ],
    }
    locations = {"locations": [{"lat": 0.0, "lon": 0.0, "time": 1_700_000_001.0}]}
    block = b"x" * WRITE_SIZE
    with ZipFile(destination, "w", compression=ZIP_STORED, allowZip64=True) as archive:
        archive.writestr("user/user.json", json.dumps(user))
        archive.writestr("trip/trip-100/trip.json", json.dumps(trip))
        archive.writestr("trip/trip-100/locations.json", json.dumps(locations))
        prefix = b'{"payload":"'
        suffix = b'"}'
        filler_size = PAYLOAD_SIZE - len(prefix) - len(suffix)
        with archive.open(
            "user/multipart-payload.json", "w", force_zip64=True
        ) as payload:
            payload.write(prefix)
            for _ in range(filler_size // WRITE_SIZE):
                payload.write(block)
            payload.write(b"x" * (filler_size % WRITE_SIZE))
            payload.write(suffix)


if __name__ == "__main__":
    if len(argv) != 2:
        raise SystemExit("usage: generate_direct_upload_fixture.py <output.zip>")
    generate_fixture(Path(argv[1]))
