"""The slash commands, as `/help` lists them. bot.py registers each one with
this description, and syncs the list with Discord at every startup.

No `start` command: `help` is the start. Descriptions never name the bot, and
Discord caps each at 100 characters.
"""

COMMANDS = [
    ("help", "How to play, scoring, the leaderboard, and every command."),
    ("play", "Start a run of ten questions."),
    ("leaderboard", "Best scores and total points, one row per name."),
    ("settings", "Your leaderboard name, automatic adding, and card tidying."),
]

DESCRIPTIONS = dict(COMMANDS)


if __name__ == "__main__":
    for name, description in COMMANDS:
        print(f"/{name} - {description}")
