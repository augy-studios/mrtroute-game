-- The cumulative leaderboard: every submitted run's score added up per name.
-- Run after 001 and 002. Safe to run again.

-- One row per name (case-insensitive). The casing shown is the name's most
-- recent submission. Ranked by total; ties go to fewer runs, then to
-- whoever reached it first, which is the earlier last_at.
create or replace view lineorder_leaderboard_total
with (security_invoker = true) as
select
  (array_agg(name order by created_at desc))[1] as name,
  sum(score)::bigint as total,
  count(*)::int as runs,
  max(score) as best,
  max(created_at) as last_at
from lineorder_leaderboard
group by lower(name);

-- submit now also returns the name's total and its place on that board. The
-- return type changes, which "create or replace" cannot do, hence the drop.
drop function if exists lineorder_submit(uuid, text);

create function lineorder_submit(p_run_id uuid, p_name text)
returns table (status text, best_score int, rank bigint, total bigint, runs int, total_rank bigint)
language plpgsql
volatile
as $$
#variable_conflict use_column
declare
  v_run lineorder_runs%rowtype;
  v_best int;
  v_best_at timestamptz;
  v_total bigint;
  v_runs int;
begin
  select * into v_run from lineorder_runs where id = p_run_id for update;

  if not found then
    return query select 'not_found'::text, null::int, null::bigint, null::bigint, null::int, null::bigint;
    return;
  end if;
  if not v_run.finished then
    return query select 'unfinished'::text, null::int, null::bigint, null::bigint, null::int, null::bigint;
    return;
  end if;
  if v_run.submitted then
    return query select 'already_submitted'::text, null::int, null::bigint, null::bigint, null::int, null::bigint;
    return;
  end if;
  if v_run.created_at < now() - interval '1 hour' then
    return query select 'expired'::text, null::int, null::bigint, null::bigint, null::int, null::bigint;
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

  select sum(l.score)::bigint, count(*)::int into v_total, v_runs
  from lineorder_leaderboard l
  where lower(l.name) = lower(p_name);

  return query
  select
    'ok'::text,
    v_best,
    (
      select count(*) + 1
      from lineorder_leaderboard_best b
      where b.score > v_best or (b.score = v_best and b.created_at < v_best_at)
    ),
    v_total,
    v_runs,
    (
      select count(*) + 1
      from lineorder_leaderboard_total t
      where lower(t.name) <> lower(p_name)
        and (
          t.total > v_total
          or (t.total = v_total and t.runs < v_runs)
          -- This name's total was only just reached, so an equal one got there first.
          or (t.total = v_total and t.runs = v_runs)
        )
    );
end;
$$;

revoke all on function lineorder_submit(uuid, text) from public, anon, authenticated;
grant execute on function lineorder_submit(uuid, text) to service_role;
