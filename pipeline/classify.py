"""Rule-based classification: proximity to known facilities + persistence."""

import math

from config import FACILITY_PROXIMITY_METERS


def haversine_meters(lat1, lon1, lat2, lon2):
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    return 2 * R * math.asin(math.sqrt(a))


def nearest_facility(hotspot, facilities):
    nearest, nearest_dist = None, float("inf")
    for f in facilities:
        dist = haversine_meters(hotspot["lat"], hotspot["lon"], f["lat"], f["lon"])
        if dist < nearest_dist:
            nearest, nearest_dist = f, dist
    return nearest, nearest_dist


def classify_hotspot(hotspot, facilities, seen_before, land_cover):
    """
    seen_before: bool, whether a hotspot has occurred repeatedly at ~this spot
    land_cover: string from fetch_context.land_cover_at()
    """
    facility, dist = nearest_facility(hotspot, facilities)

    if facility and dist <= FACILITY_PROXIMITY_METERS:
        classification = "gas_flare" if seen_before else "industrial_fire"
        confidence = 0.9 if dist < 200 else 0.7
    elif land_cover == "forest":
        classification = "wildfire"
        confidence = 0.6
    elif land_cover == "farmland":
        classification = "agricultural_burning"
        confidence = 0.6
    else:
        classification = "unclassified"
        confidence = 0.3

    priority = "high" if (classification == "industrial_fire" and not seen_before) else "low"

    return {
        "classification": classification,
        "confidence": confidence,
        "priority": priority,
        "nearest_facility": facility["name"] if facility else None,
        "distance_m": round(dist) if facility else None,
    }
