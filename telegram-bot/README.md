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
- Tapping an answer is the whole move. With "Remove old cards" on (the
  default), the run is one card: it turns into the next question, with how
  the last one went at its top (right or wrong, the right answer, and why).
  Off, the answered card stays with its buttons gone, marking the right
  answer and the one picked, and the next card follows below it.
- After the tenth, the result card: score, how many were right, and
  `Add as NAME` in one tap, "Another name" (the next message is the name),
  Play again and Leaderboard. NAME is the saved leaderboard name or, until
  one is saved, the player's Telegram first name with emoji and symbols
  dropped. A typed name is remembered in its place; the Telegram name is
  never saved, so it follows the account. With automatic adding on, the
  result card says the run was added instead.
- `/play` again mid-run starts a fresh run. The old run's card is deleted,
  or with old card removal off, left without buttons; a button pressed on it
  is refused.
- If the next question cannot be fetched, a Try again button picks the run
  up where it stopped.
- `/leaderboard` shows the top ten on the best score board, with a button
  that swaps the same message to total points and back.
- `/start` is the help; there is no `/help`, and typing it points back to
  `/start`.
- `/settings` holds the leaderboard name and two switches, each redrawn in
  place when pressed:

| Setting | Default | What it does |
|---|---|---|
| Leaderboard name | Telegram first name | Filled in by every successful submit under a typed name; can be changed (checked by the API) or cleared back to the Telegram name. |
| Add finished runs automatically | off | Submits every finished run under the leaderboard name. Needs a usable name, saved or from Telegram. |
| Remove old cards | on | A run stays as one card, and an old run's card is deleted. Off leaves every answered card in the chat. |

## What lives where

| | |
|---|---|
| Questions, answers, scores | The API, in Supabase. The bot has no Supabase key. |
| Buttons, each chat's current run and card, question cards as sent, a waiting name prompt, settings | `bot.sqlite3`, local and gitignored. |

Buttons carry an opaque id looked up in SQLite, so answer buttons keep working
across a restart and cannot be forged. A card's question is kept too, without
its answer, so it can still be redrawn as answered after a restart. Losing
`bot.sqlite3` costs old buttons and everyone's settings, never a score.

Nothing here is timed, so there is no scheduler beyond an hourly tidy of
expired buttons and prompts.

## Files

| File | What it does |
|---|---|
| `bot.py` | Entry point: config, lock, Telethon, routing, the hourly tidy. |
| `handlers.py` | Commands, answer buttons, names, settings and the leaderboard. |
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
3. Tap an answer: the same card becomes question 2, with how question 1
   went at the top. No new message arrives.
4. Restart the bot mid-run and tap an answer on the waiting card: it still
   works.
5. Finish the run: the result card with `Add as FIRSTNAME`, and
   `/settings` shows the name as "(your Telegram name)". Press Another name,
   send a rude name (refused, asks again), then a good one.
6. Finish another: the card offers `Add as NAME` with the typed name. In
   `/settings`, Use Telegram name goes back to the first name.
7. `/settings`: turn on automatic adding and finish a run; the result card
   says it was added, with both ranks. Turn off old card removal: each
   answered card now stays, marked, and the next arrives below.
8. `/play` mid-run, then tap an answer on the previous run's card: refused.
9. `/leaderboard`: a table, and the button swaps to total points in place.
10. Start a second copy: refused with the first one's pid.
