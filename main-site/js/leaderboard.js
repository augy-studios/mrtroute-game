// The leaderboard window: one row per name, its best run.

import { api } from "./api.js";
import { escapeHtml, openModal } from "./ui.js";

let loading = 0;

async function load() {
  const body = document.getElementById("boardBody");
  const ticket = ++loading;
  body.setAttribute("aria-busy", "true");

  try {
    const { entries = [] } = await api.leaderboard();
    if (ticket !== loading) return;
    body.innerHTML = entries.length
      ? `<table class="board-table">
          <thead><tr><th scope="col">#</th><th scope="col">Name</th><th scope="col">Score</th></tr></thead>
          <tbody>${entries
            .map((e) => `<tr><td>${e.rank}</td><td>${escapeHtml(e.name)}</td><td>${e.score}</td></tr>`)
            .join("")}</tbody>
        </table>`
      : `<p class="board-empty">No scores yet. Finish a run and add yours.</p>`;
  } catch (err) {
    if (ticket !== loading) return;
    body.innerHTML = `<p class="board-empty">${
      err.code === "offline" ? "The leaderboard needs a connection." : "The leaderboard did not load. Try again in a moment."
    }</p>`;
  } finally {
    if (ticket === loading) body.removeAttribute("aria-busy");
  }
}

export function openLeaderboard() {
  openModal("boardModal");
  load();
}

export function initLeaderboard() {
  document.getElementById("boardBtn").addEventListener("click", openLeaderboard);
}
