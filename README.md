# Thermoscope backend — SIH26162

AI-based detection and classification of industrial fires and persistent
thermal sources, built for SIH26162 (NTRO).

## What this does

Pulls hotspots from NASA FIRMS, cross-checks them against known industrial
facilities (OSM) and land cover, classifies each one, tags a priority level,
and writes the result into Supabase — where the frontend reads it directly.

## Structure

```
pipeline/
  fetch_firms.py     - pulls raw hotspots from NASA FIRMS API
  fetch_context.py   - pulls OSM facility data + land cover for each hotspot
  classify.py        - proximity + persistence rules -> classification + confidence
  main.py             - runs the full pipeline end to end
  config.py            - region bounding box, thresholds, API keys (from env)
supabase/
  schema.sql          - tables, PostGIS setup, RLS policies
.github/workflows/
  pipeline.yml         - runs main.py on a schedule via GitHub Actions
```

## Setup

1. Create a Supabase project, enable the PostGIS extension
2. Run `supabase/schema.sql` in the Supabase SQL editor
3. Copy `.env.example` to `.env`, fill in your keys
4. Add the same keys as GitHub repo secrets (Settings -> Secrets -> Actions)
   so the scheduled workflow can run
5. `pip install -r requirements.txt`
6. `python pipeline/main.py` to run one pass locally

## Status

Prototype skeleton — fetch/classify logic is stubbed, wiring it up next.
