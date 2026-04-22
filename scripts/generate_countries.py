# /// script
# dependencies = [
#   "geopandas",
# ]
# ///

import json
import re
import tempfile
import urllib.request
from pathlib import Path

import geopandas as gpd
import shapely.affinity

ROOT = Path(__file__).resolve().parent.parent

# 1. Download medium-resolution GeoJSON (50m) - clean silhouettes for print
url = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_50m_admin_0_countries.geojson"
tmp = tempfile.NamedTemporaryFile(suffix=".geojson", delete=False)
ne_path = Path(tmp.name)
tmp.close()
print("Downloading Natural Earth data (this may take a moment)...")
urllib.request.urlretrieve(url, str(ne_path))


def resolve_code(row: object) -> str | None:
    """Resolve a 2-letter lowercase ISO code for the country.

    Prefers ISO_A2_EH (most complete 2-letter field in Natural Earth),
    then ISO_A2, then truncates ADM0_A3 as a last resort.
    """
    for field in ("ISO_A2_EH", "ISO_A2"):
        val = row.get(field, "-99")  # type: ignore[union-attr]
        if isinstance(val, str) and val != "-99" and len(val) == 2:
            return val.lower()
    # Fallback: use ADM0_A3 (always present, 3-letter)
    val = row.get("ADM0_A3", "-99")  # type: ignore[union-attr]
    if isinstance(val, str) and val != "-99":
        return val.lower()
    return None


def mainland_bounds(geom: object) -> tuple[float, float, float, float]:
    """Return the bounding box of the mainland + major nearby islands.

    For countries with overseas territories (France, Netherlands, US, …),
    the full MultiPolygon spans half the globe.  We use the shorter side
    of the mainland's bounding box as the proximity reference - this
    avoids elongated countries (Chile) being overly permissive.

    Include a polygon if:
    - **nearby**: centroid within 1.5× the shorter side, OR
    - **significant**: area ≥ 10 % of mainland AND within 4× shorter side.
    """
    if geom.geom_type != "MultiPolygon":  # type: ignore[union-attr]
        return geom.bounds  # type: ignore[union-attr, return-value]

    polys = list(geom.geoms)  # type: ignore[union-attr]
    largest = max(polys, key=lambda g: g.area)
    largest_area = largest.area
    lx0, ly0, lx1, ly1 = largest.bounds
    shorter_side = min(lx1 - lx0, ly1 - ly0)
    nearby_threshold = shorter_side * 1.5
    significant_threshold = shorter_side * 4

    included = [largest.bounds]
    lc = largest.centroid
    for poly in polys:
        if poly is largest:
            continue
        dist = lc.distance(poly.centroid)
        is_nearby = dist <= nearby_threshold
        is_significant = (
            poly.area >= largest_area * 0.10 and dist <= significant_threshold
        )
        if is_nearby or is_significant:
            included.append(poly.bounds)

    minx = min(b[0] for b in included)
    miny = min(b[1] for b in included)
    maxx = max(b[2] for b in included)
    maxy = max(b[3] for b in included)
    return (minx, miny, maxx, maxy)


try:
    # 2. Load the data
    print("Loading GeoJSON data...")
    gdf = gpd.read_file(str(ne_path))

    # 3. CRITICAL: Reproject to Web Mercator (EPSG:3857)
    print("Reprojecting to Web Mercator...")
    gdf = gdf.to_crs(epsg=3857)

    # Create an output directory for the hundreds of SVG files
    output_dir = ROOT / "frontend" / "public" / "countries"
    output_dir.mkdir(parents=True, exist_ok=True)

    bounds_dir = ROOT / "frontend" / "src" / "countries"
    bounds_dir.mkdir(parents=True, exist_ok=True)
    json_path = bounds_dir / "bounds.json"
    bounds_dict = {}

    print(f"Generating individual SVGs in '/{output_dir}' and {json_path}...")

    # 4. Loop through and create individual files
    for idx, row in gdf.iterrows():
        code = resolve_code(row)
        if code is None:
            continue

        geom = row.geometry

        if geom is None or geom.is_empty:
            continue

        # Flip the geometry vertically for standard SVG rendering
        geom_flipped = shapely.affinity.scale(
            geom, xfact=1.0, yfact=-1.0, origin=(0, 0)
        )

        # Full bounds for the SVG viewBox (shows all territories)
        minx, miny, maxx, maxy = geom_flipped.bounds
        width = maxx - minx
        height = maxy - miny

        # Mainland bounds for the JSON (excludes distant overseas territories)
        m_minx, m_miny, m_maxx, m_maxy = mainland_bounds(geom_flipped)
        m_width = m_maxx - m_minx
        m_height = m_maxy - m_miny
        bounds_dict[code] = [m_minx, m_miny, m_width, m_height]

        # Generate SVG paths and clean up hardcoded styles
        svg_paths = geom_flipped.svg()
        svg_paths = re.sub(r'fill="[^"]+"', 'fill="currentColor"', svg_paths)
        svg_paths = re.sub(r'stroke="[^"]+"', "", svg_paths)
        svg_paths = re.sub(r'stroke-width="[^"]+"', "", svg_paths)
        svg_paths = re.sub(r'opacity="[^"]+"', "", svg_paths)

        # Write the standalone SVG file with paths in a <g> (no <symbol> viewport issues)
        svg_path = output_dir / f"{code}.svg"
        with svg_path.open("w", encoding="utf-8") as f:
            f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
            f.write(
                f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{minx} {miny} {width} {height}">\n'
            )
            f.write(f'  <g id="map">{svg_paths}</g>\n')
            f.write("</svg>\n")

    # 5. Export the master dictionary
    json_path.write_text(json.dumps(bounds_dict, indent=2) + "\n", encoding="utf-8")

    print("Success! Your frontend assets are fully generated.")
finally:
    ne_path.unlink(missing_ok=True)
