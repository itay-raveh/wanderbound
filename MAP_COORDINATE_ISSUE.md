# Map Coordinate System Issue

## Problem
The mapsicon SVG maps are **NOT geo-calibrated**. They are vectorized shapes (potrace) without a documented coordinate system that maps to geographic coordinates (lat/lon).

## Current Status
- Dots form the correct relative shape (proving our geographic calculations are correct)
- But dots are positioned in the wrong absolute location (proving the SVG coordinate system doesn't match geographic coordinates)

## Research Findings
1. Mapsicon SVGs are created using potrace (bitmap-to-vector conversion)
2. They don't preserve geographic coordinate information
3. The coordinate system in the SVG paths is arbitrary and doesn't correspond to lat/lon
4. There's no documented way to map lat/lon to the SVG coordinate space

## Solution Options

### Option 1: Switch to Geo-Calibrated Map Source
- Use a map source that provides geo-calibrated SVGs
- Examples: MapSVG (paid), Natural Earth Data (complex), custom generated maps
- **Pros**: Accurate positioning
- **Cons**: May require paid service or complex setup

### Option 2: Use Python Library to Generate Maps
- Use libraries like `geopandas` + `matplotlib` or `folium` to generate country maps with proper coordinates
- **Pros**: Full control, accurate coordinates
- **Cons**: Requires additional dependencies, more complex

### Option 3: Accept Limitation
- Document that map dots are approximate
- **Pros**: No code changes
- **Cons**: Inaccurate positioning

### Option 4: Manual Calibration (Rejected)
- Manually calibrate each country
- **Pros**: Could work
- **Cons**: Not systematic, rejected by user

## Recommendation
Switch to a geo-calibrated map source or generate maps using a Python library with proper geographic coordinates.
