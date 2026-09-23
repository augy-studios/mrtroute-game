// Player settings, the ones the bots' /settings hold that make sense in a
// browser, kept in this browser. The bots' "remove old cards" has no page to
// tidy here.

import { api } from "./api.js";
import { openModal } from "./ui.js";

const STORAGE = "mrtnav.settings";
// Where the name lived before there were settings.
const OLD_NAME = "mrtnav.name";

const DEFAULTS = { name: null, auto_submit: false };

let current = null;

function load() {
  let saved = {};
  try {
    saved = JSON.parse(localStorage.getItem(STORAGE) ?? "{}") ?? {};
    if (!saved.name && localStorage.getItem(OLD_NAME)) saved.name = localStorage.getItem(OLD_NAME);
  } catch {
    // Unreadable or blocked storage: the defaults.
  }
  const out = { ...DEFAULTS };
  if (typeof saved.name === "string" && saved.name.trim()) out.name = saved.name.trim();
  // Adding runs automatically needs a name to add them under.
  out.auto_submit = saved.auto_submit === true && Boolean(out.name);
  return out;
}

export function getSettings() {
  current ??= load();
  return { ...current };
}

export function saveSettings(changes) {
  current = { ...getSettings(), ...changes };
  if (!current.name) current.auto_submit = false;
  try {
    localStorage.setItem(STORAGE, JSON.stringify(current));
    localStorage.removeItem(OLD_NAME);
  } catch {
    // Kept for this page view only.
  }
  render();
  return getSettings();
}

const $ = (id) => document.getElementById(id);

function render() {
  const s = getSettings();
  $("clearNameBtn").classList.toggle("hidden", !s.name);
  $("savedName").textContent = `Now: ${s.name ?? "Not set"}`;

  document.querySelectorAll("#settingsModal [data-setting]").forEach((el) => {
    const on = s[el.dataset.setting];
    el.setAttribute("aria-checked", String(on));
    el.querySelector(".switch-state").textContent = on ? "On" : "Off";
  });
  document.querySelector('[data-setting="auto_submit"]').disabled = !s.name;
  $("autoNote").classList.toggle("hidden", Boolean(s.name));
}

async function onSaveName(event) {
  event.preventDefault();
  const input = $("settingsName");
  const msg = $("nameMsg");
  const name = input.value.trim();
  if (!name) {
    msg.textContent = "Enter a name.";
    input.focus();
    return;
  }
  $("saveNameBtn").disabled = true;
  msg.textContent = "";
  try {
    // The API cleans and checks it, the same check a submission gets.
    const result = await api.checkName(name);
    saveSettings({ name: result.name });
    input.value = "";
    msg.textContent = "Saved.";
  } catch (err) {
    msg.textContent =
      err.code === "offline"
        ? "Checking a name needs a connection."
        : err.message || "That did not go through. Try again in a moment.";
  } finally {
    $("saveNameBtn").disabled = false;
  }
}

export function openSettings() {
  $("nameMsg").textContent = "";
  $("settingsName").value = "";
  render();
  openModal("settingsModal");
}

export function initSettings() {
  $("settingsBtn").addEventListener("click", openSettings);
  $("nameForm").addEventListener("submit", onSaveName);
  $("clearNameBtn").addEventListener("click", () => {
    saveSettings({ name: null });
    $("nameMsg").textContent = "Name cleared.";
  });
  document.querySelectorAll("#settingsModal [data-setting]").forEach((el) => {
    el.addEventListener("click", () => saveSettings({ [el.dataset.setting]: !getSettings()[el.dataset.setting] }));
  });
}
