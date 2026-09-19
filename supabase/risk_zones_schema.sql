-- Optional daily pre-fire risk scores. Service role writes bypass RLS; public reads only.
create table if not exists risk_zones (
  location_id text primary key,
  risk_score double precision not null check (risk_score between 0 and 100),
  factors jsonb not null default '{}'::jsonb,
  computed_at timestamptz not null default now()
);
alter table risk_zones enable row level security;
create policy "public read risk zones" on risk_zones for select using (true);
