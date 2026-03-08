import math
from collections import defaultdict
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Literal

import numpy as np
import rasterio

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Sequence

    from app.logic.spatial.points import Lat, Lon

__all__ = ["ELEVATION_RESOLUTION_METERS", "elevations", "init_elevations"]

ELEVATION_RESOLUTION_METERS: Literal[30] = 30


@asynccontextmanager
async def init_elevations() -> AsyncGenerator[None]:
    with rasterio.Env(AWS_NO_SIGN_REQUEST="YES"):
        yield


def elevations(lats: Sequence[Lat], lons: Sequence[Lon]) -> np.ndarray:
    elevs = np.zeros(len(lats))

    # Group points by tile to minimize file opens
    tiles = defaultdict[str, list[int]](list)
    for i, (lat, lon) in enumerate(zip(lats, lons, strict=True)):
        tiles[_get_tile_name(lat, lon)].append(i)

    for tile_name, indices in tiles.items():
        with rasterio.open(
            f"/vsicurl/https://copernicus-dem-{ELEVATION_RESOLUTION_METERS}m.s3.amazonaws.com/{tile_name}/{tile_name}.tif"
        ) as src:
            coords = [(lons[i], lats[i]) for i in indices]
            samples = np.array(list(src.sample(coords)))
            tile_elevs = samples[:, 0].astype(float)

            # Fallback to 0 if tile not found (e.g. ocean)
            # (the lowest land point on earth is higher than -500)
            tile_elevs[tile_elevs < -500.0] = 0.0

            elevs[indices] = tile_elevs

    return elevs


def _get_tile_name(lat: float, lon: float) -> str:
    ilat = math.floor(lat)
    ilon = math.floor(lon)
    ns = "N" if ilat >= 0 else "S"
    ew = "E" if ilon >= 0 else "W"
    # Copernicus DEM tiles are named by the south-west corner
    return f"Copernicus_DSM_COG_10_{ns}{abs(ilat):02d}_00_{ew}{abs(ilon):03d}_00_DEM"
