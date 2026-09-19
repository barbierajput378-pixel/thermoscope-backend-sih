-- Optional alert audit log. The service role writes; no public alert access is granted.
create table if not exists alerts (
  id bigint generated always as identity primary key,
  hotspot_id bigint references hotspots(id) on delete set null,
  location_id text not null,
  alert_type text not null,
  routed_to text not null,
  sent_at timestamptz not null default now(),
  status text not null check (status in ('sent', 'failed', 'dry_run', 'skipped_cooldown'))
);
create index if not exists alerts_location_type_sent_idx on alerts (location_id, alert_type, sent_at desc);
alter table alerts enable row level security;
