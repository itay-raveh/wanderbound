# /// script
# dependencies = [
#   "geopandas",
# ]
# ///

import json
import os
import re
import urllib.request

import geopandas as gpd
import shapely.affinity

# 1. Download HIGH FIDELITY GeoJSON (10m)
url = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_10m_admin_0_countries.geojson"
ne_filename = "ne_10m_admin_0_countries.geojson"

if not os.path.exists(ne_filename):
    print(f"Downloading {ne_filename} (this may take a moment)...")
    urllib.request.urlretrieve(url, ne_filename)

# 2. Load the data
print("Loading GeoJSON data...")
gdf = gpd.read_file(ne_filename)

# 3. CRITICAL: Reproject to Web Mercator (EPSG:3857)
print("Reprojecting to Web Mercator...")
gdf = gdf.to_crs(epsg=3857)

# Create an output directory for the hundreds of SVG files
output_dir = "frontend/public/countries"
os.makedirs(output_dir, exist_ok=True)

bounds_dir = "frontend/src/countries"
os.makedirs(bounds_dir, exist_ok=True)
json_filename = bounds_dir + "/bounds.json"
bounds_dict = {}

print(f"Generating individual SVGs in '/{output_dir}' and {json_filename}...")

# 4. Loop through and create individual files
for idx, row in gdf.iterrows():
    code = row.get("ISO_A2", "-99")
    if code == "-99":
        code = row.get("ADM0_A3", "-99")
    if code == "-99" or not isinstance(code, str):
        continue

    symbol_id = code.lower()
    geom = row.geometry

    if geom is None or geom.is_empty:
        continue

    # Flip the geometry vertically for standard SVG rendering
    geom_flipped = shapely.affinity.scale(geom, xfact=1.0, yfact=-1.0, origin=(0, 0))

    # Calculate the SVG viewBox
    minx, miny, maxx, maxy = geom_flipped.bounds
    width = maxx - minx
    height = maxy - miny

    # Save the clean float array to our JSON dictionary
    bounds_dict[symbol_id] = [minx, miny, width, height]

    # Generate SVG paths and clean up hardcoded styles
    svg_paths = geom_flipped.svg()
    svg_paths = re.sub(r'fill="[^"]+"', 'fill="currentColor"', svg_paths)
    svg_paths = re.sub(r'stroke="[^"]+"', "", svg_paths)
    svg_paths = re.sub(r'stroke-width="[^"]+"', "", svg_paths)
    svg_paths = re.sub(r'opacity="[^"]+"', "", svg_paths)

    # Write the standalone SVG file with paths in a <g> (no <symbol> viewport issues)
    svg_filepath = os.path.join(output_dir, f"{symbol_id}.svg")
    with open(svg_filepath, "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        f.write(
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{minx} {miny} {width} {height}">\n'
        )
        f.write(f'  <g id="map">{svg_paths}</g>\n')
        f.write("</svg>\n")

# 5. Export the master dictionary
with open(json_filename, "w", encoding="utf-8") as jf:
    json.dump(bounds_dict, jf, indent=2)

os.unlink(ne_filename)

print("Success! Your frontend assets are fully generated.")
