// The rail network as the question generator sees it: stations, each line's
// stops in code order, and the links between them. Line order and links are
// computed once at seed time (scripts/seed_supabase.py); this only reads them.

import { rest } from "./supabase.js";
import { HttpError } from "./http.js";
import { lineName } from "./lines.js";

const TTL_MS = 60 * 60 * 1000;
let cache = null;

// Rows as Supabase returns them, or as scripts/sample-questions.mjs builds
// them from data/network.json. Pure, so the sample script can use it too.
export function buildNetwork(stationRows, stopRows, linkRows) {
  const stations = new Map(stationRows.map((s) => [s.id, { ...s, onLines: new Set() }]));
  const lines = new Map();

  const sorted = [...stopRows].sort((a, b) => a.line_code.localeCompare(b.line_code) || a.seq - b.seq);
  for (const row of sorted) {
    const station = stations.get(row.station_id);
    if (!station) throw new Error(`line stop ${row.line_code} ${row.code} has no station ${row.station_id}`);
    let line = lines.get(row.line_code);
    if (!line) {
      line = { code: row.line_code, name: lineName(row.line_code), stops: [], codeOf: new Map(), adj: new Map() };
      lines.set(row.line_code, line);
    }
    line.stops.push(station.id);
    line.codeOf.set(station.id, row.code);
    line.adj.set(station.id, new Set());
    station.onLines.add(row.line_code);
  }

  for (const { line_code, a_station, b_station } of linkRows) {
    const line = lines.get(line_code);
    if (!line?.adj.has(a_station) || !line.adj.has(b_station)) {
      throw new Error(`link ${line_code} ${a_station}-${b_station} is not between two of its stops`);
    }
    line.adj.get(a_station).add(b_station);
    line.adj.get(b_station).add(a_station);
  }

  for (const line of lines.values()) {
    line.dist = new Map(line.stops.map((id) => [id, hops(line, id)]));
    line.ends = line.stops.filter((id) => line.adj.get(id).size === 1);
    line.loop = cycleMembers(line);
  }

  return { stations, lines };
}

// Hop counts from one stop to every other on the same line.
function hops(line, from) {
  const dist = new Map([[from, 0]]);
  const queue = [from];
  while (queue.length) {
    const id = queue.shift();
    for (const next of line.adj.get(id)) {
      if (!dist.has(next)) {
        dist.set(next, dist.get(id) + 1);
        queue.push(next);
      }
    }
  }
  return dist;
}

// Stops that sit on a loop: what is left after trimming dead ends away.
function cycleMembers(line) {
  const degree = new Map(line.stops.map((id) => [id, line.adj.get(id).size]));
  const queue = line.stops.filter((id) => degree.get(id) <= 1);
  const gone = new Set(queue);
  while (queue.length) {
    const id = queue.shift();
    for (const next of line.adj.get(id)) {
      if (gone.has(next)) continue;
      degree.set(next, degree.get(next) - 1);
      if (degree.get(next) <= 1) {
        gone.add(next);
        queue.push(next);
      }
    }
  }
  return new Set(line.stops.filter((id) => !gone.has(id)));
}

// One shortest way along a line, both ends included.
export function pathAlong(line, from, to) {
  const path = [from];
  let at = from;
  while (at !== to) {
    const left = line.dist.get(at).get(to);
    at = [...line.adj.get(at)].find((n) => line.dist.get(n).get(to) === left - 1);
    path.push(at);
  }
  return path;
}

export async function loadNetwork() {
  if (cache && Date.now() - cache.at < TTL_MS) return cache.net;
  const [stations, stops, links] = await Promise.all([
    // The shared station table, from MRT Station Guesser. See migrations/README.md.
    rest("mrtguessr_stations?select=id,name_en,name_zh,codes,lat,lon"),
    rest("lineorder_line_stops?select=line_code,seq,station_id,code&order=line_code,seq"),
    rest("lineorder_links?select=line_code,a_station,b_station"),
  ]);
  if (!stops?.length || !links?.length) throw new HttpError(503, "no_network", "Line data is not loaded yet.");
  cache = { at: Date.now(), net: buildNetwork(stations, stops, links) };
  return cache.net;
}
