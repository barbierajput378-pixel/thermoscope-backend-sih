"""Pulls raw thermal hotspots from NASA FIRMS for the configured region."""

import csv
import io
import json
import os
import time
from pathlib import Path

import requests
import urllib3
from config import FIRMS_MAP_KEY, REGION_BBOX

# GitHub Actions runners sometimes can't reach NASA's IPv6 endpoint - force IPv4
urllib3.util.connection.HAS_IPV6 = False

# Comma-separated hosts, tried in order. Add a mirror via env once verified.
FIRMS_HOSTS = [
    h.strip()
    for h in os.getenv("FIRMS_HOSTS", "firms.modaps.eosdis.nasa.gov").split(",")
    if h.strip()
]
FIRMS_PATH = "/api/area/csv/{map_key}/VIIRS_SNPP_NRT/{bbox}/1"

CACHE_FILE = Path(os.getenv("FIRMS_CACHE_FILE", ".cache/firms_last.json"))
CACHE_MAX_AGE_S = 6 * 3600  # don't reuse data older than 6h


def get_with_retries(url, attempts=3, connect_timeout=30, read_timeout=120, backoff=5):
    """GET with retries + exponential backoff (5s, 10s, ...)."""
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
                raise  # bad key / bad request: don't retry, don't fall back
            if attempt < attempts:
                wait = backoff * (2 ** (attempt - 1))
                print(f"[FIRMS] attempt {attempt}/{attempts} failed: {type(e).__name__}. Retrying in {wait}s...")
                time.sleep(wait)
    raise RuntimeError(f"FIRMS request failed after {attempts} attempts") from last_error


def _parse(text):
    reader = csv.DictReader(io.StringIO(text.strip()))
    if not reader.fieldnames or "latitude" not in reader.fieldnames:
        raise ValueError(f"Unexpected FIRMS response: {text[:200]!r}")
    return [
        {
            "lat": float(row.get("latitude") or 0),
            "lon": float(row.get("longitude") or 0),
            "brightness": float(row.get("bright_ti4") or 0),
            "confidence": row.get("confidence", ""),
            "acq_date": row.get("acq_date", ""),
            "acq_time": row.get("acq_time", ""),
        }
        for row in reader
    ]


def _save_cache(hotspots):
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps({"saved_at": time.time(), "hotspots": hotspots}))


def _load_cache():
    if not CACHE_FILE.exists():
        return None
    data = json.loads(CACHE_FILE.read_text())
    age = time.time() - data["saved_at"]
    if age > CACHE_MAX_AGE_S:
        print(f"[FIRMS] cache too old ({age / 3600:.1f}h), ignoring")
        return None
    print(f"[FIRMS] WARNING: using cached hotspots ({age / 60:.0f} min old)")
    return data["hotspots"]


def fetch_hotspots():
    """Returns a list of raw hotspot dicts: lat, lon, brightness, confidence, acq_date."""
    path = FIRMS_PATH.format(map_key=FIRMS_MAP_KEY, bbox=REGION_BBOX)
    last_error = None

    for host in FIRMS_HOSTS:
        try:
            response = get_with_retries(f"https://{host}{path}")
            hotspots = _parse(response.text)
            _save_cache(hotspots)
            return hotspots
        except RuntimeError as e:  # network-level failure -> try next host
            print(f"[FIRMS] host {host} unreachable, trying next")
            last_error = e

    cached = _load_cache()
    if cached is not None:
        return cached
    raise last_error


if __name__ == "__main__":
    for h in fetch_hotspots()[:5]:
        print(h)