# setup.md

Discord Developer Portal setup for the Discord bot, and the `.env` it runs
from. Everything is at <https://discord.com/developers/applications>.

## 1. Create the application

**New Application**, and name it. The name is what players see on the bot
and on its slash commands.

## 2. General Information

**Description**, up to 400 characters, shown on the bot's profile:

```text
A quiz on the order of Singapore's MRT and LRT stations. Which station is between two others, which comes next, which is not on a line, how many stops. Ten questions a run, four answers each, one tap, getting harder as you go. Put your score on the public leaderboard at the end. No sign up. Send /help for the rules.
```

Upload the app icon from `main-site/RSG-512.png`.

## 3. Bot

| Setting | Value | Why |
|---|---|---|
| **Reset Token** | copy it | This is `DISCORD_BOT_TOKEN`. If it ever leaks, reset it again at once. |
| Public Bot | On, or off to keep invites to yourself | Off means only you can add it to a server. |
| Requires OAuth2 Code Grant | Off | Not used. |
| Presence Intent | Off | Not used. |
| Server Members Intent | Off | Not used. |
| Message Content Intent | Off | Not needed. Everything is a slash command or a button. |

## 4. Installation

| Setting | Value |
|---|---|
| Installation Contexts | **Guild Install** only. Untick User Install: cards are sent and edited with the bot's own token, which needs the bot in the channel. The commands are declared server and DM only, so Discord keeps them off user installs anyway. |
| Install Link | Discord Provided Link |
| Guild Install scopes | `applications.commands`, `bot` |
| Guild Install permissions | View Channels, Send Messages, Send Messages in Threads, Embed Links |

Open the install link to add the bot to a server. Direct messages need no
install: once you share a server with the bot, message it, or use its
commands from its profile.

## 5. Commands

Nothing to paste. The bot registers its slash commands from `commands.py`
and syncs them with Discord at every startup; the log says `synced 3 slash
commands`. `python commands.py` prints the list:

```text
/help - How to play, scoring, the leaderboard, and every command.
/play - Start a run of ten questions.
/leaderboard - The best run under each name.
```

A new or changed command can take a minute to show in the client. Restarting
Discord makes it show at once.

## 6. `.env`

```bash
cp .env.example .env
```

| Variable | From |
|---|---|
| `DISCORD_BOT_TOKEN` | Step 3 |
| `BOT_API_TOKEN` | The same value as on the Vercel project |
| `DONATION_URL` | Optional. The coffee button on `/help`; empty hides it |

`SUPABASE_URL` and `SUPABASE_SERVICE_KEY` are not needed: the bot only talks
to the game API.

## 7. Start it

```bash
pip install -r requirements.txt
python bot.py
```

The log should show `synced 3 slash commands` and `connected as <name>`.
Then send `/help`, and walk the checklist in [`README.md`](README.md).
