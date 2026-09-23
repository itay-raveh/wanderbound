"""Thresholds used by location cleaning and movement segmentation."""

# Edge classification
# GPS underreports speed on winding trails (~6.5 km/h vs ~8 km/h actual).
# Motorized transport (tuk-tuks, minibuses) typically exceeds this even in traffic.
HIKE_MAX_SPEED_KMH = 6.5
FLIGHT_MIN_SPEED_KMH = 200.0
# Long GPS gaps can include waiting time, lowering a flight's apparent speed.
FLIGHT_SPARSE_MIN_SPEED_KMH = 140.0
FLIGHT_SPARSE_MIN_DISTANCE_KM = 500.0
FLIGHT_CONNECTION_GAP_H = 2.0
# Step pins may be offset from nearby GPS points, but cannot anchor long transfers.
STEP_ADJACENT_MAX_EXTRA_KM = 10.0

# Hike validity (all three must pass, otherwise downgraded to "walking")
# Displacement = max distance from start, filters hostel GPS drift.
HIKE_MIN_DURATION_H = 2.0
HIKE_MIN_DISTANCE_KM = 2.0
HIKE_MIN_DISPLACEMENT_KM = 1.0

FLIGHT_MIN_DISTANCE_KM = 100.0
MAX_HIKE_GAP_H = 4.0

# GPS noise
# Approximate km per degree at mid-latitudes (used for cheap degree-space checks).
_KM_PER_DEG = 80.0
# > 1000 km/h = impossible GPS jump.  Step waypoints are immune.
TELEPORT_MAX_SPEED_KMH = 1000.0
# Spike detection: point > 0.5 km from neighbor where skipping it is much shorter.
SPIKE_MIN_DIST_KM = 0.5
ISOLATED_POINT_MIN_DIST_KM = 5.0

# Densification
# Interpolate slow edges to ~15 m spacing so sparse GPS doesn't hide short hikes.
DENSIFY_MAX_SPEED_KMH = 5.0
DENSIFY_RESOLUTION_KM = 0.015

# Absorption pass 1: noise gaps
# Short "other" between two hikes at hike speed -> fold back into hike.
# Requires a following hike anchor to avoid absorbing post-hike hotel drift.
NOISE_GAP_MAX_DIST_KM = 4.0
NOISE_GAP_MAX_H = 3.0

# Absorption pass 2: camps + blackouts

# Camp: GPS barely moved overnight.  No speed check - tight distance cap
# prevents transport; a speed check would reject walks-to-trailhead.
CAMP_GAP_MAX_DIST_KM = 1.0
CAMP_GAP_MAX_H = 20.0

# Blackout: phone stopped logging mid-hike.  Absorbed at hike speed.
# Short (< 6 h): only following anchor needed.  Long (6-24 h): both anchors,
# to avoid merging evening city walk with next morning's hike.
# Distance caps: short can cover more (bus to trailhead); long with significant
# distance likely includes driving (real overnight has only GPS drift).
BLACKOUT_GAP_SHORT_MAX_H = 6.0
BLACKOUT_GAP_LONG_MAX_H = 24.0
BLACKOUT_GAP_SHORT_MAX_DIST_KM = 10.0
BLACKOUT_GAP_LONG_MAX_DIST_KM = 4.0

# Anchor: min hike run adjacent to a gap.  Lower than HIKE_MIN_DURATION_H
# so a 1.5 h fragment before a mountain camp still qualifies.
HIKE_ANCHOR_MIN_H = 1.5
# Camp merge needs a lower bar on the *preceding* hike to guard against
# a brief evening city walk anchoring an overnight merge.
CAMP_PREV_ANCHOR_MIN_H = 1.0

RDP_EPSILON_DEG = 0.001  # RDP simplification tolerance (degrees)
