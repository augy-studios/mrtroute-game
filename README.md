# MRT Navigator Game

A Singapore MRT quiz about the order of stations along a line. Ten questions a
run, four answers each, one tap. Every question is generated from the station
data, so there is nothing hand-written and the pool is effectively unlimited.

Live at <https://mrtnav.uwuapps.org>. Three clients over one API: a PWA, a
Telegram bot and a Discord bot.

## What runs where

| Part | Runs on |
|---|---|
| `main-site/`, the PWA and the game API (`main-site/api/`) | Vercel, root directory `main-site` |
| Database, `lineorder_*` tables | The shared uwuapps Supabase project |
| `telegram-bot/` | The Debian 13 VPS, one process |
| `discord-bot/` | The Debian 13 VPS, one process |

**On the VPS: the two bots, one process each, and nothing else.** No cron, no
database, no web server. Each bot keeps a small SQLite file beside it for its
buttons; neither holds a Supabase key.

**Station data is shared.** The stations themselves come from
`mrtguessr_stations`, which MRT Station Guesser already loaded into the same
Supabase project from the same sgraildata snapshot. This app adds only the
line order and adjacency (`lineorder_line_stops`, `lineorder_links`). That
repo's migrations must have run first; `001` here refuses otherwise.

## Layout

```
README.md
migrations/      SQL to run in the Supabase SQL editor
scripts/         seed, question sampler, and pre-deploy checks
main-site/       the site Vercel deploys, including api/
telegram-bot/    Telethon bot
discord-bot/     discord.py bot
```

The `uwuapps-*.md`, `update-bar-spec.md`, `telethon-richmessage-retrofit.md`
and `02-line-order.md` files at the root are the specs this is built to.

## First setup

1. Check `mrtguessr_stations` exists in the Supabase project (it does if MRT
   Station Guesser is deployed).
2. Run `migrations/001_lineorder_schema.sql`, then
   `002_lineorder_load_network.sql`, in the Supabase SQL editor.
   `python scripts/seed_supabase.py` does the same as `002` if you would
   rather not paste it.
3. On the Vercel project, add `BOT_API_TOKEN`: a long random string, for
   example from `openssl rand -hex 32`. `SUPABASE_URL` and
   `SUPABASE_SERVICE_KEY` are already there.
4. Point `mrtnav.uwuapps.org` at the Vercel project and deploy `main-site`.
5. Set up the Telegram bot: `telegram-bot/setup.md`.
6. Set up the Discord bot: `discord-bot/setup.md`.

## Before every deploy

1. Bump `VERSION` in `main-site/sw.js`. Without it, returning visitors keep
   the previous build and never see the update bar.
2. Run the checks:

```
node scripts/check-sw.mjs
node scripts/check-precache.mjs
node scripts/check-theme.mjs
```

## Checking the questions

The game stands or falls on its wrong answers. `node scripts/sample-questions.mjs 30`
prints questions from the vendored data using the API's own generator, with
the right answer in brackets and a one-line reason, for checking against a
real MRT map. See `scripts/README.md`.

## Build status

Following the build order in `02-line-order.md`:

- [x] 0. Theme and the head template (`main-site/index.html`)
- [x] 1. Seed, schema and the adjacency computation
- [x] 2. Question generation, sampled and checked by eye, all five templates
      and all three difficulty tiers
- [x] 3. The endpoints
- [x] 4. Telegram bot
- [x] 5. PWA, Discord bot
