// The game API. Every rule lives on the server; this only carries requests.

const KEY_STORAGE = "mrtnav.clientKey";

export class ApiError extends Error {
  constructor(status, code, message, data = null) {
    super(message || code);
    this.status = status;
    this.code = code;
    this.data = data;
  }
}

// A random id tying this browser's requests to its own runs. Not an
// identity: it grants nothing and is never shown.
function makeKey() {
  const bytes = crypto.getRandomValues(new Uint8Array(24));
  return btoa(String.fromCharCode(...bytes)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

let memoryKey = null;

export function clientKey() {
  try {
    let key = localStorage.getItem(KEY_STORAGE);
    if (!/^[A-Za-z0-9_-]{16,64}$/.test(key ?? "")) {
      key = makeKey();
      localStorage.setItem(KEY_STORAGE, key);
    }
    return key;
  } catch {
    // Storage blocked: runs still work for this page view.
    memoryKey ??= makeKey();
    return memoryKey;
  }
}

async function call(method, path, body) {
  let response;
  try {
    response = await fetch(path, {
      method,
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError(0, "offline", "Questions need a connection.");
  }
  let data = null;
  try {
    data = await response.json();
  } catch {
    // An HTML error page from the platform, not the API.
  }
  if (!response.ok) {
    throw new ApiError(response.status, data?.error ?? "server", data?.message, data);
  }
  return data;
}

const withKey = (path, body) => call("POST", path, { client_key: clientKey(), ...body });

export const api = {
  newRun: () => withKey("/api/run/new", {}),
  runState: (runId) => withKey("/api/run/state", { run_id: runId }),
  question: (runId) => withKey("/api/question/new", { run_id: runId }),
  answer: (questionId, choice) => withKey("/api/question/answer", { question_id: questionId, choice }),
  checkName: (name) => call("POST", "/api/leaderboard/name", { name }),
  submit: (runId, name) => call("POST", "/api/leaderboard/submit", { run_id: runId, name }),
  leaderboard: (board) => call("GET", `/api/leaderboard?board=${encodeURIComponent(board)}`),
};
