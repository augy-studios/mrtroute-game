// POST /api/leaderboard/submit  { run_id, name }
//   -> { name, rank, best_score, total, runs, total_rank }
// rank and best_score are the best-score board; total, runs and total_rank
// are the cumulative one. The score is read from the run, never taken from
// the request.

import { endpoint, HttpError, uuid } from "../_lib/http.js";
import { cleanName } from "../_lib/names.js";
import { rpc } from "../_lib/supabase.js";

const REFUSALS = {
  not_found: [404, "That run does not exist."],
  unfinished: [409, "Only a finished run can go on the leaderboard."],
  already_submitted: [409, "That run is already on the leaderboard."],
  expired: [410, "That run is more than an hour old."],
};

export default endpoint("POST", async ({ body }) => {
  const id = uuid(body.run_id, "bad_run_id");
  const name = cleanName(body.name);

  const [row] = (await rpc("lineorder_submit", { p_run_id: id, p_name: name })) ?? [];
  if (row?.status !== "ok") {
    const [status, message] = REFUSALS[row?.status] ?? [500, "Could not submit."];
    throw new HttpError(status, row?.status ?? "server", message);
  }

  return {
    name,
    rank: Number(row.rank),
    best_score: row.best_score,
    total: Number(row.total),
    runs: row.runs,
    total_rank: Number(row.total_rank),
  };
});
