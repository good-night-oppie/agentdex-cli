-- 0001_arena_event_log.sql — apply to the prod Supabase project (agentdex.builders)
-- via the SQL editor or supabase CLI. GENERATED from agentdex_arena.eventsync
-- .ARENA_EVENT_LOG_DDL — a test asserts this file matches; edit the Python, not this.

create table if not exists arena_event_log (
  id          bigint generated always as identity primary key,
  tenant_id   text not null,
  battle_id   text not null,
  seq         bigint not null,
  event_type  text not null,
  prev_digest text not null,
  payload     jsonb not null default '{}'::jsonb,
  created_at  timestamptz not null default now(),
  unique (tenant_id, battle_id, seq)
);
alter table arena_event_log enable row level security;
alter table arena_event_log force row level security;

-- Read scoping: each tenant (arena consent token) sees only its own rows.
-- The gateway authenticates agents with its OWN Ed25519 consent tokens (not
-- Supabase Auth), so the tenant predicate is a per-connection GUC the reader
-- path sets AFTER validating the token (RLS-POC-verified on Postgres 16).
drop policy if exists arena_event_tenant_select on arena_event_log;
create policy arena_event_tenant_select on arena_event_log for select
  using (tenant_id = current_setting('app.tenant_id', true));
drop policy if exists arena_event_tenant_insert on arena_event_log;
create policy arena_event_tenant_insert on arena_event_log for insert
  with check (tenant_id = current_setting('app.tenant_id', true));
-- NO update/delete policy => append-only by absence of policy.

-- Belt-and-suspenders: service_role/superuser BYPASS RLS, so a trigger makes
-- the log physically immutable for EVERY role including the gateway's own.
create or replace function arena_event_log_immutable() returns trigger
language plpgsql as $$
begin
  raise exception 'arena_event_log is append-only (% denied)', tg_op;
end; $$;
drop trigger if exists arena_event_no_mutate on arena_event_log;
create trigger arena_event_no_mutate
  before update or delete on arena_event_log
  for each row execute function arena_event_log_immutable();
