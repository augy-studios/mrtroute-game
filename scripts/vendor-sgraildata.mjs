#!/usr/bin/env node
// Builds main-site/data/stations.geojson from a local clone of
// cheeaun/sgraildata. Stations only: codes, names and coordinates. Exits,
// buildings and line geometry are left out; this game does not use them.
//
// Run: node scripts/vendor-sgraildata.mjs <path to sgraildata clone>
// Then: python scripts/seed_supabase.py --json, and --sql or a live seed.

import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const clone = process.argv[2];
if (!clone) {
  console.error("usage: node scripts/vendor-sgraildata.mjs <path to sgraildata clone>");
  process.exit(1);
}

const OUT = join(dirname(fileURLToPath(import.meta.url)), "..", "main-site", "data");

const round = (n) => Math.round(n * 1e6) / 1e6;
const source = JSON.parse(readFileSync(join(clone, "data", "v1", "sg-rail.geojson"), "utf8"));

const stations = source.features
  .filter((f) => f.properties.stop_type === "station")
  .map((f) => ({
    type: "Feature",
    properties: {
      name: f.properties.name,
      name_zh: f.properties["name_zh-Hans"] ?? "",
      name_ta: f.properties.name_ta ?? "",
      // Interchanges arrive as one feature with joined codes, "NS17-CC15".
      codes: f.properties.station_codes.split("-").filter(Boolean),
    },
    geometry: { type: "Point", coordinates: f.geometry.coordinates.map(round) },
  }))
  .sort((a, b) => a.properties.name.localeCompare(b.properties.name));

let commit = "unknown";
try {
  commit = execFileSync("git", ["-C", clone, "log", "-1", "--format=%H %cs"], { encoding: "utf8" }).trim();
} catch {
  // Not a git clone. The snapshot still builds; the README just cannot say which one.
}

mkdirSync(OUT, { recursive: true });
writeFileSync(join(OUT, "stations.geojson"), JSON.stringify({ type: "FeatureCollection", features: stations }));
console.log(`${stations.length} stations, from sgraildata ${commit}`);
