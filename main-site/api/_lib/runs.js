// Runs and what a client may see of them. A run is one game: a fixed set of
// questions, scored together, submitted to the leaderboard once at the end.

import { HttpError } from "./http.js";
import { DIFFICULTY_NAMES, POINTS } from "./questions.js";
import { rest } from "./supabase.js";

export const QUESTION_COUNT = 10;
export const RUN_TTL_MS = 60 * 60 * 1000;

export const isExpired = (run, now = Date.now()) => now - Date.parse(run.created_at) > RUN_TTL_MS;

export async function loadRun(id, clientKey) {
  const rows = await rest(`lineorder_runs?id=eq.${id}&select=*`);
  const run = rows?.[0];
  // Someone else's run reads as no run at all.
  if (!run || run.client_key !== clientKey) throw new HttpError(404, "run_not_found", "That run does not exist.");
  return run;
}

export function runView(run) {
  return {
    run_id: run.id,
    question_count: run.question_count,
    answered: run.answered,
    correct: run.correct,
    score: run.score,
    finished: run.finished,
    submitted: run.submitted,
    // Past answering, and past adding to the leaderboard.
    expired: isExpired(run),
  };
}

// Never the answer: that is only returned once the question is answered.
export function questionView(q, run) {
  return {
    question_id: q.id,
    prompt: q.prompt,
    options: q.options,
    difficulty: q.difficulty,
    difficulty_name: DIFFICULTY_NAMES[q.difficulty],
    points: POINTS[q.difficulty],
    index: q.seq,
    total: run.question_count,
    run_score: run.score,
  };
}
