from collections.abc import Sequence
from itertools import chain

from fastapi import APIRouter
from pydantic import BaseModel
from sqlmodel import select

from app.logic.spatial.segments import Segment, build_segments
from app.models.db import Album, AlbumId, AlbumSettings, Step, StepIdx, StepLayout
from app.models.trips import Locations

from ..deps import AlbumDep, SessionDep, UserDep

router = APIRouter(prefix="/albums", tags=["albums"])


@router.get("/")
async def read_album_ids(user: UserDep, session: SessionDep) -> Sequence[str]:
    return (await session.scalars(select(Album.id).where(Album.uid == user.id))).all()


@router.get("/{aid}")
async def read_album(aid: AlbumId, album: AlbumDep) -> Album:
    return album


@router.patch("/{aid}")
async def update_album(
    aid: AlbumId,
    update: AlbumSettings,
    album: AlbumDep,
    session: SessionDep,
) -> Album:
    album.sqlmodel_update(update)
    session.add(album)
    await session.commit()
    await session.refresh(album)
    return album


class Range(BaseModel):
    start: int
    end: int


@router.post("/{aid}/steps")
async def read_steps(
    aid: AlbumId,
    ranges: list[Range],
    user: UserDep,
    session: SessionDep,
) -> Sequence[Step]:
    indexes = list(chain(*(range(rng.start, rng.end + 1) for rng in ranges)))

    # noinspection PyUnresolvedReferences
    return (
        await session.scalars(
            select(Step)
            .where(Step.uid == user.id, Step.aid == aid, Step.idx.in_(indexes))  # type: ignore[unresolved-attribute]
            .order_by(Step.idx)  # type: ignore[invalid-argument-type]
        )
    ).all()


@router.patch("/{aid}/steps/{sid}")
async def update_step(
    aid: AlbumId,
    sid: StepIdx,
    update: StepLayout,
    user: UserDep,
    session: SessionDep,
) -> Step:
    # noinspection PyTypeChecker
    step: Step = await session.get_one(Step, (user.id, aid, sid))
    step.sqlmodel_update(update)
    session.add(step)
    await session.commit()
    await session.refresh(step)
    return step


@router.get("/{aid}/segments")
async def read_segments(
    aid: AlbumId,
    first: StepIdx,
    last: StepIdx,
    user: UserDep,
    session: SessionDep,
) -> Sequence[Segment]:
    # Get steps ordered by time
    stmt = (
        select(Step)
        .where(Step.uid == user.id, Step.aid == aid, Step.idx >= first, Step.idx <= last)
        .order_by(Step.idx)  # type: ignore[invalid-argument-type]
    )
    steps = (await session.scalars(stmt)).all()
    locations = Locations.from_trip_dir(user.trips_folder / aid).locations
    return list(build_segments(steps, locations))  # type: ignore[invalid-argument-type]
