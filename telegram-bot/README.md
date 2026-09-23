# telegram-bot

The Telegram client for MRT Navigator Game. Telethon, private chats only.
First-time BotFather setup is in [`setup.md`](setup.md).

## Running it

On the VPS, in your own tmux session, from this directory:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then fill it in
python bot.py
```

A second copy is refused while one is running (exit status 3, naming the pid).
Exit status 2 means the environment is incomplete, with every missing
variable listed.

## How it plays

- `/play` starts a run of ten questions and sends the first card: the
  question, its level and points, the score so far, and one button per answer.
- Tapping an answer redraws that card as answered, with its buttons gone:
  which answer was right, which was picked, and a line saying why. The next
  card follows below it straight away, so each question is one tap.
- After the tenth, the result card: score, how many were right, and
  `Add as NAME` in one tap, "Another name" (the next message is the name),
  Play again and Leaderboard. NAME is the name last used on the leaderboard
  or, until there is one, the player's Telegram first name with emoji and
  symbols dropped. A typed name is remembered; the Telegram name is never
  saved, so it follows the account.
- `/play` again mid-run starts a fresh run. Buttons on the old run's card
  are then refused and removed.
- If the next question cannot be fetched, a Try again button picks the run
  up where it stopped.
- `/leaderboard` shows the top ten. `/start` is the help; there is no
  `/help`, and typing it points back to `/start`.

## What lives where

| | |
|---|---|
| Questions, answers, scores | The API, in Supabase. The bot has no Supabase key. |
| Buttons, each chat's current run, question cards as sent, remembered names, a waiting name prompt | `bot.sqlite3`, local and gitignored. |

Buttons carry an opaque id looked up in SQLite, so answer buttons keep working
across a restart and cannot be forged. A card's question is kept too, without
its answer, so it can still be redrawn as answered after a restart. Losing
`bot.sqlite3` costs old buttons and remembered names, never a score.

Nothing here is timed, so there is no scheduler beyond an hourly tidy of
expired buttons and prompts.

## Files

| File | What it does |
|---|---|
| `bot.py` | Entry point: config, lock, Telethon, routing, the hourly tidy. |
| `handlers.py` | Commands, answer buttons, names and the leaderboard. |
| `views.py` | Message builders, as rich message plus buttons. |
| `reply.py` | Telegram Rich Messages, per `telethon-richmessage-retrofit.md`. |
| `commands.py` | The command list. `python commands.py` prints it for BotFather. |
| `api.py` | The game API client. |
| `db.py` | SQLite. |
| `config.py` | Environment variables. |
| `lock.py` | One instance at a time. |

## Rich messages

Structured replies (`/start`, question cards, answered cards, results, the
leaderboard) go out as native Telegram Rich Messages with a plain text
fallback, through raw `SendMessageRequest` and `EditMessageRequest` in
`reply.py`. One-line notices ("Send /play to start a run.", the name prompt,
errors) stay plain. A refused rich send falls back to the plain text and logs
`rich send failed, falling back`; on a current client that line should never
appear. There is no inline mode, so no inline results.

## Checking it by hand

1. `/start`: how to play, the question kinds, a scoring table, the
   leaderboard rules, the command table and what is stored, rendered
   natively. "Play in the browser" opens the site.
2. `/play`: a card with four answer buttons, "Question 1 of 10, Easy".
3. Tap an answer: the card redraws with the right answer marked and a reason,
   its buttons gone, and question 2 arrives below. Tap the old card's area:
   nothing to press.
4. Restart the bot mid-run and tap an answer on the waiting card: it still
   works, and the card still redraws.
5. `/play` mid-run, then tap an answer on the previous run's card: refused,
   and its buttons disappear.
6. Finish the run: the result card with `Add as FIRSTNAME`. Press Another
   name, send a rude name (refused, asks again), then a good one.
7. Finish another: the card offers `Add as NAME` with the typed name.
8. `/leaderboard`: a table.
9. Start a second copy: refused with the first one's pid.
