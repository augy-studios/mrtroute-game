"""Computes line order and adjacency from the vendored snapshot, and loads it.

Run from the repo root, after migrations/001_lineorder_schema.sql:

    SUPABASE_URL=... SUPABASE_SERVICE_KEY=... python scripts/seed_supabase.py
    python scripts/seed_supabase.py --dry-run
    python scripts/seed_supabase.py --sql
    python scripts/seed_supabase.py --json

Stations are not loaded here. The shared project already holds them in
mrtguessr_stations (MRT Station Guesser, same sgraildata snapshot), so this
app reads that table and only adds lineorder_line_stops and lineorder_links,
matched to it by English name.

--dry-run  prints every line in order, its ends and junctions, and loads nothing.
--sql      writes the same load as the next numbered file in migrations/,
           for pasting into the SQL editor. Never overwrites a migration.
--json     writes main-site/data/network.json, the PWA's offline line guide.

Standard library only. The load replaces both tables in one transaction, so
it is safe to run again after refreshing main-site/data/.
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATIONS = ROOT / "main-site" / "data" / "stations.geojson"
NETWORK_JSON = ROOT / "main-site" / "data" / "network.json"
MIGRATIONS = ROOT / "migrations"
STATIONS_TABLE = "mrtguessr_stations"
SNAPSHOT = "sgraildata d64f9408, 12 July 2026"

# Line code, name and colour. Names and colours must match LINES in
# main-site/api/_lib/lines.js.
LINES = {
    "NS": ("North-South Line", "#d42e12"),
    "EW": ("East-West Line", "#009645"),
    "NE": ("North East Line", "#9900aa"),
    "CC": ("Circle Line", "#fa9e0d"),
    "DT": ("Downtown Line", "#005ec4"),
    "TE": ("Thomson-East Coast Line", "#9d5b25"),
    "BP": ("Bukit Panjang LRT", "#748477"),
    "SK": ("Sengkang LRT", "#748477"),
    "PG": ("Punggol LRT", "#748477"),
}

# Station code prefix to line, in the order a line lists its stations: the
# trunk first, then its branch or loops. A bare prefix with no number (STC,
# PTC, and the CG that Tanah Merah also carries) marks a junction and is only
# used for ordering.
SEGMENTS = {
    "NS": ["NS"],
    "EW": ["EW", "CG"],
    "NE": ["NE"],
    "CC": ["CC", "CE"],
    "DT": ["DT"],
    "TE": ["TE"],
    "BP": ["BP"],
    "SK": ["STC", "SE", "SW"],
    "PG": ["PTC", "PE", "PW"],
}
PREFIX_TO_LINE = {prefix: line for line, prefixes in SEGMENTS.items() for prefix in prefixes}

# Within a segment, consecutive codes are consecutive stations; a skipped
# number (NS6, NE2, TE10, TE21, CC18) is a station that does not exist, and
# trains run straight through. These are the links sorting cannot see: where
# a branch leaves its trunk, and where a loop closes.
EXTRA_LINKS = [
    ("EW", "EW4", "CG1"),  # Tanah Merah to Expo, the Changi Airport branch
    ("CC", "CC34", "CC4"),  # Bayfront to Promenade, where stage 6 closes the loop
    ("BP", "BP13", "BP6"),  # Senja back to Bukit Panjang, the end of the loop
    ("SK", "STC", "SE1"),
    ("SK", "SE5", "STC"),
    ("SK", "STC", "SW1"),
    ("SK", "SW8", "STC"),
    ("PG", "PTC", "PE1"),
    ("PG", "PE7", "PTC"),
    ("PG", "PTC", "PW1"),
    ("PG", "PW7", "PTC"),
]

CODE = re.compile(r"^([A-Z]+)(\d*)([A-Z]?)$")


def clean(name: str) -> str:
    """The same cleaning MRT Station Guesser's seed applies, so names match."""
    return re.sub(r"\s+", " ", name or "").strip()


def load_stations() -> dict[str, dict]:
    """English name to {name_en, name_zh, codes}, interchanges merged."""
    features = json.loads(STATIONS.read_text(encoding="utf-8"))["features"]
    by_name: dict[str, dict] = {}
    for feature in features:
        p = feature.get("properties") or {}
        name = clean(p.get("name"))
        if not name:
            continue
        row = by_name.setdefault(name.casefold(), {"name_en": name, "name_zh": p.get("name_zh") or None, "codes": []})
        for code in p.get("codes") or []:
            code = (code or "").strip()
            if code and code not in row["codes"]:
                row["codes"].append(code)
        row["name_zh"] = row["name_zh"] or p.get("name_zh") or None
    return {k: v for k, v in by_name.items() if v["codes"]}


def build(stations: dict[str, dict]) -> dict[str, dict]:
    """Per line: the ordered stops and the links between them."""
    unknown: set[str] = set()
    code_to_name: dict[str, str] = {}
    # line -> station name -> (sort key, code)
    members: dict[str, dict[str, tuple]] = {line: {} for line in SEGMENTS}
    # (line, prefix) -> [(number, suffix, code, name)]
    numbered: dict[tuple[str, str], list] = {}

    for row in stations.values():
        for code in row["codes"]:
            m = CODE.match(code)
            line = PREFIX_TO_LINE.get(m.group(1)) if m else None
            if line is None:
                unknown.add(code)
                continue
            prefix, number, suffix = m.groups()
            code_to_name[code] = row["name_en"]
            rank = SEGMENTS[line].index(prefix)
            key = (rank, int(number) if number else 0, suffix)
            current = members[line].get(row["name_en"])
            if current is None or key < current[0]:
                members[line][row["name_en"]] = (key, code)
            if number:
                numbered.setdefault((line, prefix), []).append((int(number), suffix, code, row["name_en"]))

    if unknown:
        sys.exit(f"unknown station code prefixes, add them to SEGMENTS: {sorted(unknown)}")

    out: dict[str, dict] = {}
    for line in SEGMENTS:
        ordered = sorted(members[line].items(), key=lambda kv: kv[1][0])
        links: set[tuple[str, str]] = set()
        for (seg_line, _), items in numbered.items():
            if seg_line != line:
                continue
            items.sort()
            for a, b in zip(items, items[1:]):
                if a[3] != b[3]:
                    links.add(tuple(sorted((a[3], b[3]))))
        for extra_line, code_a, code_b in EXTRA_LINKS:
            if extra_line != line:
                continue
            if code_a not in code_to_name or code_b not in code_to_name:
                sys.exit(f"EXTRA_LINKS names {code_a}-{code_b}, which the snapshot no longer has. Check the map.")
            links.add(tuple(sorted((code_to_name[code_a], code_to_name[code_b]))))
        out[line] = {
            "stops": [{"name_en": name, "code": code} for name, (_, code) in ordered],
            "links": sorted(links),
        }
    return out


def check(network: dict[str, dict]) -> list[str]:
    """Every line must be one connected piece. Returns a summary per line."""
    report = []
    for line, data in network.items():
        names = [s["name_en"] for s in data["stops"]]
        adj: dict[str, set[str]] = {n: set() for n in names}
        for a, b in data["links"]:
            if a not in adj or b not in adj:
                sys.exit(f"{line}: link {a} - {b} leaves the line")
            adj[a].add(b)
            adj[b].add(a)
        seen, todo = set(), [names[0]]
        while todo:
            n = todo.pop()
            if n not in seen:
                seen.add(n)
                todo.extend(adj[n] - seen)
        if len(seen) != len(names):
            sys.exit(f"{line} is in pieces; unreachable: {sorted(set(names) - seen)}")
        ends = [n for n in names if len(adj[n]) == 1]
        junctions = [f"{n} ({len(adj[n])})" for n in names if len(adj[n]) >= 3]
        report.append(
            f"{line}: {len(names)} stations, {len(data['links'])} links. "
            f"Ends: {', '.join(ends) or 'none, it loops'}. Junctions: {', '.join(junctions) or 'none'}."
        )
    return report


def load_payload(network: dict[str, dict]) -> tuple[list, list]:
    stops = [
        {"line": line, "seq": seq, "name_en": s["name_en"], "code": s["code"]}
        for line, data in network.items()
        for seq, s in enumerate(data["stops"], 1)
    ]
    links = [{"line": line, "a": a, "b": b} for line, data in network.items() for a, b in data["links"]]
    return stops, links


def write_json(network: dict[str, dict], stations: dict[str, dict]) -> None:
    """The PWA's line guide: each line's stations in order, and every link as
    a pair of indexes into that list. Neighbours in the list are not always
    linked (Tuas Link, then Expo), so the links are the whole story."""
    lines = []
    for line, data in network.items():
        name, color = LINES[line]
        index = {s["name_en"]: i for i, s in enumerate(data["stops"])}
        links = sorted(sorted((index[a], index[b])) for a, b in data["links"])
        lines.append(
            {
                "code": line,
                "name": name,
                "color": color,
                "stations": [
                    {"code": s["code"], "name": s["name_en"], "zh": stations[s["name_en"].casefold()]["name_zh"]}
                    for s in data["stops"]
                ],
                "links": links,
            }
        )
    NETWORK_JSON.write_text(
        json.dumps({"source": SNAPSHOT, "lines": lines}, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
        newline="\n",
    )


def next_migration_path() -> Path:
    """The next free migration number. Files already there are never touched."""
    numbers = [int(p.name[:3]) for p in MIGRATIONS.glob("[0-9][0-9][0-9]_*.sql")]
    return MIGRATIONS / f"{max(numbers, default=0) + 1:03d}_lineorder_load_network.sql"


def sql_json(value) -> str:
    return "'" + json.dumps(value, ensure_ascii=False).replace("'", "''") + "'::jsonb"


def write_sql(stops: list, links: list, path: Path) -> None:
    path.write_text(
        "-- Line order and adjacency for lineorder_line_stops and lineorder_links.\n"
        "-- Generated by `python scripts/seed_supabase.py --sql` from\n"
        f"-- main-site/data/stations.geojson ({SNAPSHOT}). Do not edit; a later\n"
        "-- refresh is a new file. Replaces both tables in one call, and refuses\n"
        "-- if any station is missing from mrtguessr_stations.\n\n"
        f"select * from lineorder_load_network(\n  {sql_json(stops)},\n  {sql_json(links)}\n);\n",
        encoding="utf-8",
        newline="\n",
    )


def load_env_file(path: Path) -> None:
    """A .env beside this script or at the repo root, without overriding."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ.setdefault(key.strip(), value)


def request(method: str, path: str, body=None):
    url = f"{os.environ['SUPABASE_URL'].rstrip('/')}/rest/v1/{path}"
    key = os.environ["SUPABASE_SERVICE_KEY"]
    headers = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            text = res.read().decode("utf-8")
            return res.status, json.loads(text) if text else None
    except urllib.error.HTTPError as err:
        return err.code, err.read().decode("utf-8", "replace")


def main() -> int:
    # Chinese names, on a Windows console that defaults to cp1252.
    sys.stdout.reconfigure(encoding="utf-8")
    args = set(sys.argv[1:])
    stations = load_stations()
    network = build(stations)
    report = check(network)
    stops, links = load_payload(network)
    print(f"{len(stations)} stations, {len(stops)} line stops, {len(links)} links, from {STATIONS.relative_to(ROOT)}")

    if "--dry-run" in args:
        for line, data in network.items():
            print(f"\n{line} {LINES[line][0]}")
            print("  " + " | ".join(f"{s['code']} {s['name_en']}" for s in data["stops"]))
        print()
        print("\n".join(report))
        return 0

    print("\n".join(report))

    if "--json" in args:
        write_json(network, stations)
        print(f"wrote {NETWORK_JSON.relative_to(ROOT)}")
        return 0

    if "--sql" in args:
        path = next_migration_path()
        write_sql(stops, links, path)
        print(f"wrote {path.relative_to(ROOT)}")
        return 0

    load_env_file(Path(__file__).resolve().parent / ".env")
    load_env_file(ROOT / ".env")
    missing = [n for n in ("SUPABASE_URL", "SUPABASE_SERVICE_KEY") if not os.environ.get(n)]
    if missing:
        print(f"missing: {', '.join(missing)}", file=sys.stderr)
        return 2

    status, body = request("GET", f"{STATIONS_TABLE}?select=id&limit=1")
    if status != 200 or not body:
        print(
            f"{STATIONS_TABLE} is not reachable or empty ({status}). It belongs to MRT Station Guesser; "
            f"run that repo's migrations first.\n{body}",
            file=sys.stderr,
        )
        return 1

    status, body = request("POST", "rpc/lineorder_load_network", {"p_stops": stops, "p_links": links})
    if status != 200:
        print(f"load failed ({status}). Run migrations/001_lineorder_schema.sql first.\n{body}", file=sys.stderr)
        return 1
    print(f"done: {body}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
