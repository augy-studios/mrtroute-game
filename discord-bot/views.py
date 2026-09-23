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


def question_embed(q: dict, score: int, colour=BRAND) -> discord.Embed:
    embed = discord.Embed(
        title=f"Question {q['index']} of {q['total']}",
        description=f"**{escape(q['prompt'])}**",
        colour=colour,
    )
    embed.set_footer(text=f"{q['difficulty_name']}, {q['points']} points · Score {score}")
    return embed


def question_card(q: dict, button, user_id: int, run_id: str):
    """Four answer buttons, two to a row. A tap is the whole move."""
    buttons = [
        button("answer", option[:80], GREY, run_id=run_id, question_id=q["question_id"], choice=i, user_id=user_id)
        for i, option in enumerate(q["options"])
    ]
    return question_embed(q, q["run_score"]), [buttons[:2], buttons[2:]]


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
    return (
        f"Added as **{escape(result['name'])}**. "
        f"Best score **{result['best_score']}**, ranked **{result['rank']}**."
    )


def submitted_card(result: dict, button, user_id: int):
    embed = discord.Embed(description=submitted_line(result), colour=BRAND)
    return embed, [[button("leaderboard", "Leaderboard", GREY, user_id=user_id), button("play", "Play again", PRIMARY, user_id=user_id)]]


def result_card(state: dict, button, user_id: int, run_id: str, name: str | None):
    """The end of a run: the score, then one tap to add it under the name the
    player used last (or their Discord name), or another name."""
    embed = discord.Embed(
        title="Run complete",
        description=f"**{state['score']}** points · {state['correct']} of {state['question_count']} right",
        colour=BRAND,
    )
    play = button("play", "Play again", PRIMARY, user_id=user_id)
    board = button("leaderboard", "Leaderboard", GREY, user_id=user_id)
    if state.get("submitted") or state.get("expired"):
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


def leaderboard_card(entries: list[dict], button, user_id: int, limit: int = 10):
    if entries:
        table = _table(["#", "Name", "Score"], [[e["rank"], e["name"], e["score"]] for e in entries[:limit]])
        description = f"{table}\nEach name's best run. Anyone who picks the same name shares its entry."
    else:
        description = "No scores yet. Finish a run and add yours."
    embed = discord.Embed(title="Leaderboard", description=description, colour=BRAND)
    return embed, [[button("play", "Play", PRIMARY, user_id=user_id)]]


SCORING = [
    ["1 to 3", "Easy", "100"],
    ["4 to 7", "Medium", "200"],
    ["8 to 10", "Hard", "300"],
]


def help_card(button, user_id: int, site_url: str, donation_url: str | None):
    """Everything a start command would say. There is no start command."""
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
                "3. The card shows the right answer straight away, and the next question follows. "
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
        value="Add a finished run under your Discord display name, or pick another name of up to 20 characters. "
        "Each run can go on once, within an hour of starting it. The board shows each name's best run. Names "
        "are not accounts: anyone who picks the same name shares its entry.",
        inline=False,
    )
    embed.add_field(name="Commands", value="\n".join(f"`/{name}` {description}" for name, description in COMMANDS), inline=False)
    embed.add_field(
        name="About",
        value="There is no account. Your runs are kept against your Discord user id so the game can find them "
        "again, and runs that never reach the leaderboard are deleted after two days. The bot remembers the last "
        "leaderboard name you used. Only a name you choose to submit is ever shown. Each player's run is their "
        "own, in a server channel or a direct message. The same game runs in the browser, with the same "
        "leaderboard.",
        inline=False,
    )

    rows = [
        [button("play", "Play", PRIMARY, user_id=user_id), button("leaderboard", "Leaderboard", GREY, user_id=user_id)],
        [discord.ui.Button(label="Play in the browser", url=site_url)],
    ]
    if donation_url:
        rows[1].append(discord.ui.Button(label="Buy Augy a Coffee", url=donation_url))
    return embed, rows
