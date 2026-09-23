"""Message builders. Each returns (rich, buttons). `button(kind, label,
**payload)` is passed in, so the registry stays in one place.
"""

from __future__ import annotations

import unicodedata

from telethon import Button

import reply as r
from commands import COMMANDS

NAME_LENGTH = 20


def clean_name(value: str | None) -> str | None:
    """A Telegram first name made fit for the leaderboard, following
    main-site/api/_lib/names.js: emoji and other symbols dropped, whitespace
    collapsed, cut to 20 characters. None when nothing usable is left. The
    API still has the last word, profanity included."""
    name = unicodedata.normalize("NFKC", value or "")
    name = "".join(c for c in name if c in " _-" or c.isspace() or unicodedata.category(c)[0] in "LNM")
    name = " ".join(name.split())[:NAME_LENGTH].strip()
    return name if any(unicodedata.category(c)[0] in "LN" for c in name) else None


def question_head(q: dict, score: int) -> list[dict]:
    level = f"{q['difficulty_name']}, {q['points']} points"
    return [
        r.heading(f"Question {q['index']} of {q['total']}", 2),
        r.para(f"{r.escape_md(level)} · Score **{score}**", f"{level} · Score {score}"),
        r.para(f"**{r.escape_md(q['prompt'])}**", q["prompt"]),
    ]


def question_card(q: dict, button, user_id: int, run_id: str):
    """One button per answer. A tap is the whole move."""
    rich = r.join(question_head(q, q["run_score"]))
    buttons = [
        [button("answer", option, run_id=run_id, question_id=q["question_id"], choice=i, user_id=user_id)]
        for i, option in enumerate(q["options"])
    ]
    return rich, buttons


def answered_card(q: dict, result: dict, choice: int):
    """The same card once answered: which was right, which was picked. No
    buttons, so it cannot be answered twice."""
    marks = []
    for i, option in enumerate(q["options"]):
        if i == result["answer_index"]:
            marks.append(r.para(f"**{r.escape_md(option)}**, the right answer", f"{option}, the right answer"))
        elif i == choice:
            marks.append(r.para(f"{r.escape_md(option)}, your answer", f"{option}, your answer"))
        else:
            marks.append(r.text(option))
    if result["correct"]:
        verdict = r.para(f"Correct. **+{result.get('points', q['points'])}** points.", f"Correct. +{result.get('points', q['points'])} points.")
    else:
        right = q["options"][result["answer_index"]]
        verdict = r.para(f"Not quite. It was **{r.escape_md(right)}**.", f"Not quite. It was {right}.")
    parts = question_head(q, result["run_score"]) + [r.bullets(marks), verdict]
    if result.get("explain"):
        parts.append(r.para(f"*{r.escape_md(result['explain'])}*", result["explain"]))
    return r.join(parts), None


def submitted_line(result: dict) -> dict:
    name = result["name"]
    return r.para(
        f"Added as **{r.escape_md(name)}**. Best score **{result['best_score']}**, ranked **{result['rank']}**.",
        f"Added as {name}. Best score {result['best_score']}, ranked {result['rank']}.",
    )


def result_card(state: dict, button, user_id: int, run_id: str, name: str | None,
                submitted: dict | None = None, note: str | None = None):
    """The end of a run: the score, then one tap to add it under the name the
    player used last (or their Telegram name), or another name."""
    right = f"{state['correct']} of {state['question_count']} right"
    rich = r.join(
        [
            r.heading("Run complete"),
            r.para(f"**{state['score']}** points · {right}", f"{state['score']} points · {right}"),
            submitted_line(submitted) if submitted else None,
            r.para(f"*{r.escape_md(note)}*", note) if note else None,
        ]
    )
    play = button("play", "Play again", user_id=user_id)
    board = button("leaderboard", "Leaderboard", user_id=user_id)
    if submitted or state.get("submitted") or state.get("expired"):
        buttons = [[play, board]]
    elif name:
        buttons = [
            [
                button("submit", f"Add as {name}", run_id=run_id, user_id=user_id, name=name),
                button("submit", "Another name", run_id=run_id, user_id=user_id),
            ],
            [play, board],
        ]
    else:
        buttons = [[button("submit", "Add to leaderboard", run_id=run_id, user_id=user_id)], [play, board]]
    return rich, buttons


def leaderboard_card(entries: list[dict], button, user_id: int, limit: int = 10):
    parts = [r.heading("Leaderboard")]
    if entries:
        parts.append(r.table(["#", "Name", "Score"], [[e["rank"], e["name"], e["score"]] for e in entries[:limit]]))
        parts.append(r.text("Each name's best run. Anyone who picks the same name shares its entry."))
    else:
        parts.append(r.text("No scores yet. Finish a run and add yours."))
    return r.join(parts), [[button("play", "Play", user_id=user_id)]]


def start_card(button, user_id: int, site_url: str, donation_url: str | None):
    """Everything a help command would say. There is no help command."""
    rich = r.join(
        [
            r.heading("How well do you know the MRT lines?"),
            r.text("A quiz on the order of Singapore's MRT and LRT stations, played in this chat. No sign up."),
            r.heading("How to play", 2),
            r.numbered(
                [
                    r.text("Send /play, or press Play below. A run is ten questions."),
                    r.text("Each question has four answers. Tap one. That is the whole game."),
                    r.text(
                        "The card shows the right answer straight away, and the next question follows. "
                        "Questions get harder as the run goes on."
                    ),
                    r.text("At the end, add your score to the leaderboard in one tap, or play again."),
                ]
            ),
            r.heading("The questions", 2),
            r.bullets(
                [
                    r.text("Which station is between two others"),
                    r.text("Which station comes next, heading one way along a line"),
                    r.text("Which of four stations is not on a line"),
                    r.text("How many stops from one station to another"),
                    r.text("Which line a station belongs to"),
                ]
            ),
            r.heading("Scoring", 2),
            r.table(
                ["Questions", "Level", "Points each"],
                [["1 to 3", "Easy", "100"], ["4 to 7", "Medium", "200"], ["8 to 10", "Hard", "300"]],
            ),
            r.text("A wrong answer scores nothing and costs nothing. The best possible run is 2000."),
            r.heading("Leaderboard", 2),
            r.text(
                "Add a finished run under your Telegram first name, or pick another name of up to 20 "
                "characters. Each run can go on once, within an hour of starting it. The board shows each "
                "name's best run. Names are not accounts: anyone who picks the same name shares its entry."
            ),
            r.heading("Commands", 2),
            r.table(["Command", "What it does"], [[f"/{name}", description] for name, description in COMMANDS]),
            r.heading("About", 2),
            r.text(
                "There is no account. Your runs are kept against your Telegram user id so the game can find "
                "them again, and runs that never reach the leaderboard are deleted after two days. The bot "
                "remembers the last leaderboard name you used. Only a name you choose to submit is ever shown. "
                "Works in private chats only."
            ),
            r.text(
                "The same game runs in the browser, with a line guide that works offline, and can be installed "
                "as an app from there. Both share one leaderboard."
            ),
        ]
    )
    buttons = [
        [button("play", "Play", user_id=user_id), button("leaderboard", "Leaderboard", user_id=user_id)],
        [Button.url("Play in the browser", site_url)],
    ]
    if donation_url:
        buttons.append([Button.url("Buy Augy a Coffee", donation_url)])
    return rich, buttons
