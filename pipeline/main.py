"""Runs the full pipeline: fetch -> context -> classify -> write to Supabase."""

import logging
import os

from supabase import create_client

from config import SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, REGION_BBOX
from fetch_firms import fetch_hotspots
from fetch_context import fetch_facilities, land_cover_at
from classify import classify_hotspot


def to_overpass_bbox(region_bbox):
    # REGION_BBOX is min_lon,min_lat,max_lon,max_lat -> Overpass wants south,west,north,east
    min_lon, min_lat, max_lon, max_lat = [float(v) for v in region_bbox.split(",")]
    return f"{min_lat},{min_lon},{max_lat},{max_lon}"


def hotspot_seen_before(supabase, lat, lon, tolerance=0.01):
    """Very rough check for now: any prior row within ~1km of this lat/lon."""
    result = (
        supabase.table("hotspots")
        .select("id")
        .gte("lat", lat - tolerance)
        .lte("lat", lat + tolerance)
        .gte("lon", lon - tolerance)
        .lte("lon", lon + tolerance)
        .execute()
    )
    return len(result.data) > 0


def run():
    supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

    hotspots = fetch_hotspots()
    facilities = fetch_facilities(to_overpass_bbox(REGION_BBOX))

    rows = []
    for h in hotspots:
        seen_before = hotspot_seen_before(supabase, h["lat"], h["lon"])
        land_cover = land_cover_at(h["lat"], h["lon"])
        result = classify_hotspot(h, facilities, seen_before, land_cover)

        rows.append(
            {
                "lat": h["lat"],
                "lon": h["lon"],
                "brightness": h["brightness"],
                "acq_date": h["acq_date"],
                "acq_time": h["acq_time"],
                **result,
            }
        )

    if rows:
        write_result = supabase.table("hotspots").insert(rows).execute()

        # Alerts are optional and intentionally occur only after a successful hotspot
        # write.  A failure here must never affect the completed pipeline run.
        if os.environ.get("ENABLE_ALERTS", "").lower() == "true":
            try:
                from alerts.alert_engine import should_alert, send_alert

                written_rows = getattr(write_result, "data", None) or rows
                for original, written in zip(rows, written_rows):
                    if should_alert(
                        original["classification"], original["confidence"], original["priority"]
                    ):
                        payload = {**original, **written}
                        payload.setdefault("location_id", f"{payload['lat']:.3f},{payload['lon']:.3f}")
                        send_alert(payload, routed_to=None, supabase_client=supabase)
            except Exception:
                logging.getLogger(__name__).exception("Optional alert processing failed")

    print(f"Processed {len(rows)} hotspots.")


if __name__ == "__main__":
    run()
