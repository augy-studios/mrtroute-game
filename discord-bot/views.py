"""Message builders. Each returns (embed, rows): an embed and rows of buttons.
`button(kind, label, style, **payload)` is passed in, so the registry stays in
one place. The wording follows telegram-bot/views.py.
"""

from __future__ import annotations

import unicodedata

import discord

from commands import COMMANDS

# The PWA's default brand mint.
BRAND = discord.Colour(0xCCFFCC)
RIGHT = discord.Colour(0x0F7234)
WRONG = discord.Colour(0xB91C1C)

NAME_LENGTH = 20

GREY = discord.ButtonStyle.secondary
PRIMARY = discord.ButtonStyle.primary
SUCCESS = discord.ButtonStyle.success
DANGER = discord.ButtonStyle.danger

ON_OFF = {True: "On", False: "Off"}


def clean_name(value: str | None) -> str | None:
    """A Discord display name made fit for the leaderboard, following
    main-site/api/_lib/names.js: emoji and other symbols dropped, whitespace
    collapsed, cut to 20 characters. None when nothing usable is left. The
    API still has the last word, profanity included."""
    name = unicodedata.normalize("NFKC", value or "")
    name = "".join(c for c in name if c in " _-" or c.isspace() or unicodedata.category(c)[0] in "LNM")
    name = " ".join(name.split())[:NAME_LENGTH].strip()
    return name if any(unicodedata.category(c)[0] in "LN" for c in name) else None


def escape(text) -> str:
    return discord.utils.escape_markdown(str(text))


def question_embed(q: dict, score: int, colour=BRAND, note: str | None = None) -> discord.Embed:
    description = f"**{escape(q['prompt'])}**"
    if note:
        description = f"{note}\n\n{description}"
    embed = discord.Embed(title=f"Question {q['index']} of {q['total']}", description=description, colour=colour)
    embed.set_footer(text=f"{q['difficulty_name']}, {q['points']} points · Score {score}")
    return embed


def answer_note(q: dict, result: dict, choice: int) -> str:
    """How the last question went, in one line, for the top of the next card
    when old cards are removed rather than kept."""
    right = q["options"][result["answer_index"]]
    if result["correct"]:
        line = f"Question {q['index']}: correct, +{result.get('points', q['points'])} points."
    else:
        line = f"Question {q['index']}: you picked {escape(q['options'][choice])}. It was **{escape(right)}**."
    if result.get("explain"):
        line += f" {escape(result['explain'])}"
    return f"*{line}*"


def question_card(q: dict, button, user_id: int, run_id: str, note: str | None = None):
    """Four answer buttons, two to a row. A tap is the whole move."""
    buttons = [
        button("answer", option[:80], GREY, run_id=run_id, question_id=q["question_id"], choice=i, user_id=user_id)
        for i, option in enumerate(q["options"])
    ]
    return question_embed(q, q["run_score"], note=note), [buttons[:2], buttons[2:]]


def answered_card(q: dict, result: dict, choice: int):
    """The same card once answered. The buttons stay, disabled, coloured to
    show the right answer and the one picked."""
    right = q["options"][result["answer_index"]]
    if result["correct"]:
        verdict = f"Correct. **+{result.get('points', q['points'])}** points."
    else:
        verdict = f"Not quite. It was **{escape(right)}**."
    embed = question_embed(q, result["run_score"], RIGHT if result["correct"] else WRONG)
    embed.description += f"\n\n{verdict}"
    if result.get("explain"):
        embed.description += f"\n*{escape(result['explain'])}*"

    view = discord.ui.View(timeout=None)
    for i, option in enumerate(q["options"]):
        style = SUCCESS if i == result["answer_index"] else DANGER if i == choice else GREY
        view.add_item(discord.ui.Button(label=option[:80], style=style, disabled=True, custom_id=f"x:{i}", row=i // 2))
    return embed, view


def submitted_line(result: dict) -> str:
    """Where the name now stands on both boards."""
    runs = result.get("runs") or 1
    plural = "run" if runs == 1 else "runs"
    out = [
        f"Added as **{escape(result['name'])}**.",
        f"Best score **{result['best_score']}**, ranked **{result['rank']}**.",
    ]
    if result.get("total") is not None:
        out.append(f"Total **{result['total']}** over {runs} {plural}, ranked **{result['total_rank']}**.")
    return " ".join(out)


def submitted_card(result: dict, button, user_id: int):
    embed = discord.Embed(description=submitted_line(result), colour=BRAND)
    return embed, [[button("leaderboard", "Leaderboard", GREY, user_id=user_id), button("play", "Play again", PRIMARY, user_id=user_id)]]


def result_card(state: dict, button, user_id: int, run_id: str, name: str | None,
                submitted: dict | None = None, note: str | None = None, last: str | None = None):
    """The end of a run, with three endings: already added (automatically),
    one tap under the saved name, or asked for a name. `last` is how the final
    question went, when its own card has been replaced by this one."""
    parts = [
        last,
        f"**{state['score']}** points · {state['correct']} of {state['question_count']} right",
        submitted_line(submitted) if submitted else None,
        f"*{escape(note)}*" if note else None,
    ]
    embed = discord.Embed(title="Run complete", description="\n\n".join(p for p in parts if p), colour=BRAND)
    play = button("play", "Play again", PRIMARY, user_id=user_id)
    board = button("leaderboard", "Leaderboard", GREY, user_id=user_id)
    if submitted or state.get("submitted") or state.get("expired"):
        rows = [[play, board]]
    elif name:
        rows = [
            [
                button("submit", f"Add as {name}", SUCCESS, run_id=run_id, user_id=user_id, name=name),
                button("submit", "Another name", GREY, run_id=run_id, user_id=user_id),
            ],
            [play, board],
        ]
    else:
        rows = [[button("submit", "Add to leaderboard", SUCCESS, run_id=run_id, user_id=user_id)], [play, board]]
    return embed, rows


def _table(headers: list[str], rows: list[list]) -> str:
    """A fixed width table in a code block; Discord embeds have no tables."""
    cells = [headers] + [[str(v) for v in row] for row in rows]
    widths = [max(len(r[i]) for r in cells) for i in range(len(headers))]
    lines = ["  ".join(v.ljust(widths[i]) for i, v in enumerate(r)).rstrip() for r in cells]
    body = "\n".join(lines).replace("```", "'''")
    return f"```\n{body}\n```"


def leaderboard_card(board: str, entries: list[dict], button, user_id: int, limit: int = 10):
    """Either board, with a button that swaps to the other in place."""
    if board == "total":
        title = "Leaderboard: total points"
        table = _table(["#", "Name", "Total", "Runs"], [[e["rank"], e["name"], e["total"], e["runs"]] for e in entries[:limit]])
        about = "Every run added to the leaderboard under a name, scores added up."
        switch = button("leaderboard", "Best scores", GREY, board="best", user_id=user_id)
    else:
        title = "Leaderboard: best score"
        table = _table(["#", "Name", "Score"], [[e["rank"], e["name"], e["score"]] for e in entries[:limit]])
        about = "Each name's single best run."
        switch = button("leaderboard", "Total points", GREY, board="total", user_id=user_id)

    if entries:
        description = f"{table}\n{about} Anyone who picks the same name shares its entry."
    else:
        description = "No scores yet. Finish a run and add yours."
    embed = discord.Embed(title=title, description=description, colour=BRAND)
    return embed, [[switch, button("play", "Play", PRIMARY, user_id=user_id)]]


def settings_card(settings: dict, button, user_id: int, note: str | None = None):
    name = settings["name"]
    default = settings.get("name_is_default", False)
    shown = f"{escape(name)} (your Discord name)" if name and default else escape(name) if name else "Not set"
    embed = discord.Embed(title="Settings", description=f"*{escape(note)}*" if note else None, colour=BRAND)
    embed.add_field(name="Leaderboard name", value=shown, inline=False)
    embed.add_field(name="Add finished runs automatically", value=ON_OFF[settings["auto_submit"]])
    embed.add_field(name="Remove old cards", value=ON_OFF[settings["tidy_chat"]])
    embed.set_footer(
        text="Until you pick a leaderboard name, your Discord display name is used. A name you set here or "
        "type when adding a run is remembered instead; clear it to go back to your Discord name. With "
        "automatic adding on, every finished run goes on the leaderboard under it. With old cards removed, "
        "a run stays as one card that turns into each next question."
    )

    def toggle(key: str, label: str):
        on = settings[key]
        return button("setting", f"{label}: {ON_OFF[on]}", SUCCESS if on else GREY, key=key, user_id=user_id)

    name_row = [button("setname", "Change name" if name else "Set name", PRIMARY, user_id=user_id)]
    if name and not default:
        name_row.append(button("setting", "Use Discord name", GREY, key="name", user_id=user_id))
    rows = [name_row, [toggle("auto_submit", "Add automatically"), toggle("tidy_chat", "Remove old cards")]]
    return embed, rows


SCORING = [
    ["1 to 3", "Easy", "100"],
    ["4 to 7", "Medium", "200"],
    ["8 to 10", "Hard", "300"],
]


def help_card(button, site_url: str, donation_url: str | None):
    """Everything a start command would say. There is no start command.

    The card is public, so its buttons belong to no one: whoever taps Play or
    Leaderboard gets their own run or board."""
    embed = discord.Embed(
        title="How well do you know the MRT lines?",
        description="A quiz on the order of Singapore's MRT and LRT stations, played right here. No sign up.",
        colour=BRAND,
    )
    embed.add_field(
        name="How to play",
        value="\n".join(
            [
                "1. Send /play, or press Play below. A run is ten questions.",
                "2. Each question has four answers. Tap one. That is the whole game.",
                "3. You see the right answer straight away, and the next question follows. "
                "Questions get harder as the run goes on.",
                "4. At the end, add your score to the leaderboard in one tap, or play again.",
            ]
        ),
        inline=False,
    )
    embed.add_field(
        name="The questions",
        value="\n".join(
            [
                "- Which station is between two others",
                "- Which station comes next, heading one way along a line",
                "- Which of four stations is not on a line",
                "- How many stops from one station to another",
                "- Which line a station belongs to",
            ]
        ),
        inline=False,
    )
    embed.add_field(
        name="Scoring",
        value=_table(["Questions", "Level", "Points each"], SCORING)
        + "A wrong answer scores nothing and costs nothing. The best possible run is 2000.",
        inline=False,
    )
    embed.add_field(
        name="Leaderboard",
        value="Add a finished run in one tap under your Discord display name, or pick another name of up to 20 "
        "characters. Each run can go on once, within an hour of starting it. There are two boards: best score, "
        "each name's single best run, and total points, every run under a name added up. Names are not "
        "accounts: anyone who picks the same name shares its entry.",
        inline=False,
    )
    embed.add_field(
        name="Settings",
        value="/settings holds your leaderboard name, automatic adding of finished runs, and whether old cards "
        "are removed so a run stays as one card.",
        inline=False,
    )
    embed.add_field(name="Commands", value="\n".join(f"`/{name}` {description}" for name, description in COMMANDS), inline=False)
    embed.add_field(
        name="About",
        value="There is no account. Your runs are kept against your Discord user id so the game can find them "
        "again, and runs that never reach the leaderboard are deleted after two days. Your settings, including "
        "your leaderboard name, are kept by the bot against the same id. Only a name you choose to submit is "
        "ever shown. Each player's run is their own, in a server channel or a direct message. The same game "
        "runs in the browser, with the same leaderboard.",
        inline=False,
    )

    rows = [
        [button("play", "Play", PRIMARY), button("leaderboard", "Leaderboard", GREY)],
        [discord.ui.Button(label="Play in the browser", url=site_url)],
    ]
    if donation_url:
        rows[1].append(discord.ui.Button(label="Buy Augy a Coffee", url=donation_url))
    return embed, rows
