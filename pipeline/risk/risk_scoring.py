"""Daily facility risk scoring, intentionally independent of hotspot ingestion."""

from datetime import datetime, timedelta, timezone
import hashlib
import logging
import os
from pathlib import Path
import sys
import requests

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.config import REGION_BBOX, SUPABASE_SERVICE_ROLE_KEY, SUPABASE_URL
from pipeline.fetch_context import fetch_facilities

logger = logging.getLogger(__name__)


def location_id_for_facility(facility):
    """Use an OSM ID if one is later supplied, otherwise a stable coordinate cell."""
    return str(facility.get("id") or f"{facility['lat']:.3f},{facility['lon']:.3f}")


def mock_conditions(location_id):
    """Deterministic plausible demo conditions, avoiding nondeterministic daily scores."""
    seed = int(hashlib.sha256(location_id.encode()).hexdigest()[:8], 16)
    return {
        "temperature_trend_c": round(1 + (seed % 50) / 10, 1),
        "dryness": round(35 + (seed // 7 % 60), 1),
        "rainfall_mm": round((seed // 13 % 120) / 10, 1),
        "wind_kph": round(5 + (seed // 17 % 45), 1),
        "source": "mock",
    }


def conditions_for(location_id, lat, lon):
    """Use a configured JSON weather endpoint, falling back safely to demo data.

    The endpoint is expected to return temperature_trend_c, dryness, rainfall_mm,
    and wind_kph. This small adapter keeps provider choice outside pipeline logic.
    """
    url, key = os.environ.get("RISK_WEATHER_API_URL"), os.environ.get("RISK_WEATHER_API_KEY")
    if url and key:
        try:
            response = requests.get(url, params={"lat": lat, "lon": lon}, headers={"Authorization": f"Bearer {key}"}, timeout=20)
            response.raise_for_status()
            data = response.json()
            return {"temperature_trend_c": float(data["temperature_trend_c"]), "dryness": float(data["dryness"]),
                    "rainfall_mm": float(data["rainfall_mm"]), "wind_kph": float(data["wind_kph"]), "source": "live"}
        except Exception:
            logger.exception("Live weather lookup failed for %s; falling back to mock data", location_id)
    logger.warning("Risk scoring is using mock weather conditions for %s", location_id)
    return mock_conditions(location_id)


def score_risk(temperature_trend_c, dryness, rainfall_mm, wind_kph, hotspot_frequency):
    """Calculate 0-100 risk: heat/dryness dominate, rain reduces, wind/history amplify."""
    heat = min(max(temperature_trend_c, 0) / 5, 1) * 25
    dry = min(max(dryness, 0) / 100, 1) * 30
    rain_penalty = min(max(rainfall_mm, 0) / 50, 1) * 15
    wind = min(max(wind_kph, 0) / 50, 1) * 15
    history = min(max(hotspot_frequency, 0) / 10, 1) * 30
    return round(min(100, max(0, heat + dry + wind + history - rain_penalty)), 2)


def historical_frequency(supabase, location_id, days):
    """Count prior hotspot rows assigned to the same rounded location cell."""
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        rows = supabase.table("hotspots").select("lat,lon").gte("created_at", cutoff).execute().data or []
        return sum(f"{row['lat']:.3f},{row['lon']:.3f}" == location_id for row in rows)
    except Exception:
        logger.exception("Could not read hotspot history for %s; using zero", location_id)
        return 0


def run():
    """Fetch facilities, compute scores, and upsert them without affecting other jobs."""
    try:
        from supabase import create_client
        if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
            logger.error("Risk scoring skipped: Supabase credentials are not configured")
            return []
        supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
        min_lon, min_lat, max_lon, max_lat = [float(v) for v in REGION_BBOX.split(",")]
        facilities = fetch_facilities(f"{min_lat},{min_lon},{max_lat},{max_lon}")
        days = int(os.environ.get("RISK_HISTORY_DAYS", "90"))
        rows = []
        for facility in facilities:
            location_id = location_id_for_facility(facility)
            factors = conditions_for(location_id, facility["lat"], facility["lon"])
            factors["historical_hotspot_frequency"] = historical_frequency(supabase, location_id, days)
            risk_score = score_risk(
                factors["temperature_trend_c"], factors["dryness"], factors["rainfall_mm"],
                factors["wind_kph"], factors["historical_hotspot_frequency"],
            )
            rows.append({"location_id": location_id, "risk_score": risk_score, "factors": factors,
                         "computed_at": datetime.now(timezone.utc).isoformat()})
        if rows:
            supabase.table("risk_zones").upsert(rows, on_conflict="location_id").execute()
            if os.environ.get("ENABLE_ALERTS", "").lower() == "true":
                try:
                    from pipeline.alerts.alert_engine import should_alert_for_risk, send_alert
                    for row in rows:
                        if should_alert_for_risk(row["risk_score"]):
                            send_alert({**row, "classification": "risk_warning", "priority": "high"}, supabase_client=supabase)
                except Exception:
                    logger.exception("Optional risk alert processing failed")
        logger.info("Computed %d daily risk zones", len(rows))
        return rows
    except Exception:
        logger.exception("Optional risk scoring failed")
        return []


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
