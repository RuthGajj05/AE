-- Competitor monitoring and advice for small businesses.
--
-- The Python pipeline (agent/supabase_store.py) writes with the service-role
-- key, which bypasses row level security. The app reads and updates as the
-- signed-in owner, limited by the policies at the bottom to their own rows.

-- ---------- Businesses (one per owner's shop) ----------

create table public.businesses (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null default auth.uid() references auth.users (id) on delete cascade,
  name text not null,
  business_type text not null,             -- e.g. 'bakery', 'cafe'
  location text not null,                  -- e.g. 'Fremont, Seattle'
  website text,
  timezone text not null default 'America/Los_Angeles',

  -- Monitoring and notification preferences
  monitor_enabled boolean not null default true,
  notify_hour smallint not null default 14 check (notify_hour between 0 and 23),  -- local hour to send texts/emails
  sms_phone text,                          -- E.164, e.g. +12065550123
  sms_opt_in boolean not null default false,
  sms_opt_in_at timestamptz,               -- when the owner consented to texts
  email text,
  email_opt_in boolean not null default true,

  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index businesses_owner_id_idx on public.businesses (owner_id);

-- ---------- Monitor runs (one per scheduled check) ----------

create table public.monitor_runs (
  id uuid primary key default gen_random_uuid(),
  business_id uuid not null references public.businesses (id) on delete cascade,
  started_at timestamptz not null default now(),
  finished_at timestamptz,
  status text not null default 'running' check (status in ('running', 'succeeded', 'failed')),
  is_baseline boolean not null default false,
  changes_count integer not null default 0,
  error text
);
create index monitor_runs_business_idx on public.monitor_runs (business_id, started_at desc);

-- ---------- Snapshots (full competitor research from one run) ----------

create table public.snapshots (
  id uuid primary key default gen_random_uuid(),
  business_id uuid not null references public.businesses (id) on delete cascade,
  run_id uuid references public.monitor_runs (id) on delete set null,
  taken_at timestamptz not null default now(),
  data jsonb not null                      -- competitor_agent.run() output: competitors, gaps_and_caveats, ...
);
create index snapshots_business_idx on public.snapshots (business_id, taken_at desc);

-- ---------- Competitors (latest known state of each tracked competitor) ----------

create table public.competitors (
  id uuid primary key default gen_random_uuid(),
  business_id uuid not null references public.businesses (id) on delete cascade,
  name text not null,
  address text,
  website text,
  rating numeric(2, 1),
  review_count integer,
  hours text,
  status text,                             -- e.g. 'Opened Oct 2026 (Eater Seattle)', 'Permanently closed'
  details jsonb not null default '{}',     -- full latest entry: prices, praise, complaints, sources
  first_seen_at timestamptz not null default now(),
  last_seen_at timestamptz not null default now(),
  unique (business_id, name)
);

-- ---------- Changes detected between two snapshots ----------

create table public.changes (
  id uuid primary key default gen_random_uuid(),
  business_id uuid not null references public.businesses (id) on delete cascade,
  run_id uuid references public.monitor_runs (id) on delete set null,
  snapshot_id uuid references public.snapshots (id) on delete set null,
  previous_snapshot_id uuid references public.snapshots (id) on delete set null,
  kind text not null check (kind in (
    'new_competitor', 'closed', 'price_change', 'hours_change', 'rating_change', 'review_trend', 'other'
  )),
  competitor_name text not null,
  before text,
  after text,
  evidence text,
  why_it_matters text,
  created_at timestamptz not null default now()
);
create index changes_business_idx on public.changes (business_id, created_at desc);

-- ---------- Notifications (in-app feed + outgoing texts/emails) ----------

create table public.notifications (
  id uuid primary key default gen_random_uuid(),
  business_id uuid not null references public.businesses (id) on delete cascade,
  run_id uuid references public.monitor_runs (id) on delete set null,
  channel text not null check (channel in ('in_app', 'sms', 'email')),
  title text,
  message text not null,
  status text not null default 'pending' check (status in ('pending', 'sent', 'failed', 'skipped')),
  send_after timestamptz not null default now(),  -- respects the owner's notify_hour
  sent_at timestamptz,
  read_at timestamptz,                     -- set by the app when the owner opens it
  error text,
  created_at timestamptz not null default now()
);
create index notifications_business_idx on public.notifications (business_id, created_at desc);
create index notifications_pending_idx on public.notifications (send_after) where status = 'pending';

-- ---------- Advisor reports (full tailored advice runs) ----------

create table public.advisor_reports (
  id uuid primary key default gen_random_uuid(),
  business_id uuid not null references public.businesses (id) on delete cascade,
  created_at timestamptz not null default now(),
  advice jsonb not null,                   -- snapshot, strengths, gaps, recommendations, caveats
  sales_summary jsonb,
  online_presence jsonb,
  competitors jsonb
);
create index advisor_reports_business_idx on public.advisor_reports (business_id, created_at desc);

-- ---------- updated_at ----------

create function public.set_updated_at() returns trigger
language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create trigger businesses_set_updated_at
  before update on public.businesses
  for each row execute function public.set_updated_at();

-- ---------- Row level security: owners see only their own data ----------

alter table public.businesses enable row level security;
alter table public.monitor_runs enable row level security;
alter table public.snapshots enable row level security;
alter table public.competitors enable row level security;
alter table public.changes enable row level security;
alter table public.notifications enable row level security;
alter table public.advisor_reports enable row level security;

create policy "Owners manage their businesses" on public.businesses
  for all to authenticated
  using (owner_id = (select auth.uid()))
  with check (owner_id = (select auth.uid()));

create function public.owns_business(b uuid) returns boolean
language sql stable security definer set search_path = '' as $$
  select exists (select 1 from public.businesses where id = b and owner_id = (select auth.uid()));
$$;

create policy "Owners read their runs" on public.monitor_runs
  for select to authenticated using (public.owns_business(business_id));
create policy "Owners read their snapshots" on public.snapshots
  for select to authenticated using (public.owns_business(business_id));
create policy "Owners read their competitors" on public.competitors
  for select to authenticated using (public.owns_business(business_id));
create policy "Owners read their changes" on public.changes
  for select to authenticated using (public.owns_business(business_id));
create policy "Owners read their advisor reports" on public.advisor_reports
  for select to authenticated using (public.owns_business(business_id));
create policy "Owners read their notifications" on public.notifications
  for select to authenticated using (public.owns_business(business_id));

-- Owners may only mark notifications as read; the column grant keeps every other field read-only.
create policy "Owners mark their notifications read" on public.notifications
  for update to authenticated
  using (public.owns_business(business_id))
  with check (public.owns_business(business_id));
revoke update on public.notifications from authenticated;
grant update (read_at) on public.notifications to authenticated;
