# discord-bot

The Discord client for MRT Navigator Game. discord.py with slash commands,
installable on a server or on a user account, and usable in servers, the
bot's direct messages, and other DMs and group DMs. First-time Developer
Portal setup is in [`setup.md`](setup.md).

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
variable listed, or that Discord refused the token.

## How it plays

The same game as the Telegram bot. Where Discord differs:

- A run belongs to one player in one channel. A server channel can hold
  several players' runs at once, each on its own cards, and a card's buttons
  answer only the player it belongs to.
- `/play` sends the first card: the question as an embed, with four answer
  buttons two to a row.
- Tapping an answer is the whole move. With "Remove old cards" on (the
  default), the run is one card that turns into the next question, with how
  the last one went at its top. Off, the answered card stays, its buttons
  disabled, the right answer green and a wrong pick red, and the next card
  follows below it.
- After the tenth, the result card: `Add as NAME` in one tap, and "Another
  name", which opens a box. NAME is the saved leaderboard name or, until one
  is saved, the player's Discord display name. With automatic adding on, the
  result card says the run was added instead.
- `/leaderboard` shows best scores, with a button that swaps the same
  message to total points and back.
- `/help` is shown to the whole channel, and anyone can press its Play and
  Leaderboard buttons for their own run or board. `/help` is the help; there
  is no `/start`.
- `/settings` answers only the player who asked.
- The bot's status reads "Quizzing MRT routes in x guilds". It is updated
  whenever the bot joins or leaves a server. User installs are not counted.
- In the bot's own DM, plain text gets a pointer to the card or `/play`.
  Elsewhere, plain messages are ignored.
- Through a user install, in a channel the bot is not in, every card is sent
  and edited through the interaction's own token, so a run plays the same.
  Removing an old run's card when `/play` starts a new one uses the token of
  the command that sent it, which lasts 15 minutes; after that the old card
  is left in place, its buttons refusing the old run.
- `/settings` holds the same name and two switches as the Telegram bot,
  each redrawn in place when pressed:

| Setting | Default | What it does |
|---|---|---|
| Leaderboard name | Discord display name | Filled in by every successful submit under a typed name; can be changed (checked by the API) or cleared back to the Discord name. |
| Add finished runs automatically | off | Submits every finished run under the leaderboard name. |
| Remove old cards | on | A run stays as one card, and an old run's card is deleted. Off leaves every answered card in the channel. |

Settings are the bot's own, kept against the Discord user id. They are not
shared with the Telegram bot or the PWA; the leaderboard is.

## What lives where

| | |
|---|---|
| Questions, answers, scores | The API, in Supabase. The bot has no Supabase key. |
| Buttons, each player's current run and card per channel (with the token that sent it), question cards as sent, settings | `bot.sqlite3`, local and gitignored. |

Buttons carry an opaque id looked up in SQLite, matched by pattern, so answer
buttons keep working across restarts and cannot be forged. Losing
`bot.sqlite3` costs old buttons and everyone's settings, never a score. Nothing
here is timed; an hourly tidy clears expired buttons.

## Files

| File | What it does |
|---|---|
| `bot.py` | Entry point: config, lock, the client, slash commands, the hourly tidy. |
| `handlers.py` | Commands, answer buttons, the name box, settings and the leaderboard. |
| `views.py` | Message builders, as embed plus buttons. |
| `buttons.py` | The one button class every button uses, and the registry lookup. |
| `commands.py` | The command list. `python commands.py` prints it. |
| `api.py` | The game API client. |
| `db.py` | SQLite. |
| `config.py` | Environment variables. |
| `lock.py` | One instance at a time. The same as the Telegram bot's. |

## Checking it by hand

1. `/help`: how to play, the question kinds, a scoring table, the leaderboard
   rules and the command list, visible to everyone in the channel. Press its
   Play from a second account: that account gets its own run.
2. `/play`: a card with four answer buttons.
3. Tap an answer: the same card becomes question 2, with how question 1 went
   at the top. Turn off old card removal in `/settings` and tap again: the
   card's buttons go grey, green and red, and the next card arrives below.
4. Have a second account `/play` in the same channel: two runs, and neither
   player can press the other's buttons.
5. Restart the bot mid-run and tap an answer on the waiting card: it works.
6. Finish the run: `Add as NAME`, or Another name with a rude name (refused,
   only you see why), then a good one.
7. `/settings`: set a name, turn on automatic adding, and finish a run; the
   result card says it was added, with both ranks.
8. Direct message the bot: `/play` works there too.
9. Install the app to your account and, in a DM with a friend (or a server
   without the bot), type `/`: the commands are listed. `/play` there and
   play a whole run from the card's buttons. Then `/play` again: the old
   card goes.
10. `/leaderboard`: a table, and the button swaps to total points in place.
11. Start a second copy: refused with the first one's pid.
