-- Run this in the Supabase SQL editor after enabling the PostGIS extension
-- (Database -> Extensions -> postgis, or run: create extension if not exists postgis;)

create extension if not exists postgis;

create table if not exists hotspots (
  id bigint generated always as identity primary key,
  lat double precision not null,
  lon double precision not null,
  location geography(point, 4326) generated always as (
    st_setsrid(st_makepoint(lon, lat), 4326)::geography
  ) stored,
  brightness double precision,
  acq_date text,
  acq_time text,
  classification text,
  confidence double precision,
  priority text,
  nearest_facility text,
  distance_m double precision,
  created_at timestamptz default now()
);

create index if not exists hotspots_location_idx on hotspots using gist (location);

-- Public can read, only the service role (backend pipeline) can write
alter table hotspots enable row level security;

create policy "public read access"
  on hotspots for select
  using (true);

-- No insert/update/delete policy for the public anon role on purpose.
-- The pipeline writes using the service_role key, which bypasses RLS entirely.
