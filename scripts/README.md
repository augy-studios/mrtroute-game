# scripts

Run from the repo root. The Node scripts need Node 18 or later and no
dependencies; the seed needs Python 3.10 or later and no dependencies.

| Script | What it does |
|---|---|
| `seed_supabase.py` | Computes each line's order and adjacency from `main-site/data/stations.geojson` and loads it into `lineorder_line_stops` and `lineorder_links`. `--dry-run` prints every line, its ends and junctions; `--sql` writes the load as the next numbered migration; `--json` writes `main-site/data/network.json` for the PWA. |
| `sample-questions.mjs [count] [seed] [template] [level]` | Prints generated questions from the vendored data, using the API's own generator, for checking by eye. No Supabase needed. |
| `vendor-sgraildata.mjs <clone>` | Rebuilds `main-site/data/stations.geojson` from a local sgraildata clone. |
| `check-sw.mjs` | Fails if `skipWaiting()` or `clients.claim()` appear outside the service worker's message handler, or other update bar rules break. |
| `check-precache.mjs` | Fails if a `PRECACHE` entry is missing on disk, or a module or data file is not precached. |
| `check-theme.mjs` | Fails if a page's pre-paint script drifts from the hours or key in `js/theme.js`. |

## How line order is worked out

Within a line, codes sort into order: NS1, NS2, NS3. A skipped number (NS6,
NE2, TE10, TE21, CC18) is a station that does not exist, and trains run
straight past, so consecutive codes are neighbours whatever the gap. What
sorting cannot see is listed in `EXTRA_LINKS`:

- The Changi Airport branch leaves the East-West Line at Tanah Merah.
- Circle Line stage 6 closes the loop, Bayfront back to Promenade.
- The Bukit Panjang LRT loop returns from Senja to Bukit Panjang.
- The Sengkang and Punggol LRT loops start and end at their hubs.

`--dry-run` ends with each line's ends and junctions, which should read:

```
NS: Ends: Jurong East, Marina South Pier. Junctions: none.
EW: Ends: Pasir Ris, Tuas Link, Changi Airport. Junctions: Tanah Merah (3).
CC: Ends: Dhoby Ghaut. Junctions: Promenade (3).
BP: Ends: Choa Chu Kang. Junctions: Bukit Panjang (3).
SK: Ends: none, it loops. Junctions: Sengkang (4).
PG: Ends: none, it loops. Junctions: Punggol (4).
```

If a new snapshot renumbers a code that `EXTRA_LINKS` names, the seed stops
rather than guess. Check the map, then update the list.

## Checking questions

```
node scripts/sample-questions.mjs 30          # a mix, easy, medium, hard in turn
node scripts/sample-questions.mjs 20 7 next 3 # 20 hard "comes next" questions
```

Each prints the prompt, the options with the right one in brackets, and the
reason shown to players after they answer. Run it after any change to
`main-site/api/_lib/questions.js` or the data.

## Seeding

The seed reads `SUPABASE_URL` and `SUPABASE_SERVICE_KEY` from the environment,
or from a `.env` in `scripts/` or the repo root (both gitignored):

```
python scripts/seed_supabase.py --dry-run
python scripts/seed_supabase.py
```

After refreshing `main-site/data/stations.geojson`, run it with `--json` too,
and bump `VERSION` in `main-site/sw.js`.
