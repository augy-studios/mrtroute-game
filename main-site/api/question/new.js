// POST /api/question/new  { run_id, client_key }
//   -> { question_id, prompt, options, difficulty, index, total, ... }
// The run's open question if it has one, otherwise the next. Asking again
// never replaces an unanswered question, so there is no rolling for an
// easier one. The answer stays in lineorder_questions.

import { randomInt } from "node:crypto";
import { clientKey, endpoint, HttpError, uuid } from "../_lib/http.js";
import { loadNetwork } from "../_lib/network.js";
import { difficultyFor, generate } from "../_lib/questions.js";
import { isExpired, loadRun, questionView } from "../_lib/runs.js";
import { rest, UpstreamError } from "../_lib/supabase.js";

const SHOWN = "id,seq,template,subject,prompt,options,difficulty,answered";

export default endpoint("POST", async ({ bot, body }) => {
  const id = uuid(body.run_id, "bad_run_id");
  const key = clientKey(body.client_key, bot);

  const run = await loadRun(id, key);
  if (run.finished) throw new HttpError(409, "run_finished", "This run is over.");
  if (isExpired(run)) throw new HttpError(410, "run_expired", "This run has expired. Start a new one.");

  const asked = (await rest(`lineorder_questions?run_id=eq.${id}&select=${SHOWN}&order=seq`)) ?? [];
  const open = asked.find((q) => !q.answered);
  if (open) return questionView(open, run);
  if (asked.length >= run.question_count) throw new HttpError(409, "run_finished", "This run is over.");

  const q = generate(await loadNetwork(), {
    difficulty: difficultyFor(asked.length, run.question_count),
    rand: (n) => randomInt(Math.max(1, n)),
    used: new Set(asked.map((a) => a.subject)),
    after: asked.at(-1)?.template ?? null,
  });

  try {
    const [row] = await rest("lineorder_questions", {
      method: "POST",
      body: {
        run_id: id,
        seq: asked.length + 1,
        template: q.template,
        subject: q.subject,
        prompt: q.prompt,
        options: q.options,
        answer_index: q.answer_index,
        difficulty: q.difficulty,
        explain: q.explain,
      },
      prefer: "return=representation",
    });
    return questionView(row, run);
  } catch (err) {
    // Two requests at once: the other one's question won. Return that.
    if (!(err instanceof UpstreamError) || !err.message.startsWith("supabase 409")) throw err;
    const [existing] = (await rest(`lineorder_questions?run_id=eq.${id}&answered=is.false&select=${SHOWN}`)) ?? [];
    if (!existing) throw err;
    return questionView(existing, run);
  }
});
