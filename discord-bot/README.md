# discord-bot

The Discord client for MRT Navigator Game. discord.py with slash commands,
in servers and direct messages. First-time Developer Portal setup is in
[`setup.md`](setup.md).

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
- Tapping an answer redraws that card as answered: the buttons stay but are
  disabled, the right answer green and a wrong pick red, with a line saying
  why. The next card follows below it.
- After the tenth, the result card: `Add as NAME` in one tap, and "Another
  name", which opens a box. NAME is the name last used or, until there is
  one, the player's Discord display name.
- `/help` answers only the player who asked, in a server. It is the help;
  there is no `/start`.
- In a direct message, plain text gets a pointer to the card or `/play`.
  In a server, plain messages are ignored.

## What lives where

| | |
|---|---|
| Questions, answers, scores | The API, in Supabase. The bot has no Supabase key. |
| Buttons, each player's current run per channel, question cards as sent, remembered names | `bot.sqlite3`, local and gitignored. |

Buttons carry an opaque id looked up in SQLite, matched by pattern, so answer
buttons keep working across restarts and cannot be forged. Losing
`bot.sqlite3` costs old buttons and remembered names, never a score. Nothing
here is timed; an hourly tidy clears expired buttons.

## Files

| File | What it does |
|---|---|
| `bot.py` | Entry point: config, lock, the client, slash commands, the hourly tidy. |
| `handlers.py` | Commands, answer buttons, the name box and the leaderboard. |
| `views.py` | Message builders, as embed plus buttons. |
| `buttons.py` | The one button class every button uses, and the registry lookup. |
| `commands.py` | The command list. `python commands.py` prints it. |
| `api.py` | The game API client. |
| `db.py` | SQLite. |
| `config.py` | Environment variables. |
| `lock.py` | One instance at a time. The same as the Telegram bot's. |

## Checking it by hand

1. `/help`: how to play, the question kinds, a scoring table, the leaderboard
   rules and the command list. In a server only you see it.
2. `/play`: a card with four answer buttons.
3. Tap an answer: the card's buttons go grey, green and red, the reason shows,
   and the next card arrives below.
4. Have a second account `/play` in the same channel: two runs, and neither
   player can press the other's buttons.
5. Restart the bot mid-run and tap an answer on the waiting card: it works.
6. Finish the run: `Add as NAME`, or Another name with a rude name (refused,
   only you see why), then a good one.
7. Direct message the bot: `/play` works there too.
8. `/leaderboard`: a table.
9. Start a second copy: refused with the first one's pid.
