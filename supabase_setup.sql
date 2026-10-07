-- Carguito — Supabase-only DDL.
--
-- ============================================================================
-- EVERYTHING ELSE COMES FROM ALEMBIC.
--
-- `backend/src/carguito/adapters/outbound/persistence/models.py` is the single
-- source of truth for the application schema, and `backend/migrations/` is how
-- that schema reaches a database. Tables (categories, merchants, accounts,
-- statements, transactions, goals), their indexes, their constraints and their
-- RLS policies are all created by `alembic upgrade head` — RLS included, as a
-- dialect-guarded migration, so a new user-owned table cannot reach Supabase
-- unprotected. Do not add application tables to this file; they will drift.
--
-- What remains below is only what SQLAlchemy cannot express: objects that live
-- in Supabase's `auth` schema or depend on it.
--   1. `profiles`, which foreign-keys `auth.users`
--   2. the `handle_new_user` trigger on `auth.users`
--   3. role grants
--
-- Run this ONCE against a new Supabase project, then run `alembic upgrade head`
-- from `backend/`. For a project whose tables predate Alembic, run
-- `alembic stamp 0001` first — see backend/README.md.
-- ============================================================================

-- 1. Profiles (mirrors auth.users) -------------------------------------------
create table if not exists public.profiles (
  id uuid references auth.users on delete cascade not null primary key,
  updated_at timestamptz default now(),
  full_name text,
  email text unique,
  rfc text,                       -- Mexican Tax ID (for SAT integration)
  monthly_income_goal numeric(14,2)
);

alter table public.profiles enable row level security;

drop policy if exists "Profiles are viewable by owner." on public.profiles;
create policy "Profiles are viewable by owner." on public.profiles
  for select using (auth.uid() = id);

drop policy if exists "Users can insert their own profile." on public.profiles;
create policy "Users can insert their own profile." on public.profiles
  for insert with check (auth.uid() = id);

drop policy if exists "Users can update own profile." on public.profiles;
create policy "Users can update own profile." on public.profiles
  for update using (auth.uid() = id);

-- 2. New-user trigger ---------------------------------------------------------
create or replace function public.handle_new_user()
returns trigger as $$
begin
  insert into public.profiles (id, full_name, email)
  values (new.id, new.raw_user_meta_data->>'full_name', new.email);
  return new;
end;
$$ language plpgsql security definer;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute procedure public.handle_new_user();

-- 3. Grants -------------------------------------------------------------------
-- Alembic connects as the migration role and creates tables owned by it; the
-- PostgREST roles need to be granted access explicitly. RLS (added by migration
-- 0003) is what actually restricts rows -- these grants only open the door.
grant usage on schema public to anon, authenticated, service_role;

grant all on all tables in schema public to anon, authenticated, service_role;
grant all on all sequences in schema public to anon, authenticated, service_role;
grant all on all functions in schema public to anon, authenticated, service_role;

-- Apply the same grants to tables created by future Alembic revisions.
alter default privileges in schema public
  grant all on tables to anon, authenticated, service_role;
alter default privileges in schema public
  grant all on sequences to anon, authenticated, service_role;
alter default privileges in schema public
  grant all on functions to anon, authenticated, service_role;
