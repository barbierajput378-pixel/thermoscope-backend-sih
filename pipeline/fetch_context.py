"""Pulls facility locations (OSM) for the region. Land-cover lookup TODO."""

import time

import requests

OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.osm.ch/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]

# OSM tags for the facility types we care about
FACILITY_QUERY_TEMPLATE = """
[out:json][timeout:90];
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


def fetch_facilities(bbox):
    """bbox format expected by Overpass: south,west,north,east"""
    query = FACILITY_QUERY_TEMPLATE.format(bbox=bbox)
    headers = {"User-Agent": "thermoscope-sih26162/1.0 (SIH hackathon project)"}
    last_err = None

    for url in OVERPASS_URLS:
        try:
            response = requests.post(url, data={"data": query}, headers=headers, timeout=90)
            response.raise_for_status()
            data = response.json()
            return _parse_facilities(data)
        except requests.RequestException as e:
            last_err = e
            time.sleep(2)
            continue

    raise RuntimeError(f"All Overpass mirrors failed. Last error: {last_err}")


def _parse_facilities(data):
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
    """TODO: wire up ESA WorldCover or similar. Returns a placeholder for now."""
    return "unknown"