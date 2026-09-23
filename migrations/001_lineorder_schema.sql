-- MRT Navigator Game schema, in the shared uwuapps Supabase project.
-- Paste into the Supabase SQL editor and run, then 002 (or
-- `python scripts/seed_supabase.py`). Safe to run again: everything is
-- "if not exists" or "or replace".
--
-- Access model: only the Vercel functions and the seed script touch these
-- tables, with the service role key. There is no Supabase Auth and no
-- uwu_users here. RLS is on with no policies, so an anon key reads nothing.
--
-- Stations are not copied. The project already holds them in
-- mrtguessr_stations (MRT Station Guesser, same sgraildata snapshot, with
-- Chinese and Tamil names), so line stops point at that table.

do $$
begin
  if to_regclass('public.mrtguessr_stations') is null then
    raise exception 'mrtguessr_stations is missing. It comes from the mrtguess-game repo: run its migrations first.';
  end if;
end $$;

-- Each line's stations in code order: NS1, NS2, NS3. Skipped codes (NS6,
-- TE10) are stations that do not exist. A branch or loop follows its trunk:
-- EW33 then CG1, STC then SE1..SE5 then SW1..SW8. Computed at seed time.
create table if not exists lineorder_line_stops (
  line_code text not null,        -- 'NS', 'EW', 'CC', see api/_lib/lines.js
  seq smallint not null,
  station_id bigint not null references mrtguessr_stations(id),
  code text not null,             -- this station's code on this line
  primary key (line_code, seq),
  unique (line_code, station_id)
);

-- Which stops are next to each other on a line. Also computed at seed time,
-- since order alone cannot say it: Tuas Link and Expo are neighbours in the
-- list above but not on the map, and Bayfront to Promenade closes a loop.
create table if not exists lineorder_links (
  line_code text not null,
  a_station bigint not null references mrtguessr_stations(id),
  b_station bigint not null references mrtguessr_stations(id),
  primary key (line_code, a_station, b_station),
  check (a_station < b_station)
);

-- One run is one game: a fixed number of questions, scored together.
create table if not exists lineorder_runs (
  id uuid primary key default gen_random_uuid(),
  client_key text,
  question_count smallint not null default 10,
  answered smallint not null default 0,
  score int not null default 0,
  finished boolean not null default false,
  submitted boolean not null default false,
  created_at timestamptz not null default now(),
  -- Beyond the spec's columns.
  correct smallint not null default 0
);

create index if not exists lineorder_runs_created on lineorder_runs (created_at);

-- answer_index never leaves the server until the question is answered.
create table if not exists lineorder_questions (
  id uuid primary key default gen_random_uuid(),
  run_id uuid references lineorder_runs(id) on delete cascade,
  template text not null,
  prompt text not null,
  options text[] not null,
  answer_index smallint not null,
  difficulty smallint not null,
  answered boolean not null default false,
  correct boolean,
  created_at timestamptz not null default now(),
  -- Beyond the spec's columns. seq is the question's place in the run;
  -- subject stops a run asking about the same thing twice; explain is shown
  -- once the question is answered.
  seq smallint not null,
  subject text not null,
  explain text,
  unique (run_id, seq)
);

-- At most one open question per run, so asking again returns the same one
-- rather than rolling for an easier question.
create unique index if not exists lineorder_questions_open
  on lineorder_questions (run_id) where not answered;

create table if not exists lineorder_leaderboard (
  id bigserial primary key,
  name text not null,
  score int not null,
  run_id uuid not null unique references lineorder_runs(id),
  created_at timestamptz not null default now()
);

create index if not exists lineorder_lb_best
  on lineorder_leaderboard (lower(name), score desc);

-- Each name's best score. The earliest of an equal top score wins, and the
-- casing shown is the one attached to that score.
create or replace view lineorder_leaderboard_best
with (security_invoker = true) as
select distinct on (lower(name)) name, score, created_at
from lineorder_leaderboard
order by lower(name), score desc, created_at asc;

-- Fixed window counters for rate limiting by IP. There are no accounts to
-- limit against, and Vercel functions share no memory.
create table if not exists lineorder_rate_limits (
  bucket text primary key,
  window_start timestamptz not null,
  hits int not null
);

alter table lineorder_line_stops enable row level security;
alter table lineorder_links enable row level security;
alter table lineorder_runs enable row level security;
alter table lineorder_questions enable row level security;
alter table lineorder_leaderboard enable row level security;
alter table lineorder_rate_limits enable row level security;

-- True while the bucket is under its limit. One statement, so concurrent
-- hits cannot both read the old count.
create or replace function lineorder_hit(p_bucket text, p_window_seconds int, p_max int)
returns boolean
language sql
volatile
as $$
  insert into lineorder_rate_limits as r (bucket, window_start, hits)
  values (p_bucket, now(), 1)
  on conflict (bucket) do update set
    window_start = case
      when r.window_start < now() - make_interval(secs => p_window_seconds) then now()
      else r.window_start end,
    hits = case
      when r.window_start < now() - make_interval(secs => p_window_seconds) then 1
      else r.hits + 1 end
  returning hits <= p_max;
$$;

-- Replaces the line stops and links in one go, matching stations by English
-- name. Refuses, and changes nothing, if any name is not in
-- mrtguessr_stations. Called by scripts/seed_supabase.py and by the
-- generated load migrations.
create or replace function lineorder_load_network(p_stops jsonb, p_links jsonb)
returns table (stops int, links int)
language plpgsql
volatile
as $$
declare
  v_missing text;
  v_stops int;
  v_links int;
begin
  select string_agg(distinct n, ', ') into v_missing
  from (
    select e->>'name_en' as n from jsonb_array_elements(p_stops) e
    union select e->>'a' from jsonb_array_elements(p_links) e
    union select e->>'b' from jsonb_array_elements(p_links) e
  ) names
  where not exists (select 1 from mrtguessr_stations s where s.name_en = names.n);

  if v_missing is not null then
    raise exception 'not in mrtguessr_stations: %. Seed that table from the same snapshot first.', v_missing;
  end if;

  delete from lineorder_links where true;
  delete from lineorder_line_stops where true;

  insert into lineorder_line_stops (line_code, seq, station_id, code)
  select e->>'line', (e->>'seq')::smallint, s.id, e->>'code'
  from jsonb_array_elements(p_stops) e
  join mrtguessr_stations s on s.name_en = e->>'name_en';
  get diagnostics v_stops = row_count;

  insert into lineorder_links (line_code, a_station, b_station)
  select distinct e->>'line', least(a.id, b.id), greatest(a.id, b.id)
  from jsonb_array_elements(p_links) e
  join mrtguessr_stations a on a.name_en = e->>'a'
  join mrtguessr_stations b on b.name_en = e->>'b';
  get diagnostics v_links = row_count;

  return query select v_stops, v_links;
end;
$$;

-- Answers a question. The run's score moves here and nowhere else, and only
-- once per question: the row lock makes a double tap count one answer.
create or replace function lineorder_answer(p_question_id uuid, p_client_key text, p_choice smallint)
returns table (
  status text, correct boolean, answer_index smallint, points int,
  run_score int, answered smallint, question_count smallint, finished boolean, explain text
)
language plpgsql
volatile
as $$
#variable_conflict use_column
declare
  v_q lineorder_questions%rowtype;
  v_run lineorder_runs%rowtype;
  v_correct boolean;
  v_points int;
begin
  select * into v_q from lineorder_questions where id = p_question_id for update;
  if found then
    select * into v_run from lineorder_runs where id = v_q.run_id for update;
  end if;

  -- Someone else's question reads as no question at all.
  if not found or v_run.client_key is distinct from p_client_key then
    return query select 'not_found'::text, null::boolean, null::smallint, null::int,
      null::int, null::smallint, null::smallint, null::boolean, null::text;
    return;
  end if;
  if v_q.answered then
    return query select 'already_answered'::text, v_q.correct, v_q.answer_index, null::int,
      v_run.score, v_run.answered, v_run.question_count, v_run.finished, v_q.explain;
    return;
  end if;
  if v_run.finished then
    return query select 'run_finished'::text, null::boolean, null::smallint, null::int,
      v_run.score, v_run.answered, v_run.question_count, v_run.finished, null::text;
    return;
  end if;
  if v_run.created_at < now() - interval '1 hour' then
    return query select 'run_expired'::text, null::boolean, null::smallint, null::int,
      v_run.score, v_run.answered, v_run.question_count, v_run.finished, null::text;
    return;
  end if;

  v_correct := p_choice = v_q.answer_index;
  v_points := case when v_correct then v_q.difficulty * 100 else 0 end;

  update lineorder_questions set answered = true, correct = v_correct where id = p_question_id;
  update lineorder_runs set
    answered = answered + 1,
    correct = correct + (case when v_correct then 1 else 0 end),
    score = score + v_points,
    finished = answered + 1 >= question_count
  where id = v_run.id
  returning * into v_run;

  return query select 'ok'::text, v_correct, v_q.answer_index, v_points,
    v_run.score, v_run.answered, v_run.question_count, v_run.finished, v_q.explain;
end;
$$;

-- Submits a finished run under a name the API has already validated. The
-- score is read from the run, never taken from the caller.
create or replace function lineorder_submit(p_run_id uuid, p_name text)
returns table (status text, best_score int, rank bigint)
language plpgsql
volatile
as $$
#variable_conflict use_column
declare
  v_run lineorder_runs%rowtype;
  v_best int;
  v_best_at timestamptz;
begin
  select * into v_run from lineorder_runs where id = p_run_id for update;

  if not found then
    return query select 'not_found'::text, null::int, null::bigint;
    return;
  end if;
  if not v_run.finished then
    return query select 'unfinished'::text, null::int, null::bigint;
    return;
  end if;
  if v_run.submitted then
    return query select 'already_submitted'::text, null::int, null::bigint;
    return;
  end if;
  if v_run.created_at < now() - interval '1 hour' then
    return query select 'expired'::text, null::int, null::bigint;
    return;
  end if;

  update lineorder_runs set submitted = true where id = p_run_id;
  insert into lineorder_leaderboard (name, score, run_id)
  values (p_name, v_run.score, p_run_id);

  select l.score, l.created_at into v_best, v_best_at
  from lineorder_leaderboard l
  where lower(l.name) = lower(p_name)
  order by l.score desc, l.created_at asc
  limit 1;

  return query
  select 'ok'::text, v_best, (
    select count(*) + 1
    from lineorder_leaderboard_best b
    where b.score > v_best or (b.score = v_best and b.created_at < v_best_at)
  );
end;
$$;

-- Housekeeping, called now and then by /api/run/new. Old counters, and runs
-- nobody submitted that are past any use; their questions go with them.
create or replace function lineorder_prune()
returns void
language sql
volatile
as $$
  delete from lineorder_rate_limits where window_start < now() - interval '1 day';
  delete from lineorder_runs r
  where r.created_at < now() - interval '2 days'
    and not r.submitted
    and not exists (select 1 from lineorder_leaderboard l where l.run_id = r.id);
$$;

-- Service role only.
revoke all on function lineorder_hit(text, int, int) from public, anon, authenticated;
revoke all on function lineorder_load_network(jsonb, jsonb) from public, anon, authenticated;
revoke all on function lineorder_answer(uuid, text, smallint) from public, anon, authenticated;
revoke all on function lineorder_submit(uuid, text) from public, anon, authenticated;
revoke all on function lineorder_prune() from public, anon, authenticated;
grant execute on function lineorder_hit(text, int, int) to service_role;
grant execute on function lineorder_load_network(jsonb, jsonb) to service_role;
grant execute on function lineorder_answer(uuid, text, smallint) to service_role;
grant execute on function lineorder_submit(uuid, text) to service_role;
grant execute on function lineorder_prune() to service_role;
