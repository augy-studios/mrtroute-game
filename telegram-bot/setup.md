# setup.md

BotFather setup for the Telegram bot, and the credentials that do not come from
BotFather.

## 1. Telethon credentials

Telethon speaks MTProto, so it needs an application id and hash from a
Telegram account as well as the bot token.

1. Sign in at [my.telegram.org](https://my.telegram.org).
2. Open **API development tools** and fill in the form once. Platform: Other.
3. Keep **App api_id** and **App api_hash**: `TELEGRAM_API_ID` and
   `TELEGRAM_API_HASH` in `.env`.

A pair already made for another uwuapps bot can be reused.

## 2. Create the bot

Message [@BotFather](https://t.me/BotFather) and send `/newbot`. Give it a
display name, then a username ending in `bot`. The token it replies with is
`TELEGRAM_BOT_TOKEN`. If it ever leaks, `/revoke` at once.

## 3. About text

`/setabouttext`, up to 120 characters, shown on the profile card:

```text
How well do you know Singapore's MRT lines? Ten quick questions on station order, one tap each.
```

## 4. Description

`/setdescription`, up to 512 characters, shown above the Start button in an
empty chat:

```text
A quiz on the order of Singapore's MRT and LRT stations. Which station is between two others, which comes next, which is not on a line, how many stops from here to there. Ten questions a run, four answers each, one tap, getting harder as you go. Put your score on the public leaderboard at the end. No sign up. Press Start for the rules and the commands.
```

## 5. Commands

`/setcommands`, then paste this block exactly (it is `python commands.py`):

```text
start - How to play, scoring, the leaderboard, and every command.
play - Start a run of ten questions.
leaderboard - Best scores and total points, one row per name.
settings - Your leaderboard name, automatic adding, and chat tidying.
```

The bot also registers this list itself at every startup, so this step only
makes the menu right before the first run. If the block and `commands.py`
disagree, the file is right.

## 6. Settings

`/mybots`, the bot, **Bot Settings**:

| Setting | Value | Why |
|---|---|---|
| Allow Groups? | Disabled | A run belongs to one player; the bot ignores groups. |
| Group Privacy | Enabled (default) | Nothing to read in groups. |
| Inline Mode | Disabled (default) | Not used. |

## 7. `.env`

```bash
cp .env.example .env
```

| Variable | From |
|---|---|
| `TELEGRAM_API_ID`, `TELEGRAM_API_HASH` | Step 1 |
| `TELEGRAM_BOT_TOKEN` | Step 2 |
| `BOT_API_TOKEN` | The same value as on the Vercel project |
| `DONATION_URL` | Optional. The coffee button on `/start`; empty hides it |

`SUPABASE_URL` and `SUPABASE_SERVICE_KEY` are not needed: the bot only talks
to the game API.

## 8. Start it

```bash
python bot.py
```

The log should end with `connected as @<username>` and `ready`. Then send
`/start` to the bot, and walk the checklist in [`README.md`](README.md).
