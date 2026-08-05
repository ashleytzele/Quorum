-- Phase 4: meeting lifecycle status (idempotent — safe to re-run)
alter table meetings add column if not exists status text;

-- backfill only rows that don't yet have a status
update meetings set status = case
    when is_active = false then 'published'
    when minutes_final is not null and minutes_final <> '' then 'draft'
    else 'collecting'
  end
where status is null;

-- new meetings default to 'setup' (MeeTeam inserts don't set status)
alter table meetings alter column status set default 'setup';
