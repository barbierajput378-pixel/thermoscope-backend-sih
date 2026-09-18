"""Pulls raw thermal hotspots from NASA FIRMS for the configured region."""

import requests
import urllib3
from config import FIRMS_MAP_KEY, REGION_BBOX

# GitHub Actions runners sometimes can't reach NASA's IPv6 endpoint - force IPv4
urllib3.util.connection.HAS_IPV6 = False

FIRMS_URL = (
    "https://firms.modaps.eosdis.nasa.gov/api/area/csv/"
    "{map_key}/VIIRS_SNPP_NRT/{bbox}/1"
)


def fetch_hotspots():
    """Returns a list of raw hotspot dicts: lat, lon, brightness, confidence, acq_date."""
    url = FIRMS_URL.format(map_key=FIRMS_MAP_KEY, bbox=REGION_BBOX)
    response = requests.get(url, timeout=30)
    response.raise_for_status()

    hotspots = []
    lines = response.text.strip().split("\n")
    if len(lines) < 2:
        return hotspots

    headers = lines[0].split(",")
    for line in lines[1:]:
        values = line.split(",")
        row = dict(zip(headers, values))
        hotspots.append(
            {
                "lat": float(row.get("latitude", 0)),
                "lon": float(row.get("longitude", 0)),
                "brightness": float(row.get("bright_ti4", 0) or 0),
                "confidence": row.get("confidence", ""),
                "acq_date": row.get("acq_date", ""),
                "acq_time": row.get("acq_time", ""),
            }
        )
    return hotspots


if __name__ == "__main__":
    for h in fetch_hotspots()[:5]:
        print(h)