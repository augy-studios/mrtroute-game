// The line guide: every line's stations in order, from data/network.json.
// The service worker precaches that file, so this works with no connection.

import { escapeHtml, openModal } from "./ui.js";

const LINE_STORAGE = "mrtnav.guideLine";

let network = null;
let current = null;

const $ = (id) => document.getElementById(id);
const safeHex = (hex) => (/^#[0-9a-f]{6}$/i.test(hex ?? "") ? hex : "#748477");

async function loadNetwork() {
  if (network) return network;
  const response = await fetch("/data/network.json");
  if (!response.ok) throw new Error(`network.json ${response.status}`);
  network = await response.json();
  return network;
}

// Rows in code order. Where the next station in the list is not the next on
// the map, a branch or loop starts; say where it leaves from. Where a loop
// closes, say where it returns to.
function rows(line) {
  const linked = new Set(line.links.map(([a, b]) => `${a}-${b}`));
  const earlier = (i) => line.links.filter(([a, b]) => b === i && a < i - 1).map(([a]) => a);
  const out = [];
  line.stations.forEach((s, i) => {
    const back = earlier(i);
    if (i > 0 && !linked.has(`${i - 1}-${i}`)) {
      out.push(`<li class="stop-break">${back.length ? `From ${escapeHtml(line.stations[back[0]].name)}` : ""}</li>`);
    }
    out.push(
      `<li class="stop"><span class="stop-code">${escapeHtml(s.code)}</span>` +
        `<span class="stop-name">${escapeHtml(s.name)}</span>` +
        (s.zh ? `<span class="stop-zh" lang="zh-Hans">${escapeHtml(s.zh)}</span>` : "") +
        `</li>`
    );
    if (i > 0 && linked.has(`${i - 1}-${i}`) && back.length) {
      out.push(`<li class="stop-break">Then back to ${escapeHtml(line.stations[back[0]].name)}</li>`);
    }
  });
  return out.join("");
}

function show(code) {
  const line = network.lines.find((l) => l.code === code) ?? network.lines[0];
  current = line.code;
  try {
    localStorage.setItem(LINE_STORAGE, current);
  } catch {
    // Remembering the tab is a nicety.
  }
  document.querySelectorAll("#lineTabs [data-line]").forEach((el) => {
    const on = el.dataset.line === current;
    el.classList.toggle("active", on);
    el.setAttribute("aria-selected", String(on));
    el.tabIndex = on ? 0 : -1;
  });
  const body = $("lineBody");
  body.style.setProperty("--line", safeHex(line.color));
  body.innerHTML = `<h3 class="line-title">${escapeHtml(line.name)}</h3><ol class="stops">${rows(line)}</ol>`;
  body.scrollTop = 0;
}

function renderTabs() {
  $("lineTabs").innerHTML = network.lines
    .map(
      (l) =>
        `<button class="line-tab" type="button" role="tab" data-line="${escapeHtml(l.code)}" aria-selected="false" ` +
        `aria-label="${escapeHtml(l.name)}" style="--line:${safeHex(l.color)}"><span class="dot"></span>${escapeHtml(l.code)}</button>`
    )
    .join("");
  $("guideNote").textContent = `Stations in code order, from ${network.source}. Skipped numbers are stations not yet open.`;
}

export async function openGuide() {
  openModal("guideModal");
  if (network) return;
  $("lineBody").innerHTML = `<p class="board-empty">Loading the lines.</p>`;
  try {
    await loadNetwork();
  } catch {
    $("lineBody").innerHTML = `<p class="board-empty">The line guide did not load. Reload the page to try again.</p>`;
    return;
  }
  renderTabs();
  let saved = null;
  try {
    saved = localStorage.getItem(LINE_STORAGE);
  } catch {
    // The first line, then.
  }
  show(saved ?? network.lines[0].code);
}

export function initGuide() {
  $("guideBtn").addEventListener("click", openGuide);
  $("lineTabs").addEventListener("click", (e) => {
    const tab = e.target.closest("[data-line]");
    if (tab && tab.dataset.line !== current) show(tab.dataset.line);
  });
  // Arrow keys move between tabs, as a tab list should.
  $("lineTabs").addEventListener("keydown", (e) => {
    if (!network || (e.key !== "ArrowRight" && e.key !== "ArrowLeft")) return;
    const codes = network.lines.map((l) => l.code);
    const at = codes.indexOf(current);
    const next = codes[(at + (e.key === "ArrowRight" ? 1 : codes.length - 1)) % codes.length];
    show(next);
    document.querySelector(`#lineTabs [data-line="${next}"]`)?.focus();
    e.preventDefault();
  });
}
