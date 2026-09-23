# main-site

What Vercel deploys, served at <https://mrtnav.uwuapps.org>. No build step:
these files are served as they are, and `api/` holds the serverless
functions.

| Path | What it is |
|---|---|
| `index.html` | The game page. Its `<head>` is the template every other page copies. |
| `404.html`, `404.css` | Not-found page. |
| `sw.js` | Service worker: offline shell, and the update bar's waiting worker. |
| `manifest.json` | PWA manifest. |
| `api/` | The game API, the only place questions are made and answers checked. See `api/README.md`. |
| `css/` | Theme system and app styles. |
| `js/` | ES modules. `app.js` is the entry point. |
| `data/` | Vendored sgraildata snapshot, and the line guide built from it. |
| `images/` | Manifest screenshots. |

**The game screen:** the page opens straight on a question. Four answers,
one tap; the right answer and the one picked are marked at once, with a line
saying why, and Next moves on. Keys 1 to 4 answer too. Ten questions make a
run, easy to hard. At the end the run can go on the leaderboard under a name,
which this browser remembers. A run left open survives a reload, keyed by a
random `client_key` in local storage.

**Line guide:** the route button lists every line's stations in order, with
where branches leave and loops return. It reads `data/network.json`, which is
precached, so it works with no connection.

**Offline:** the page, its scripts, the line data and the Jua font are
precached, so the site loads with no connection and says questions need one,
offering the line guide meanwhile. It carries on by itself when the
connection returns. Nothing under `/api/` is ever cached.

**Updates:** a new service worker installs and waits. The update bar at the
top of the page offers Reload or Not now, and nothing reloads until the reader
asks. See `update-bar-spec.md` at the repo root.

**Theme:** `uwuapps-theme.md`, with the time-based mode: light, dark, or
follow the clock (light 09:00 to 18:00), resolved before first paint.

Bump `VERSION` in `sw.js` on every change to anything in this directory.

## Environment variables (Vercel)

Documented in `.env.example`. `.vercelignore` keeps every env file out of
deployments, since anything in this directory would otherwise be served.

| Variable | Used for |
|---|---|
| `SUPABASE_URL` | The shared uwuapps project. Already set. |
| `SUPABASE_SERVICE_KEY` | Service role key. Server side only, never sent to a browser. Already set. |
| `BOT_API_TOKEN` | The bots' bearer token. New for this app. |

`LTA_ACCOUNT_KEY` exists on the project and is not used here.
