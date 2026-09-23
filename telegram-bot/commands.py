"""The command list. `start` prints it, the bot registers it with Telegram at
every startup, and `python commands.py` prints the block for BotFather.

No `help` command: `start` is the help. Descriptions never name the bot.
"""

COMMANDS = [
    ("start", "How to play, scoring, the leaderboard, and every command."),
    ("play", "Start a run of ten questions."),
    ("leaderboard", "The best run under each name."),
]


def botfather_lines() -> list[str]:
    return [f"{name} - {description}" for name, description in COMMANDS]


if __name__ == "__main__":
    print("\n".join(botfather_lines()))
