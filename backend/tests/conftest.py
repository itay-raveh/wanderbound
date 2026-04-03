import io
import tempfile
from collections.abc import AsyncIterator, Generator
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import jwt as jwt_module
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.v1.deps import _get_session
from app.core.config import get_settings
from app.logic.layout.media import Media
from app.logic.upload import TripMeta
from app.main import app
from app.models.album import Album
from app.models.polarsteps import Location, Point, PSLocations, PSTrip
from app.models.segment import Segment, SegmentKind
from app.models.step import Step
from app.models.user import PSUser
from app.models.weather import Weather, WeatherData


async def collect_async[T](it: AsyncIterator[T]) -> list[T]:
    return [item async for item in it]


def create_test_jpeg(
    path: Path, width: int, height: int, *, exif_orientation: int = 0
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (width, height), color="red")
    if exif_orientation:
        exif = img.getexif()
        exif[0x0112] = exif_orientation
        buf = io.BytesIO()
        img.save(buf, "JPEG", exif=exif.tobytes())
        path.write_bytes(buf.getvalue())
    else:
        img.save(path, "JPEG")
    return path


def make_async_session_mock(**kwargs: object) -> AsyncMock:
    mock = AsyncMock(**kwargs)
    mock.__aenter__ = AsyncMock(return_value=mock)
    mock.__aexit__ = AsyncMock(return_value=False)
    return mock


TEST_DATA_DIR = Path(__file__).parent / "test_data"


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def engine() -> AsyncEngine:
    eng = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with eng.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    return eng


@pytest_asyncio.fixture
async def session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    async with engine.connect() as conn:
        txn = await conn.begin()
        async with AsyncSession(bind=conn, expire_on_commit=False) as sess:
            yield sess
        await txn.rollback()


@pytest_asyncio.fixture
async def client(
    session: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[AsyncClient]:
    monkeypatch.setattr(get_settings(), "DATA_FOLDER", tmp_path)
    (tmp_path / "users").mkdir(exist_ok=True)

    async def _override() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[_get_session] = _override
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as c:
        yield c
    app.dependency_overrides.clear()


GOOGLE_PAYLOAD = {
    "sub": "google-123",
    "given_name": "Test",
    "picture": "https://example.com/photo.jpg",
}

MICROSOFT_PAYLOAD = {
    "sub": "microsoft-456",
    "given_name": "Test",
    "name": "Test Microsoft",
    "iss": "https://login.microsoftonline.com/00000000-0000-0000-0000-000000000000/v2.0",
}

_DEFAULT_PAYLOADS = {"google": GOOGLE_PAYLOAD, "microsoft": MICROSOFT_PAYLOAD}

PS_USER = PSUser(
    id=999,
    first_name="Zip",
    locale="en-US",
    unit_is_km=True,
    temperature_is_celsius=True,
)

TRIPS = [TripMeta(id="trip-1", title="Test Trip", step_count=5, country_codes=["nl"])]


@contextmanager
def mock_jwt(
    provider: str = "google",
    payload: dict | None = None,
    *,
    decode_error: bool = False,
) -> Generator[None]:
    mock_key = MagicMock()
    mock_key.key = "fake-key"
    decode_kwargs: dict = (
        {"side_effect": jwt_module.InvalidTokenError}
        if decode_error
        else {"return_value": payload or _DEFAULT_PAYLOADS[provider]}
    )
    with (
        patch(
            f"app.api.v1.routes.auth._{provider}_jwks.get_signing_key_from_jwt",
            return_value=mock_key,
        ),
        patch("jwt.decode", **decode_kwargs),
    ):
        yield


def mock_extract(users_dir: Path) -> patch:
    def _side_effect(*_args: object, **_kwargs: object) -> tuple:
        folder = Path(tempfile.mkdtemp(dir=users_dir))
        return folder, PS_USER, TRIPS

    return patch(
        "app.api.v1.routes.users.extract_and_scan",
        side_effect=_side_effect,
    )


async def sign_in_and_upload(
    client: AsyncClient,
    users_dir: Path,
    provider: str = "google",
    payload: dict | None = None,
) -> dict:
    with mock_jwt(provider, payload=payload), mock_extract(users_dir):
        resp = await client.post(
            "/api/v1/users/upload",
            data={"credential": "fake", "provider": provider},
            files={"file": ("data.zip", b"fake", "application/zip")},
        )
    assert resp.status_code == 200
    return resp.json()["user"]


LOCATION = Location(
    name="Amsterdam", detail="NH", country_code="nl", lat=52.37, lon=4.89
)
WEATHER = Weather(day=WeatherData(temp=20.0, feels_like=18.0, icon="sun"), night=None)
AID = "trip-1"


def make_points(times: list[float]) -> list[Point]:
    return [
        Point(lat=52.0 + i * 0.01, lon=4.0 + i * 0.01, time=t)
        for i, t in enumerate(times)
    ]


async def insert_album(
    session: AsyncSession,
    uid: int,
    aid: str = AID,
) -> Album:
    album = Album(
        uid=uid,
        id=aid,
        title="Test Album",
        subtitle="A subtitle",
        excluded_steps=[],
        maps_ranges=[],
        front_cover_photo="photo1.jpg",
        back_cover_photo="photo2.jpg",
        colors={"nl": "#0000ff"},
        media=[Media(name="photo1.jpg", width=1920, height=1080)],
        font="Assistant",
        body_font="Frank Ruhl Libre",
    )
    session.add(album)
    await session.flush()
    return album


async def insert_step(
    session: AsyncSession,
    uid: int,
    aid: str = AID,
    step_id: int = 1,
    timestamp: float = 1_700_000_000.0,
) -> Step:
    step = Step(
        uid=uid,
        aid=aid,
        id=step_id,
        name="Test Step",
        description="A test step.",
        cover=None,
        pages=[["photo1.jpg"]],
        unused=["photo2.jpg"],
        timestamp=timestamp,
        timezone_id="Europe/Amsterdam",
        location=LOCATION,
        elevation=0,
        weather=WEATHER,
    )
    session.add(step)
    await session.flush()
    return step


async def insert_segment(
    session: AsyncSession,
    uid: int,
    aid: str = AID,
    start_time: float = 1_700_000_000.0,
    end_time: float = 1_700_003_600.0,
    kind: SegmentKind = SegmentKind.driving,
    points: list[Point] | None = None,
) -> Segment:
    pts = points or make_points([start_time, (start_time + end_time) / 2, end_time])
    segment = Segment(
        uid=uid,
        aid=aid,
        start_time=start_time,
        end_time=end_time,
        kind=kind,
        timezone_id="UTC",
        points=pts,
    )
    session.add(segment)
    await session.flush()
    return segment


@pytest.fixture(scope="module")
def sa_trip_dir() -> Path:
    trip_dir = TEST_DATA_DIR / "trip" / "south-america-2024-2025_14232450"
    assert trip_dir.exists(), f"SA test data not found at {trip_dir}"
    return trip_dir


@pytest.fixture(scope="module")
def sa_trip(sa_trip_dir: Path) -> PSTrip:
    return PSTrip.from_trip_dir(sa_trip_dir)


@pytest.fixture(scope="module")
def sa_locations(sa_trip_dir: Path) -> PSLocations:
    return PSLocations.from_trip_dir(sa_trip_dir)
