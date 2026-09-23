// Question generation. Every question comes from the network; none is
// written by hand. Pure: the network, a random source and a difficulty in,
// a question out, so scripts/sample-questions.mjs runs this same code.
//
// Wrong answers matter more than the question. They come from the same line
// wherever that is possible, so a question tests the line rather than being
// solvable by elimination:
//   1 easy    wrong answers from other lines, or far away
//   2 medium  the same line, far from the answer
//   3 hard    right next to the answer
//
// A question is only kept if exactly one option is right. Each template
// checks that for its own shape before returning.

import { pathAlong } from "./network.js";

export const TEMPLATES = ["between", "next", "not_on", "stops", "which_line"];
export const DIFFICULTY_NAMES = { 1: "Easy", 2: "Medium", 3: "Hard" };
export const POINTS = { 1: 100, 2: 200, 3: 300 };

// The easy tier sticks to the six MRT lines; the LRT names are the hard part
// of knowing the network, not a warm-up.
const LRT = new Set(["BP", "SK", "PG"]);

const pick = (rand, list) => list[rand(list.length)];

function shuffle(rand, list) {
  const out = [...list];
  for (let i = out.length - 1; i > 0; i--) {
    const j = rand(i + 1);
    [out[i], out[j]] = [out[j], out[i]];
  }
  return out;
}

// Difficulty rises through a run: the first third easy, the last third hard.
export function difficultyFor(index, total) {
  const third = index / total;
  return third < 0.3 ? 1 : third < 0.7 ? 2 : 3;
}

function km(a, b) {
  const x = (b.lon - a.lon) * Math.cos((((a.lat + b.lat) / 2) * Math.PI) / 180);
  return Math.hypot(x, b.lat - a.lat) * 111.32;
}

function kmToLine(net, station, line) {
  let best = Infinity;
  for (const id of line.stops) best = Math.min(best, km(station, net.stations.get(id)));
  return best;
}

// A line chosen with a chance in proportion to its size, so the six MRT lines
// come up far more than a 13 stop LRT.
function pickLine(net, rand, difficulty) {
  const weighted = [];
  for (const line of net.lines.values()) {
    if (difficulty === 1 && LRT.has(line.code)) continue;
    weighted.push(...Array(line.stops.length).fill(line));
  }
  return pick(rand, weighted);
}

// Neighbours on every line, for "nothing else is between these two" checks
// and for hard distractors that sit one stop away on a crossing line.
function neighboursAnywhere(net, id) {
  const out = new Set();
  for (const code of net.stations.get(id).onLines) {
    for (const n of net.lines.get(code).adj.get(id)) out.add(n);
  }
  return out;
}

// Three wrong answers, trying each pool in turn: the pool that fits the
// difficulty first, easier pools only to fill a gap. null if even that fails.
function wrongAnswers(rand, pools, exclude, count = 3) {
  const chosen = [];
  const taken = new Set(exclude);
  for (const pool of pools) {
    for (const id of shuffle(rand, [...new Set(pool)])) {
      if (chosen.length === count) return chosen;
      if (taken.has(id)) continue;
      taken.add(id);
      chosen.push(id);
    }
  }
  return chosen.length === count ? chosen : null;
}

function offLine(net, line) {
  return [...net.stations.values()].filter((s) => !s.onLines.has(line.code)).map((s) => s.id);
}

function nameOf(net, id) {
  return net.stations.get(id).name_en;
}

function labelled(net, line, id) {
  return `${nameOf(net, id)} (${line.codeOf.get(id)})`;
}

// Options shuffled, with the right answer's place recorded.
function finish(rand, net, q, answerId, wrongIds) {
  const names = shuffle(rand, [answerId, ...wrongIds]).map((id) => nameOf(net, id));
  return { ...q, options: names, answer_index: names.indexOf(nameOf(net, answerId)) };
}

// "Which station is between Bishan and Toa Payoh on the North-South Line?"
function between(net, rand, difficulty) {
  const line = pickLine(net, rand, difficulty);
  const middle = pick(rand, line.stops.filter((id) => line.adj.get(id).size >= 2));
  let [a, c] = shuffle(rand, [...line.adj.get(middle)]).slice(0, 2);
  if (line.stops.indexOf(a) > line.stops.indexOf(c)) [a, c] = [c, a];

  // The answer must be the only station next to both, on any line.
  const both = [...neighboursAnywhere(net, a)].filter((id) => neighboursAnywhere(net, c).has(id));
  if (both.length !== 1 || both[0] !== middle) return null;

  const d = line.dist.get(middle);
  const sameFar = line.stops.filter((id) => d.get(id) >= 4);
  const sameMid = line.stops.filter((id) => d.get(id) === 3);
  const close = [
    ...line.stops.filter((id) => d.get(id) === 2),
    ...[a, middle, c].flatMap((id) => [...neighboursAnywhere(net, id)]),
  ];
  const other = offLine(net, line);
  const pools = { 1: [other], 2: [sameFar, sameMid, other], 3: [close, sameMid, sameFar] }[difficulty];

  const wrong = wrongAnswers(rand, pools, [a, middle, c]);
  if (!wrong) return null;
  return finish(rand, net, {
    template: "between",
    subject: `between:${middle}`,
    prompt: `Which station is between ${nameOf(net, a)} and ${nameOf(net, c)} on the ${line.name}?`,
    explain: `${labelled(net, line, middle)} sits between ${labelled(net, line, a)} and ${labelled(net, line, c)}.`,
  }, middle, wrong);
}

// "Which station comes immediately after Bishan, heading towards Marina South
// Pier on the North-South Line?" Off a loop, the direction is the line's end
// the train is heading for. On a loop, "towards" is a matter of opinion, so
// the question names the station the train just left instead.
function next(net, rand, difficulty) {
  const line = pickLine(net, rand, difficulty);
  const here = pick(rand, line.stops);
  const after = pick(rand, [...line.adj.get(here)]);
  const d = line.dist;

  let prompt;
  let behind = [];
  let from = null;
  let towards = null;
  if (!line.loop.has(here)) {
    // Ends the train could be heading for, where the only way there from
    // here goes through `after`, and that are not `after` itself.
    const ends = line.ends.filter((end) => {
      if (end === here || end === after) return false;
      const left = d.get(here).get(end);
      const ways = [...line.adj.get(here)].filter((n) => d.get(n).get(end) === left - 1);
      return ways.length === 1 && ways[0] === after;
    });
    if (!ends.length) return null;
    towards = pick(rand, ends);
    behind = [...line.adj.get(here)].filter((n) => n !== after);
    prompt = `Which station comes immediately after ${nameOf(net, here)}, heading towards ${nameOf(net, towards)} on the ${line.name}?`;
  } else {
    if (line.adj.get(here).size !== 2) return null;
    from = [...line.adj.get(here)].find((n) => n !== after);
    prompt = `On the ${line.name}, coming from ${nameOf(net, from)}, which station comes immediately after ${nameOf(net, here)}?`;
  }

  const fromAfter = d.get(after);
  const close = [
    ...behind,
    ...[...line.adj.get(after)].filter((n) => n !== here),
    ...[...neighboursAnywhere(net, here)].filter((n) => !line.adj.has(n)),
  ];
  const sameFar = line.stops.filter((id) => fromAfter.get(id) >= 3);
  const sameMid = line.stops.filter((id) => fromAfter.get(id) === 2);
  const other = offLine(net, line);
  const pools = { 1: [other], 2: [sameFar, sameMid, other], 3: [close, sameMid, sameFar] }[difficulty];

  const wrong = wrongAnswers(rand, pools, [here, after, from, towards].filter(Boolean));
  if (!wrong) return null;
  return finish(rand, net, {
    template: "next",
    subject: `next:${here}:${after}`,
    prompt,
    explain: `After ${labelled(net, line, here)} comes ${labelled(net, line, after)}${
      towards ? `, on the way to ${nameOf(net, towards)}` : ""
    }.`,
  }, after, wrong);
}

// "Which of these is NOT on the Downtown Line?" The right answer is the
// station off the line; the three wrong ones are on it.
function notOn(net, rand, difficulty) {
  const line = pickLine(net, rand, difficulty);
  const off = offLine(net, line)
    .map((id) => ({ id, away: kmToLine(net, net.stations.get(id), line) }))
    .sort((x, y) => x.away - y.away);

  // Easy: far from the line. Hard: one stop from it, or as near as can be.
  let pool;
  if (difficulty === 1) {
    pool = off.slice(Math.floor(off.length * 0.6));
  } else if (difficulty === 2) {
    pool = off;
  } else {
    const oneStop = new Set(line.stops.flatMap((id) => [...neighboursAnywhere(net, id)]));
    pool = off.filter((o) => oneStop.has(o.id));
    if (pool.length < 4) pool = off.slice(0, 12);
  }
  const answer = pick(rand, pool).id;

  // Hard: the on-line options are the ones nearest the answer, so they all
  // look like they belong to the same part of the map.
  const station = net.stations.get(answer);
  const onLine = difficulty === 3
    ? [...line.stops].sort((x, y) => km(station, net.stations.get(x)) - km(station, net.stations.get(y))).slice(0, 5)
    : line.stops;
  const wrong = wrongAnswers(rand, [onLine, line.stops], [answer]);
  if (!wrong) return null;

  const itsLines = [...station.onLines].map((code) => net.lines.get(code).name);
  return finish(rand, net, {
    template: "not_on",
    subject: `not_on:${line.code}:${answer}`,
    prompt: `Which of these is NOT on the ${line.name}?`,
    explain: `${station.name_en} is on the ${andList(itsLines)}, not the ${line.name}.`,
  }, answer, wrong);
}

// "How many stops from Jurong East to Buona Vista on the East-West Line?"
function stops(net, rand, difficulty) {
  const line = pickLine(net, rand, difficulty);
  const from = pick(rand, line.stops);
  const reach = line.stops.filter((id) => {
    const n = line.dist.get(from).get(id);
    return n >= 2 && n <= 10;
  });
  if (!reach.length) return null;
  const to = pick(rand, reach);
  const answer = line.dist.get(from).get(to);

  // Easy: well apart. Medium: two or three off. Hard: one or two off.
  const gaps = { 1: [3, 4, 5, 6, 7], 2: [2, 3], 3: [1, 2] }[difficulty];
  const wrong = [];
  for (const gap of shuffle(rand, gaps.flatMap((g) => [g, -g]))) {
    const n = answer + gap;
    if (n >= 1 && !wrong.includes(n) && wrong.length < 3) wrong.push(n);
  }
  // Very short trips run out of room below; fill from above.
  for (let n = answer + 1; wrong.length < 3; n++) if (!wrong.includes(n)) wrong.push(n);

  const options = [answer, ...wrong].sort((x, y) => x - y).map(String);
  const path = pathAlong(line, from, to).map((id) => nameOf(net, id));
  return {
    template: "stops",
    subject: `stops:${line.code}:${Math.min(from, to)}:${Math.max(from, to)}`,
    prompt: `How many stops from ${nameOf(net, from)} to ${nameOf(net, to)} on the ${line.name}?`,
    explain: `${path.join(", ")}: ${answer} stops.`,
    options,
    answer_index: options.indexOf(String(answer)),
  };
}

// "Which line does Bras Basah belong to?" Only stations on a single line, so
// there is one right answer.
function whichLine(net, rand, difficulty) {
  const singles = [...net.stations.values()].filter(
    (s) => s.onLines.size === 1 && !(difficulty === 1 && LRT.has([...s.onLines][0]))
  );
  const station = pick(rand, singles);
  const [code] = station.onLines;
  const line = net.lines.get(code);

  // Easy: lines nowhere near. Hard: the lines that pass closest.
  const others = [...net.lines.values()]
    .filter((l) => l.code !== code)
    .map((l) => ({ l, away: kmToLine(net, station, l) }))
    .sort((x, y) => x.away - y.away)
    .map((o) => o.l);
  const pool = { 1: others.slice(-5), 2: others, 3: others.slice(0, 3) }[difficulty];
  const wrong = shuffle(rand, pool).slice(0, 3);

  const options = shuffle(rand, [line, ...wrong]).map((l) => l.name);
  return {
    template: "which_line",
    subject: `which_line:${station.id}`,
    prompt: `Which line does ${station.name_en} belong to?`,
    explain: `${station.name_en} is ${line.codeOf.get(station.id)} on the ${line.name}.`,
    options,
    answer_index: options.indexOf(line.name),
  };
}

function andList(items) {
  return items.length <= 1 ? items.join("") : `${items.slice(0, -1).join(", ")} and ${items.at(-1)}`;
}

const BUILDERS = { between, next, not_on: notOn, stops, which_line: whichLine };

// One question. `used` holds the subjects already asked in this run, and
// `after` the previous template, so a run neither repeats itself nor asks the
// same kind of question twice in a row.
export function generate(net, { difficulty, rand, used = new Set(), after = null }) {
  const order = shuffle(rand, TEMPLATES.filter((t) => t !== after));
  if (after) order.push(after);
  for (const template of order) {
    for (let attempt = 0; attempt < 60; attempt++) {
      const q = BUILDERS[template](net, rand, difficulty);
      if (!q || used.has(q.subject)) continue;
      if (q.options.length !== 4 || new Set(q.options).size !== 4 || q.answer_index < 0) continue;
      return { ...q, difficulty };
    }
  }
  throw new Error("no question could be generated");
}
