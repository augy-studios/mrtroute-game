"""Bot-local SQLite: the button registry, the run each player is playing in
each channel, the question cards as sent, and each player's settings.

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
-- One run per player per channel: a server channel can hold several
-- players' runs at once. A button from any other run is refused. hook_token
-- and hook_at are the token of the interaction that sent the card and when
-- it was issued; see card_hook in handlers.py.
create table if not exists live_runs (
    channel_id integer not null,
    user_id integer not null,
    run_id text not null,
    msg_id integer,
    hook_token text,
    hook_at real,
    primary key (channel_id, user_id)
);
-- One row per Discord user, created on first change. Missing means defaults.
create table if not exists settings (
    user_id integer primary key,
    name text,
    auto_submit integer not null default 0,
    tidy_chat integer not null default 1
);
-- Each question card as sent, so it can be redrawn as answered after a
-- restart. Never holds the answer.
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
    """Files from before settings: names move into settings, and live_runs
    gains the card's message id and the token that can edit it."""
    tables = {r["name"] for r in conn.execute("select name from sqlite_master where type = 'table'")}
    if "players" in tables:
        conn.execute("insert or ignore into settings (user_id, name) select user_id, name from players")
        conn.execute("drop table players")
    have = {r["name"] for r in conn.execute("pragma table_info(live_runs)")}
    for column, kind in (("msg_id", "integer"), ("hook_token", "text"), ("hook_at", "real")):
        if column not in have:
            conn.execute(f"alter table live_runs add column {column} {kind}")


def prune(conn) -> None:
    conn.execute("delete from buttons where created_at < ?", (time.time() - BUTTON_TTL_S,))
    conn.execute("delete from shown where created_at < ?", (time.time() - BUTTON_TTL_S,))


# Buttons. The custom id is opaque; what it means is a row here, so a button
# survives restarts and cannot be forged by editing its id.

CUSTOM_ID_PATTERN = r"b:(?P<id>[A-Za-z0-9_-]{8,32})"


def register_button(conn, kind: str, **payload) -> str:
    button_id = secrets.token_urlsafe(9)
    conn.execute(
        "insert into buttons (id, kind, payload, created_at) values (?, ?, ?, ?)",
        (button_id, kind, json.dumps(payload), time.time()),
    )
    return f"b:{button_id}"


def read_button(conn, button_id: str) -> tuple[str, dict] | None:
    row = conn.execute("select kind, payload from buttons where id = ?", (button_id,)).fetchone()
    return (row["kind"], json.loads(row["payload"])) if row else None


# The run each player is playing, per channel, and its current card. A card
# is (msg_id, hook_token, hook_at); the hook is None, None for a card the bot
# sent with its own token.

Card = tuple[int, "str | None", "float | None"]


def set_live(conn, channel_id: int, user_id: int, run_id: str) -> None:
    conn.execute(
        "insert or replace into live_runs (channel_id, user_id, run_id) values (?, ?, ?)",
        (channel_id, user_id, run_id),
    )


def set_live_card(conn, channel_id: int, user_id: int, card: Card) -> None:
    conn.execute(
        "update live_runs set msg_id = ?, hook_token = ?, hook_at = ? where channel_id = ? and user_id = ?",
        (*card, channel_id, user_id),
    )


def get_live(conn, channel_id: int, user_id: int):
    return conn.execute(
        "select * from live_runs where channel_id = ? and user_id = ?", (channel_id, user_id)
    ).fetchone()


def clear_live(conn, channel_id: int, user_id: int) -> None:
    conn.execute("delete from live_runs where channel_id = ? and user_id = ?", (channel_id, user_id))


# Question cards.


def remember_question(conn, view: dict) -> None:
    conn.execute(
        "insert or replace into shown (question_id, view, created_at) values (?, ?, ?)",
        (view["question_id"], json.dumps(view), time.time()),
    )


def shown_question(conn, question_id: str) -> dict | None:
    row = conn.execute("select view from shown where question_id = ?", (question_id,)).fetchone()
    return json.loads(row["view"]) if row else None


# Settings, the same three as the Telegram bot's.

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
    # to the Discord display name, and skips adding when there is none usable.
    conn.execute(
        """insert into settings (user_id, name, auto_submit, tidy_chat)
           values (:user_id, :name, :auto_submit, :tidy_chat)
           on conflict (user_id) do update set name = excluded.name,
             auto_submit = excluded.auto_submit, tidy_chat = excluded.tidy_chat""",
        {"user_id": user_id, **{k: int(v) if k in _BOOLEANS else v for k, v in current.items()}},
    )
    return current
