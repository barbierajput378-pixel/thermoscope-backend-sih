"""Seed or remove clearly identified presentation data without running the pipeline.

This script deliberately uses the same service-role configuration as the pipeline.
It is safe to rerun: fixed coordinates/names/location IDs are checked before any
insert, and alert delivery is only evaluated through the real alert engine.
"""

import argparse
from datetime import date
import logging

from supabase import create_client

from config import REGION_BBOX, SUPABASE_SERVICE_ROLE_KEY, SUPABASE_URL
from alerts.alert_engine import should_alert, should_alert_for_risk, send_alert

logger = logging.getLogger(__name__)

DEMO_STEEL_PLANT = "Demo Steel Plant — Rourkela"
DEMO_LNG_TERMINAL = "Demo LNG Terminal"
HIGH_RISK_LOCATION_ID = "demo_facility_high_risk"
LOW_RISK_LOCATION_ID = "demo_facility_low_risk"


def _demo_points():
    """Return three stable, distinct points safely inside the configured bbox."""
    min_lon, min_lat, max_lon, max_lat = [float(value) for value in REGION_BBOX.split(",")]
    lon_range, lat_range = max_lon - min_lon, max_lat - min_lat
    return [
        (min_lat + lat_range * 0.25, min_lon + lon_range * 0.25),
        (min_lat + lat_range * 0.50, min_lon + lon_range * 0.50),
        (min_lat + lat_range * 0.75, min_lon + lon_range * 0.75),
    ]


def _location_id(row):
    return f"{float(row['lat']):.3f},{float(row['lon']):.3f}"


def _safe(label, operation):
    """Keep a missing table/column from aborting the remaining demo setup."""
    try:
        return operation()
    except Exception as error:
        print(f"ERROR {label}: {error}")
        logger.exception("Demo seed operation failed: %s", label)
        return None


def _first(result):
    rows = getattr(result, "data", None) or []
    return rows[0] if rows else None


def _find_hotspot(client, row):
    # Fixed point + classification is the wildfire identifier; named facilities are
    # additionally fixed identifiers for the two facility-associated demonstrations.
    return _safe(
        f"checking hotspot {row['classification']}",
        lambda: _first(
            client.table("hotspots")
            .select("id,lat,lon,classification")
            .eq("lat", row["lat"])
            .eq("lon", row["lon"])
            .eq("classification", row["classification"])
            .execute()
        ),
    )


def _seed_hotspot(client, row):
    existing = _find_hotspot(client, row)
    if existing:
        updated = _safe(
            f"updating hotspot {row['classification']} (check that hotspots has is_demo)",
            lambda: _first(client.table("hotspots").update(row).eq("id", existing["id"]).execute()),
        )
        return updated or existing, "already existed" if updated else "failed"
    inserted = _safe(
        f"inserting hotspot {row['classification']} (check that hotspots has is_demo)",
        lambda: _first(client.table("hotspots").insert(row).execute()),
    )
    return inserted, "new" if inserted else "failed"


def _seed_risk_zone(client, row):
    existing = _safe(
        f"checking risk zone {row['location_id']}",
        lambda: _first(
            client.table("risk_zones").select("location_id,risk_score").eq(
                "location_id", row["location_id"]
            ).execute()
        ),
    )
    if existing:
        return existing, "already existed"
    inserted = _safe(
        f"inserting risk zone {row['location_id']}",
        lambda: _first(client.table("risk_zones").insert(row).execute()),
    )
    return inserted, "new" if inserted else "failed"


def _alert_already_recorded(client, location_id, alert_type):
    result = _safe(
        f"checking existing demo alert for {location_id}",
        lambda: client.table("alerts").select("id").eq("location_id", location_id).eq(
            "alert_type", alert_type
        ).limit(1).execute(),
    )
    return bool(getattr(result, "data", None))


def _evaluate_alerts(client, hotspots, risk_zones):
    """Evaluate every row, but do not create repeated demo alert audit entries."""
    evaluations, outcomes = 0, []
    for row in hotspots:
        evaluations += 1
        if should_alert(row["classification"], row["confidence"], row["priority"]):
            location_id = _location_id(row)
            if _alert_already_recorded(client, location_id, row["classification"]):
                outcomes.append("already recorded")
            else:
                outcome = _safe(
                    f"sending demo hotspot alert for {row['classification']}",
                    lambda: send_alert({**row, "location_id": location_id}, supabase_client=client),
                )
                outcomes.append(outcome or "failed")
        else:
            outcomes.append("did not meet threshold")
    for row in risk_zones:
        evaluations += 1
        if should_alert_for_risk(row["risk_score"]):
            if _alert_already_recorded(client, row["location_id"], "risk_warning"):
                outcomes.append("already recorded")
            else:
                outcome = _safe(
                    f"sending demo risk alert for {row['location_id']}",
                    lambda: send_alert(
                        {**row, "classification": "risk_warning", "priority": "high"},
                        supabase_client=client,
                    ),
                )
                outcomes.append(outcome or "failed")
        else:
            outcomes.append("did not meet threshold")
    return evaluations, outcomes


def seed(client):
    """Insert five fixed demo records and run the normal alert decisions."""
    steel, wildfire, lng = _demo_points()
    today = date.today().isoformat()
    hotspots = [
        {"lat": steel[0], "lon": steel[1], "acq_date": today, "acq_time": "1200", "brightness": 340,
         "classification": "industrial_fire", "confidence": 0.92, "priority": "high",
         "nearest_facility": DEMO_STEEL_PLANT, "distance_m": 150, "is_demo": True},
        {"lat": wildfire[0], "lon": wildfire[1], "acq_date": today, "acq_time": "1230", "brightness": 320,
         "classification": "wildfire", "confidence": 0.65, "priority": "low",
         "nearest_facility": None, "distance_m": None, "is_demo": True},
        {"lat": lng[0], "lon": lng[1], "acq_date": today, "acq_time": "1300", "brightness": 335,
         "classification": "gas_flare", "confidence": 0.8, "priority": "low",
         "nearest_facility": DEMO_LNG_TERMINAL, "distance_m": 180, "is_demo": True},
    ]
    risk_zones = [
        {"location_id": HIGH_RISK_LOCATION_ID, "risk_score": 87,
         "factors": {"temperature_trend_c": 4.5, "dryness": 92, "rainfall_mm": 1,
                     "wind_kph": 38, "historical_hotspot_frequency": 8, "source": "demo"}},
        {"location_id": LOW_RISK_LOCATION_ID, "risk_score": 15,
         "factors": {"temperature_trend_c": 0.5, "dryness": 30, "rainfall_mm": 35,
                     "wind_kph": 6, "historical_hotspot_frequency": 0, "source": "demo"}},
    ]
    hotspot_results = [_seed_hotspot(client, row) for row in hotspots]
    risk_results = [_seed_risk_zone(client, row) for row in risk_zones]
    hotspot_states = [state for _, state in hotspot_results]
    risk_states = [state for _, state in risk_results]
    # Do not alert about a row that could not be written to the requested table.
    alert_hotspots = [row for row, (_, state) in zip(hotspots, hotspot_results) if state != "failed"]
    alert_risk_zones = [row for row, (_, state) in zip(risk_zones, risk_results) if state != "failed"]
    evaluations, outcomes = _evaluate_alerts(client, alert_hotspots, alert_risk_zones)
    print(
        "Seeded: 3 hotspots "
        f"({hotspot_states.count('new')} new, {hotspot_states.count('already existed')} already existed, "
        f"{hotspot_states.count('failed')} failed), 2 risk_zones "
        f"({risk_states.count('new')} new, {risk_states.count('already existed')} already existed, "
        f"{risk_states.count('failed')} failed), {evaluations} alert evaluations "
        f"({', '.join(outcomes)})."
    )


def cleanup(client):
    """Delete only the fixed records and alert audit entries created by this script."""
    steel, wildfire, lng = _demo_points()
    deleted_hotspots, deleted_risk_zones, deleted_alerts = [], [], []
    for label, row in zip(("industrial_fire", "wildfire", "gas_flare"), (steel, wildfire, lng)):
        lat, lon = row
        result = _safe(
            f"deleting demo hotspot {label}",
            lambda lat=lat, lon=lon, label=label: client.table("hotspots").delete().eq("lat", lat).eq(
                "lon", lon
            ).eq("classification", label).eq("is_demo", True).execute(),
        )
        deleted_hotspots.append(len(getattr(result, "data", None) or []))
    for location_id in (HIGH_RISK_LOCATION_ID, LOW_RISK_LOCATION_ID):
        result = _safe(
            f"deleting demo risk zone {location_id}",
            lambda location_id=location_id: client.table("risk_zones").delete().eq(
                "location_id", location_id
            ).execute(),
        )
        deleted_risk_zones.append(len(getattr(result, "data", None) or []))
    for location_id, alert_type in ((_location_id({"lat": steel[0], "lon": steel[1]}), "industrial_fire"),
                                    (HIGH_RISK_LOCATION_ID, "risk_warning")):
        result = _safe(
            f"deleting demo alert {location_id}",
            lambda location_id=location_id, alert_type=alert_type: client.table("alerts").delete().eq(
                "location_id", location_id
            ).eq("alert_type", alert_type).execute(),
        )
        deleted_alerts.append(len(getattr(result, "data", None) or []))
    print(
        f"Cleanup complete: deleted {sum(deleted_hotspots)} demo hotspots, "
        f"{sum(deleted_risk_zones)} demo risk zones, and {sum(deleted_alerts)} demo alert records."
    )


def main():
    parser = argparse.ArgumentParser(description="Seed presentation-only Thermoscope demo data")
    parser.add_argument("--cleanup", action="store_true", help="Remove only this script's fixed demo rows")
    args = parser.parse_args()
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        print("ERROR: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be configured.")
        return 1
    try:
        client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
    except Exception as error:
        print(f"ERROR: could not create Supabase client: {error}")
        return 1
    cleanup(client) if args.cleanup else seed(client)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    raise SystemExit(main())
