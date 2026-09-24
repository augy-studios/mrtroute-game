# api

Vercel serverless functions. The only place questions are generated and
answers checked; the PWA and both bots call these endpoints and hold no
rules of their own.

**`answer_index` never leaves the server before the question is answered.**
A question is generated here, stored in `lineorder_questions` with its
answer, and returned as the prompt and four options only. The answer comes
back in the reply to an answer, so the client can show what was right.

## Endpoints

All take and return JSON. Run and question endpoints need `client_key`: a
random id the browser keeps in local storage, or `tg:<user id>` /
`dc:<user id>` from a bot. A run is only visible to the key that started it.

| Endpoint | Body | Returns |
|---|---|---|
| `POST /api/run/new` | `client_key` | `run_id, question_count` |
| `POST /api/question/new` | `run_id, client_key` | `question_id, prompt, options, difficulty, difficulty_name, points, index, total, run_score` |
| `POST /api/question/answer` | `question_id, client_key, choice` | `correct, answer_index, points, run_score, finished, answered, total, explain` |
| `POST /api/run/state` | `run_id, client_key` | `run_id, question_count, answered, correct, score, finished, submitted, expired` |
| `POST /api/leaderboard/submit` | `run_id, name` | `name, rank, best_score, total, runs, total_rank` |
| `POST /api/leaderboard/name` | `name` | `name`, cleaned, or a `400` saying why not |
| `GET /api/leaderboard` | `?board=best` (default) or `?board=total` | `board, entries`, cached 30 s |

`run/state` and `leaderboard/name` are additions to the spec's list:
`run/state` so a client can pick a run up again after a reload or restart,
and `name` so a client can check a name it wants to save in its settings.
`choice` is the index of the option picked, 0 to 3.

## Leaderboards

Two boards over the same submissions, one row per name, names compared
case-insensitively:

| Board | Entries | Ranked by |
|---|---|---|
| `best` | `{ rank, name, score }` | the name's single best run; ties to whoever got it first |
| `total` | `{ rank, name, total, runs }` | every submitted run added up; ties to fewer runs, then whoever got there first |

Only submitted runs count towards either, since a run has no name until it
is submitted. Submit returns the name's place on both.

`question/new` returns the run's open question if it has one, and only makes
a new one once that is answered. A unique index allows one open question per
run, so asking twice, or from two tabs, never rolls a fresh question.

Errors are `{ "error": code, "message"? }` with a matching status: `400` bad
input, `401` bad bot token, `404` no such run or question, `409` already
answered, run finished or already submitted, `410` run expired. A
`409 already_answered` also carries the result the first answer
got, so a double tap shows the same thing twice.

## Rules

| | |
|---|---|
| Questions per run | 10 |
| Levels | 1 to 3 easy, 4 to 7 medium, 8 to 10 hard |
| Points | 100, 200, 300 for a right answer; nothing lost for a wrong one |
| Run lifetime | An hour, for answering and for submitting |

Answering is one SQL function, `lineorder_answer`, which locks the question
and its run, so a score moves once per question however many taps arrive.

## Questions

`_lib/questions.js`, from the network in `_lib/network.js`. Five templates:

| Template | Example |
|---|---|
| `between` | Which station is between Bishan and Toa Payoh on the North-South Line? |
| `next` | Which station comes immediately after Bishan, heading towards Marina South Pier on the North-South Line? |
| `not_on` | Which of these is NOT on the Downtown Line? |
| `stops` | How many stops from Jurong East to Buona Vista on the East-West Line? |
| `which_line` | Which line does Bras Basah belong to? |

Wrong answers come from the same line wherever possible, so a question tests
the line rather than elimination:

| Level | Wrong answers |
|---|---|
| Easy | From other lines, or far away; MRT lines only |
| Medium | The same line, far from the answer |
| Hard | Next to the answer: one stop beyond, the station behind, a neighbour on a crossing line |

A question is kept only when exactly one option is right: "between" checks
no other station sits next to both, and "which line" only asks about
stations on one line. On a loop, "heading towards" is a matter of opinion, so
"next" names the station the train just left instead. Stop counts are the
shortest ride along the named line.

Check changes with `node scripts/sample-questions.mjs`.

## Auth

Bots send `Authorization: Bearer <BOT_API_TOKEN>`. A wrong token is a `401`,
not a fallback to browser rules. Browsers send nothing. There is no rate
limiting.

## Files

| Path | What it is |
|---|---|
| `run/*.js`, `question/*.js`, `leaderboard/*.js` | The endpoints. |
| `_lib/questions.js` | The five templates, difficulty and wrong answers. Pure. |
| `_lib/network.js` | Lines, stops and links as a graph, loaded from Supabase and cached. |
| `_lib/runs.js` | Runs, and what a client may see of runs and questions. |
| `_lib/http.js` | Auth, input checks, error replies. |
| `_lib/names.js` | Leaderboard name cleaning and the English and Chinese word filter. |
| `_lib/lines.js` | Line codes, names and colours. |
| `_lib/supabase.js` | Supabase REST with the service role key. |

Vercel does not route files under `_lib/`.
