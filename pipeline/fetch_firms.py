"""Pulls raw thermal hotspots from NASA FIRMS for the configured region."""

import time
import requests
import urllib3
from config import FIRMS_MAP_KEY, REGION_BBOX

# GitHub Actions runners sometimes can't reach NASA's IPv6 endpoint - force IPv4
urllib3.util.connection.HAS_IPV6 = False

FIRMS_URL = (
    "https://firms.modaps.eosdis.nasa.gov/api/area/csv/"
    "{map_key}/VIIRS_SNPP_NRT/{bbox}/1"
)


def get_with_retries(url, attempts=5, connect_timeout=20, read_timeout=120, backoff=5):
    """GET with retries + exponential backoff (5s, 10s, 20s, 40s)."""
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            response = requests.get(url, timeout=(connect_timeout, read_timeout))
            if response.status_code >= 500 or response.status_code == 429:
                raise requests.exceptions.HTTPError(
                    f"HTTP {response.status_code}", response=response
                )
            response.raise_for_status()
            return response
        except requests.exceptions.RequestException as e:
            last_error = e
            status = getattr(getattr(e, "response", None), "status_code", None)
            if status is not None and 400 <= status < 500 and status != 429:
                raise
            if attempt < attempts:
                wait = backoff * (2 ** (attempt - 1))
                print(f"[FIRMS] attempt {attempt}/{attempts} failed: {type(e).__name__}. Retrying in {wait}s...")
                time.sleep(wait)
    raise RuntimeError(f"FIRMS request failed after {attempts} attempts") from last_error

def fetch_hotspots():
    """Returns a list of raw hotspot dicts: lat, lon, brightness, confidence, acq_date."""
    url = FIRMS_URL.format(map_key=FIRMS_MAP_KEY, bbox=REGION_BBOX)
    response = get_with_retries(url)
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