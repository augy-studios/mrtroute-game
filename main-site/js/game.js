// The game screen. The API holds every rule and every answer; this shows
// what it says and sends what the player taps.

import { api } from "./api.js";
import { openGuide } from "./guide.js";
import { openLeaderboard } from "./leaderboard.js";
import { escapeHtml, hydrateIcons } from "./ui.js";

const RUN_STORAGE = "mrtnav.run";
const NAME_STORAGE = "mrtnav.name";
const GONE = new Set(["run_not_found", "run_expired", "question_not_found"]);

const $ = (id) => document.getElementById(id);

let runId = null;
let question = null;
// The answer to the question on screen, once it has one.
let result = null;
// Per question: "right", "wrong", or "done" for one answered before a reload.
let progress = [];
let busy = false;

const store = {
  get: (key) => {
    try {
      return localStorage.getItem(key);
    } catch {
      return null;
    }
  },
  set: (key, value) => {
    try {
      localStorage.setItem(key, value);
    } catch {
      // Private mode: nothing to remember across reloads, nothing broken.
    }
  },
  remove: (key) => {
    try {
      localStorage.removeItem(key);
    } catch {
      // As above.
    }
  },
};

function showPanel(id) {
  for (const panel of ["play", "result", "notice"]) $(panel).classList.toggle("hidden", panel !== id);
}

function say(text, tone = "") {
  const el = $("feedback");
  el.textContent = text;
  el.className = `feedback${tone ? ` ${tone}` : ""}`;
}

function renderProgress(total, current) {
  progress.length = total;
  $("progress").innerHTML = Array.from({ length: total }, (_, i) => {
    const state = progress[i] ?? (i === current - 1 ? "now" : "");
    return `<li class="${state}"></li>`;
  }).join("");
}

// A question.

function renderQuestion(q) {
  question = q;
  result = null;
  $("qCount").textContent = `Question ${q.index} of ${q.total}`;
  $("qLevel").textContent = `${q.difficulty_name}, ${q.points} points`;
  $("qLevel").dataset.level = q.difficulty;
  $("score").textContent = q.run_score;
  renderProgress(q.total, q.index);
  $("prompt").textContent = q.prompt;
  $("options").innerHTML = q.options
    .map(
      (option, i) =>
        `<button type="button" class="option" data-choice="${i}">` +
        `<span class="key" aria-hidden="true">${i + 1}</span>` +
        `<span class="label">${escapeHtml(option)}</span>` +
        `<span class="mark"></span></button>`
    )
    .join("");
  say("");
  $("explain").textContent = "";
  $("nextBtn").classList.add("hidden");
  showPanel("play");
  $("prompt").focus({ preventScroll: true });
}

function showAnswer(choice, r) {
  result = r;
  $("options").querySelectorAll(".option").forEach((btn, i) => {
    btn.disabled = true;
    const right = i === r.answer_index;
    const picked = i === choice;
    btn.classList.toggle("right", right);
    btn.classList.toggle("wrong", picked && !right);
    btn.classList.toggle("dim", !right && !picked);
    const mark = btn.querySelector(".mark");
    if (right || picked) {
      mark.innerHTML =
        `<span data-icon="${right ? "check" : "cross"}"></span>` +
        `<span class="visually-hidden">${right ? ", the right answer" : ", your answer"}</span>`;
    }
  });
  hydrateIcons($("options"));

  const answer = question.options[r.answer_index];
  if (r.correct) say(`Correct. +${r.points ?? question.points} points.`, "right");
  else say(`Not quite. It was ${answer}.`, "miss");
  $("explain").textContent = r.explain ?? "";
  $("score").textContent = r.run_score;

  progress[question.index - 1] = r.correct ? "right" : "wrong";
  renderProgress(question.total, question.index);

  $("nextLabel").textContent = r.finished ? "See your score" : "Next question";
  $("nextBtn").classList.remove("hidden");
  $("nextBtn").focus({ preventScroll: true });
  $("nextBtn").scrollIntoView({ block: "nearest", behavior: "smooth" });
}

async function choose(choice) {
  if (busy || !question || result) return;
  busy = true;
  const buttons = $("options").querySelectorAll(".option");
  buttons.forEach((btn) => (btn.disabled = true));
  buttons[choice]?.classList.add("picked");
  try {
    showAnswer(choice, await api.answer(question.question_id, choice));
  } catch (err) {
    buttons[choice]?.classList.remove("picked");
    if (err.code === "already_answered" && err.data?.answer_index != null) {
      // A double tap, or a second tab: show the result the first one got.
      showAnswer(choice, err.data);
    } else if (GONE.has(err.code)) {
      runGone();
    } else if (err.code === "run_finished") {
      finishRun();
    } else {
      buttons.forEach((btn) => (btn.disabled = false));
      say(
        err.code === "offline"
          ? "No connection. Tap again once you are back online."
          : err.status === 429
            ? err.message
            : "The game server did not answer. Tap again in a moment.",
        "error"
      );
    }
  } finally {
    busy = false;
  }
}

async function loadQuestion() {
  busy = true;
  try {
    renderQuestion(await api.question(runId));
  } catch (err) {
    if (GONE.has(err.code)) runGone();
    else if (err.code === "run_finished") finishRun();
    else startFailed(err);
  } finally {
    busy = false;
  }
}

function onNext() {
  if (!result || busy) return;
  if (result.finished) finishRun();
  else loadQuestion();
}

// The end of a run.

async function finishRun() {
  let state;
  try {
    state = await api.runState(runId);
  } catch {
    // Offline at the last step: what this page already knows is enough.
    const correct = progress.filter((p) => p === "right").length;
    state = { score: result?.run_score ?? 0, correct, question_count: progress.length, submitted: false, expired: false };
  }
  showResult(state);
}

function showResult(state) {
  $("resultScore").textContent = `${state.score} points`;
  $("resultCorrect").textContent = `${state.correct} of ${state.question_count} right.`;
  const canSubmit = !state.submitted && !state.expired;
  $("submitForm").classList.toggle("hidden", !canSubmit);
  $("submitted").classList.add("hidden");
  $("submitMsg").textContent = state.expired && !state.submitted ? "This run is too old to add to the leaderboard." : "";
  $("nameInput").value = store.get(NAME_STORAGE) ?? "";
  $("submitBtn").disabled = false;
  showPanel("result");
  say("");
  $("resultTitle").focus({ preventScroll: true });
}

async function onSubmit(event) {
  event.preventDefault();
  const name = $("nameInput").value.trim();
  const msg = $("submitMsg");
  if (!name) {
    msg.textContent = "Enter a name.";
    $("nameInput").focus();
    return;
  }
  $("submitBtn").disabled = true;
  msg.textContent = "";
  try {
    const r = await api.submit(runId, name);
    store.set(NAME_STORAGE, r.name);
    $("submittedText").textContent = `Added as ${r.name}. Best score ${r.best_score}, ranked ${r.rank}.`;
    $("submitForm").classList.add("hidden");
    $("submitted").classList.remove("hidden");
  } catch (err) {
    msg.textContent =
      err.code === "offline"
        ? "No connection. Try again once you are back online."
        : err.message || "That did not go through. Try again in a moment.";
    if (err.code === "already_submitted" || err.code === "expired") $("submitForm").classList.add("hidden");
    else $("submitBtn").disabled = false;
  }
}

// Starting and resuming.

function showNotice(text, iconName, { retry = null, guide = false } = {}) {
  $("notice").dataset.kind = iconName;
  $("noticeIcon").setAttribute("data-icon", iconName);
  hydrateIcons($("notice"));
  $("noticeText").textContent = text;
  $("noticeBtn").classList.toggle("hidden", !retry);
  if (retry) $("noticeBtnLabel").textContent = retry;
  $("noticeGuideBtn").classList.toggle("hidden", !guide);
  showPanel("notice");
}

function runGone() {
  store.remove(RUN_STORAGE);
  runId = null;
  showNotice("That run is over.", "flag", { retry: "New run" });
}

function startFailed(err) {
  if (err.code === "offline") {
    showNotice(
      "You are offline. Questions need a connection, and the game carries on once you are back. The line guide works offline.",
      "offline",
      { retry: "Try again", guide: true }
    );
  } else {
    showNotice(err.status === 429 ? err.message : "The game server did not answer. Try again in a moment.", "train", {
      retry: "Try again",
    });
  }
}

async function newRun() {
  store.remove(RUN_STORAGE);
  runId = null;
  progress = [];
  $("playAgainBtn").disabled = true;
  try {
    const run = await api.newRun();
    runId = run.run_id;
    store.set(RUN_STORAGE, runId);
    progress = new Array(run.question_count);
  } catch (err) {
    startFailed(err);
    return;
  } finally {
    $("playAgainBtn").disabled = false;
  }
  await loadQuestion();
}

// A run left open in this browser carries on after a reload, and a finished
// one can still be added to the leaderboard.
async function resumeOrStart() {
  const saved = store.get(RUN_STORAGE);
  if (saved) {
    try {
      const state = await api.runState(saved);
      if (!state.expired && !state.submitted) {
        runId = saved;
        progress = Array.from({ length: state.question_count }, (_, i) => (i < state.answered ? "done" : undefined));
        if (state.finished) showResult(state);
        else await loadQuestion();
        return;
      }
    } catch (err) {
      if (err.code === "offline") return startFailed(err);
    }
    store.remove(RUN_STORAGE);
  }
  await newRun();
}

let starting = false;

async function start() {
  if (starting) return;
  starting = true;
  $("noticeBtn").disabled = true;
  try {
    // A run already going only needs its question again.
    if (runId) await loadQuestion();
    else await resumeOrStart();
  } finally {
    starting = false;
    $("noticeBtn").disabled = false;
  }
}

export function initGame() {
  $("options").addEventListener("click", (e) => {
    const btn = e.target.closest("[data-choice]");
    if (btn) choose(Number(btn.dataset.choice));
  });
  $("nextBtn").addEventListener("click", onNext);
  $("submitForm").addEventListener("submit", onSubmit);
  $("playAgainBtn").addEventListener("click", async () => {
    showNotice("Getting your first question.", "train");
    await newRun();
  });
  $("resultBoardBtn").addEventListener("click", () => openLeaderboard());
  $("noticeBtn").addEventListener("click", start);
  $("noticeGuideBtn").addEventListener("click", () => openGuide());

  // 1 to 4 answer from the keyboard, when nothing else wants the keys.
  document.addEventListener("keydown", (e) => {
    if (e.altKey || e.ctrlKey || e.metaKey || document.body.classList.contains("modal-open")) return;
    if (e.target.closest?.("input, textarea")) return;
    const n = Number(e.key);
    if (n >= 1 && n <= 4 && !$("play").classList.contains("hidden")) choose(n - 1);
  });

  window.addEventListener("online", () => {
    if (!$("notice").classList.contains("hidden") && $("notice").dataset.kind === "offline") start();
  });

  start();
}
