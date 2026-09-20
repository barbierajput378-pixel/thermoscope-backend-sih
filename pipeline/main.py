"""Runs the full pipeline: fetch -> context -> classify -> write to Supabase."""

import logging
import os
from collections import defaultdict

from supabase import create_client

from config import SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, REGION_BBOX, FACILITY_PROXIMITY_METERS
from fetch_firms import fetch_hotspots
from fetch_context import fetch_facilities, land_cover_at
from classify import classify_hotspot, nearest_facility


def to_overpass_bbox(region_bbox):
    # REGION_BBOX is min_lon,min_lat,max_lon,max_lat -> Overpass wants south,west,north,east
    min_lon, min_lat, max_lon, max_lat = [float(v) for v in region_bbox.split(",")]
    return f"{min_lat},{min_lon},{max_lat},{max_lon}"


def _coord_bucket(lat, lon, tolerance=0.01):
    return (round(float(lat) / tolerance), round(float(lon) / tolerance))


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


def build_seen_before_index(supabase, tolerance=0.01):
    """Warm a bucketed coordinate index so we avoid one DB query per hotspot."""
    result = supabase.table("hotspots").select("lat,lon").execute()
    seen = defaultdict(list)
    for row in result.data or []:
        lat = row.get("lat")
        lon = row.get("lon")
        if lat is None or lon is None:
            continue
        seen[_coord_bucket(lat, lon, tolerance)].append((float(lat), float(lon)))
    return seen


def has_seen_before(seen_index, lat, lon, tolerance=0.01):
    """Check nearby buckets and preserve the original exact tolerance behavior."""
    lat_bucket, lon_bucket = _coord_bucket(lat, lon, tolerance)
    for lat_offset in (-1, 0, 1):
        for lon_offset in (-1, 0, 1):
            for seen_lat, seen_lon in seen_index.get(
                (lat_bucket + lat_offset, lon_bucket + lon_offset), ()
            ):
                if abs(float(lat) - seen_lat) <= tolerance and abs(float(lon) - seen_lon) <= tolerance:
                    return True
    return False


def run():
    supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

    hotspots = fetch_hotspots()
    facilities = fetch_facilities(to_overpass_bbox(REGION_BBOX))
    seen_before_index = build_seen_before_index(supabase)

    rows = []
    for h in hotspots:
        seen_before = has_seen_before(seen_before_index, h["lat"], h["lon"])

        # Only call the (slow, network-bound) land-cover lookup when it's
        # actually needed - i.e. no facility nearby to classify against.
        facility, dist = nearest_facility(h, facilities)
        if facility and dist <= FACILITY_PROXIMITY_METERS:
            land_cover = "unknown"
        else:
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