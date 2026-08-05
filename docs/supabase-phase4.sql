-- Phase 4: meeting lifecycle status
alter table meetings add column if not exists status text default 'setup';

-- one-time reclassify of existing rows to a truthful state
update meetings set status = case
    when is_active = false then 'published'
    when minutes_final is not null and minutes_final <> '' then 'draft'
    else 'collecting'
  end;
