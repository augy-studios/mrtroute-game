#!/usr/bin/env node
// Prints generated questions from the vendored data, with no Supabase, using
// the API's own generator. For checking questions by eye against a real MRT
// map, which is the step the whole game rests on.
//
// Run: node scripts/sample-questions.mjs [count] [seed] [template] [difficulty]
//   node scripts/sample-questions.mjs 30
//   node scripts/sample-questions.mjs 20 7 next 3

import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { buildNetwork } from "../main-site/api/_lib/network.js";
import { DIFFICULTY_NAMES, generate, TEMPLATES } from "../main-site/api/_lib/questions.js";

const DATA = join(dirname(fileURLToPath(import.meta.url)), "..", "main-site", "data");
const [count = "20", seed = "1", only, level] = process.argv.slice(2);
if (only && !TEMPLATES.includes(only)) {
  console.error(`template is one of: ${TEMPLATES.join(", ")}`);
  process.exit(1);
}

// Stations as mrtguessr_stations holds them: one row per English name, with
// the same whitespace cleaning its seed applies.
const clean = (s) => String(s ?? "").replace(/\s+/g, " ").trim();
const byName = new Map();
for (const f of JSON.parse(readFileSync(join(DATA, "stations.geojson"), "utf8")).features) {
  const name = clean(f.properties.name);
  const row = byName.get(name) ?? { name_en: name, name_zh: f.properties.name_zh, codes: [], lon: f.geometry.coordinates[0], lat: f.geometry.coordinates[1] };
  row.codes.push(...f.properties.codes);
  byName.set(name, row);
}
const stations = [...byName.values()].sort((a, b) => a.name_en.localeCompare(b.name_en)).map((s, i) => ({ id: i + 1, ...s }));
const idOf = new Map(stations.map((s) => [s.name_en, s.id]));

// Line stops and links as lineorder_line_stops and lineorder_links hold them.
const network = JSON.parse(readFileSync(join(DATA, "network.json"), "utf8"));
const stops = [];
const links = [];
for (const line of network.lines) {
  const ids = line.stations.map((s) => idOf.get(s.name));
  line.stations.forEach((s, i) => stops.push({ line_code: line.code, seq: i + 1, station_id: ids[i], code: s.code }));
  for (const [a, b] of line.links) links.push({ line_code: line.code, a_station: ids[a], b_station: ids[b] });
}

const net = buildNetwork(stations, stops, links);

// Small seeded generator, so a run can be repeated.
let state = Number(seed) >>> 0 || 1;
const rand = (n) => {
  state = (state * 1664525 + 1013904223) >>> 0;
  return Math.floor((state / 2 ** 32) * n);
};

const used = new Set();
let after = null;
for (let i = 0; i < Number(count); i++) {
  const difficulty = level ? Number(level) : (i % 3) + 1;
  let q;
  if (only) {
    do q = generate(net, { difficulty, rand, used });
    while (q.template !== only);
  } else {
    q = generate(net, { difficulty, rand, used, after });
  }
  used.add(q.subject);
  after = q.template;
  const options = q.options.map((o, j) => (j === q.answer_index ? `[${o}]` : o)).join(" | ");
  console.log(`${String(i + 1).padStart(2)}. ${DIFFICULTY_NAMES[difficulty].padEnd(6)} ${q.template}\n    ${q.prompt}\n    ${options}\n    ${q.explain}\n`);
}
