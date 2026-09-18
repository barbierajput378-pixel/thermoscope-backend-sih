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
fetch_context.py - pulls OSM facility data via Overpass API + land cover for each hotspot
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
hotspots to Supabase, frontend can query the table directly. Not yet built:
auto-alerting fire authorities (future scope), ML-based classification
(current version is rule-based), land-cover lookup (`land_cover_at` is a
stub, always returns "unknown").
