-- Anti-cheat: a right answer that arrives faster than anyone could read the
-- question is counted, and a run with more than one of them stays off the
-- leaderboard. The network is public, so a script can answer everything
-- correctly in milliseconds; a person cannot.
-- Run after 001 to 003. Safe to run again.
--
-- Timed on the server, from the question being made to the answer arriving,
-- both by the database clock. Anything a client does in between (loading,
-- a reload, a bot relaying through Telegram or Discord) only adds time.
-- One fast answer is forgiven; wrong ones never count, since they score
-- nothing.

alter table lineorder_questions add column if not exists answered_at timestamptz;
alter table lineorder_runs add column if not exists fast_answers smallint not null default 0;

-- As in 001, plus answered_at and the fast answer count.
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
  v_fast boolean;
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
  v_fast := v_correct and now() - v_q.created_at < interval '1 second';
  v_points := case when v_correct then v_q.difficulty * 100 else 0 end;

  update lineorder_questions set answered = true, correct = v_correct, answered_at = now()
  where id = p_question_id;
  update lineorder_runs set
    answered = answered + 1,
    correct = correct + (case when v_correct then 1 else 0 end),
    score = score + v_points,
    fast_answers = fast_answers + (case when v_fast then 1 else 0 end),
    finished = answered + 1 >= question_count
  where id = v_run.id
  returning * into v_run;

  return query select 'ok'::text, v_correct, v_q.answer_index, v_points,
    v_run.score, v_run.answered, v_run.question_count, v_run.finished, v_q.explain;
end;
$$;

-- As in 003, plus the too_fast refusal. The run stays unsubmitted, so it
-- is pruned like any other abandoned run.
create or replace function lineorder_submit(p_run_id uuid, p_name text)
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
  if v_run.fast_answers > 1 then
    return query select 'too_fast'::text, null::int, null::bigint, null::bigint, null::int, null::bigint;
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

revoke all on function lineorder_answer(uuid, text, smallint) from public, anon, authenticated;
revoke all on function lineorder_submit(uuid, text) from public, anon, authenticated;
grant execute on function lineorder_answer(uuid, text, smallint) to service_role;
grant execute on function lineorder_submit(uuid, text) to service_role;
