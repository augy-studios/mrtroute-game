// POST /api/run/new  { client_key } -> { run_id, question_count }

import { randomInt } from "node:crypto";
import { clientKey, endpoint, rateLimit } from "../_lib/http.js";
import { QUESTION_COUNT } from "../_lib/runs.js";
import { rest, rpc } from "../_lib/supabase.js";

export default endpoint("POST", async ({ req, bot, body }) => {
  await rateLimit(req, bot, "run", 20);
  const key = clientKey(body.client_key, bot);

  const [run] = await rest("lineorder_runs", {
    method: "POST",
    body: { client_key: key, question_count: QUESTION_COUNT },
    prefer: "return=representation",
  });

  // Now and then, clear out old rate limit rows and abandoned runs.
  if (randomInt(50) === 0) await rpc("lineorder_prune", {}).catch((err) => console.warn("prune failed:", err.message));

  return { run_id: run.id, question_count: run.question_count };
});
