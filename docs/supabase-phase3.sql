-- Phase 3, Task 1: template registry.
-- Run this ONCE in the Supabase dashboard SQL editor. Not executed by any
-- script or test — the unit tests stub the network and don't need the live
-- table. The Mac's template JSON files remain the source of truth; this
-- table is a mirror for the web dropdown.

-- templates registry: mirror of the Mac's template files (source of truth stays local)
create table if not exists templates (
  stem        text primary key,
  name        text not null,
  description text,
  updated_at  timestamptz default now()
);
alter table templates enable row level security;
create policy "templates readable by authenticated"
  on templates for select to authenticated using (true);
-- No insert/update policy: only the service_role key (the Mac sync) writes, and it bypasses RLS.

-- meetings gain a chosen template stem (null = pipeline default)
alter table meetings add column if not exists template text;
