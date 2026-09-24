// POST /api/run/state  { run_id, client_key }
//   -> { run_id, question_count, answered, correct, score, finished, submitted, expired }
// Where a run stands, so a client can pick it up again after a reload.

import { clientKey, endpoint, uuid } from "../_lib/http.js";
import { loadRun, runView } from "../_lib/runs.js";

export default endpoint("POST", async ({ bot, body }) => {
  const id = uuid(body.run_id, "bad_run_id");
  const key = clientKey(body.client_key, bot);
  return runView(await loadRun(id, key));
});
