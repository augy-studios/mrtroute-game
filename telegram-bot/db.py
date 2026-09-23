"""Bot-local SQLite: the button registry, each chat's current run, the
question cards as sent, a waiting name prompt, and each player's settings.

No game state lives here. Questions, answers and scores are the API's; losing
this file costs old buttons and saved settings, never a score.
"""

from __future__ import annotations

import json
import secrets
import sqlite3
import time
from pathlib import Path

BUTTON_TTL_S = 14 * 24 * 3600

SCHEMA = """
create table if not exists buttons (
    id text primary key,
    kind text not null,
    payload text not null,
    created_at real not null
);
-- The run a chat is playing, and its card. A button from any other run is
-- refused, so a card left over from before /play cannot move the old run on.
create table if not exists live_runs (
    chat_id integer primary key,
    user_id integer not null,
    run_id text not null,
    msg_id integer
);
-- A typed message the bot is waiting for. kind is 'submit' (a name for
-- run_id) or 'setname' (a name for settings).
create table if not exists prompts (
    chat_id integer primary key,
    kind text not null default 'submit',
    run_id text,
    expires_at real not null
);
-- One row per Telegram user, created on first change. Missing means defaults.
create table if not exists settings (
    user_id integer primary key,
    name text,
    auto_submit integer not null default 0,
    tidy_chat integer not null default 1
);
-- Each question card as sent, so the card can be redrawn as answered after a
-- restart without asking the API what it said. Never holds the answer.
create table if not exists shown (
    question_id text primary key,
    view text not null,
    created_at real not null
);
"""


def connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("pragma journal_mode=wal")
    conn.executescript(SCHEMA)
    _upgrade(conn)
    prune(conn)
    return conn


def _upgrade(conn) -> None:
    """Files from before settings: names move into settings, live_runs gains
    the card's message id, and prompts, which only live ten minutes and used
    to require a run, is simply made again."""
    tables = {r["name"] for r in conn.execute("select name from sqlite_master where type = 'table'")}
    if "players" in tables:
        conn.execute("insert or ignore into settings (user_id, name) select user_id, name from players")
        conn.execute("drop table players")
    if "msg_id" not in {r["name"] for r in conn.execute("pragma table_info(live_runs)")}:
        conn.execute("alter table live_runs add column msg_id integer")
    if "kind" not in {r["name"] for r in conn.execute("pragma table_info(prompts)")}:
        conn.execute("drop table prompts")
        conn.executescript(SCHEMA)


def prune(conn) -> None:
    conn.execute("delete from buttons where created_at < ?", (time.time() - BUTTON_TTL_S,))
    conn.execute("delete from shown where created_at < ?", (time.time() - BUTTON_TTL_S,))
    conn.execute("delete from prompts where expires_at < ?", (time.time(),))


# Buttons. The callback data is an opaque id; what it means is a row here,
# so a button survives restarts and cannot be forged by editing its data.


def register_button(conn, kind: str, **payload) -> bytes:
    button_id = secrets.token_urlsafe(9)
    conn.execute(
        "insert into buttons (id, kind, payload, created_at) values (?, ?, ?, ?)",
        (button_id, kind, json.dumps(payload), time.time()),
    )
    return f"b:{button_id}".encode()


def read_button(conn, data: bytes) -> tuple[str, dict] | None:
    raw = data.decode("utf-8", "replace")
    if not raw.startswith("b:"):
        return None
    row = conn.execute("select kind, payload from buttons where id = ?", (raw[2:],)).fetchone()
    return (row["kind"], json.loads(row["payload"])) if row else None


# The run each chat is playing, and the message its current card is in.


def set_live(conn, chat_id: int, user_id: int, run_id: str, msg_id: int | None = None) -> None:
    conn.execute(
        "insert or replace into live_runs (chat_id, user_id, run_id, msg_id) values (?, ?, ?, ?)",
        (chat_id, user_id, run_id, msg_id),
    )


def set_live_card(conn, chat_id: int, msg_id: int | None) -> None:
    conn.execute("update live_runs set msg_id = ? where chat_id = ?", (msg_id, chat_id))


def get_live(conn, chat_id: int):
    return conn.execute("select * from live_runs where chat_id = ?", (chat_id,)).fetchone()


def clear_live(conn, chat_id: int) -> None:
    conn.execute("delete from live_runs where chat_id = ?", (chat_id,))


# Question cards.


def remember_question(conn, view: dict) -> None:
    conn.execute(
        "insert or replace into shown (question_id, view, created_at) values (?, ?, ?)",
        (view["question_id"], json.dumps(view), time.time()),
    )


def shown_question(conn, question_id: str) -> dict | None:
    row = conn.execute("select view from shown where question_id = ?", (question_id,)).fetchone()
    return json.loads(row["view"]) if row else None


# Prompts: the next plain message is a name, not chatter.

PROMPT_TTL_S = 10 * 60


def set_prompt(conn, chat_id: int, kind: str, run_id: str | None = None) -> None:
    conn.execute(
        "insert or replace into prompts (chat_id, kind, run_id, expires_at) values (?, ?, ?, ?)",
        (chat_id, kind, run_id, time.time() + PROMPT_TTL_S),
    )


def get_prompt(conn, chat_id: int):
    """The waiting prompt, or None. Left in place until the caller clears it,
    so a refused name can be tried again."""
    row = conn.execute("select kind, run_id, expires_at from prompts where chat_id = ?", (chat_id,)).fetchone()
    if not row or row["expires_at"] < time.time():
        clear_prompt(conn, chat_id)
        return None
    return row


def clear_prompt(conn, chat_id: int) -> None:
    conn.execute("delete from prompts where chat_id = ?", (chat_id,))


# Settings.

DEFAULTS = {"name": None, "auto_submit": False, "tidy_chat": True}
_BOOLEANS = ("auto_submit", "tidy_chat")


def get_settings(conn, user_id: int) -> dict:
    row = conn.execute("select * from settings where user_id = ?", (user_id,)).fetchone()
    if row is None:
        return dict(DEFAULTS)
    out = {key: row[key] for key in DEFAULTS}
    for key in _BOOLEANS:
        out[key] = bool(out[key])
    return out


def save_settings(conn, user_id: int, **changes) -> dict:
    unknown = set(changes) - set(DEFAULTS)
    if unknown:
        raise ValueError(f"unknown settings: {unknown}")
    current = get_settings(conn, user_id)
    current.update(changes)
    # No saved name is fine even with automatic adding on: the bot falls back
    # to the platform name, and skips adding when there is none usable.
    conn.execute(
        """insert into settings (user_id, name, auto_submit, tidy_chat)
           values (:user_id, :name, :auto_submit, :tidy_chat)
           on conflict (user_id) do update set name = excluded.name,
             auto_submit = excluded.auto_submit, tidy_chat = excluded.tidy_chat""",
        {"user_id": user_id, **{k: int(v) if k in _BOOLEANS else v for k, v in current.items()}},
    )
    return current
