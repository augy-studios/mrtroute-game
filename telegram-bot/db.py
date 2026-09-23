"""Bot-local SQLite: the button registry, each chat's current run, a waiting
name prompt, and the name each player last used on the leaderboard.

No game state lives here. Questions, answers and scores are the API's; losing
this file costs old buttons and remembered names, never a score.
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
-- The run a chat is playing. A button from any other run is refused, so a
-- card left over from before /play cannot move the old run on.
create table if not exists live_runs (
    chat_id integer primary key,
    user_id integer not null,
    run_id text not null
);
-- A typed message the bot is waiting for: a leaderboard name for run_id.
create table if not exists prompts (
    chat_id integer primary key,
    run_id text not null,
    expires_at real not null
);
create table if not exists players (
    user_id integer primary key,
    name text
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
    prune(conn)
    return conn


def prune(conn) -> None:
    conn.execute("delete from buttons where created_at < ?", (time.time() - BUTTON_TTL_S,))
    conn.execute("delete from shown where created_at < ?", (time.time() - BUTTON_TTL_S,))
    conn.execute("delete from prompts where expires_at < ?", (time.time(),))


def remember_question(conn, view: dict) -> None:
    conn.execute(
        "insert or replace into shown (question_id, view, created_at) values (?, ?, ?)",
        (view["question_id"], json.dumps(view), time.time()),
    )


def shown_question(conn, question_id: str) -> dict | None:
    row = conn.execute("select view from shown where question_id = ?", (question_id,)).fetchone()
    return json.loads(row["view"]) if row else None


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


# The run each chat is playing.


def set_live(conn, chat_id: int, user_id: int, run_id: str) -> None:
    conn.execute(
        "insert or replace into live_runs (chat_id, user_id, run_id) values (?, ?, ?)",
        (chat_id, user_id, run_id),
    )


def get_live(conn, chat_id: int):
    return conn.execute("select * from live_runs where chat_id = ?", (chat_id,)).fetchone()


def clear_live(conn, chat_id: int) -> None:
    conn.execute("delete from live_runs where chat_id = ?", (chat_id,))


# Prompts: the next plain message is a name, not chatter.

PROMPT_TTL_S = 10 * 60


def set_prompt(conn, chat_id: int, run_id: str) -> None:
    conn.execute(
        "insert or replace into prompts (chat_id, run_id, expires_at) values (?, ?, ?)",
        (chat_id, run_id, time.time() + PROMPT_TTL_S),
    )


def get_prompt(conn, chat_id: int) -> str | None:
    """The run a name is awaited for, or None. Left in place until cleared,
    so a refused name can be tried again."""
    row = conn.execute("select run_id, expires_at from prompts where chat_id = ?", (chat_id,)).fetchone()
    if not row or row["expires_at"] < time.time():
        clear_prompt(conn, chat_id)
        return None
    return row["run_id"]


def clear_prompt(conn, chat_id: int) -> None:
    conn.execute("delete from prompts where chat_id = ?", (chat_id,))


# The leaderboard name a player last used.


def saved_name(conn, user_id: int) -> str | None:
    row = conn.execute("select name from players where user_id = ?", (user_id,)).fetchone()
    return row["name"] if row else None


def save_name(conn, user_id: int, name: str | None) -> None:
    conn.execute("insert or replace into players (user_id, name) values (?, ?)", (user_id, name))
