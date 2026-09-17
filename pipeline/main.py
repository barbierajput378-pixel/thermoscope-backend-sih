"""Runs the full pipeline: fetch -> context -> classify -> write to Supabase."""

from supabase import create_client

from config import SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, REGION_BBOX
from fetch_firms import fetch_hotspots
from fetch_context import fetch_facilities, land_cover_at
from classify import classify_hotspot


def to_overpass_bbox(region_bbox):
    # REGION_BBOX is min_lon,min_lat,max_lon,max_lat -> Overpass wants south,west,north,east
    min_lon, min_lat, max_lon, max_lat = [float(v) for v in region_bbox.split(",")]
    return f"{min_lat},{min_lon},{max_lat},{max_lon}"


def fetch_existing_hotspots(supabase):
    """Fetch all existing hotspots once for efficient deduplication."""
    result = supabase.table("hotspots").select("lat,lon").execute()
    return [(row["lat"], row["lon"]) for row in result.data]


def hotspot_seen_before(lat, lon, existing_hotspots, tolerance=0.01):
    """Check if hotspot exists within tolerance of any prior hotspot.
     
    Args:
        lat, lon: coordinates of new hotspot
        existing_hotspots: pre-fetched list of (lat, lon) tuples
        tolerance: search radius in degrees (~1km at equator)
     
    Returns:
        bool: True if hotspot exists nearby in existing_hotspots
    """
    for ex_lat, ex_lon in existing_hotspots:
        if abs(lat - ex_lat) <= tolerance and abs(lon - ex_lon) <= tolerance:
            return True
    return False


def run():
    supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

    hotspots = fetch_hotspots()
    facilities = fetch_facilities(to_overpass_bbox(REGION_BBOX))
    existing_hotspots = fetch_existing_hotspots(supabase)

    rows = []
    for h in hotspots:
        seen_before = hotspot_seen_before(h["lat"], h["lon"], existing_hotspots)
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
        supabase.table("hotspots").insert(rows).execute()

    print(f"Processed {len(rows)} hotspots.")


if __name__ == "__main__":
    run()
