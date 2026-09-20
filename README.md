 # Thermoscope backend — SIH26162

AI-based detection and classification of industrial fires and persistent
thermal sources, built for SIH26162 (NTRO).

## What this does

Pulls hotspots from NASA FIRMS, cross-checks them against known industrial
facilities (OSM) and land cover, classifies each one, tags a priority level,
and writes the result into Supabase — where the frontend reads it directly.

## Structure
pipeline/
fetch_firms.py - pulls raw hotspots from NASA FIRMS API (IPv4-forced for CI compatibility)
fetch_context.py - pulls OSM facility data + land cover via Overpass API, with multi-mirror fallback
classify.py - proximity + persistence rules -> classification + confidence
main.py - runs the full pipeline end to end, writes results to Supabase
config.py - region bounding box, thresholds, API keys (from env)
supabase/
schema.sql - hotspots table, PostGIS setup, RLS policies (public read, service-role write)
.github/workflows/
pipeline.yml - runs main.py every 3 hours via GitHub Actions


## Live setup

- **Region:** Odisha (industrial/mining belt) — bbox `81.3,17.8,87.5,22.6`
- **Schedule:** runs automatically every 3 hours via GitHub Actions
- **Database:** Supabase project `thermoscope_sih'26`, Mumbai region
- **Demo data:** 3 seeded rows (`is_demo = true`) always present in the table so the
  frontend map has data to render even when no real hotspots exist in the region
  at query time. Real pipeline writes have `is_demo = false`.

## `hotspots` table (what the frontend queries)

| Column | Type | Notes |
|---|---|---|
| id | int | |
| lat, lon | float | |
| classification | text | industrial_fire / gas_flare / wildfire / agricultural_burning / unclassified |
| confidence | float | 0–1 |
| priority | text | high / low |
| nearest_facility | text | nullable |
| distance_m | float | nullable |
| is_demo | boolean | true = seeded sample, false = real pipeline data |
| created_at | timestamptz | |

Table is publicly readable via Supabase's auto-generated REST API
(PostgREST) using the **publishable key** — no custom backend API needed.
Only the service-role key (used by this pipeline, never exposed to the
frontend) can write.

## Setup from scratch

1. Create a Supabase project, enable the PostGIS extension
2. Run `supabase/schema.sql` in the Supabase SQL editor
3. Copy `.env.example` to `.env`, fill in your keys
4. Add the same keys as GitHub repo secrets (Settings -> Secrets -> Actions)
   so the scheduled workflow can run
5. `pip install -r requirements.txt`
6. `python pipeline/main.py` to run one pass locally

## Status

Working end-to-end. Pipeline runs live on a schedule, writes real classified
hotspots to Supabase, frontend can query the table directly. Classification
is rule-based (proximity + persistence + OSM-derived land cover), with
multi-mirror fallback on the Overpass calls for reliability.

## New and optional: ML, risk, and alerts

These features are disabled unless their environment flags are set, so the
scheduled rule-based pipeline retains its original behavior. Install the updated
requirements before using ML tools.

- **ML classification:** run `python pipeline/ml/train_model.py --csv history.csv`
  (or omit `--csv` to read `hotspots` from Supabase). It uses a location-grouped
  test split and saves `pipeline/ml/fire_classifier.pkl`. Set
  `USE_ML_CLASSIFIER=true` only after reviewing the evaluation output.
- **Daily risk scoring:** run `python pipeline/risk/risk_scoring.py`. It produces
  facility-level 0–100 pre-fire risk scores in `risk_zones`. Without weather API
  configuration it explicitly uses deterministic mock conditions for demos. Run
  `supabase/risk_zones_schema.sql` first.
- **Alerts:** set `ENABLE_ALERTS=true` and email/routing environment variables.
  Alerts are sent only after hotspot writes and are deduplicated for the configured
  cooldown. With no email configuration they are safely logged as `[DRY RUN]`.
  Run `supabase/alerts_schema.sql` first.

## Demo/presentation utility: fixed seed data

`python pipeline/seed_demo_data.py` adds three fixed demonstration hotspots and
two risk zones, then evaluates them through the real alert engine. It is manual,
idempotent, and not part of the scheduled pipeline. Use
`python pipeline/seed_demo_data.py --cleanup` after a presentation to remove only
these fixed demo records and their alert audit rows.
