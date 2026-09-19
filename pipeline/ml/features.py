"""Dependency-light feature helpers shared by training and tests."""


def location_id_for(lat, lon):
    """A stable ~100 m coordinate cell used when no facility/location ID exists."""
    return f"{float(lat):.3f},{float(lon):.3f}"
