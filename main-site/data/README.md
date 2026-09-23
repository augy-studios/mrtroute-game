# data

A snapshot of [cheeaun/sgraildata](https://github.com/cheeaun/sgraildata),
`data/v1/sg-rail.geojson`, at commit `d64f9408` (12 July 2026), the same one
MRT Station Guesser ships. Never fetched at runtime.

- `stations.geojson`: 184 stations. Properties `name`, `name_zh`
  (Simplified Chinese), `name_ta` and `codes`. An interchange is one feature
  with several codes. Built by `scripts/vendor-sgraildata.mjs`; do not edit
  by hand. The seed's source; the page never loads it.
- `network.json`: each line's stations in code order with their Chinese
  names, and every link between neighbours as a pair of indexes. Built by
  `python scripts/seed_supabase.py --json` from `stations.geojson`, with the
  same computation that loads Supabase. The PWA's offline line guide.

This snapshot includes Circle Line stage 6 (CC30 Keppel to CC34 Bayfront, the
old CE codes), which closes the Circle Line's loop at Promenade.

To refresh:

```
git clone --depth 1 https://github.com/cheeaun/sgraildata.git <somewhere>
node scripts/vendor-sgraildata.mjs <somewhere>/sgraildata
python scripts/seed_supabase.py --dry-run
python scripts/seed_supabase.py --json
python scripts/seed_supabase.py --sql
```

Check the dry run's ends and junctions against the map, run the new
migration, update the commit and date above and in `SNAPSHOT` in the seed,
and bump `VERSION` in `sw.js`. `mrtguessr_stations` must be refreshed from
the same snapshot, or the load refuses the station names it does not know.
