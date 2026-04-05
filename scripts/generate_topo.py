# /// script
# dependencies = [
#   "numpy",
#   "scipy",
#   "matplotlib",
# ]
# ///

"""Generate a topographic contour SVG from a noise heightfield."""

from pathlib import Path

import numpy as np
from scipy.ndimage import gaussian_filter
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

np.random.seed(7)
W, H = 300, 225  # grid resolution
SVG_W, SVG_H = 1200, 900

# Base noise: multiple octaves for natural terrain
heightfield = np.zeros((H, W))
for freq, amp in [(0.015, 1.0), (0.03, 0.5), (0.06, 0.25), (0.12, 0.12)]:
    phase_x = np.random.uniform(0, 100)
    phase_y = np.random.uniform(0, 100)
    x = np.linspace(phase_x, phase_x + W * freq, W)
    y = np.linspace(phase_y, phase_y + H * freq, H)
    X, Y = np.meshgrid(x, y)
    heightfield += amp * (
        np.sin(X) * np.cos(Y * 1.3)
        + np.sin(X * 0.7 + Y * 0.5)
        + np.cos(X * 1.2 - Y * 0.8)
    )

# Add distinct peaks and ridges
features = [
    (0.15, 0.25, 35, 25, 1.2),  # elongated peak upper-left
    (0.75, 0.35, 30, 30, 1.0),  # round peak right
    (0.45, 0.55, 40, 35, 0.9),  # broad feature center
    (0.20, 0.75, 25, 20, 0.8),  # small peak lower-left
    (0.85, 0.70, 35, 28, 1.1),  # peak lower-right
    (0.55, 0.15, 28, 38, 0.7),  # elongated ridge top-center
    (0.05, 0.50, 30, 30, 0.6),  # edge feature left
    (0.95, 0.15, 25, 25, 0.5),  # corner feature
    (0.40, 0.85, 32, 22, 0.8),  # bottom feature
    (0.65, 0.60, 20, 20, 0.6),  # small knoll
]

YY, XX = np.ogrid[:H, :W]
for fx, fy, rx, ry, amp in features:
    cx, cy = int(fx * W), int(fy * H)
    dist = ((XX - cx) / rx) ** 2 + ((YY - cy) / ry) ** 2
    heightfield += amp * np.exp(-dist / 2)

# Smooth for natural contours
heightfield = gaussian_filter(heightfield, sigma=4)

# Extract contour paths
fig, ax = plt.subplots()
cs = ax.contour(heightfield, levels=22)
plt.close()

sx, sy = SVG_W / W, SVG_H / H

paths = []
for level_segs in cs.allsegs:
    for seg in level_segs:
        if len(seg) < 3:
            continue
        parts = [f"M{seg[0][0] * sx:.1f},{seg[0][1] * sy:.1f}"]
        for x, y in seg[1:]:
            parts.append(f" {x * sx:.1f},{y * sy:.1f}")
        paths.append(f'  <path d="{"".join(parts)}"/>')

svg = (
    f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {SVG_W} {SVG_H}"'
    f' fill="none" stroke="#0063D1" stroke-width="0.6"'
    f' stroke-linecap="round" stroke-linejoin="round">\n'
    + "\n".join(paths)
    + "\n</svg>\n"
)

out = (
    Path(__file__).resolve().parent.parent / "frontend" / "public" / "topo-contours.svg"
)
out.write_text(svg)

print(f"Wrote {len(paths)} contour paths to {out}")
