"""Rule-based classification: proximity to known facilities + persistence.

The optional ML branch is deliberately a thin wrapper around this established rule
engine.  If it is not explicitly enabled (or is unavailable), this module behaves
exactly as it did before.
"""

import math
import logging
import os

from config import FACILITY_PROXIMITY_METERS

logger = logging.getLogger(__name__)


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

    rule_result = {
        "classification": classification,
        "confidence": confidence,
        "priority": priority,
        "nearest_facility": facility["name"] if facility else None,
        "distance_m": round(dist) if facility else None,
    }

    # ML is opt-in and any model error must leave the proven rule result intact.
    if os.environ.get("USE_ML_CLASSIFIER", "").lower() == "true":
        try:
            from ml.classify_ml import classify_with_model, model_available

            if model_available():
                ml_label, ml_confidence = classify_with_model(
                    rule_result["distance_m"], int(bool(seen_before)),
                    hotspot.get("frp", hotspot.get("brightness", 0)),
                    facility.get("type") if facility else None,
                )
                rule_result["classification"] = ml_label
                rule_result["confidence"] = ml_confidence
                rule_result["priority"] = (
                    "high" if ml_label == "industrial_fire" and not seen_before else "low"
                )
                logger.info("ML classifier used for hotspot at %s,%s", hotspot["lat"], hotspot["lon"])
                return rule_result
            logger.info("Rule-based classifier used: ML model file is unavailable")
        except Exception:
            logger.exception("ML classification failed; using rule-based result")

    logger.info("Rule-based classifier used for hotspot at %s,%s", hotspot["lat"], hotspot["lon"])
    return rule_result
