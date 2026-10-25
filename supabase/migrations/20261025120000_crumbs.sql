-- crumbs: the consumer food map and the business dashboard, on top of Ruth's competitor monitoring
-- (20261025000000_competitor_monitoring.sql, unchanged).
--
-- Writers: backend/store.py and backend/scripts/sync_to_supabase.py, with the service-role (or sb_secret_) key,
-- which bypasses row level security. Readers: the Lovable app with the anon key, limited by the policies below.
--
--   spots, spot_scores        anyone can read (the public map)
--   alerts                    consumer alerts: anyone; business alerts: only the owner of that business
--   picks                     anyone can add one, nobody can read them back (anonymous; no user id, IP or device)
--   saved_spots, profiles     only the signed-in user's own rows
--   business_insights         only the owner of that business (Ruth's owns_business pattern)

-- ---------- crumbs fields on Ruth's businesses ----------
-- Nullable or defaulted, so Ruth's pipeline and her existing rows are unaffected.

alter table public.businesses
  add column if not exists address text,
  add column if not exists lat double precision,
  add column if not exists lng double precision,
  add column if not exists cuisine text,                       -- crumbs food type id: sushi, ramen, steak, pizza, tacos
  add column if not exists goals text[] not null default '{}',  -- onboarding goals, e.g. {'Shorter waits','Rice'}
  add column if not exists share_stock_alerts boolean not null default false,  -- opt-in to public "fresh in" alerts
  add column if not exists low_stock_threshold numeric not null default 5,
  add column if not exists spot_id text;                       -- this business's row in spots, once scored

-- ---------- Spots (the public map) ----------

create table public.spots (
  id text primary key,                     -- e.g. 'sushi-hikari' or 'spot-hikari-sushi-bar-1525'
  name text not null,
  address text,
  street text,
  lat double precision,
  lng double precision,
  price text,                              -- '$' … '$$$$'
  phone text,
  open_until text,                         -- e.g. '10 pm'
  website text,
  rating numeric(2, 1),
  platform_review_count integer,           -- what a listing shows, not reviews we read
  hours text,
  collection_status text not null default 'complete' check (collection_status in ('complete', 'partial')),
  demo boolean not null default false,     -- made-up sample spot (backend/demo fixtures)
  updated_at timestamptz not null default now()
);

-- ---------- Spot scores (one row per spot and food type) ----------

create table public.spot_scores (
  spot_id text not null references public.spots (id) on delete cascade,
  cuisine text not null,
  area text not null default 'capitol-hill',
  scores jsonb not null default '{}',      -- {attribute: 0-100 or null}; null = no review mentioned it
  highlights jsonb not null default '{}',  -- {attribute: one short line from the reviews}
  summary text,
  wait_minutes numeric,
  ambiance_pct integer,
  ambiance_mention_rate numeric,
  review_count integer not null default 0, -- review texts actually read
  source_kinds text[] not null default '{}',
  best_at text,                            -- 'Best rice', 'Shortest wait', … (#1 in this food type and area)
  reason text,                             -- one line paraphrasing reviewers about best_at
  is_pick boolean not null default false,  -- the crumbs pick for this food type and area
  model text,
  demo boolean not null default false,
  scored_at timestamptz not null default now(),
  primary key (spot_id, cuisine)
);
create index spot_scores_cuisine_idx on public.spot_scores (cuisine, area);

-- ---------- Picks (anonymous) ----------

create table public.picks (
  id bigint generated always as identity primary key,
  cuisine text not null check (char_length(cuisine) <= 40),
  chosen_spot_id text not null check (char_length(chosen_spot_id) between 1 and 120),
  compared_spot_ids text[] not null default '{}' check (cardinality(compared_spot_ids) <= 12),
  demo boolean not null default false,
  created_at timestamptz not null default now()
);
create index picks_cuisine_idx on public.picks (cuisine, created_at desc);

-- ---------- Alerts ----------

create table public.alerts (
  id text primary key,
  kind text not null check (kind in (
    'fresh_stock', 'low_stock', 'top_rated', 'new_spot', 'closed', 'price_change',
    'new_competitor', 'hours_change', 'rating_change', 'review_trend', 'other'
  )),
  audience text not null check (audience in ('consumer', 'business')),
  business_id uuid references public.businesses (id) on delete cascade,  -- required for business alerts
  spot_id text,
  cuisine text,
  title text not null,
  detail text not null,
  lat double precision,
  lng double precision,
  dedupe_key text unique,
  demo boolean not null default false,
  created_at timestamptz not null default now(),
  check (audience = 'consumer' or business_id is not null)
);
create index alerts_audience_idx on public.alerts (audience, created_at desc);
create index alerts_business_idx on public.alerts (business_id, created_at desc);

-- ---------- Saved spots (per signed-in user) ----------

create table public.saved_spots (
  user_id uuid not null default auth.uid() references auth.users (id) on delete cascade,
  spot_id text not null check (char_length(spot_id) between 1 and 120),
  cuisine text,
  snapshot jsonb not null default '{}',    -- {name, price, bestAt, reason, lat, lng}: what the Saved tab shows
  created_at timestamptz not null default now(),
  primary key (user_id, spot_id)
);

-- ---------- Profiles (one per signed-in user) ----------

create table public.profiles (
  id uuid primary key default auth.uid() references auth.users (id) on delete cascade,
  display_name text not null default 'Guest' check (char_length(display_name) <= 80),
  home_area text not null default 'Capitol Hill',
  account_type text not null default 'consumer' check (account_type in ('consumer', 'business')),
  business_id uuid references public.businesses (id) on delete set null,
  favorites text[] not null default '{}',
  alert_prefs jsonb not null default '{}', -- {setting id: false} for switched-off alert kinds
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create trigger profiles_set_updated_at
  before update on public.profiles
  for each row execute function public.set_updated_at();

-- ---------- Business insights (Home: Insights + Rivals), written by the sync script ----------

create table public.business_insights (
  business_id uuid primary key references public.businesses (id) on delete cascade,
  cuisine text,
  insights jsonb not null,                 -- backend GET /api/business/{id}/insights shape
  rivals jsonb not null,                   -- backend GET /api/business/{id}/rivals shape
  demo boolean not null default false,
  updated_at timestamptz not null default now()
);

-- ---------- Row level security ----------

alter table public.spots enable row level security;
alter table public.spot_scores enable row level security;
alter table public.picks enable row level security;
alter table public.alerts enable row level security;
alter table public.saved_spots enable row level security;
alter table public.profiles enable row level security;
alter table public.business_insights enable row level security;

create policy "Anyone reads spots" on public.spots
  for select to anon, authenticated using (true);
create policy "Anyone reads spot scores" on public.spot_scores
  for select to anon, authenticated using (true);

-- Insert-only: no select, update or delete policy, so a pick can't be read back or changed from the app.
create policy "Anyone adds an anonymous pick" on public.picks
  for insert to anon, authenticated with check (demo = false);
revoke select, update, delete on public.picks from anon, authenticated;

create policy "Anyone reads consumer alerts" on public.alerts
  for select to anon, authenticated using (audience = 'consumer');
create policy "Owners read their business alerts" on public.alerts
  for select to authenticated using (audience = 'business' and public.owns_business(business_id));

create policy "Users manage their saved spots" on public.saved_spots
  for all to authenticated
  using (user_id = (select auth.uid()))
  with check (user_id = (select auth.uid()));

-- A profile can only point at a business its user owns.
create policy "Users read their profile" on public.profiles
  for select to authenticated using (id = (select auth.uid()));
create policy "Users create their profile" on public.profiles
  for insert to authenticated
  with check (id = (select auth.uid()) and (business_id is null or public.owns_business(business_id)));
create policy "Users update their profile" on public.profiles
  for update to authenticated
  using (id = (select auth.uid()))
  with check (id = (select auth.uid()) and (business_id is null or public.owns_business(business_id)));

create policy "Owners read their business insights" on public.business_insights
  for select to authenticated using (public.owns_business(business_id));
