// POST /api/question/answer  { question_id, client_key, choice }
//   -> { correct, answer_index, points, run_score, finished, answered, total, explain }
// `choice` is the index of the option picked, 0 to 3. It is checked against
// the stored answer here; answer_index is only ever sent back after that.

import { clientKey, endpoint, HttpError, uuid } from "../_lib/http.js";
import { rpc } from "../_lib/supabase.js";

const REFUSALS = {
  not_found: [404, "question_not_found", "That question does not exist."],
  already_answered: [409, "already_answered", "That question is already answered."],
  run_finished: [409, "run_finished", "This run is over."],
  run_expired: [410, "run_expired", "This run has expired. Start a new one."],
};

export default endpoint("POST", async ({ bot, body }) => {
  const id = uuid(body.question_id, "bad_question_id");
  const key = clientKey(body.client_key, bot);
  const choice = body.choice;
  if (!Number.isInteger(choice) || choice < 0 || choice > 3) throw new HttpError(400, "bad_choice");

  const [row] = (await rpc("lineorder_answer", { p_question_id: id, p_client_key: key, p_choice: choice })) ?? [];
  if (row?.status !== "ok") {
    const [status, code, message] = REFUSALS[row?.status] ?? [500, "server", "Could not record that answer."];
    // A second tap on an answered question gets the result it would have had.
    const extra = row?.status === "already_answered"
      ? { correct: row.correct, answer_index: row.answer_index, run_score: row.run_score, finished: row.finished }
      : undefined;
    throw new HttpError(status, code, message, extra);
  }

  return {
    correct: row.correct,
    answer_index: row.answer_index,
    points: row.points,
    run_score: row.run_score,
    finished: row.finished,
    answered: row.answered,
    total: row.question_count,
    explain: row.explain,
  };
});
