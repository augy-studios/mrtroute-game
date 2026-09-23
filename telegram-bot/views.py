"""Message builders. Each returns (rich, buttons). `button(kind, label,
**payload)` is passed in, so the registry stays in one place.
"""

from __future__ import annotations

import unicodedata

from telethon import Button

import reply as r
from commands import COMMANDS

NAME_LENGTH = 20

ON_OFF = {True: "On", False: "Off"}


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


def answer_note(q: dict, result: dict, choice: int) -> dict:
    """How the last question went, in one line, for the top of the next card
    when old cards are removed rather than kept."""
    right = q["options"][result["answer_index"]]
    if result["correct"]:
        md = plain = f"Question {q['index']}: correct, +{result.get('points', q['points'])} points."
    else:
        picked = q["options"][choice]
        md = f"Question {q['index']}: you picked {r.escape_md(picked)}. It was **{r.escape_md(right)}**."
        plain = f"Question {q['index']}: you picked {picked}. It was {right}."
    if result.get("explain"):
        md += f" {r.escape_md(result['explain'])}"
        plain += f" {result['explain']}"
    return r.para(f"*{md}*", plain)


def question_card(q: dict, button, user_id: int, run_id: str, note: dict | None = None):
    """One button per answer. A tap is the whole move."""
    rich = r.join([note, *question_head(q, q["run_score"])])
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
    points = result.get("points", q["points"])
    if result["correct"]:
        verdict = r.para(f"Correct. **+{points}** points.", f"Correct. +{points} points.")
    else:
        right = q["options"][result["answer_index"]]
        verdict = r.para(f"Not quite. It was **{r.escape_md(right)}**.", f"Not quite. It was {right}.")
    parts = question_head(q, result["run_score"]) + [r.bullets(marks), verdict]
    if result.get("explain"):
        parts.append(r.para(f"*{r.escape_md(result['explain'])}*", result["explain"]))
    return r.join(parts), None


def submitted_line(result: dict) -> dict:
    """Where the name now stands on both boards."""
    name = result["name"]
    runs = result.get("runs") or 1
    plural = "run" if runs == 1 else "runs"
    md = [
        f"Added as **{r.escape_md(name)}**.",
        f"Best score **{result['best_score']}**, ranked **{result['rank']}**.",
    ]
    plain = [f"Added as {name}.", f"Best score {result['best_score']}, ranked {result['rank']}."]
    if result.get("total") is not None:
        md.append(f"Total **{result['total']}** over {runs} {plural}, ranked **{result['total_rank']}**.")
        plain.append(f"Total {result['total']} over {runs} {plural}, ranked {result['total_rank']}.")
    return r.para(" ".join(md), " ".join(plain))


def result_card(state: dict, button, user_id: int, run_id: str, name: str | None,
                submitted: dict | None = None, note: str | None = None, last: dict | None = None):
    """The end of a run, with three endings: already added (automatically),
    one tap under the saved name, or asked for a name. `last` is how the final
    question went, when its own card has been replaced by this one."""
    right = f"{state['correct']} of {state['question_count']} right"
    rich = r.join(
        [
            last,
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


def leaderboard_card(board: str, entries: list[dict], button, user_id: int, limit: int = 10):
    """Either board, with a button that swaps to the other in place."""
    if board == "total":
        parts = [r.heading("Leaderboard: total points")]
        table = r.table(
            ["#", "Name", "Total", "Runs"],
            [[e["rank"], e["name"], e["total"], e["runs"]] for e in entries[:limit]],
        )
        about = "Every run added to the leaderboard under a name, scores added up."
        switch = button("leaderboard", "Best scores", board="best", user_id=user_id)
    else:
        parts = [r.heading("Leaderboard: best score")]
        table = r.table(["#", "Name", "Score"], [[e["rank"], e["name"], e["score"]] for e in entries[:limit]])
        about = "Each name's single best run."
        switch = button("leaderboard", "Total points", board="total", user_id=user_id)

    if entries:
        parts.append(table)
        parts.append(r.text(f"{about} Anyone who picks the same name shares its entry."))
    else:
        parts.append(r.text("No scores yet. Finish a run and add yours."))
    return r.join(parts), [[switch, button("play", "Play", user_id=user_id)]]


def settings_card(settings: dict, button, user_id: int, note: str | None = None):
    name = settings["name"]
    default = settings.get("name_is_default", False)
    shown = f"{name} (your Telegram name)" if name and default else name or "Not set"
    rich = r.join(
        [
            r.para(f"*{r.escape_md(note)}*", note) if note else None,
            r.heading("Settings"),
            r.table(
                ["Setting", "Now"],
                [
                    ["Leaderboard name", shown],
                    ["Add finished runs automatically", ON_OFF[settings["auto_submit"]]],
                    ["Remove old cards", ON_OFF[settings["tidy_chat"]]],
                ],
            ),
            r.text(
                "Until you pick a leaderboard name, your Telegram first name is used. A name you set here or "
                "type when adding a run is remembered instead; clear it to go back to your Telegram name. "
                "With automatic adding on, every finished run goes on the leaderboard under it."
            ),
            r.text(
                "With old cards removed, a run stays as one card: each answer turns it into the next question, "
                "with how the last one went at the top. Off, every answered card stays in the chat."
            ),
        ]
    )

    def toggle(key: str, label: str):
        return [button("setting", f"{label}: {ON_OFF[settings[key]]}", key=key, user_id=user_id)]

    name_row = [button("setname", "Change name" if name else "Set name", user_id=user_id)]
    if name and not default:
        name_row.append(button("setting", "Use Telegram name", key="name", user_id=user_id))
    buttons = [
        name_row,
        toggle("auto_submit", "Add automatically"),
        toggle("tidy_chat", "Remove old cards"),
    ]
    return rich, buttons


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
                        "You see the right answer straight away, and the next question follows. "
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
                "Add a finished run in one tap under your Telegram first name, or pick another name of up to "
                "20 characters. Each run can go on once, within an hour of starting it. There are two boards: "
                "best score, each name's single best run, and total points, every run under a name added up. "
                "Names are not accounts: anyone who picks the same name shares its entry."
            ),
            r.heading("Settings", 2),
            r.text(
                "/settings holds your leaderboard name, automatic adding of finished runs, and whether old "
                "cards are removed so a run stays as one card."
            ),
            r.heading("Commands", 2),
            r.table(["Command", "What it does"], [[f"/{name}", description] for name, description in COMMANDS]),
            r.heading("About", 2),
            r.text(
                "There is no account. Your runs are kept against your Telegram user id so the game can find "
                "them again, and runs that never reach the leaderboard are deleted after two days. Your "
                "settings, including your leaderboard name, are kept by the bot against the same id. Only a "
                "name you choose to submit is ever shown. Works in private chats only."
            ),
            r.text(
                "The same game runs in the browser, with a line guide that works offline, and can be installed "
                "as an app from there. Both share one leaderboard. Settings and runs do not carry over."
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
