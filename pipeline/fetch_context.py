"""Pulls facility locations (OSM) for the region. Land-cover lookup via Overpass."""

import requests

OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.osm.ch/api/interpreter",
]

HEADERS = {"User-Agent": "thermoscope-sih26162/1.0 (SIH hackathon project)"}

# OSM tags for the facility types we care about
FACILITY_QUERY_TEMPLATE = """
[out:json][timeout:60];
(
  node["man_made"="works"]({bbox});
  node["industrial"]({bbox});
  node["power"="plant"]({bbox});
  way["man_made"="works"]({bbox});
  way["industrial"]({bbox});
  way["power"="plant"]({bbox});
);
out center;
"""


def _run_overpass_query(query):
    """Tries each mirror in order, returns the first successful response's JSON."""
    last_err = None
    for url in OVERPASS_URLS:
        try:
            response = requests.post(url, data={"data": query}, headers=HEADERS, timeout=45)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            last_err = e
            continue
    raise RuntimeError(f"All Overpass mirrors failed: {last_err}")


def fetch_facilities(bbox):
    """bbox format expected by Overpass: south,west,north,east"""
    query = FACILITY_QUERY_TEMPLATE.format(bbox=bbox)
    data = _run_overpass_query(query)

    facilities = []
    for el in data.get("elements", []):
        lat = el.get("lat") or el.get("center", {}).get("lat")
        lon = el.get("lon") or el.get("center", {}).get("lon")
        if lat is None or lon is None:
            continue
        facilities.append(
            {
                "lat": lat,
                "lon": lon,
                "name": el.get("tags", {}).get("name", "unnamed facility"),
                "type": el.get("tags", {}).get("industrial")
                or el.get("tags", {}).get("power")
                or "industrial",
            }
        )
    return facilities


def land_cover_at(lat, lon):
    """Checks OSM tags in a small radius around the point to guess land cover."""
    query = f"""
    [out:json][timeout:25];
    (
      way["natural"="wood"](around:500,{lat},{lon});
      way["landuse"="forest"](around:500,{lat},{lon});
      way["landuse"="farmland"](around:500,{lat},{lon});
      way["landuse"="farm"](around:500,{lat},{lon});
    );
    out tags 1;
    """
    try:
        data = _run_overpass_query(query)
    except RuntimeError:
        return "unknown"

    for el in data.get("elements", []):
        tags = el.get("tags", {})
        if tags.get("natural") == "wood" or tags.get("landuse") == "forest":
            return "forest"
        if tags.get("landuse") in ("farmland", "farm"):
            return "farmland"

    return "unknown"